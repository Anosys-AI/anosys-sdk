"""
anosys_sdk_codex.mapper — Schema mapper for Codex CLI hook turns.
Maps OpenAI Codex rollout session turns and tool calls into the AnoSys ingestion format.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

INTEGRATION_VERSION = "0.1.0"
OS_USER = os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"
REDACTION = os.environ.get("REDACTION", "false").lower() == "true"

OPENAI_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4o": {
        "input": 2.50 / 1e6,
        "output": 10.00 / 1e6,
        "cached": 1.25 / 1e6,
    },
    "gpt-4o-mini": {
        "input": 0.15 / 1e6,
        "output": 0.60 / 1e6,
        "cached": 0.075 / 1e6,
    },
    "o1": {
        "input": 15.00 / 1e6,
        "output": 60.00 / 1e6,
        "cached": 7.50 / 1e6,
    },
    "o1-mini": {
        "input": 1.10 / 1e6,
        "output": 4.40 / 1e6,
        "cached": 0.55 / 1e6,
    },
    "o3": {
        "input": 15.00 / 1e6,
        "output": 60.00 / 1e6,
        "cached": 7.50 / 1e6,
    },
    "o3-mini": {
        "input": 1.10 / 1e6,
        "output": 4.40 / 1e6,
        "cached": 0.55 / 1e6,
    },
    "default": {
        "input": 2.50 / 1e6,
        "output": 10.00 / 1e6,
        "cached": 1.25 / 1e6,
    },
}


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
) -> float:
    rates = OPENAI_PRICING.get("default", {"input": 2.5e-6, "output": 1.0e-5, "cached": 1.25e-6})
    for m_key, r in OPENAI_PRICING.items():
        if m_key in model.lower():
            rates = r
            break

    billable_input = max(0, input_tokens - cached_tokens)
    cost = (billable_input * rates["input"]) + (cached_tokens * rates["cached"]) + (output_tokens * rates["output"])
    return round(cost, 6)


def extract_commands_and_paths(tool_calls: List[Dict[str, Any]]) -> tuple[List[str], List[str]]:
    commands: List[str] = []
    written_paths: List[str] = []

    for call in tool_calls:
        tool = str(call.get("tool", "")).lower()
        args = call.get("args") or ""

        if tool in ("shell", "bash", "exec", "terminal"):
            cmd = ""
            if isinstance(args, dict):
                cmd = args.get("command") or args.get("cmd") or ""
            elif isinstance(args, str):
                try:
                    parsed = json.loads(args)
                    if isinstance(parsed, dict):
                        cmd = parsed.get("command") or parsed.get("cmd") or ""
                except Exception:
                    cmd = args
            if cmd:
                commands.append(cmd.strip())

        if tool in ("apply_patch", "write_to_file", "replace_file_content", "edit", "save"):
            fp = ""
            if isinstance(args, dict):
                fp = args.get("path") or args.get("target_file") or args.get("file") or ""
            elif isinstance(args, str):
                try:
                    parsed = json.loads(args)
                    if isinstance(parsed, dict):
                        fp = parsed.get("path") or parsed.get("target_file") or parsed.get("file") or ""
                except Exception:
                    fp = args
            if fp:
                written_paths.append(fp.strip())

    return commands, written_paths


def transform_codex_turn(
    turn: Dict[str, Any],
    session_id: str,
    turn_id: str,
    incremental_tokens: Optional[Dict[str, float]] = None,
    redact: bool | None = None,
) -> Dict[str, Any]:
    do_redact = REDACTION if redact is None else redact

    model = turn.get("model") or "unknown"
    provider = turn.get("model_provider") or "openai"
    cwd = turn.get("cwd") or ""
    project = Path(cwd).name if cwd else None

    user_prompt = turn.get("user_prompt") or ""
    assistant_text = turn.get("assistant_output") or ""

    if do_redact:
        user_prompt = "[REDACTED]"
        assistant_text = "[REDACTED]"

    tokens = turn.get("tokens") or {}
    input_tokens = int(tokens.get("input_tokens", 0))
    output_tokens = int(tokens.get("output_tokens", 0))
    total_tokens = int(tokens.get("total_tokens", input_tokens + output_tokens))
    cached_tokens = int(tokens.get("cached_input_tokens", 0))
    cache_write_tokens = int(tokens.get("cache_write_input_tokens", 0))
    reasoning_tokens = int(tokens.get("reasoning_output_tokens", 0))

    cost_est = calculate_cost(model, input_tokens, output_tokens, cached_tokens)

    inc = incremental_tokens or {
        "input": float(input_tokens),
        "output": float(output_tokens),
        "total": float(total_tokens),
        "cache_read": float(cached_tokens),
        "cache_creation": float(cache_write_tokens),
        "cost": float(cost_est),
    }

    tool_calls = turn.get("tool_calls") or []
    commands, written_paths = extract_commands_and_paths(tool_calls)

    tool_calls_clean = []
    for tc in tool_calls:
        clean_entry = dict(tc)
        if do_redact:
            clean_entry["args"] = "[REDACTED]"
            clean_entry["output"] = "[REDACTED]"
        tool_calls_clean.append(clean_entry)

    tool_durations = [
        int(tc.get("end_ts", 0)) - int(tc.get("start_ts", 0))
        for tc in tool_calls
        if tc.get("end_ts") and tc.get("start_ts") and tc.get("end_ts") >= tc.get("start_ts")
    ]
    tool_duration_ms = sum(tool_durations) if tool_durations else None

    start_ts = turn.get("turn_start_ms") or int(time.time() * 1000)
    duration_ms = turn.get("duration_ms")

    payload: Dict[str, Any] = {
        "sessionId": session_id,
        "uuid": turn_id,
        "eventId": turn_id,
        "timestamp": start_ts,
        "userPrompt": user_prompt,
        "assistantText": assistant_text,
        "model": model,
        "model_provider": provider,
        "cwd": cwd or None,
        "project": project,
        "permissionMode": turn.get("permission_mode") or None,
        "sandbox_mode": turn.get("sandbox_mode") or None,
        "duration_ms": duration_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cache_read": cached_tokens,
        "cache_creation": cache_write_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cost_estimate": cost_est,
        "incremental_input": inc.get("input", input_tokens),
        "incremental_output": inc.get("output", output_tokens),
        "incremental_total": inc.get("total", total_tokens),
        "incremental_cost": inc.get("cost", cost_est),
        "incremental_cache_read": inc.get("cache_read", cached_tokens),
        "incremental_cache_creation": inc.get("cache_creation", cache_write_tokens),
        "tool_count": len(tool_calls),
        "tool_duration_ms": tool_duration_ms,
        "tools_used": [tc.get("tool") for tc in tool_calls if tc.get("tool")],
        "commands": commands if commands else None,
        "written_paths": written_paths if written_paths else None,
        "has_thinking": reasoning_tokens > 0,
        "integration_version": INTEGRATION_VERSION,
        "os_user": OS_USER,
        "cvs199": json.dumps(tool_calls_clean, separators=(",", ":")),
        "cvs200": "CodexHook",
    }

    return {k: v for k, v in payload.items() if v is not None}
