"""
Schema mapper for Google Antigravity hook turns.
Maps Antigravity turns, planner steps, and tool calls into AnoSys CC schema.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from anosys_sdk_core.privacy import BASE_METADATA_FIELDS

from anosys_sdk_antigravity.constants import INTEGRATION_VERSION

OS_USER = os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"


def is_cc_pixel() -> bool:
    """Return True if targeting a pixel with native CC schema columns (Claude Code / Codex / Antigravity)."""
    pt = os.environ.get("ANOSYS_PIXEL_TYPE", "").strip().lower()
    if pt:
        return pt in ("cc", "claudecode", "codex", "antigravity")
    if os.environ.get("ANOSYS_ANTIGRAVITY_PIXEL", "").strip().lower() == "false":
        return False
    if os.environ.get("ANOSYS_CODEX_PIXEL", "").strip().lower() == "false":
        return False
    if os.environ.get("ANOSYS_CLAUDE_PIXEL", "").strip().lower() == "false":
        return False
    url = os.environ.get("ANOSYS_HOOK_ENDPOINT_URL", "").lower()
    if any(seg in url for seg in ("/g/", "/generic/", "/c/", "/custom/", "/t/", "/otel/")):
        return False
    return True


# Fields sent at the `metadata` level: the shared allowlist plus Antigravity's
# own metadata and the CV columns that hold it. Content (prompts, answers,
# commands, viewed/written paths, queries, subagent tasks, errors, the active
# document and the raw turn in cvs199) is `full`-only.
METADATA_FIELDS = BASE_METADATA_FIELDS | {
    "active_document_language", "cursor_line", "client_timestamp_iso", "termination_reason",
    "llm_step_count", "fully_idle", "execution_num", "workspace_paths",
    "cvs1", "cvs2", "cvs6", "cvs9", "cvs12", "cvs13", "cvs16", "cvs17", "cvs18", "cvs19",
    "cvs32", "cvs33", "cvs71", "cvs72", "cvs93",
    "cvn1", "cvn2", "cvn3", "cvn6", "cvn7", "cvn8", "cvn25", "cvn26", "cvn27", "cvn28", "cvn39", "cvn41",
    "cvb1", "cvb2", "cvb3",
}


def extract_tool_details(tool_steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract structured details from tool invocations in the turn."""
    tools_used: List[str] = []
    commands: List[str] = []
    written_paths: List[str] = []
    viewed_paths: List[str] = []
    searched_queries: List[str] = []
    subagents_spawned: List[str] = []
    tool_errors: List[str] = []
    durations: List[int] = []

    for tool in tool_steps:
        name = str(tool.get("name") or "").strip()
        if name and name not in tools_used:
            tools_used.append(name)

        args = tool.get("args") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {"raw": args}
        if not isinstance(args, dict):
            args = {}

        output = str(tool.get("output") or "")
        status = str(tool.get("status") or "")
        dur = int(tool.get("duration_ms", 0) or 0)
        if dur > 0:
            durations.append(dur)

        output_head = output.lstrip().lower()[:200]
        if status.upper() in ("ERROR", "FAILED") or output_head.startswith(
            ("error:", "exception:", "traceback", "encountered error")
        ):
            tool_errors.append(f"{name}: {output[:300]}")

        # Commands (run_command, terminal, bash)
        if name in ("run_command", "bash", "shell", "exec", "terminal"):
            cmd = args.get("CommandLine") or args.get("command") or args.get("cmd") or ""
            if cmd and isinstance(cmd, str):
                commands.append(cmd.strip())

        # Written/modified files (write_to_file, replace_file_content, multi_replace_file_content)
        if name in ("write_to_file", "replace_file_content", "multi_replace_file_content", "edit", "save"):
            fp = args.get("TargetFile") or args.get("FilePath") or args.get("file_path") or args.get("path") or ""
            if fp and isinstance(fp, str):
                written_paths.append(fp.strip())

        # Viewed files (view_file)
        if name in ("view_file", "read_file"):
            fp = args.get("AbsolutePath") or args.get("FilePath") or args.get("file") or args.get("path") or ""
            if fp and isinstance(fp, str):
                viewed_paths.append(fp.strip())

        # Searches (search_web, grep_search)
        if name in ("search_web", "grep_search"):
            q = args.get("query") or args.get("Query") or ""
            if q and isinstance(q, str):
                searched_queries.append(q.strip())

        # Subagents (browser_subagent, invoke_subagent)
        if "subagent" in name:
            task = args.get("TaskName") or args.get("Task") or args.get("task") or name
            if task and isinstance(task, str):
                subagents_spawned.append(task.strip())

    return {
        "tools_used": tools_used,
        "commands": commands,
        "written_paths": written_paths,
        "viewed_paths": viewed_paths,
        "searched_queries": searched_queries,
        "subagents_spawned": subagents_spawned,
        "tool_errors": tool_errors,
        "tool_duration_ms": sum(durations) if durations else 0,
        "tool_count": len(tool_steps),
    }


