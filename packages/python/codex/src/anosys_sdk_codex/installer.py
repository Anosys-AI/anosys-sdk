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
from typing import Any, Dict, List, Optional, Tuple

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
        if inner and _notify_head(inner) == rest:
            # The wrapper had chained to itself through us (e.g. Codex Computer Use re-wrapping
            # notify): keep one copy instead of calling the same notifier twice.
            return inner
        return rest + [PREVIOUS_NOTIFY_FLAG, json.dumps(inner)] if inner else rest
    return items


def _notify_head(command: List[str]) -> List[str]:
    """The command without its ``--previous-notify`` argument."""
    if PREVIOUS_NOTIFY_FLAG in command:
        i = command.index(PREVIOUS_NOTIFY_FLAG)
        return command[:i] + command[i + 2 :]
    return list(command)


def _toml_array(values: List[str]) -> str:
    return "[" + ", ".join(json.dumps(v) for v in values) + "]"


# One top-level `notify = [...]` line (its strings may themselves contain brackets)
_NOTIFY_START = re.compile(r'^[ \t]*notify[ \t]*=[ \t]*', re.MULTILINE)
_TABLE_HEADER = re.compile(r'^[ \t]*\[', re.MULTILINE)


def _notify_span(content: str) -> Optional[Tuple[int, int]]:
    """
    Start and end of the top-level ``notify = ...`` entry, including a value that
    spans several lines (``notify = [\n  "a",\n  "b",\n]``) and brackets inside
    strings. Entries inside a [table] are not the top-level key and are ignored.
    """
    header = _TABLE_HEADER.search(content)
    limit = header.start() if header else len(content)
    m = _NOTIFY_START.search(content, 0, limit)
    if not m:
        return None
    i = m.end()
    if i < len(content) and content[i] == "[":
        depth, quote = 0, None
        while i < len(content):
            ch = content[i]
            if quote:
                if ch == "\\" and quote == '"':
                    i += 1
                elif ch == quote:
                    quote = None
            elif ch in ('"', "'"):
                quote = ch
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    break
            i += 1
    end = content.find("\n", i)
    return m.start(), (len(content) if end == -1 else end + 1)


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
    span = _notify_span(content)
    if span:
        new_content = content[:span[0]] + line + content[span[1]:]
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



# ── Codex's own OpenTelemetry export (opt-in, --otel-key) ─────────────────────
#
# Codex refuses to start when config.toml is invalid, so this block is only ever
# written after the whole new file has been parsed and checked: the [otel] table
# must come out exactly as intended and every other setting must be unchanged.
# An [otel] table the user wrote themselves is never touched.

OTEL_BEGIN = "# >>> anosys-codex otel (managed by anosys-codex; remove with: anosys-codex uninstall)"
OTEL_END = "# <<< anosys-codex otel"
OTEL_SIGNALS = (("exporter", "logs"), ("trace_exporter", "traces"), ("metrics_exporter", "metrics"))


class OtelConfigError(RuntimeError):
    """config.toml could not be updated safely; nothing was written."""


