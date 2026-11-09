"""
Unified capture control for the application SDKs (OpenAI, OpenAI Agents,
Anthropic, Claude Agent SDK, decorators).

One level, resolved in one place, decides what every application integration
sends; the SDK-specific flags (``capture_content``, ``capture_inputs`` ...)
remain as explicit overrides.

Levels are the same as the hooks' (``off`` / ``metadata`` / ``full``) but the
default and the source of consent differ:

- The coding-agent hooks observe a person's whole machine, so they default to
  ``metadata`` and need the person's acceptance of the policy for ``full``
  (see ``privacy.effective_level``). Their records say ``full;<policy version>``.
- An application SDK is code a developer adds to their own application, so the
  developer chooses. It defaults to ``full`` and does not read the per-user
  consent file (which does not exist in servers and containers). Its records
  say ``<level>;app`` so they never claim a policy acceptance.

Precedence for application SDKs (strongest first):

    1. ANOSYS_DISABLE=1                     -> off
    2. project ``.anosys`` file             -> ceiling: can only lower the result
    3. explicit argument (constructor flag)
    4. ANOSYS_COLLECTION_LEVEL
    5. default                              -> full

At ``metadata`` only numbers, booleans and an allowlist of descriptive string
columns are sent (ids, names, models, status). Every other string, list or
object (prompts, completions, messages, tool arguments and results, raw spans,
attribute blobs, dynamically mapped attributes) is dropped. Allowlist, never
a denylist: a new attribute stays out until it is listed here.
"""

import logging
import os
from typing import Any, Dict, Iterable, Optional, Tuple, Union

from anosys_sdk_core.privacy import (
    CONSENT_COLUMN, FULL, LEVELS, METADATA, OFF, _project_level, _rank_lower,
)

logger = logging.getLogger(__name__)

APP_SOURCE = "app"

# Column names (after key mapping) that may carry a string at ``metadata``.
APP_METADATA_STRING_COLUMNS = frozenset({
    # identity, timing and structure
    "timestamp", "otel_observed_timestamp", "otel_record_type", "otel_schema_url",
    "otel_name", "otel_trace_id", "otel_span_id", "otel_trace_flags",
    "otel_parent_span_id", "otel_start_time", "otel_end_time", "otel_kind",
    "otel_status_code",
    # provider, model and operation
    "gen_ai_system", "gen_ai_provider_name", "gen_ai_operation_name",
    "gen_ai_request_model", "gen_ai_response_model", "gen_ai_response_id",
    "gen_ai_response_finish_reasons", "gen_ai_output_type",
    "gen_ai_agent_id", "gen_ai_agent_name", "gen_ai_conversation_id",
    "gen_ai_data_source_id", "llm_model",
    "cvs10",   # error.type / error_type (a class name, not the message)
    "cvs14",   # server.address
    "cvs16",   # llm_model_name
    "cvs17",   # service.name
    "cvs19",   # gen_ai.span.kind
    "cvs5",    # developer-supplied user context (session id)
    # source and privacy tags
    CONSENT_COLUMN, "cvs200",
})

_EXPLICIT = Union[None, bool, str]


def _normalize(level: _EXPLICIT) -> Optional[str]:
    if level is None:
        return None
    if isinstance(level, bool):
        return FULL if level else METADATA
    value = str(level).strip().lower()
    return value if value in LEVELS else None


def resolve_app_level(explicit: _EXPLICIT = None, cwd: Optional[str] = None) -> Tuple[str, str]:
    """
    The level an application SDK collects at, and where it came from.

    ``explicit`` is a level name, or a boolean content flag (True = full,
    False = metadata), or None to inherit.
    """
    if os.environ.get("ANOSYS_DISABLE", "").strip().lower() in ("1", "true", "yes"):
        return OFF, "ANOSYS_DISABLE"

    level, source = None, None
    for candidate, name in (
        (_normalize(explicit), "argument"),
        (_normalize(os.environ.get("ANOSYS_COLLECTION_LEVEL")), "ANOSYS_COLLECTION_LEVEL"),
    ):
        if candidate:
            level, source = candidate, name
            break
    if level is None:
        level, source = FULL, "default"

    project = _project_level(cwd)
    if project and _rank_lower(project, level):
        level, source = project, ".anosys"
    return level, source


def app_consent_value(level: str) -> str:
    """The value written to cvs198 by application SDKs, e.g. ``metadata;app``."""
    return f"{level};{APP_SOURCE}"


def strip_content(record: Dict[str, Any], allowed: Iterable[str] = APP_METADATA_STRING_COLUMNS) -> Dict[str, Any]:
    """Keep numbers, booleans and allow-listed string columns; drop everything else."""
    allowed = allowed if isinstance(allowed, (set, frozenset)) else set(allowed)
    result: Dict[str, Any] = {}
    for key, value in record.items():
        if value is None:
            continue
        if isinstance(value, bool) or isinstance(value, (int, float)):
            result[key] = value
        elif key in allowed and isinstance(value, (str, list)):
            result[key] = value
    return result


def finalize_app_record(record: Dict[str, Any], level: str, extra_allowed: Iterable[str] = ()) -> Optional[Dict[str, Any]]:
    """
    Apply ``level`` to one outgoing application record (before encryption).

    Returns None at ``off`` (send nothing), a content-free copy at
    ``metadata``, the record itself at ``full``; cvs198 always says which.
    ``extra_allowed`` adds an integration's own descriptive string columns.
    """
    if level == OFF:
        return None
    if level == METADATA:
        allowed = APP_METADATA_STRING_COLUMNS | frozenset(extra_allowed)
        result = strip_content(record, allowed)
    else:
        result = dict(record)
    result.pop("consent", None)
    result[CONSENT_COLUMN] = app_consent_value(level)
    return result


_LEVEL_CACHE: Dict[Tuple[str, str, str], Tuple[str, str]] = {}


def current_app_level() -> Tuple[str, str]:
    """``resolve_app_level()`` for code without an explicit setting, cached per environment and folder."""
    key = (os.environ.get("ANOSYS_DISABLE", ""), os.environ.get("ANOSYS_COLLECTION_LEVEL", ""), os.getcwd())
    if key not in _LEVEL_CACHE:
        _LEVEL_CACHE[key] = resolve_app_level()
    return _LEVEL_CACHE[key]


def prepare_app_record(record: Dict[str, Any], level: str, extra_allowed: Iterable[str] = ()) -> Optional[Dict[str, Any]]:
    """``finalize_app_record`` then encryption: the last step before posting an app record."""
    from anosys_sdk_core.encryption import encrypt_payload

    result = finalize_app_record(record, level, extra_allowed)
    return None if result is None else encrypt_payload(result)
