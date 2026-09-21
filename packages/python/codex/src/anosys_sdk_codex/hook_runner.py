"""
anosys_sdk_codex.hook_runner — OpenAI Codex notify hook runner.

Executed automatically by Codex CLI notify hook on lifecycle events.
Finds and parses the local session rollout JSONL, maps the turn into the
AnoSys schema, and POSTs batches to the AnoSys ingestion endpoint.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from anosys_sdk_codex.installer import get_codex_home, get_env_path
from anosys_sdk_codex.mapper import transform_codex_turn

CODEX_HOME = get_codex_home()
STATE_DIR = CODEX_HOME / "state"
STATE_FILE = STATE_DIR / "anosys_state.json"
PENDING_FILE = STATE_DIR / "pending_records.jsonl"
LOG_FILE = STATE_DIR / "anosys_hook.log"

STATE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("anosys_codex_hook")

_stderr = logging.StreamHandler(sys.stderr)
_stderr.setLevel(logging.INFO)
_stderr.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
log.addHandler(_stderr)


def load_env_file(path: Path | None = None) -> None:
    if path is None:
        path = get_env_path()
    if not path.is_file():
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :]
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            key = k.strip()
            val = v.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception as e:
        log.warning("Failed to load env file %s: %s", path, e)


load_env_file()

INGESTION_URL = os.environ.get("ANOSYS_HOOK_ENDPOINT_URL", "https://api.anosys.ai/ingestion")
API_KEY = os.environ.get("ANOSYS_HOOK_APIKEY", "")
DRY_RUN = os.environ.get("ANOSYS_HOOK_DRY_RUN", "false").lower() == "true"


def load_state() -> Dict[str, Any]:
    if not STATE_FILE.is_file():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: Dict[str, Any]) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        log.error("Failed to save state: %s", e)


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


def post_records_batch(payloads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not payloads:
        return []

    import requests

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "anosys-codex-hook/0.1.0",
    }
    if API_KEY:
        headers["anosys-apikey"] = API_KEY
        headers["x-api-key"] = API_KEY

    failed_records = []
    batch_size = 100

    for i in range(0, len(payloads), batch_size):
        chunk = payloads[i : i + batch_size]
        if DRY_RUN:
            log.info("[DRY RUN] Would POST chunk of %d records", len(chunk))
            continue
        try:
            resp = requests.post(INGESTION_URL, json=chunk, headers=headers, timeout=15)
            resp.raise_for_status()
            log.info("Batch POST success — sent %d records", len(chunk))
        except Exception as e:
            log.error("Batch POST failed for %d records: %s", len(chunk), e)
            failed_records.extend(chunk)

    return failed_records


def find_rollout_file(session_id: str) -> Optional[Path]:
    root = CODEX_HOME / "sessions"
    if not root.is_dir() or not session_id:
        return None
    try:
        for p in root.rglob(f"rollout-*-{session_id}.jsonl"):
            return p
    except OSError:
        return None
    return None


def _iso_to_ms(ts: str) -> int:
    if not ts:
        return 0
    try:
        normalized = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return int(dt.timestamp() * 1000)
    except Exception:
        return 0


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        res = []
        for c in content:
            if isinstance(c, str):
                res.append(c)
            elif isinstance(c, dict):
                res.append(c.get("text") or c.get("content") or "")
        return "".join(res)
    if isinstance(content, dict):
        return content.get("text") or content.get("content") or ""
    return ""


def extract_turn_from_rollout(rollout_path: Path, turn_id: str, fallback_event: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    if not turn_id or not rollout_path.is_file():
        return None

    token_fields = (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "reasoning_output_tokens",
    )
    token_sums = {k: 0 for k in token_fields}
    observed_tokens = False
    prev_total_token_usage: Optional[Dict[str, Any]] = None

    in_turn = False
    turn_start_ms = 0
    turn_end_ms = 0
    duration_ms: Optional[int] = None
    user_prompt = ""
    assistant_output = ""
    model = ""
    model_provider = "openai"
    cwd = ""
    permission_mode = ""
    sandbox_mode = ""

    tool_calls: List[Dict[str, Any]] = []
    pending_func: Dict[str, Dict[str, Any]] = {}
    pending_custom: Dict[str, Dict[str, Any]] = {}
    pending_search_end: Optional[Dict[str, Any]] = None

    raw_events: List[Dict[str, Any]] = []

    try:
        with rollout_path.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue

                outer = obj.get("type")
                payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
                ptype = payload.get("type")
                ts_ms = _iso_to_ms(obj.get("timestamp") or "")

                if outer == "session_meta":
                    model_provider = payload.get("model_provider") or model_provider
                    continue

                if outer == "turn_context":
                    if payload.get("turn_id") == turn_id:
                        raw_events.append(obj)
                        model = payload.get("model") or model
                        cwd = payload.get("cwd") or cwd
                        permission_mode = payload.get("approval_policy") or permission_mode
                        sb = payload.get("sandbox_policy")
                        if isinstance(sb, dict):
                            sandbox_mode = sb.get("type") or sandbox_mode
                    continue

                if outer == "event_msg" and ptype == "task_started":
                    if in_turn:
                        break
                    if payload.get("turn_id") == turn_id:
                        in_turn = True
                        raw_events.append(obj)
                        started_at = payload.get("started_at")
                        if isinstance(started_at, int):
                            turn_start_ms = started_at * 1000
                        elif ts_ms:
                            turn_start_ms = ts_ms
                    continue

                if not in_turn:
                    continue

                raw_events.append(obj)

                if outer == "event_msg" and ptype == "item_completed" and payload.get("item"):
                    item = payload["item"]
                    if isinstance(item, dict):
                        itype = item.get("type")
                        if itype == "UserMessage":
                            t = _extract_text_from_content(item.get("content"))
                            if t:
                                user_prompt = t
                        elif itype == "AgentMessage":
                            t = _extract_text_from_content(item.get("content"))
                            if t:
                                assistant_output = t
                        elif itype == "CommandExecution":
                            cmd = item.get("command")
                            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd or "")
                            tool_calls.append({
                                "tool": "exec",
                                "args": cmd_str,
                                "output": item.get("stdout") or item.get("aggregated_output") or "",
                                "call_id": item.get("id") or "",
                                "start_ts": payload.get("started_at_ms") or ts_ms,
                                "end_ts": payload.get("completed_at_ms") or ts_ms,
                            })
                    continue

                if outer == "response_item" and ptype == "message":
                    role = payload.get("role")
                    if role == "user":
                        t = _extract_text_from_content(payload.get("content"))
                        if t:
                            user_prompt = t
                    elif role == "assistant":
                        t = _extract_text_from_content(payload.get("content"))
                        if t:
                            assistant_output = t
                    continue

                if outer == "event_msg" and ptype == "user_message":
                    user_prompt = payload.get("message") or user_prompt
                    continue

                if outer == "event_msg" and ptype in ("agent_message", "task_complete"):
                    msg = payload.get("message") or payload.get("last_agent_message")
                    if msg:
                        assistant_output = msg
                    completed_at = payload.get("completed_at")
                    if isinstance(completed_at, int):
                        turn_end_ms = completed_at * 1000
                    d = payload.get("duration_ms")
                    if isinstance(d, int):
                        duration_ms = d
                    continue

                if outer == "token_usage_record":
                    usage = payload.get("turn_token_usage") or payload.get("usage") or {}
                    if isinstance(usage, dict):
                        for k in token_fields:
                            v = usage.get(k)
                            if isinstance(v, int):
                                token_sums[k] = v
                                observed_tokens = True
                    continue

                if outer == "event_msg" and ptype == "token_count":
                    info = payload.get("info") or {}
                    total = info.get("total_token_usage")
                    if isinstance(total, dict) and total == prev_total_token_usage:
                        continue
                    if isinstance(total, dict):
                        prev_total_token_usage = total
                    last = info.get("last_token_usage") or {}
                    for k in token_fields:
                        v = last.get(k)
                        if isinstance(v, int):
                            token_sums[k] += v
                            observed_tokens = True
                    continue

                if outer == "response_item" and ptype == "function_call":
                    call_id = payload.get("call_id") or ""
                    entry = {
                        "tool": payload.get("name") or "function_call",
                        "args": payload.get("arguments") or "",
                        "output": "",
                        "call_id": call_id,
                        "start_ts": ts_ms,
                        "end_ts": ts_ms,
                    }
                    tool_calls.append(entry)
                    if call_id:
                        pending_func[call_id] = entry
                    continue

                if outer == "response_item" and ptype == "function_call_output":
                    call_id = payload.get("call_id") or ""
                    pending = pending_func.get(call_id) if call_id else None
                    if pending is not None:
                        pending["output"] = payload.get("output") or ""
                        pending["end_ts"] = ts_ms or pending["end_ts"]
                    continue

                if outer == "response_item" and ptype == "custom_tool_call":
                    call_id = payload.get("call_id") or ""
                    entry = {
                        "tool": payload.get("name") or "custom_tool_call",
                        "args": payload.get("input") or "",
                        "output": "",
                        "call_id": call_id,
                        "start_ts": ts_ms,
                        "end_ts": ts_ms,
                    }
                    tool_calls.append(entry)
                    if call_id:
                        pending_custom[call_id] = entry
                    continue

                if outer == "response_item" and ptype == "custom_tool_call_output":
                    call_id = payload.get("call_id") or ""
                    pending = pending_custom.get(call_id) if call_id else None
                    if pending is not None:
                        pending["output"] = payload.get("output") or ""
                        pending["end_ts"] = ts_ms or pending["end_ts"]
                    continue

                if outer == "event_msg" and ptype == "web_search_end":
                    pending_search_end = {"call_id": payload.get("call_id") or "", "ts_ms": ts_ms}
                    continue

                if outer == "response_item" and ptype == "web_search_call":
                    action = payload.get("action") or {}
                    action_type = action.get("type") or "search"
                    tool_name = "open_page" if action_type == "open_page" else "web_search"
                    args = action.get("url") if action_type == "open_page" else (action.get("query") or "")
                    call_id = ""
                    start_ts = ts_ms
                    if pending_search_end is not None:
                        call_id = pending_search_end["call_id"]
                        start_ts = pending_search_end["ts_ms"] or start_ts
                        pending_search_end = None
                    tool_calls.append({
                        "tool": tool_name,
                        "args": args,
                        "output": payload.get("status") or "",
                        "call_id": call_id,
                        "start_ts": start_ts,
                        "end_ts": ts_ms,
                    })
                    continue

    except OSError as e:
        log.error("Error reading rollout file %s: %s", rollout_path, e)
        return None

    if not in_turn:
        return None

    if not turn_end_ms:
        candidates = [e["end_ts"] for e in tool_calls if e.get("end_ts")]
        turn_end_ms = max(candidates) if candidates else (turn_start_ms or int(time.time() * 1000))

    if duration_ms is None and turn_start_ms and turn_end_ms >= turn_start_ms:
        duration_ms = turn_end_ms - turn_start_ms

    if not user_prompt and fallback_event:
        user_msgs = fallback_event.get("input-messages") or fallback_event.get("input_messages") or ""
        if isinstance(user_msgs, list) and user_msgs:
            last = user_msgs[-1]
            user_prompt = last if isinstance(last, str) else (last.get("content") or "")
        elif isinstance(user_msgs, str):
            user_prompt = user_msgs

    if not assistant_output and fallback_event:
        ast = fallback_event.get("last-assistant-message") or fallback_event.get("last_assistant_message") or ""
        if isinstance(ast, dict):
            assistant_output = ast.get("text") or ast.get("content") or ""
        elif isinstance(ast, str):
            assistant_output = ast

    return {
        "turn_id": turn_id,
        "model": model,
        "model_provider": model_provider,
        "cwd": cwd,
        "permission_mode": permission_mode,
        "sandbox_mode": sandbox_mode,
        "user_prompt": user_prompt,
        "assistant_output": assistant_output,
        "turn_start_ms": turn_start_ms,
        "turn_end_ms": turn_end_ms,
        "duration_ms": duration_ms or 0,
        "tokens": token_sums if observed_tokens else {},
        "tool_calls": tool_calls,
        "raw": {
            "hook_event": fallback_event,
            "events": raw_events,
        },
    }


def _extract_turn_fallback(input_json: Dict[str, Any], thread_id: str, turn_id: str) -> Dict[str, Any]:
    assistant_msg = (
        input_json.get("last-assistant-message")
        or input_json.get("last_assistant_message")
        or input_json.get("lastAssistantMessage")
        or ""
    )
    if isinstance(assistant_msg, dict):
        assistant_msg = assistant_msg.get("text") or assistant_msg.get("content") or ""

    user_msgs = input_json.get("input-messages") or input_json.get("input_messages") or ""
    user_prompt = ""
    if isinstance(user_msgs, list) and user_msgs:
        last = user_msgs[-1]
        user_prompt = last if isinstance(last, str) else (last.get("content") or "")
    elif isinstance(user_msgs, str):
        user_prompt = user_msgs

    now = int(time.time() * 1000)
    return {
        "turn_id": turn_id,
        "model": input_json.get("model", "unknown"),
        "model_provider": "openai",
        "cwd": input_json.get("cwd", ""),
        "user_prompt": str(user_prompt),
        "assistant_output": str(assistant_msg),
        "turn_start_ms": now,
        "turn_end_ms": now,
        "duration_ms": 0,
        "tokens": {},
        "tool_calls": [],
        "raw": {
            "hook_event": input_json,
            "events": [],
        },
    }


def run() -> None:
    log.info("anosys-codex run invoked with argv: %s", sys.argv)

    pending = load_pending_records()
    if pending:
        log.info("Found %d pending records. Retrying delivery...", len(pending))
        still_failed = post_records_batch(pending)
        if not still_failed:
            clear_pending_records()
            log.info("Successfully flushed pending records.")
        else:
            save_pending_records(still_failed, overwrite=True)

    raw_input = "{}"
    for arg in sys.argv[1:]:
        arg_clean = arg.strip()
        if arg_clean == "run":
            continue
        if arg_clean.startswith("{") or arg_clean.startswith("["):
            raw_input = arg_clean
            break
    if raw_input == "{}":
        for arg in sys.argv[1:]:
            arg_clean = arg.strip()
            if arg_clean != "run":
                raw_input = arg_clean
                break
    if raw_input == "{}" and not sys.stdin.isatty():
        try:
            raw_input = sys.stdin.read().strip() or "{}"
        except Exception:
            raw_input = "{}"

    try:
        event = json.loads(raw_input)
    except Exception as e:
        log.error("Failed to parse notify event JSON: %s", e)
        return

    event_type = event.get("type")
    if event_type and event_type not in ("agent-turn-complete", "turn-complete", "test"):
        log.info("Ignoring event type '%s'", event_type)
        return

    thread_id = (
        event.get("thread-id")
        or event.get("thread_id")
        or event.get("threadId")
        or event.get("sessionId")
        or "unknown_session"
    )
    turn_id = (
        event.get("turn-id")
        or event.get("turn_id")
        or event.get("turnId")
        or f"turn_{int(time.time()*1000)}"
    )

    state = load_state()
    session_state = state.setdefault(thread_id, {"processed_turns": []})
    if turn_id in session_state.get("processed_turns", []):
        log.info("Turn %s already processed for session %s. Skipping.", turn_id, thread_id)
        return

    rollout_file = find_rollout_file(thread_id)
    turn_data: Optional[Dict[str, Any]] = None
    if rollout_file:
        log.info("Extracting turn %s from %s", turn_id, rollout_file)
        turn_data = extract_turn_from_rollout(rollout_file, turn_id, fallback_event=event)

    if not turn_data:
        log.warning("Could not extract turn from rollout file. Using fallback.")
        turn_data = _extract_turn_fallback(event, thread_id, turn_id)

    mapped = transform_codex_turn(turn_data, session_id=thread_id, turn_id=turn_id)

    failed = post_records_batch([mapped])
    if failed:
        log.warning("Ingestion failed. Saving record to pending storage.")
        save_pending_records(failed)
    else:
        log.info("Turn %s successfully sent to AnoSys.", turn_id)
        session_state.setdefault("processed_turns", []).append(turn_id)
        session_state["last_seen"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        save_state(state)


if __name__ == "__main__":
    run()
