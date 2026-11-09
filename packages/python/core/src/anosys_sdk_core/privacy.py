"""
Collection levels and consent for AnoSys integrations.

Coding-agent hooks (Claude Code, Codex, Antigravity) observe everything a
person does in those tools, so they collect **metadata only** by default.
Full content (prompts, answers, tool input/output, commands, file contents)
is sent only after the user accepts the current AnoSys data-collection policy.

Levels:
    off       hook installed, nothing is sent
    metadata  ids, timestamps, models, token/cost numbers, durations, tool
              names and counts, status (default)
    full      everything the integration maps, after consent

The effective level is computed in one place, ``effective_level()``, with a
fixed precedence (strongest first):

    1. ANOSYS_DISABLE=1                      -> off
    2. explicit level passed by the caller (CLI flag)
    3. project ``.anosys`` file              (can only lower the level)
    4. consent file ``~/.anosys/consent.json`` (written by ``privacy`` commands)
    5. ANOSYS_COLLECTION_LEVEL (saved env file or process environment)
    6. legacy REDACTION=true                 -> metadata
    7. default                               -> metadata

``full`` always requires a consent record for the current POLICY_VERSION;
without it the level falls back to ``metadata``.
"""

import json
import logging
import os
import stat
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set, Tuple

logger = logging.getLogger(__name__)

OFF = "off"
METADATA = "metadata"
FULL = "full"
LEVELS = (OFF, METADATA, FULL)
_RANK = {OFF: 0, METADATA: 1, FULL: 2}

# Bump when PRIVACY.md changes in a way that needs fresh consent
POLICY_VERSION = "2026-11-09"
POLICY_URL = "https://github.com/anosys-ai/anosys-sdk/blob/main/PRIVACY.md"

# Every record carries its collection level and accepted policy version in
# cvs198, a column present in every AnoSys schema (no migration needed).
CONSENT_COLUMN = "cvs198"
CONSENT_FIELD = CONSENT_COLUMN  # older name, same column
PROJECT_FILE = ".anosys"


def consent_path() -> Path:
    custom = os.environ.get("ANOSYS_CONSENT_FILE", "").strip()
    if custom:
        return Path(os.path.expanduser(custom))
    return Path.home() / ".anosys" / "consent.json"


def _normalize(level: Optional[str]) -> Optional[str]:
    if level is None:
        return None
    level = str(level).strip().lower()
    return level if level in LEVELS else None


# ── consent file ──────────────────────────────────────────────────────────────