def _toml_str(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _otel_expected(otel_key: str, base_url: str) -> Dict[str, Any]:
    expected: Dict[str, Any] = {"log_user_prompt": False}
    for field, signal in OTEL_SIGNALS:
        expected[field] = {"otlp-http": {
            "endpoint": f"{base_url.rstrip('/')}/v1/{signal}",
            "protocol": "binary",
            "headers": {"anosys-apikey": otel_key},
        }}
    return expected


def _otel_block(otel_key: str, base_url: str) -> str:
    lines = [OTEL_BEGIN, "[otel]", "log_user_prompt = false"]
    for field, signal in OTEL_SIGNALS:
        endpoint = f"{base_url.rstrip('/')}/v1/{signal}"
        lines.append(
            f"{field} = {{ otlp-http = {{ endpoint = {_toml_str(endpoint)}, protocol = \"binary\", "
            f"headers = {{ \"anosys-apikey\" = {_toml_str(otel_key)} }} }} }}"
        )
    lines.append(OTEL_END)
    return "\n".join(lines) + "\n"


def _strip_otel_block(content: str) -> str:
    out: List[str] = []
    inside = False
    for line in content.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == OTEL_BEGIN:
            inside = True
            continue
        if inside:
            if stripped == OTEL_END:
                inside = False
            continue
        out.append(line)
    if inside:
        raise OtelConfigError("the Anosys [otel] block in config.toml has no end marker; fix it by hand")
    text = "".join(out)
    # Drop only the blank line we added before the block; leave the rest of the file as it was
    return text[:-1] if text.endswith("\n\n") else text


def _parse_strict(content: str) -> Dict[str, Any]:
    if tomllib is None:
        raise OtelConfigError("no TOML parser available (install tomli on Python 3.10)")
    try:
        return tomllib.loads(content)
    except Exception as exc:
        raise OtelConfigError(f"config.toml is not valid TOML ({exc})") from exc


def codex_accepts_config(content: str, timeout: float = 20) -> Optional[bool]:
    """
    Ask the installed Codex to load ``content`` from a private temporary
    CODEX_HOME. True: Codex loaded it. False: Codex rejected the config.
    None: Codex is not installed or could not be checked (nothing is concluded).
    """
    import subprocess
    codex = shutil.which("codex")
    if not codex:
        return None
    with tempfile.TemporaryDirectory(prefix="anosys-codex-check-") as tmp:
        cfg = Path(tmp) / "config.toml"
        cfg.write_text(content, encoding="utf-8")
        cfg.chmod(0o600)
        env = dict(os.environ, CODEX_HOME=tmp)
        try:
            result = subprocess.run([codex, "features", "list"], env=env, capture_output=True,
                                    text=True, timeout=timeout)
        except Exception:
            return None
    if result.returncode == 0:
        return True
    return False if "config" in (result.stderr or "").lower() else None


def has_anosys_otel(path: Path | None = None) -> bool:
    path = path or get_config_path()
    return path.is_file() and OTEL_BEGIN in path.read_text(encoding="utf-8")


def update_codex_otel(otel_key: str, path: Path | None = None, base_url: str = INGESTION_URL) -> bool:
    """
    Enable Codex's own OTel export to Anosys.ai (logs, traces, metrics) with
    prompt logging off. Raises OtelConfigError and writes nothing if the result
    would not be exactly right. Returns True when the file changed.
    """
    path = path or get_config_path()
    original = path.read_text(encoding="utf-8") if path.is_file() else ""
    before = _parse_strict(original)
    base = _strip_otel_block(original)
    base_parsed = _parse_strict(base)
    if "otel" in base_parsed:
        raise OtelConfigError(
            "config.toml already has an [otel] section that Anosys did not write; "
            "it was left unchanged (remove it first, or point its exporters at Anosys.ai yourself)")
    new = (base.rstrip("\n") + "\n\n" if base.strip() else "") + _otel_block(otel_key, base_url)
    after = _parse_strict(new)
    if after.get("otel") != _otel_expected(otel_key, base_url):
        raise OtelConfigError("the generated [otel] section did not parse as expected; nothing was written")
    if {k: v for k, v in after.items() if k != "otel"} != {k: v for k, v in before.items() if k != "otel"}:
        raise OtelConfigError("writing [otel] would have changed other settings; nothing was written")
    if new != original and codex_accepts_config(new) is False:
        raise OtelConfigError("the installed Codex rejected the new config.toml; nothing was written")
    if new == original:
        return False
    _write_atomic(path, new)
    return True


def remove_codex_otel(path: Path | None = None) -> bool:
    """Remove the Anosys [otel] block; any other [otel] settings are left alone."""
    path = path or get_config_path()
    if not has_anosys_otel(path):
        return False
    original = path.read_text(encoding="utf-8")
    before = _parse_strict(original)
    new = _strip_otel_block(original)
    after = _parse_strict(new)
    if after != {k: v for k, v in before.items() if k != "otel"}:
        raise OtelConfigError("removing the Anosys [otel] block would have changed other settings; nothing was written")
    _write_atomic(path, new)
    return True


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
