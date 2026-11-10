"""
Safely manage Antigravity hooks in ~/.gemini/config/hooks.json or .agents/hooks.json.
Handles idempotent install, update, uninstall, and status of the AnoSys Antigravity hook.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

from anosys_sdk_antigravity.constants import (
    DEFAULT_INGESTION_URL,
    EVENTS,
    GLOBAL_ENV_FILE,
    GLOBAL_HOOKS_FILE,
    HOOK_NAME,
    HOOK_TIMEOUT_SECONDS,
)


def get_hooks_path(workspace: bool = False, custom_path: Optional[Path] = None) -> Path:
    """Return hooks.json path (workspace-specific or machine-global)."""
    if custom_path:
        return custom_path
    if workspace:
        return Path.cwd() / ".agents" / "hooks.json"
    return GLOBAL_HOOKS_FILE


def get_env_path(workspace: bool = False, custom_path: Optional[Path] = None) -> Path:
    """Return anosys-env.json path (workspace-specific or machine-global)."""
    if custom_path:
        return custom_path
    if workspace:
        return Path.cwd() / ".agents" / "anosys-env.json"
    return GLOBAL_ENV_FILE


def load_json(path: Path) -> Dict[str, Any]:
    """Read and parse a JSON file safely. Returns {} if file does not exist."""
    if not path.is_file():
        return {}
    try:
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return {}
        data = json.loads(content)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError as exc:
        sys.exit(
            f"ERROR: {path} contains invalid JSON and cannot be parsed safely.\n"
            f"  {exc}\n"
            f"Please fix the file manually and re-run the installer."
        )


def write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    """Write data to path atomically using a temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix="hooks_", suffix=".tmp")
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


def backup(path: Path) -> Optional[Path]:
    """Create a timestamped backup of the file if it exists."""
    if path.is_file():
        timestamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
        backup_path = path.with_name(f"{path.name}.{timestamp}.bak")
        shutil.copy2(path, backup_path)
        os.chmod(backup_path, 0o600)  # backups can hold the API key
        return backup_path
    return None


def has_anosys_hook(data: Dict[str, Any]) -> bool:
    """Check if the AnoSys hook block is configured in hooks.json."""
    if not isinstance(data, dict):
        return False
    block = data.get(HOOK_NAME)
    if not isinstance(block, dict):
        return False
    # Verify events are configured
    return any(ev in block for ev in EVENTS)


def hook_command() -> str:
    """The hook command: this interpreter by absolute path, never a bare PATH lookup."""
    return f'"{sys.executable}" -m anosys_sdk_antigravity.cli run'


def update_hooks_config(hooks_path: Path, command: Optional[str] = None) -> bool:
    """
    Idempotently register or update the anosys-tracing hook block in hooks.json.
    """
    data = load_json(hooks_path)
    command = command or hook_command()

    hook_block: Dict[str, Any] = {}
    for ev in EVENTS:
        subcmd = ev.lower()
        if subcmd == "preinvocation":
            subcmd = "pre_invocation"
        hook_block[ev] = [
            {
                "type": "command",
                "command": f"{command} {subcmd}",
                "timeout": HOOK_TIMEOUT_SECONDS,
            }
        ]

    data[HOOK_NAME] = hook_block
    write_json_atomic(hooks_path, data)
    return True


def remove_hooks_config(hooks_path: Path) -> bool:
    """Remove the anosys-tracing hook block from hooks.json."""
    if not hooks_path.is_file():
        return False
    data = load_json(hooks_path)
    if HOOK_NAME in data:
        data.pop(HOOK_NAME, None)
        if not data:
            try:
                hooks_path.unlink()
            except OSError:
                write_json_atomic(hooks_path, {})
        else:
            write_json_atomic(hooks_path, data)
        return True
    return False


def update_env_config(
    env_path: Path,
    api_key: str = "",
    endpoint_url: str = DEFAULT_INGESTION_URL,
) -> None:
    """Write or update anosys-env.json configuration file."""
    # What is collected is set with `anosys-antigravity privacy`. A custom
    # endpoint is honoured only in the global file (workspace files are limited
    # to the key, see hook_runner.WORKSPACE_ALLOWED_KEYS).
    config: Dict[str, Any] = {"ANOSYS_HOOK_APIKEY": api_key}
    if endpoint_url and endpoint_url != DEFAULT_INGESTION_URL:
        config["ANOSYS_HOOK_ENDPOINT_URL"] = endpoint_url
    write_json_atomic(env_path, config)
    try:
        os.chmod(env_path, 0o600)
    except OSError:
        pass


def remove_env_config(env_path: Path) -> bool:
    """Delete anosys-env.json configuration file."""
    if env_path.is_file():
        try:
            env_path.unlink()
            return True
        except OSError:
            return False
    return False


def validate_api_key(api_key: str, key_type: str = "cc") -> bool:
    """Validate that the API key belongs to a CC pixel."""
    if not api_key:
        return False
    try:
        import urllib.parse
        import urllib.request

        url = f"https://console.anosys.ai/api/resolveapikeys?apikey={urllib.parse.quote(api_key)}"
        req = urllib.request.Request(
            url, headers={"User-Agent": "anosys-antigravity-installer"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status < 200 or response.status >= 300:
                return False
            data = json.loads(response.read().decode("utf-8"))
            api_url = data.get("apiUrl")
            if not api_url:
                return False
            lower = str(key_type).lower()
            if lower in ("cc", "claudecode", "codex", "antigravity"):
                return "/cc/" in api_url
            if lower in ("t", "otel"):
                return "/t/" in api_url
            return False
    except Exception:
        return False
