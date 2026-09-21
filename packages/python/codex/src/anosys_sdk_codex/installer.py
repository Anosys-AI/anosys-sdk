"""
Safely manage ~/.codex/config.toml with AnoSys-managed notify hook.

Handles idempotent install/uninstall of the AnoSys Codex notify hook
and ~/.codex/anosys-env.sh configuration.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


HOOK_COMMAND = "anosys-codex run"
INGESTION_URL = "https://api.anosys.ai/ingestion"


def get_codex_home() -> Path:
    """Return the active Codex home directory, respecting CODEX_HOME."""
    custom = os.environ.get("CODEX_HOME", "").strip()
    if custom:
        return Path(os.path.expandvars(os.path.expanduser(custom))).resolve()
    return Path.home() / ".codex"


def get_config_path() -> Path:
    return get_codex_home() / "config.toml"


def get_env_path() -> Path:
    return get_codex_home() / "anosys-env.sh"


def backup(path: Path | None = None) -> Optional[Path]:
    """Create a timestamped backup of the config file."""
    if path is None:
        path = get_config_path()
    if path.is_file():
        timestamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
        backup_path = path.with_name(f"{path.name}.{timestamp}.bak")
        shutil.copy2(path, backup_path)
        return backup_path
    return None


def load_toml(path: Path) -> Dict[str, Any]:
    """Read and parse TOML file. Returns empty dict if file does not exist."""
    if not path.is_file():
        return {}
    try:
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            return {}
        if tomllib is not None:
            return tomllib.loads(content)
        return _fallback_parse_toml(content)
    except Exception as exc:
        sys.exit(
            f"ERROR: {path} contains invalid TOML and cannot be parsed safely.\n"
            f"  {exc}\n"
            f"Please fix the file manually and re-run the installer."
        )


def _fallback_parse_toml(content: str) -> Dict[str, Any]:
    res: Dict[str, Any] = {}
    notify_match = re.search(r'^\s*notify\s*=\s*\[(.*?)\]', content, re.MULTILINE | re.DOTALL)
    if notify_match:
        items = re.findall(r'["\']([^"\']+)["\']', notify_match.group(1))
        res["notify"] = items
    return res


def _serialize_toml_value(val: Any) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\"')
        return f'"{escaped}"'
    if isinstance(val, list):
        items_str = ", ".join(_serialize_toml_value(x) for x in val)
        return f"[{items_str}]"
    if isinstance(val, dict):
        items_str = ", ".join(f"{k} = {_serialize_toml_value(v)}" for k, v in val.items())
        return f"{{ {items_str} }}"
    return f'"{str(val)}"'


def write_toml_atomic(path: Path, data: Dict[str, Any]) -> None:
    """Safely write TOML data atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []

    for k, v in data.items():
        if not isinstance(v, dict):
            lines.append(f"{k} = {_serialize_toml_value(v)}")

    for k, v in data.items():
        if isinstance(v, dict):
            lines.append("")
            lines.append(f"[{k}]")
            for sub_k, sub_v in v.items():
                lines.append(f"{sub_k} = {_serialize_toml_value(sub_v)}")

    content = "\n".join(lines).strip() + "\n"
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix="config_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        shutil.move(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def has_anosys_hook(data: Dict[str, Any]) -> bool:
    notify_list = data.get("notify", [])
    if isinstance(notify_list, str):
        notify_list = [notify_list]
    if isinstance(notify_list, list):
        return any("anosys-codex" in str(x) for x in notify_list)
    return False


def update_codex_config(hook_command: str = HOOK_COMMAND, path: Path | None = None) -> bool:
    if path is None:
        path = get_config_path()

    data = load_toml(path)
    notify_list = data.get("notify", [])
    if isinstance(notify_list, str):
        notify_list = [notify_list]
    elif not isinstance(notify_list, list):
        notify_list = []

    existing = [x for x in notify_list if "anosys-codex" in str(x)]
    if existing and hook_command in notify_list:
        return False

    new_notify = [x for x in notify_list if "anosys-codex" not in str(x)]
    new_notify.append(hook_command)
    data["notify"] = new_notify

    write_toml_atomic(path, data)
    return True


def remove_codex_config(path: Path | None = None) -> bool:
    if path is None:
        path = get_config_path()
    if not path.is_file():
        return False

    data = load_toml(path)
    notify_list = data.get("notify", [])
    if isinstance(notify_list, str):
        notify_list = [notify_list]
    elif not isinstance(notify_list, list):
        return False

    new_notify = [x for x in notify_list if "anosys-codex" not in str(x)]
    if len(new_notify) == len(notify_list):
        return False

    if new_notify:
        data["notify"] = new_notify
    else:
        data.pop("notify", None)

    write_toml_atomic(path, data)
    return True


def update_codex_env(
    api_key: str = "",
    redaction: bool = False,
    endpoint_url: str = INGESTION_URL,
    path: Path | None = None,
) -> None:
    if path is None:
        path = get_env_path()

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# AnoSys Codex CLI configuration",
        f'export ANOSYS_HOOK_ENDPOINT_URL="{endpoint_url}"',
    ]
    if api_key:
        lines.append(f'export ANOSYS_HOOK_APIKEY="{api_key}"')
    if redaction:
        lines.append('export REDACTION="true"')
    else:
        lines.append('export REDACTION="false"')

    content = "\n".join(lines) + "\n"
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def remove_codex_env(path: Path | None = None) -> bool:
    if path is None:
        path = get_env_path()
    if path.is_file():
        try:
            path.unlink()
            return True
        except OSError:
            return False
    return False


def validate_api_key(api_key: str, key_type: str = "cc") -> bool:
    if not api_key:
        return False
    try:
        import urllib.parse
        import urllib.request

        url = f"https://console.anosys.ai/api/resolveapikeys?apikey={urllib.parse.quote(api_key)}"
        req = urllib.request.Request(
            url, headers={"User-Agent": "anosys-codex-installer"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status < 200 or response.status >= 300:
                return False
            data = json.loads(response.read().decode("utf-8"))
            api_url = data.get("apiUrl")
            if not api_url:
                return False
            lower = str(key_type).lower()
            if lower in ("cc", "claudecode", "codex"):
                return "/cc/" in api_url
            if lower in ("t", "otel"):
                return "/t/" in api_url
            return False
    except Exception:
        return False
