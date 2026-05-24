"""
Safely patch ~/.claude/settings.json with AnoSys-managed values.

Handles idempotent install/uninstall of the AnoSys Stop hook using
the {"owner": "anosys"} marker for safe roundtrip updates.
"""

import json
import os
import shutil
import sys
import tempfile
from typing import Optional

ANOSYS_ENV_KEYS = {
    "ANOSYS_HOOK_ENDPOINT_URL",
    "ANOSYS_HOOK_API_KEY",
    "ANOSYS_HOOK_APIKEY",
    "ANOSYS_CLAUDE_PIXEL",
    "ANOSYS_HOOK_DRY_RUN",
    "CLAUDE_CODE_ENABLE_TELEMETRY",
    "OTEL_SERVICE_NAME",
    "OTEL_TRACES_EXPORTER",
    "OTEL_METRICS_EXPORTER",
    "OTEL_LOGS_EXPORTER",
    "OTEL_EXPORTER_OTLP_PROTOCOL",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_HEADERS",
    "OTEL_EXPORTER_OTLP_ANOSYS_APIKEY",  # legacy — kept for clean uninstall
}

SETTINGS_PATH = os.path.expanduser("~/.claude/settings.json")
BACKUP_PATH = SETTINGS_PATH + ".bak"


def load_settings(path: str = SETTINGS_PATH) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read().strip()
        return json.loads(content) if content else {}
    except json.JSONDecodeError as exc:
        sys.exit(
            f"ERROR: {path} contains invalid JSON and cannot be parsed safely.\n"
            f"  {exc}\n"
            f"Please fix the file manually and re-run the installer."
        )


def backup(path: str = SETTINGS_PATH) -> Optional[str]:
    if os.path.exists(path):
        import time
        timestamp = time.strftime('%Y%m%d%H%M%S', time.gmtime())
        backup_path = f"{path}.{timestamp}.bak"
        shutil.copy2(path, backup_path)
        return backup_path
    return None


def write_atomic(path: str, data: dict) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def update_env(settings: dict, new_env: dict) -> dict:
    env = dict(settings.get("env") or {})
    for key in ANOSYS_ENV_KEYS:
        env.pop(key, None)
    env.update(new_env)
    settings["env"] = env
    return settings


def _is_anosys_hook_entry(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    return str(entry.get("owner", "")).lower() == "anosys"


def _strip_anosys_from_group(group: dict) -> Optional[dict]:
    inner = group.get("hooks")
    if not isinstance(inner, list):
        return group
    cleaned = [h for h in inner if not _is_anosys_hook_entry(h)]
    if not cleaned:
        return None
    result = dict(group)
    result["hooks"] = cleaned
    return result


def update_stop_hooks(settings: dict, hook_command: str) -> dict:
    hooks_section = settings.setdefault("hooks", {})
    stop_groups = hooks_section.get("Stop", [])
    if not isinstance(stop_groups, list):
        stop_groups = []
    cleaned_groups = []
    for group in stop_groups:
        stripped = _strip_anosys_from_group(group)
        if stripped is not None:
            cleaned_groups.append(stripped)
    anosys_group = {
        "hooks": [
            {
                "owner": "anosys",
                "type": "command",
                "command": hook_command,
            }
        ]
    }
    cleaned_groups.append(anosys_group)
    hooks_section["Stop"] = cleaned_groups
    settings["hooks"] = hooks_section
    return settings


def remove_stop_hooks(settings: dict) -> dict:
    hooks_section = settings.get("hooks", {})
    stop_groups = hooks_section.get("Stop", [])
    if not isinstance(stop_groups, list):
        return settings
    cleaned_groups = []
    for group in stop_groups:
        stripped = _strip_anosys_from_group(group)
        if stripped is not None:
            cleaned_groups.append(stripped)
    hooks_section["Stop"] = cleaned_groups
    settings["hooks"] = hooks_section
    return settings


def remove_env(settings: dict) -> dict:
    env = dict(settings.get("env") or {})
    for key in ANOSYS_ENV_KEYS:
        env.pop(key, None)
    settings["env"] = env
    return settings


def has_anosys_hook(settings: dict) -> bool:
    for group in settings.get("hooks", {}).get("Stop", []):
        if not isinstance(group, dict):
            continue
        for h in group.get("hooks", []):
            if _is_anosys_hook_entry(h):
                return True
    return False


def get_anosys_hook_command(settings: dict) -> Optional[str]:
    for group in settings.get("hooks", {}).get("Stop", []):
        if not isinstance(group, dict):
            continue
        for h in group.get("hooks", []):
            if _is_anosys_hook_entry(h):
                return h.get("command")
    return None
