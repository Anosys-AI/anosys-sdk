"""
Pure parser for Google Antigravity transcript JSONL.

Parses transcript_full.jsonl (or transcript.jsonl) into structured turn dicts.
Extracts user prompts, editor metadata, model selection, reasoning blocks,
and tool invocations with execution timestamps.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_USER_REQUEST_RE = re.compile(r"<USER_REQUEST>(.*?)</USER_REQUEST>", re.DOTALL)
_ADDITIONAL_METADATA_RE = re.compile(r"<ADDITIONAL_METADATA>(.*?)</ADDITIONAL_METADATA>", re.DOTALL)
_USER_SETTINGS_CHANGE_RE = re.compile(r"<USER_SETTINGS_CHANGE>(.*?)</USER_SETTINGS_CHANGE>", re.DOTALL)
_MODEL_SELECTION_RE = re.compile(
    r"changed setting `Model Selection` from .*? to (.+?)\.(?=\s+[A-Z]|\s*$)",
    re.DOTALL,
)
_ACTIVE_DOC_RE = re.compile(r"Active Document:\s*([^\r\n(]+?)(?:\s*\((LANGUAGE_\w+)\))?(?:\r?\n|$)", re.IGNORECASE)
_CURSOR_LINE_RE = re.compile(r"Cursor is on line:\s*(\d+)", re.IGNORECASE)
_CLIENT_TIME_RE = re.compile(r"The current local time is:\s*([^\r\n.]+)", re.IGNORECASE)
_CREATED_AT_RE = re.compile(r"^Created At:\s*(\S+)", re.MULTILINE)
_COMPLETED_AT_RE = re.compile(r"^Completed At:\s*(\S+)", re.MULTILINE)

_NON_TOOL_TYPES = {"USER_INPUT", "PLANNER_RESPONSE", "CONVERSATION_HISTORY"}


def iso_to_ms(value: str) -> int:
    """Parse an ISO-8601 timestamp string to epoch milliseconds. Returns 0 on failure."""
    if not value:
        return 0
    try:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        dt = datetime.datetime.fromisoformat(normalized)
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return 0


def extract_user_request(content: str) -> str:
    """Extract clean user request text, removing metadata tags."""
    if not content:
        return ""
    match = _USER_REQUEST_RE.search(content)
    if match:
        return match.group(1).strip()
    stripped = _ADDITIONAL_METADATA_RE.sub("", content)
    stripped = _USER_SETTINGS_CHANGE_RE.sub("", stripped)
    return stripped.strip()


def extract_metadata_fields(content: str) -> Dict[str, Any]:
    """Extract active document, language, cursor line, and local time from ADDITIONAL_METADATA."""
    res: Dict[str, Any] = {
        "active_document": None,
        "active_document_language": None,
        "cursor_line": None,
        "client_timestamp_iso": None,
    }
    match = _ADDITIONAL_METADATA_RE.search(content)
    if not match:
        return res
    meta_text = match.group(1)

    doc_match = _ACTIVE_DOC_RE.search(meta_text)
    if doc_match:
        res["active_document"] = doc_match.group(1).strip()
        if doc_match.group(2):
            res["active_document_language"] = doc_match.group(2).strip()

    line_match = _CURSOR_LINE_RE.search(meta_text)
    if line_match:
        try:
            res["cursor_line"] = int(line_match.group(1))
        except ValueError:
            pass

    time_match = _CLIENT_TIME_RE.search(meta_text)
    if time_match:
        res["client_timestamp_iso"] = time_match.group(1).strip()

    return res


def extract_settings_change(content: str) -> Dict[str, Any]:
    """Extract model selection and raw settings changes."""
    res: Dict[str, Any] = {
        "model_name": None,
        "user_settings_change": None,
    }
    match = _USER_SETTINGS_CHANGE_RE.search(content)
    if not match:
        return res
    settings_text = match.group(1).strip()
    res["user_settings_change"] = settings_text

    model_match = _MODEL_SELECTION_RE.search(settings_text)
    if model_match:
        res["model_name"] = model_match.group(1).strip()

    return res


def build_turn(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Assemble a single Turn dictionary from an ordered list of records for one user turn."""
    user_record = records[0]
    user_content = str(user_record.get("content", "") or "")

    user_prompt = extract_user_request(user_content)
    meta = extract_metadata_fields(user_content)
    settings = extract_settings_change(user_content)

    step_indices = [int(r.get("step_index", 0)) for r in records if "step_index" in r]
    max_step_index = max(step_indices) if step_indices else 0

    timestamps = [iso_to_ms(r.get("created_at", "") or "") for r in records]
    valid_ts = [t for t in timestamps if t > 0]
    start_ms = valid_ts[0] if valid_ts else (iso_to_ms(meta.get("client_timestamp_iso") or "") or 0)
    end_ms = valid_ts[-1] if valid_ts else start_ms

    turn: Dict[str, Any] = {
        "user_input": user_prompt,
        "user_raw_content": user_content,
        "final_response": "",
        "model_name": settings.get("model_name") or "",
        "user_settings_change": settings.get("user_settings_change"),
        "active_document": meta.get("active_document"),
        "active_document_language": meta.get("active_document_language"),
        "cursor_line": meta.get("cursor_line"),
        "client_timestamp_iso": meta.get("client_timestamp_iso"),
        "user_source": user_record.get("source") or "USER_EXPLICIT",
        "max_step_index": max_step_index,
        "step_count": len(records),
        "start_ms": start_ms,
        "end_ms": end_ms,
        "has_thinking": False,
        "thinking_text": "",
        "llm_steps": [],
        "tool_steps": [],
        "raw_records": records,
    }

    pending_calls: List[Dict[str, Any]] = []
    last_planner_content = ""
    thinking_blocks: List[str] = []

    def _flush_pending_calls() -> None:
        for call in pending_calls:
            turn["tool_steps"].append(
                {
                    "name": call["name"],
                    "args": call["args"],
                    "output": "",
                    "status": "PENDING",
                    "step_index": call["step_index"],
                    "start_ms": call["planner_ms"],
                    "end_ms": call["planner_ms"],
                    "duration_ms": 0,
                }
            )
        pending_calls.clear()

    for idx, rec in enumerate(records):
        rec_type = rec.get("type", "")

        if rec_type == "PLANNER_RESPONSE":
            _flush_pending_calls()
            step_start = iso_to_ms(rec.get("created_at", "") or "")
            if idx + 1 < len(records):
                step_end = iso_to_ms(records[idx + 1].get("created_at", "") or "")
                if step_end == 0:
                    step_end = step_start
            else:
                step_end = step_start

            content = str(rec.get("content", "") or "")
            thinking = str(rec.get("thinking", "") or "")
            if thinking:
                turn["has_thinking"] = True
                thinking_blocks.append(thinking)

            if content:
                last_planner_content = content

            turn["llm_steps"].append(
                {
                    "content": content,
                    "thinking": thinking,
                    "step_index": int(rec.get("step_index", 0)),
                    "start_ms": step_start,
                    "end_ms": step_end,
                }
            )

            for call in rec.get("tool_calls", []) or []:
                if not isinstance(call, dict):
                    continue
                name = str(call.get("name", "") or "")
                args = call.get("args", {}) or {}
                if not isinstance(args, dict):
                    args = {}
                pending_calls.append(
                    {
                        "name": name,
                        "args": args,
                        "step_index": int(rec.get("step_index", 0)),
                        "planner_ms": step_start,
                    }
                )

        elif rec_type == "USER_INPUT":
            continue

        elif rec_type and rec_type not in _NON_TOOL_TYPES:
            if not pending_calls:
                continue
            call = pending_calls.pop(0)
            result_content = str(rec.get("content", "") or "")
            status = str(rec.get("status", "DONE") or "DONE")

            created_match = _CREATED_AT_RE.search(result_content)
            completed_match = _COMPLETED_AT_RE.search(result_content)
            fallback_ms = iso_to_ms(rec.get("created_at", "") or "")

            tool_start = iso_to_ms(created_match.group(1)) if created_match else 0
            tool_end = iso_to_ms(completed_match.group(1)) if completed_match else 0
            if tool_start == 0:
                tool_start = fallback_ms or call["planner_ms"]
            if tool_end == 0:
                tool_end = fallback_ms or tool_start

            tool_duration = max(0, tool_end - tool_start)

            turn["tool_steps"].append(
                {
                    "name": call["name"],
                    "args": call["args"],
                    "output": result_content,
                    "status": status,
                    "step_index": int(rec.get("step_index", 0)),
                    "start_ms": tool_start,
                    "end_ms": tool_end,
                    "duration_ms": tool_duration,
                }
            )

    _flush_pending_calls()
    turn["final_response"] = last_planner_content
    turn["thinking_text"] = "\n\n".join(thinking_blocks)

    return turn


def parse_transcript(path: str | Path) -> List[Dict[str, Any]]:
    """
    Parse an Antigravity transcript JSONL file into a list of Turn dictionaries.
    Automatically resolves transcript_full.jsonl if available.
    """
    if not path:
        return []
    p = Path(path).expanduser()
    full = p.with_name("transcript_full.jsonl")
    if full.is_file():
        target = full
    elif p.is_file():
        target = p
    else:
        return []

    records: List[Dict[str, Any]] = []
    try:
        with target.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                if rec.get("type") == "CONVERSATION_HISTORY":
                    continue
                records.append(rec)
    except OSError:
        return []

    turns: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []
    for rec in records:
        if rec.get("type") == "USER_INPUT":
            if current:
                turns.append(build_turn(current))
            current = [rec]
        else:
            if current:
                current.append(rec)
    if current:
        turns.append(build_turn(current))

    return turns
