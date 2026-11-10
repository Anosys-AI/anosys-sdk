"""
Hook runner for Google Antigravity PreInvocation and Stop events.
Parses Antigravity transcript, maps turns into AnoSys schema, and POSTs to ingestion endpoint.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from anosys_sdk_core.hook_cli import setup_hook_logging
from anosys_sdk_core.privacy import OFF, _rank_lower, effective_level, prepare_hook_record, write_private_file
from anosys_sdk_core.transport import PendingQueue, deliver, is_paused

from anosys_sdk_antigravity.constants import (
    DEFAULT_INGESTION_URL,
    GLOBAL_CONFIG_DIR,
    GLOBAL_ENV_FILE,
)
from anosys_sdk_antigravity.mapper import METADATA_FIELDS, transform_antigravity_turn
from anosys_sdk_antigravity.transcript import parse_transcript

STATE_DIR = GLOBAL_CONFIG_DIR / "state"
PENDING_FILE = STATE_DIR / "pending_records.jsonl"
PAUSE_FILE = STATE_DIR / "anosys_paused.json"
LOG_FILE = STATE_DIR / "anosys_hook.log"

# The hook log records ids, sizes and status codes only, never prompts or payloads.
log = setup_hook_logging(LOG_FILE, "anosys_antigravity_hook")



# A workspace file is part of the repository, so anyone who can commit to it
# controls it. It may choose which AnoSys key the records are filed under and
# lower collection; it can never raise the level, point at a consent file,
# change the endpoint, encryption, proxies or certificates.
WORKSPACE_ALLOWED_KEYS = frozenset({
    "ANOSYS_HOOK_APIKEY", "ANOSYS_HOOK_API_KEY", "ANOSYS_HOOK_DRY_RUN",
    "REDACTION", "ANOSYS_DISABLE", "ANOSYS_COLLECTION_LEVEL",
})
WORKSPACE_LEVELS = frozenset({"off", "metadata"})  # ANOSYS_COLLECTION_LEVEL may only lower


_workspace_ceiling: Optional[str] = None


def load_env_config(path: Optional[Path] = None, allowed: Optional[frozenset] = None) -> None:
    """Load settings from an anosys-env.json if not present in env (``allowed`` limits the keys)."""
    global _workspace_ceiling
    p = path or GLOBAL_ENV_FILE
    if not p.is_file():
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for k, v in data.items():
                if allowed is not None and (k not in allowed or (
                        k == "ANOSYS_COLLECTION_LEVEL" and str(v).strip().lower() not in WORKSPACE_LEVELS)):
                    log.warning("Ignored %s from the workspace settings file (not allowed there)", k)
                    continue
                if allowed is not None and v is not None:
                    val_lower = str(v).strip().lower()
                    if k == "ANOSYS_DISABLE" and val_lower in ("1", "true", "yes"):
                        _workspace_ceiling = "off"
                    elif k == "ANOSYS_COLLECTION_LEVEL" and val_lower in WORKSPACE_LEVELS:
                        if _workspace_ceiling != "off":
                            _workspace_ceiling = val_lower
                    elif k == "REDACTION" and val_lower in ("1", "true", "yes"):
                        if _workspace_ceiling is None:
                            _workspace_ceiling = "metadata"
                if k not in os.environ and v is not None:
                    os.environ[k] = str(v)
    except Exception as e:
        log.warning("Failed to load env config from %s: %s", p, type(e).__name__)


def load_runtime_environment(cwd: Optional[Path | str] = None) -> None:
    """Load user global config first so repository files cannot override user credentials."""
    load_env_config()
    base = Path(cwd) if cwd else Path.cwd()
    for directory in (base, *base.parents):
        workspace_config = directory / ".agents" / "anosys-env.json"
        if workspace_config.is_file():
            load_env_config(workspace_config, WORKSPACE_ALLOWED_KEYS)
            break


load_runtime_environment()


def get_config() -> Dict[str, Any]:
    return {
        "ingestion_url": os.environ.get("ANOSYS_HOOK_ENDPOINT_URL", DEFAULT_INGESTION_URL),
        "api_key": (
            os.environ.get("ANOSYS_HOOK_APIKEY")
            or os.environ.get("ANOSYS_HOOK_API_KEY")
            or os.environ.get("ANOSYS_API_KEY", "")
        ),
        "dry_run": os.environ.get("ANOSYS_HOOK_DRY_RUN", "false").lower() == "true",
    }


def get_session_state_file(session_id: str) -> Path:
    safe_id = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in session_id)
    return STATE_DIR / f"state_{safe_id}.json"


def load_state(session_id: str) -> Dict[str, Any]:
    sf = get_session_state_file(session_id)
    if not sf.is_file():
        return {"session_id": session_id, "last_emitted_turn": -1, "processed_turns": []}
    try:
        return json.loads(sf.read_text(encoding="utf-8"))
    except Exception:
        return {"session_id": session_id, "last_emitted_turn": -1, "processed_turns": []}


def save_state(session_id: str, state: Dict[str, Any]) -> None:
    try:
        sf = get_session_state_file(session_id)
        write_private_file(sf, json.dumps(state, indent=2))  # 0600
    except Exception as e:
        log.error("Failed to save state for %s: %s", session_id, type(e).__name__)


def prepare_record(mapped: Dict[str, Any], level: str) -> Dict[str, Any]:
    """Level filter, secret scrubbing and encryption: the shared core step."""
    return prepare_hook_record(mapped, level, METADATA_FIELDS)


def send(records: List[Dict[str, Any]], config: Dict[str, Any], cwd: Any = None) -> int:
    """Deliver records (and queued retries) within the size limit. Returns the number accepted."""
    if config.get("dry_run"):
        log.info("[DRY RUN] Would send %d record(s)", len(records))
        return len(records)
    headers = {"Content-Type": "application/json"}
    if config.get("api_key"):
        headers["anosys-apikey"] = config["api_key"]
    return deliver(config["ingestion_url"], records, PendingQueue(PENDING_FILE), PAUSE_FILE, headers=headers,
                   metadata_fields=METADATA_FIELDS, cwd=cwd)


def read_stdin() -> Dict[str, Any]:
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read().strip()
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, OSError):
        return {}


def print_response() -> None:
    """Always output {} to stdout so Antigravity agent loop terminates normally."""
    print(json.dumps({}))


def process_turns(
    event_name: str,
    input_json: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
    level: str = "metadata",
) -> None:
    cfg = config or get_config()
    transcript_path = input_json.get("transcriptPath")
    if not transcript_path:
        log.info("No transcriptPath provided in hook input; skipping.")
        return

    session_id = (
        input_json.get("conversationId")
        or Path(transcript_path).parent.name
        or "unknown_session"
    )

    turns = parse_transcript(transcript_path)
    if not turns:
        log.info("No turns parsed from the transcript of session %s", session_id)
        return

    state = load_state(session_id)
    last_turn = int(state.get("last_emitted_turn", -1))
    processed_turn_ids: List[str] = state.get("processed_turns", [])

    is_stop = event_name.lower() == "stop"
    final_idx = len(turns) - 1

    records_to_send: List[Dict[str, Any]] = []
    turns_emitted_indices: List[int] = []

    for i, turn in enumerate(turns):
        is_final = (i == final_idx)
        # PreInvocation acts as backstop for missed earlier turns; skips the active final turn
        if is_final and not is_stop:
            continue
        if i <= last_turn:
            continue

        turn_id = f"{session_id}_{i}"
        if turn_id in processed_turn_ids:
            continue

        hook_meta = dict(input_json)
        hook_meta["hook_name"] = "Stop" if is_stop else "PreInvocation"

        payload = transform_antigravity_turn(
            turn=turn,
            session_id=session_id,
            turn_id=turn_id,
            hook_metadata=hook_meta,
        )
        records_to_send.append(prepare_record(payload, level))
        turns_emitted_indices.append(i)
        processed_turn_ids.append(turn_id)

    if records_to_send:
        ws_paths = input_json.get("workspacePaths") or []
        ws_cwd = ws_paths[0] if isinstance(ws_paths, list) and ws_paths else input_json.get("cwd")
        # Failed records go to the bounded queue; turns are marked processed either way
        sent = send(records_to_send, cfg, cwd=ws_cwd)
        log.info("Session %s at '%s': %d turn(s), %d accepted", session_id, level, len(records_to_send), sent)
        state["last_emitted_turn"] = max(turns_emitted_indices)
        state["processed_turns"] = processed_turn_ids[-500:]
        state["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        save_state(session_id, state)


def run() -> None:
    """Main execution dispatcher for anosys-antigravity run."""
    event_name = "stop"
    if len(sys.argv) > 1 and sys.argv[1] not in ("run",):
        event_name = sys.argv[1].lower()
    elif len(sys.argv) > 2:
        event_name = sys.argv[2].lower()

    try:
        input_json = read_stdin()
        ws_paths = input_json.get("workspacePaths") or []
        ws_cwd = ws_paths[0] if isinstance(ws_paths, list) and ws_paths else input_json.get("cwd")
        if ws_cwd:
            load_runtime_environment(cwd=ws_cwd)
        level, source = effective_level(cwd=ws_cwd)
        if _workspace_ceiling and _rank_lower(_workspace_ceiling, level):
            level, source = _workspace_ceiling, "workspace ceiling"
        if level == OFF:
            log.info("Collection is off (%s); nothing sent", source)
        elif is_paused(PAUSE_FILE):
            log.info("Collection paused after an authorization error; nothing sent")
        else:
            process_turns(event_name, input_json, get_config(), level)
    except Exception as e:
        log.error("Antigravity hook runner error on event %s: %s", event_name, type(e).__name__)
    finally:
        print_response()


if __name__ == "__main__":
    run()
