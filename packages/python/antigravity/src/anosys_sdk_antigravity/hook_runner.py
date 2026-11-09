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

from anosys_sdk_core.encryption import encrypt_payload
from anosys_sdk_core.hook_cli import setup_hook_logging
from anosys_sdk_core.privacy import FULL, OFF, effective_level, filter_fields
from anosys_sdk_core.redaction import scrub_secrets
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

# Content fields scrubbed for secrets before sending at `full`
CONTENT_FIELDS = ("user_prompt", "userPrompt", "assistant_text", "assistantText", "cvs4", "cvs5",
                  "commands", "cvs90", "cvs199", "searched_queries", "cvs77")


def load_env_config(path: Optional[Path] = None) -> None:
    """Load credentials and settings from anosys-env.json if not present in env."""
    p = path or GLOBAL_ENV_FILE
    if not p.is_file():
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for k, v in data.items():
                if k not in os.environ and v is not None:
                    os.environ[k] = str(v)
    except Exception as e:
        log.warning("Failed to load env config from %s: %s", p, type(e).__name__)


def load_runtime_environment() -> None:
    """Prefer the nearest workspace config, then fill gaps from global config."""
    cwd = Path.cwd()
    for directory in (cwd, *cwd.parents):
        workspace_config = directory / ".agents" / "anosys-env.json"
        if workspace_config.is_file():
            load_env_config(workspace_config)
            break
    load_env_config()


load_runtime_environment()


def get_config() -> Dict[str, Any]:
    return {
        "ingestion_url": os.environ.get("ANOSYS_HOOK_ENDPOINT_URL", DEFAULT_INGESTION_URL),
        "api_key": os.environ.get("ANOSYS_HOOK_APIKEY") or os.environ.get("ANOSYS_API_KEY", ""),
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
        sf.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        log.error("Failed to save state for %s: %s", session_id, type(e).__name__)


def prepare_record(mapped: Dict[str, Any], level: str) -> Dict[str, Any]:
    """Apply the collection level, scrub secrets at `full`, then encrypt."""
    record = filter_fields(mapped, level, METADATA_FIELDS)
    if level == FULL:
        for field in CONTENT_FIELDS:
            if record.get(field) is not None:
                record[field] = scrub_secrets(record[field])
    return encrypt_payload(record)


def send(records: List[Dict[str, Any]], config: Dict[str, Any]) -> int:
    """Deliver records (and queued retries) within the size limit. Returns the number accepted."""
    if config.get("dry_run"):
        log.info("[DRY RUN] Would send %d record(s)", len(records))
        return len(records)
    headers = {"Content-Type": "application/json"}
    if config.get("api_key"):
        headers["anosys-apikey"] = config["api_key"]
    return deliver(config["ingestion_url"], records, PendingQueue(PENDING_FILE), PAUSE_FILE, headers=headers)


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
        # Failed records go to the bounded queue; turns are marked processed either way
        sent = send(records_to_send, cfg)
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
        level, source = effective_level()
        if level == OFF:
            log.info("Collection is off (%s); nothing sent", source)
        elif is_paused(PAUSE_FILE):
            log.info("Collection paused after an authorization error; nothing sent")
        else:
            process_turns(event_name, read_stdin(), get_config(), level)
    except Exception as e:
        log.error("Antigravity hook runner error on event %s: %s", event_name, type(e).__name__)
    finally:
        print_response()


if __name__ == "__main__":
    run()