def transform_antigravity_turn(
    turn: Dict[str, Any],
    session_id: str,
    turn_id: str,
    hook_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Transform an Antigravity turn into AnoSys ingestion format (dual named & CV schema).
    """
    meta = hook_metadata or {}

    user_prompt = str(turn.get("user_input") or "")
    assistant_text = str(turn.get("final_response") or "")

    # Resolve model
    model = (
        turn.get("model_name")
        or meta.get("modelName")
        or meta.get("model")
        or "gemini-2.5-pro"
    )

    # Workspace & CWD
    workspace_paths = meta.get("workspacePaths") or []
    cwd = ""
    if workspace_paths and isinstance(workspace_paths, list):
        cwd = str(workspace_paths[0])
    elif meta.get("cwd"):
        cwd = str(meta.get("cwd"))
    project = Path(cwd).name if cwd else None

    # Timings
    start_ms = turn.get("start_ms") or int(time.time() * 1000)
    end_ms = turn.get("end_ms") or start_ms
    duration_ms = max(0, end_ms - start_ms)

    # Tool extraction
    tool_steps = turn.get("tool_steps") or []
    tool_details = extract_tool_details(tool_steps)

    # Clean tool steps for raw audit
    tool_steps_clean: List[Dict[str, Any]] = []
    for tc in tool_steps:
        entry = dict(tc)
        tool_steps_clean.append(entry)

    # Raw audit context
    raw_data = {
        "turn": {
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_ms": duration_ms,
            "model_name": model,
            "has_thinking": turn.get("has_thinking", False),
            "step_count": turn.get("step_count", 0),
            "max_step_index": turn.get("max_step_index", 0),
            "llm_steps": turn.get("llm_steps", []),
            "tool_steps": tool_steps_clean,
            "hook_metadata": meta,
        }
    }

    raw_to_serialize = raw_data

    # Hook metadata fields
    termination_reason = meta.get("terminationReason")
    raw_error = meta.get("error")
    if isinstance(raw_error, (dict, list)):
        error_obj = json.dumps(raw_error, separators=(",", ":"))
    elif raw_error is not None:
        error_obj = str(raw_error)
    else:
        error_obj = None
    fully_idle = meta.get("fullyIdle", True)
    execution_num = meta.get("executionNum")
    transcript_path = meta.get("transcriptPath")
    artifact_dir = meta.get("artifactDirectoryPath")

    commands_str = json.dumps(tool_details["commands"]) if tool_details["commands"] else None
    written_paths_str = json.dumps(tool_details["written_paths"]) if tool_details["written_paths"] else None
    viewed_paths_str = json.dumps(tool_details["viewed_paths"]) if tool_details["viewed_paths"] else None
    queries_str = json.dumps(tool_details["searched_queries"]) if tool_details["searched_queries"] else None
    subagents_str = json.dumps(tool_details["subagents_spawned"]) if tool_details["subagents_spawned"] else None
    tool_errors_str = json.dumps(tool_details["tool_errors"]) if tool_details["tool_errors"] else None
    workspace_paths_str = json.dumps(workspace_paths) if workspace_paths else None

    if is_cc_pixel():
        payload: Dict[str, Any] = {
            # Identity
            "session_id": session_id,
            "sessionId": session_id,
            "uuid": turn_id,
            "raw_uuid": turn_id,
            "event_id": turn_id,
            "eventId": turn_id,
            "event_type": "antigravity_turn",
            "event_source_name": "antigravity",
            "timestamp": start_ms,
            "user_timestamp": start_ms,
            "debug": False,
            # Content
            "user_prompt": user_prompt,
            "userPrompt": user_prompt,
            "assistant_text": assistant_text,
            "assistantText": assistant_text,
            # Model
            "model": model,
            "primary_model": model,
            "model_provider": "google",
            # Environment
            "cwd": cwd or None,
            "project": project,
            # Run / user context
            "user_type": str(turn.get("user_source") or "USER_EXPLICIT"),
            "hook_name": meta.get("hook_name") or "Stop",
            "stop_reason": str(termination_reason) if termination_reason else None,
            "termination_reason": termination_reason,
            "error_obj": error_obj,
            # Metrics
            "duration_ms": duration_ms,
            "tool_count": tool_details["tool_count"],
            "tool_duration_ms": tool_details["tool_duration_ms"],
            "tools_used": tool_details["tools_used"],
            "commands": commands_str,
            "written_paths": written_paths_str,
            "viewed_paths": viewed_paths_str,
            "searched_queries": queries_str,
            "subagents_spawned": subagents_str,
            "has_thinking": turn.get("has_thinking", False),
            "integration_version": INTEGRATION_VERSION,
            "os_user": OS_USER,
            # IDE Context (descriptive names)
            "active_document": turn.get("active_document"),
            "active_document_language": turn.get("active_document_language"),
            "cursor_line": turn.get("cursor_line"),
            "client_timestamp_iso": turn.get("client_timestamp_iso"),
            "user_settings_change": turn.get("user_settings_change"),
            "llm_step_count": len(turn.get("llm_steps") or []),
            "fully_idle": fully_idle,
            "execution_num": execution_num,
            "transcript_path": transcript_path,
            "artifact_directory": artifact_dir,
            "workspace_paths": workspace_paths_str,
            # Non-native IDE fields mapped to dedicated CV columns (no native column in CC schema)
            "cvs70": turn.get("active_document"),
            "cvs71": turn.get("active_document_language"),
            "cvs72": turn.get("client_timestamp_iso"),
            "cvs75": turn.get("user_settings_change"),
            "cvs76": viewed_paths_str,
            "cvs77": queries_str,
            "cvs78": subagents_str,
            "cvs79": tool_errors_str,
            "cvs88": transcript_path,
            "cvs89": artifact_dir,
            "cvs93": workspace_paths_str,
            "cvn8": execution_num if isinstance(execution_num, (int, float)) else None,
            "cvn25": turn.get("cursor_line"),
            "cvn26": len(turn.get("llm_steps") or []),
            "cvn27": turn.get("max_step_index"),
            "cvn28": turn.get("step_count"),
            "cvb3": fully_idle if isinstance(fully_idle, bool) else None,
            # Raw backup & hook identifiers
            "cvs199": json.dumps(raw_to_serialize, default=str),
            "cvs200": "AntigravityHook",
        }
    else:
        # Fallback CV mode for generic/custom pixels without native tool/token columns
        payload = {
            "timestamp": start_ms,
            "user_timestamp": start_ms,
            "event_id": turn_id,
            "eventId": turn_id,
            "uuid": turn_id,
            "event_type": "antigravity_turn",
            "event_source_name": "antigravity",
            "debug": False,
            "cvs1": session_id,
            "cvs2": project,
            "cvs4": user_prompt,
            "cvs5": assistant_text,
            "cvs6": str(termination_reason) if termination_reason else None,
            "cvs9": model,
            "cvs12": cwd or None,
            "cvs13": turn_id,
            "cvs16": str(turn.get("user_source") or "USER_EXPLICIT"),
            "cvs17": "google",
            "cvs18": meta.get("hook_name") or "Stop",
            "cvs19": "anosys-antigravity run",
            "cvs25": str(error_obj) if error_obj else None,
            "cvs32": INTEGRATION_VERSION,
            "cvs33": OS_USER,
            "cvs70": turn.get("active_document"),
            "cvs71": turn.get("active_document_language"),
            "cvs72": turn.get("client_timestamp_iso"),
            "cvs75": turn.get("user_settings_change"),
            "cvs76": viewed_paths_str,
            "cvs77": queries_str,
            "cvs78": subagents_str,
            "cvs79": tool_errors_str,
            "cvs88": transcript_path,
            "cvs89": artifact_dir,
            "cvs90": commands_str,
            "cvs91": written_paths_str,
            "cvs93": workspace_paths_str,
            "cvn1": 0,
            "cvn2": 0,
            "cvn3": 0,
            "cvn6": duration_ms,
            "cvn7": 0.0,
            "cvn8": execution_num if isinstance(execution_num, (int, float)) else None,
            "cvn25": turn.get("cursor_line"),
            "cvn26": len(turn.get("llm_steps") or []),
            "cvn27": turn.get("max_step_index"),
            "cvn28": turn.get("step_count"),
            "cvn39": tool_details["tool_duration_ms"],
            "cvn41": tool_details["tool_count"],
            "cvb1": turn.get("has_thinking", False),
            "cvb2": bool(error_obj),
            "cvb3": fully_idle if isinstance(fully_idle, bool) else None,
            # Raw backup & hook identifiers
            "cvs199": json.dumps(raw_to_serialize, default=str),
            "cvs200": "AntigravityHook",
        }

    return {k: v for k, v in payload.items() if v is not None}
