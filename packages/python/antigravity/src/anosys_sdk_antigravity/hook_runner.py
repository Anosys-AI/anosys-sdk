"""
Hook runner for Google Antigravity PreInvocation and Stop events.
Parses Antigravity transcript, maps turns into AnoSys schema, and POSTs to ingestion endpoint.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from anosys_sdk_antigravity.constants import (
    DEFAULT_INGESTION_URL,
    GLOBAL_CONFIG_DIR,
    GLOBAL_ENV_FILE,
)
from anosys_sdk_antigravity.mapper import transform_antigravity_turn
from anosys_sdk_antigravity.transcript import parse_transcript

STATE_DIR = GLOBAL_CONFIG_DIR / "state"
PENDING_FILE = STATE_DIR / "pending_records.jsonl"
LOG_FILE = STATE_DIR / "anosys_hook.log"

STATE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("anosys_antigravity_hook")

_stderr = logging.StreamHandler(sys.stderr)
_stderr.setLevel(logging.INFO)
_stderr.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
log.addHandler(_stderr)


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
        log.warning("Failed to load env config from %s: %s", p, e)


load_env_config()


def get_config() -> Dict[str, Any]:
    return {
        "ingestion_url": os.environ.get("ANOSYS_HOOK_ENDPOINT_URL", DEFAULT_INGESTION_URL),
        "api_key": os.environ.get("ANOSYS_HOOK_APIKEY") or os.environ.get("ANOSYS_API_KEY", ""),
        "dry_run": os.environ.get("ANOSYS_HOOK_DRY_RUN", "false").lower() == "true",
        "redaction": os.environ.get("REDACTION", "false").lower() == "true",
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
        log.error("Failed to save state for %s: %s", session_id, e)


def load_pending_records() -> List[Dict[str, Any]]:
    if not PENDING_FILE.is_file():
        return []
    records = []
    try:
        with open(PENDING_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except Exception as e:
        log.error("Failed to load pending records: %s", e)
    return records


def save_pending_records(records: List[Dict[str, Any]], overwrite: bool = False) -> None:
    try:
        mode = "w" if overwrite else "a"
        with open(PENDING_FILE, mode, encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    except Exception as e:
        log.error("Failed to save pending records: %s", e)


def clear_pending_records() -> None:
    try:
        if PENDING_FILE.is_file():
            PENDING_FILE.unlink()
    except Exception as e:
        log.error("Failed to clear pending records: %s", e)


def post_records_batch(payloads: List[Dict[str, Any]], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not payloads:
        return []

    import requests

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "anosys-antigravity-hook/0.1.0",
    }
    api_key = config.get("api_key")
    if api_key:
        headers["anosys-apikey"] = api_key
        headers["x-api-key"] = api_key

    failed_records = []
    batch_size = 100
    ingestion_url = config.get("ingestion_url", DEFAULT_INGESTION_URL)
    dry_run = config.get("dry_run", False)

    for i in range(0, len(payloads), batch_size):
        chunk = payloads[i : i + batch_size]
        if dry_run:
            log.info("[DRY RUN] Would POST %d records to %s", len(chunk), ingestion_url)
            continue
        try:
            resp = requests.post(ingestion_url, json=chunk, headers=headers, timeout=10)
            resp.raise_for_status()
            log.info("Batch POST success — sent %d records", len(chunk))
        except Exception as e:
            log.error("Batch POST failed for %d records: %s", len(chunk), e)
            failed_records.extend(chunk)

    return failed_records


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
        log.info("No turns parsed from transcript: %s", transcript_path)
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
            redact=cfg.get("redaction"),
        )
        records_to_send.append(payload)
        turns_emitted_indices.append(i)
        processed_turn_ids.append(turn_id)

    if records_to_send:
        failed = post_records_batch(records_to_send, cfg)
        if failed:
            log.warning("Saving %d failed records to pending queue", len(failed))
            save_pending_records(failed)
        else:
            log.info("Successfully emitted %d turns up to index %d", len(records_to_send), max(turns_emitted_indices))
            state["last_emitted_turn"] = max(turns_emitted_indices)
            state["processed_turns"] = processed_turn_ids
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
        # Flush pending records first if any exist
        pending = load_pending_records()
        cfg = get_config()
        if pending:
            log.info("Found %d pending records. Retrying delivery...", len(pending))
            still_failed = post_records_batch(pending, cfg)
            if not still_failed:
                clear_pending_records()
                log.info("Successfully flushed pending records.")
            else:
                save_pending_records(still_failed, overwrite=True)

        input_json = read_stdin()
        process_turns(event_name, input_json, cfg)
    except Exception as e:
        log.error("Antigravity hook runner error on event %s: %s", event_name, e)
    finally:
        print_response()


if __name__ == "__main__":
    run()