def read_consent() -> Dict[str, Any]:
    """The stored privacy settings ({} when none). Never raises."""
    try:
        data = json.loads(consent_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_consent(level: str, method: str, accept_policy: Optional[str] = None) -> Dict[str, Any]:
    """
    Store the chosen level. ``full`` needs ``accept_policy`` equal to
    POLICY_VERSION; otherwise ValueError is raised and nothing is written.
    """
    level = _normalize(level)
    if level is None:
        raise ValueError(f"level must be one of {', '.join(LEVELS)}")
    if level == FULL and accept_policy != POLICY_VERSION:
        raise ValueError(
            f"full collection needs acceptance of policy {POLICY_VERSION} ({POLICY_URL})"
        )
    record = {
        "level": level,
        "policy_version": POLICY_VERSION if level == FULL else None,
        "accepted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) if level == FULL else None,
        "method": method,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_private_file(consent_path(), json.dumps(record, indent=2))
    return record


def write_private_file(path: Path, content: str) -> None:
    """Write a file readable only by the current user (0600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")  # unique per process
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.replace(tmp, path)


# ── effective level ───────────────────────────────────────────────────────────

def _project_level(cwd: Optional[str]) -> Optional[str]:
    """Level from the nearest ``.anosys`` file (``level=off|metadata``)."""
    start = Path(cwd or os.getcwd())
    for directory in (start, *start.parents):
        candidate = directory / PROJECT_FILE
        if candidate.is_file():
            try:
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    key, _, value = line.partition("=")
                    if key.strip() == "level":
                        return _normalize(value)
            except Exception:
                return None
            return None
    return None


def effective_level(explicit: Optional[str] = None, cwd: Optional[str] = None) -> Tuple[str, str]:
    """
    The level to collect at, and where it came from.

    Returns:
        (level, source) — source is one of "ANOSYS_DISABLE", "flag", "consent",
        "ANOSYS_COLLECTION_LEVEL", "REDACTION", "default", with " (no consent)"
        appended when ``full`` was requested without a valid consent record.
    """
    if os.environ.get("ANOSYS_DISABLE", "").strip().lower() in ("1", "true", "yes"):
        return OFF, "ANOSYS_DISABLE"

    consent = read_consent()
    level, source = None, None
    for candidate, name in (
        (_normalize(explicit), "flag"),
        (_normalize(consent.get("level")), "consent"),
        (_normalize(os.environ.get("ANOSYS_COLLECTION_LEVEL")), "ANOSYS_COLLECTION_LEVEL"),
    ):
        if candidate:
            level, source = candidate, name
            break
    if level is None:
        if os.environ.get("REDACTION", "").strip().lower() == "true":
            level, source = METADATA, "REDACTION"
        else:
            level, source = METADATA, "default"

    if level == FULL and consent.get("policy_version") != POLICY_VERSION:
        level, source = METADATA, source + " (no consent)"

    project = _project_level(cwd)
    if project and _rank_lower(project, level):
        level, source = project, PROJECT_FILE

    return level, source


def _rank_lower(a: str, b: str) -> bool:
    return _RANK[a] < _RANK[b]


def consent_value(level: str) -> str:
    """The consent field stored on every hook record, e.g. ``full;2026-11-09``."""
    if level == FULL:
        return f"{FULL};{POLICY_VERSION}"
    return f"{level};none"


# ── field filtering ───────────────────────────────────────────────────────────

# Fields every hook may send at ``metadata``. Anything not listed here (and not
# in the integration's own allowlist) is content and is sent only at ``full``.
# Allowlist, never a denylist: a field added upstream stays out by default.
BASE_METADATA_FIELDS: Set[str] = {
    # identity and timing
    "timestamp", "user_timestamp", "event_id", "eventId", "uuid", "event_type",
    "event_source_name", "debug", "session_id", "sessionId", "log_index",
    "integration_version", "consent", "cvs198",
    # workspace (kept at metadata and disclosed in PRIVACY.md)
    "project", "cwd", "git_branch", "os_user", "slug", "version", "entrypoint",
    "original_branch", "original_head_commit", "worktree_branch", "worktree_name",
    "worktree_path", "worktree_original_cwd", "tmux_session_name",
    "pr_url", "pr_repository", "pr_number",
    # model and run settings
    "model", "primary_model", "model_provider", "advisor_model", "service_tier",
    "usage_speed", "inference_geo", "permission_mode", "permissionMode",
    "sandbox_mode", "session_mode", "user_type", "subtype", "level",
    "stop_reason", "stop_reason_top", "stop_sequence",
    # structure ids
    "raw_uuid", "raw_message_id", "parent_uuid", "logical_parent_uuid",
    "assistant_msg_id", "leaf_uuid", "request_id", "prompt_id", "tool_use_id",
    "parent_tool_use_id", "source_tool_use_id", "source_tool_assistant_uuid",
    "agent_id", "agent_type", "agent_map_name", "agent_map_color", "team_name",
    "collapse_id", "summary_uuid", "first_archived_uuid", "last_archived_uuid",
    "hook_name", "hook_event", "hook_label", "task_status", "task_type",
    "session_tag", "attribution_surface",
    # numbers
    "input_tokens", "output_tokens", "total_tokens", "cache_read",
    "cache_creation", "reasoning_tokens", "cost_estimate", "incremental_input",
    "incremental_output", "incremental_total", "incremental_cost",
    "incremental_cache_read", "incremental_cache_creation", "duration_ms",
    "time_saved_ms", "ttft_ms", "otps", "hook_duration_ms", "turn_duration_ms",
    "tool_duration_ms", "classifier_duration_ms", "hook_count", "max_retries",
    "retry_attempt", "retry_in_ms", "exit_code", "replaced_results_count",
    "last_spawn_tokens", "prompt_count", "prompt_count_at_last_commit",
    "permission_prompt_count", "permission_prompt_count_at_last_commit",
    "escape_count", "escape_count_at_last_commit", "web_search_requests",
    "web_fetch_requests", "budget_tokens", "budget_limit", "budget_nudges",
    "message_count", "tool_count", "classifier_count", "config_write_count",
    "tools_used",
    # flags
    "has_thinking", "is_api_error_message", "is_meta", "is_sidechain",
    "is_snapshot_update", "has_output", "prevented_continuation", "is_agent",
    "hook_based", "armed", "is_synthetic", "is_visible_in_transcript_only",
    "is_virtual", "is_compact_summary", "is_p50",
    # source tag
    "cvs200",
}


def filter_fields(record: Dict[str, Any], level: str, metadata_fields: Iterable[str]) -> Dict[str, Any]:
    """
    Keep the fields allowed at ``level``.

    ``off`` keeps nothing, ``metadata`` keeps only ``metadata_fields`` and
    ``full`` keeps everything. cvs198 is set on every record.
    """
    if level == OFF:
        return {}
    if level == FULL:
        result = dict(record)
    else:
        allowed = set(metadata_fields)
        result = {k: v for k, v in record.items() if k in allowed}
    result.pop("consent", None)
    result[CONSENT_COLUMN] = consent_value(level)
    return result


def attach_consent(record: Dict[str, Any], level: Optional[str] = None) -> Dict[str, Any]:
    """Set cvs198 for a hook record (level from ``effective_level`` when omitted)."""
    if level is None:
        level, _ = effective_level()
    record.pop("consent", None)
    record[CONSENT_COLUMN] = consent_value(level)
    return record

