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


HOOK_COMMAND = "anosys-codex run"  # legacy form, still recognized on uninstall
INGESTION_URL = "https://api.anosys.ai/ingestion"
HOOK_MODULE = "anosys_sdk_codex.hook_runner"
# Markers of every hook form this package has ever written
HOOK_MARKERS = ("anosys-codex", "anosys_sdk_codex")
# Codex runs a single notify command; another one already configured is kept
# and called after ours with the same notification (the same convention the
# Codex Computer Use wrapper uses).
PREVIOUS_NOTIFY_FLAG = "--previous-notify"


def hook_command() -> List[str]:
    """The notify command: this interpreter by absolute path, never a bare PATH lookup."""
    return [sys.executable, "-m", HOOK_MODULE]


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
        os.chmod(backup_path, 0o600)  # backups can hold the API key
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
    notify_match = re.search(r'^[ \t]*notify[ \t]*=[ \t]*(\[.*\])', content, re.MULTILINE) or re.search(r'^\s*notify\s*=\s*\[(.*?)\]', content, re.MULTILINE | re.DOTALL)
    if notify_match:
        try:
            res["notify"] = json.loads(notify_match.group(1))
        except Exception:
            items = re.findall(r'["\']([^"\']+)["\']', notify_match.group(1))
            res["notify"] = items
    return res


def _is_ours(value: Any) -> bool:
    return any(marker in str(value) for marker in HOOK_MARKERS)


def has_anosys_hook(data: Dict[str, Any]) -> bool:
    """True if the AnoSys hook appears anywhere in notify, including chained inside another wrapper."""
    notify = data.get("notify", [])
    return _is_ours(json.dumps(notify))


def _notify_without_ours(notify: Any) -> Optional[List[str]]:
    """
    The notify command with the AnoSys hook taken out, or None when nothing is left.

    Handles ours as the command (restoring the command we chained to) and ours
    chained inside another wrapper's ``--previous-notify`` argument.
    """
    if isinstance(notify, str):
        notify = [notify]
    if not isinstance(notify, list) or not notify:
        return None
    items = [str(x) for x in notify]
    prev_value = None
    if PREVIOUS_NOTIFY_FLAG in items:
        i = items.index(PREVIOUS_NOTIFY_FLAG)
        prev_value = items[i + 1] if i + 1 < len(items) else None

    head = items[: items.index(PREVIOUS_NOTIFY_FLAG)] if PREVIOUS_NOTIFY_FLAG in items else items
    if any(_is_ours(x) for x in head):
        # Ours is the command: give back what we chained to, if anything
        if prev_value:
            try:
                previous = json.loads(prev_value)
                return _notify_without_ours(previous) if has_anosys_hook({"notify": previous}) else previous
            except json.JSONDecodeError:
                return None
        return None

    if prev_value and _is_ours(prev_value):
        # Ours is chained inside another wrapper
        i = items.index(PREVIOUS_NOTIFY_FLAG)
        try:
            inner = _notify_without_ours(json.loads(prev_value))
        except json.JSONDecodeError:
            inner = None
        rest = items[:i] + items[i + 2 :]
        return rest + [PREVIOUS_NOTIFY_FLAG, json.dumps(inner)] if inner else rest
    return items


def _toml_array(values: List[str]) -> str:
    return "[" + ", ".join(json.dumps(v) for v in values) + "]"


# One top-level `notify = [...]` line (its strings may themselves contain brackets)
_NOTIFY_LINE = re.compile(r'^[ \t]*notify[ \t]*=[^\n]*(?:\n|$)', re.MULTILINE)


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _set_notify(path: Path, notify: Optional[List[str]]) -> None:
    content = path.read_text(encoding="utf-8") if path.is_file() else ""
    line = f"notify = {_toml_array(notify)}\n" if notify else ""
    if _NOTIFY_LINE.search(content):
        new_content = _NOTIFY_LINE.sub(line, content, count=1)
    else:
        new_content = (f"{line}\n{content}" if content else line) if line else content
    _write_atomic(path, new_content)


def update_codex_config(hook_command_args: Optional[List[str]] = None, path: Path | None = None) -> bool:
    """
    Register the hook in notify. A notify command already there is kept and
    chained after ours. Re-running replaces an older AnoSys entry.
    Returns True when the file changed.
    """
    if path is None:
        path = get_config_path()
    data = load_toml(path)
    current = data.get("notify")
    existing = _notify_without_ours(current) if has_anosys_hook(data) else (
        [str(x) for x in current] if isinstance(current, list) and current else
        ([current] if isinstance(current, str) and current else None)
    )
    ours = list(hook_command_args or hook_command())
    notify = ours + [PREVIOUS_NOTIFY_FLAG, json.dumps(existing)] if existing else ours
    if current == notify:
        return False
    _set_notify(path, notify)
    return True


def remove_codex_config(path: Path | None = None) -> bool:
    """Remove only the AnoSys part of notify; other tools' notify commands stay."""
    if path is None:
        path = get_config_path()
    if not path.is_file():
        return False
    data = load_toml(path)
    if not has_anosys_hook(data):
        return False
    _set_notify(path, _notify_without_ours(data.get("notify")))
    return True


def update_codex_env(
    api_key: str = "",
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
    # What is collected is set with `anosys-codex privacy`, not here
    content = "\n".join(lines) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
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
