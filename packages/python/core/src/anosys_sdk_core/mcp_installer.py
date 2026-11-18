"""Shared MCP client & AI skill installation helpers for AnoSys harnesses."""

from __future__ import annotations

import getpass
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_MCP_URL = "https://console.anosys.ai/mcp"
MCP_SERVER_NAME = "anosys-intelligence"
SKILL_NAME = "anosys-platform-intelligence"
# Project files are often committed, so they reference the key through this variable.
MCP_KEY_ENV = "ANOSYS_MCP_API_KEY"
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

PLATFORM_INTELLIGENCE_SKILL_MD = """---
name: anosys-platform-intelligence
description: Use when analyzing a customer's AnoSys software architecture, linked pipelines/tables/evals, active problems, insights, or trace graphs via the AnoSys Public MCP or REST Intelligence Export API.
---

# AnoSys Platform Intelligence Skill

You are connected to **AnoSys Public MCP** (`anosys_public_mcp`), a read-only customer intelligence gateway exposing structured architecture graphs, linked component topology, active problems, eval summaries, causal trace trees, and guarded SQL analytics.

## Authentication Rules (Read First)

- Valid credentials for AnoSys MCP & REST tools:
  1. **Scoped MCP API Key** (`ak_mcp_...`) passed via HTTP header `Authorization: Bearer ak_mcp_...` or `x-api-key: ak_mcp_...`. Mint and manage personal keys in AnoSys Console (`https://console.anosys.ai`) under **My Profile -> MCP Keys**.
  2. **Customer Auth0 JWT** passed via `Authorization: Bearer <jwt>`.
- **Important:** Do **NOT** pass credentials inside tool `arguments` (`apiKey`) or URL query parameters — credentials are read strictly from HTTP headers. Do **NOT** use an AnoSys telemetry ingestion API key (standard UUID from Integration Options used for `/generateapikey` ingestion); ingestion keys are rejected (`INGESTION_KEY_NOT_SUPPORTED`).
- **Gateway Auth & Diagnostics:** `ak_mcp_...` keys authenticate upstream read-only routes via scoped gateway identity (`companyId`, `keyId`, personal `createdBySub` owner). If a key is paused in Console, tool calls fail with `PAUSED_MCP_KEY` until re-enabled in **My Profile -> MCP Keys**. Call `get_auth_and_health` anytime to inspect `authType`, `companyId`, `scopes`, and upstream BE health.

## Recommended Investigation Workflow

1. **Start Grounded (Low Token Cost):**
   - Call `export_context_pack` first to obtain the customer's architecture summary, Mermaid diagram, active problems, recent eval pass rate, and available telemetry tables in one bounded payload.
   - Call `load_skill` (or read MCP resources `anosys://playbooks/*`) for detailed playbooks on incident triage, eval regressions, cost/cardinalities, or table `tid` schemas.
2. **Trace Architecture & Linked Parts:**
   - Call `get_architecture` for full node/edge topology across ReactFlow pipelines (`nodes`, `edges`), sources, tables, saved queries, evals, and triggers.
   - Call `get_linked_parts({ target })` to inspect upstream inputs and downstream dependents around a failing pipeline, table, query, or eval.
3. **Investigate Problems, Insights & Network Context:**
   - Call `list_problems` (optionally with `severity`, `telemetryTable`, `hours`, `limit`, `cursor`) to combine failed eval executions, degraded pipelines, stale jobs, and optional telemetry anomalies.
   - Call `get_insights` to combine deterministic health findings and eval regression signals.
   - Call `resolve_ip({ ip })` (POC) to validate/classify IPv4/IPv6 addresses (and rate-limited reverse DNS PTR records).
   - Call `get_eval_summary` for configured evals and pass/fail ratios (supports pagination with `cursor`/`offset`).
4. **Deep-Dive Causal Traces, Cardinalities & Ad-Hoc SQL:**
   - Call `list_tables_and_schemas` before writing SQL so column names match the customer's actual table `tid` type:
     - **`t` (OTEL / OtelAI):** `otel_trace_id`, `otel_span_id`, `otel_parent_span_id`, `otel_name`, `otel_status_code`, `otel_exception_message`, `gen_ai_conversation_id`.
     - **`cc` (Claude Code):** `session_id`, `raw_uuid`, `parent_uuid`, `logical_parent_uuid`, `parent_tool_use_id`, `tool_use_id`, `error_obj`, `error_details`.
     - **`n` / `g` / `a` / `i` / `c`:** share the 14 base columns (`timestamp`, `event_id`, `event_type`, `event_source_name`, `risk_score`, `is_anomaly`, `risk_evidence`, etc.) and do NOT carry OTel/CC trace columns.
     - **Custom fields (`cvs*`, `cvn*`, `cvi*`, `cvf*`, `cvb*` / `cv` mapping):** inspect `displayName` in `list_tables_and_schemas` or `aliasName` in `get_cardinalities`.
   - Call `get_cardinalities` before running expensive aggregations to see distinct counts, non-null counts, top values, and human aliases.
   - Call `get_trace_graph({ table, traceId | sessionId, hours })` to reconstruct parent-child execution trees. It automatically detects `t` (`otel_*`) vs `cc` (`session_id`/`parent_uuid`) schemas, applies a 24-hour partition window by default, and enforces dry-run scan budgets.
   - Call `query_readonly({ sql, maxRows, cursor, offset, maxTokens })` only when structured tools cannot answer the question. Queries must be single-statement `SELECT`/`WITH`, reference only authorized workspace tables, include partition filters (`timestamp >= TIMESTAMP_SUB(...)`), and pass BigQuery dry-run byte checks.

## Guardrails & Client-Side Encryption (`enc2`)

- All tools in `anosys_public_mcp` are strictly **read-only**. Do not attempt `INSERT`, `UPDATE`, `DELETE`, `DROP`, `EXTERNAL_QUERY`, or multi-statement SQL.
- If the customer enabled SDK client-side encryption (`ANOSYS_ENCRYPTION_KEY`), prompt/response/command fields stored in BigQuery carry the `enc2:` ciphertext prefix. Operational metadata (counts, timestamps, statuses, model names, token/latency metrics, eval pass rates) remains directly queryable without decrypting raw text.
- Always surface `warnings` returned in tool outputs (for example, if optional monitor upstreams or sections under shared deadline degraded) so the user knows which data sources were live vs partial.
"""


def _codex_home(home_dir: Path, env: dict[str, str]) -> Path:
    custom = (env.get("CODEX_HOME") or "").strip()
    if custom:
        if custom.startswith("~"):
            return (home_dir / custom[2:] if len(custom) > 1 else home_dir).resolve()
        return Path(custom).resolve()
    return home_dir / ".codex"


def supported_mcp_harnesses() -> list[str]:
    return ["claude-code", "codex", "antigravity", "cursor"]


def is_uuid_like_key(key: str) -> bool:
    return bool(_UUID_RE.match((key or "").strip()))


def validate_mcp_key_format(key: str) -> tuple[bool, str | None, str | None]:
    trimmed = (key or "").strip()
    if not trimmed:
        return (
            False,
            "MCP_KEY_REQUIRED",
            "An AnoSys MCP API key (ak_mcp_...) is required for MCP registration.",
        )
    if is_uuid_like_key(trimmed):
        return (
            False,
            "INGESTION_KEY_NOT_SUPPORTED",
            "Standard UUID ingestion keys (ANOSYS_HOOK_APIKEY / ANOSYS_API_KEY) cannot authenticate with Public MCP. Mint a scoped ak_mcp_... key in AnoSys Console.",
        )
    if not trimmed.startswith("ak_mcp_") and not trimmed.startswith("eyJ"):
        return (
            False,
            "INVALID_MCP_KEY_PREFIX",
            'MCP key must start with "ak_mcp_" (scoped MCP API key) or be a customer JWT.',
        )
    return (True, None, trimmed)


def validate_mcp_url(url: str) -> tuple[bool, str]:
    raw = (url or DEFAULT_MCP_URL).strip()
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return (False, f"Invalid MCP URL: {raw}")
    return (True, raw)


def resolve_mcp_targets(
    harness: str,
    *,
    workspace: bool = False,
    cwd: Path | None = None,
    home_dir: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    cwd_p = Path(cwd or Path.cwd())
    home_p = Path(home_dir or Path.home())
    env_d = dict(env if env is not None else os.environ)

    if harness == "claude-code":
        return {
            "harness": "claude-code",
            "label": "Claude Code",
            "format": "json-mcpServers",
            "url_field": "url",
            "include_type_http": True,
            "workspace_key_ref": "${" + MCP_KEY_ENV + "}",
            "mcp_path": cwd_p / ".mcp.json" if workspace else home_p / ".claude.json",
            "skill_path": (
                cwd_p / ".claude" / "skills" / SKILL_NAME / "SKILL.md"
                if workspace
                else home_p / ".claude" / "skills" / SKILL_NAME / "SKILL.md"
            ),
        }
    if harness == "codex":
        codex_home = _codex_home(home_p, env_d)
        return {
            "harness": "codex",
            "label": "OpenAI Codex CLI",
            "format": "codex-toml",
            "url_field": "url",
            "include_type_http": False,
            "mcp_path": cwd_p / ".codex" / "config.toml" if workspace else codex_home / "config.toml",
            "skill_path": (
                cwd_p / ".agents" / "skills" / SKILL_NAME / "SKILL.md"
                if workspace
                else codex_home / "skills" / SKILL_NAME / "SKILL.md"
            ),
        }
    if harness == "antigravity":
        return {
            "harness": "antigravity",
            "label": "Google Antigravity",
            "format": "json-mcpServers",
            # Antigravity only accepts serverUrl for remote servers.
            "url_field": "serverUrl",
            "include_type_http": False,
            # Antigravity does not expand environment variables in mcp_config.json, so the
            # server (and its key) is always registered in the user config, never in the project.
            "mcp_global_only": bool(workspace),
            "mcp_path": home_p / ".gemini" / "config" / "mcp_config.json",
            "skill_path": (
                cwd_p / ".agents" / "skills" / SKILL_NAME / "SKILL.md"
                if workspace
                else home_p / ".gemini" / "config" / "skills" / SKILL_NAME / "SKILL.md"
            ),
        }
    if harness == "cursor":
        return {
            "harness": "cursor",
            "label": "Cursor",
            "format": "json-mcpServers",
            "url_field": "url",
            "include_type_http": False,
            "workspace_key_ref": "${env:" + MCP_KEY_ENV + "}",
            "mcp_path": cwd_p / ".cursor" / "mcp.json" if workspace else home_p / ".cursor" / "mcp.json",
            "skill_path": (
                cwd_p / ".cursor" / "skills" / SKILL_NAME / "SKILL.md"
                if workspace
                else home_p / ".cursor" / "skills" / SKILL_NAME / "SKILL.md"
            ),
        }
    raise ValueError(f'Unsupported MCP harness "{harness}". Supported: {", ".join(supported_mcp_harnesses())}')


def _backup_file(file_path: Path) -> Path | None:
    if not file_path.exists():
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    backup_path = file_path.with_name(f"{file_path.name}.{ts}.bak")
    shutil.copy2(file_path, backup_path)
    try:
        backup_path.chmod(0o600)
    except OSError:
        pass
    return backup_path


def _write_private_atomic(file_path: Path, content: str) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp_", dir=str(file_path.parent))
    try:
        try:
            os.fchmod(fd, 0o600)
        except OSError:
            pass
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        Path(tmp_name).replace(file_path)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _read_json_strict(file_path: Path) -> dict[str, Any]:
    if not file_path.exists():
        return {}
    raw = file_path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{file_path} must contain a JSON object")
    return data


def _escape_toml(val: str) -> str:
    return str(val).replace("\\", "\\\\").replace('"', '\\"')


def _strip_codex_mcp_section(content: str, server_name: str = MCP_SERVER_NAME) -> str:
    if not content:
        return ""
    exact = {
        f"[mcp_servers.{server_name}]",
        f'[mcp_servers."{server_name}"]',
        f"[mcp_servers.{server_name}.http_headers]",
        f'[mcp_servers."{server_name}".http_headers]',
    }
    kept: list[str] = []
    skipping = False
    for line in content.splitlines():
        trimmed = line.strip()
        if re.match(r"^\[[^\]]+\]$", trimmed):
            skipping = trimmed in exact
            if skipping:
                continue
        if not skipping:
            kept.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).rstrip()


def _has_codex_mcp_section(content: str, server_name: str = MCP_SERVER_NAME) -> bool:
    if not content:
        return False
    esc = re.escape(server_name)
    return bool(re.search(rf'^\[mcp_servers\."?{esc}"?\]\s*$', content, re.M))


def install_mcp_client(
    harness: str,
    *,
    mcp_key: str = "",
    mcp_url: str = DEFAULT_MCP_URL,
    workspace: bool = False,
    cwd: Path | None = None,
    home_dir: Path | None = None,
    env: dict[str, str] | None = None,
    install_mcp: bool = True,
    install_skill: bool = True,
    server_name: str = MCP_SERVER_NAME,
) -> dict[str, Any]:
    target = resolve_mcp_targets(harness, workspace=workspace, cwd=cwd, home_dir=home_dir, env=env)
    mcp_path: Path = target["mcp_path"]
    skill_path: Path = target["skill_path"]
    mcp_global_only = bool(target.get("mcp_global_only"))
    # In project files the key is referenced through ANOSYS_MCP_API_KEY, never written.
    key_from_env = bool(workspace and not mcp_global_only)
    result: dict[str, Any] = {
        "harness": target["harness"],
        "label": target["label"],
        "mcp_path": mcp_path,
        "skill_path": skill_path,
        "mcp_updated": False,
        "skill_updated": False,
        "mcp_backup_path": None,
        "mcp_url": None,
        "key_from_env": key_from_env,
        "mcp_global_only": mcp_global_only,
    }

    if install_mcp:
        ok, code, msg_or_key = validate_mcp_key_format(mcp_key)
        if not ok or msg_or_key is None:
            raise ValueError(f"{code}: {msg_or_key}")
        url_ok, url_or_err = validate_mcp_url(mcp_url)
        if not url_ok:
            raise ValueError(url_or_err)
        result["mcp_url"] = url_or_err
        result["mcp_backup_path"] = _backup_file(mcp_path)

        if target["format"] == "codex-toml":
            existing = mcp_path.read_text(encoding="utf-8") if mcp_path.exists() else ""
            stripped = _strip_codex_mcp_section(existing, server_name)
            if key_from_env:
                block = "\n".join([
                    f"[mcp_servers.{server_name}]",
                    f'url = "{_escape_toml(url_or_err)}"',
                    f'bearer_token_env_var = "{MCP_KEY_ENV}"',
                ])
            else:
                block = "\n".join([
                    f"[mcp_servers.{server_name}]",
                    f'url = "{_escape_toml(url_or_err)}"',
                    "",
                    f"[mcp_servers.{server_name}.http_headers]",
                    f'"Authorization" = "Bearer {_escape_toml(msg_or_key)}"',
                ])
            next_text = (f"{stripped}\n\n{block}" if stripped else block) + "\n"
            _write_private_atomic(mcp_path, next_text)
            result["mcp_updated"] = True
        else:
            data = _read_json_strict(mcp_path)
            servers = data.get("mcpServers")
            if not isinstance(servers, dict):
                servers = {}
                data["mcpServers"] = servers
            entry: dict[str, Any] = {}
            if target["include_type_http"]:
                entry["type"] = "http"
            entry[target["url_field"]] = url_or_err
            key_value = target["workspace_key_ref"] if key_from_env else msg_or_key
            entry["headers"] = {"Authorization": f"Bearer {key_value}"}
            servers[server_name] = entry
            _write_private_atomic(mcp_path, json.dumps(data, indent=2) + "\n")
            result["mcp_updated"] = True

    if install_skill:
        _write_private_atomic(skill_path, PLATFORM_INTELLIGENCE_SKILL_MD)
        result["skill_updated"] = True

    return result


def uninstall_mcp_client(
    harness: str,
    *,
    workspace: bool = False,
    cwd: Path | None = None,
    home_dir: Path | None = None,
    env: dict[str, str] | None = None,
    remove_mcp: bool = True,
    remove_skill: bool = True,
    server_name: str = MCP_SERVER_NAME,
) -> dict[str, Any]:
    target = resolve_mcp_targets(harness, workspace=workspace, cwd=cwd, home_dir=home_dir, env=env)
    mcp_path: Path = target["mcp_path"]
    skill_path: Path = target["skill_path"]

    result: dict[str, Any] = {
        "harness": target["harness"],
        "mcp_path": mcp_path,
        "skill_path": skill_path,
        "mcp_removed": False,
        "skill_removed": False,
        "mcp_backup_path": None,
    }

    if remove_mcp and mcp_path.exists():
        if target["format"] == "codex-toml":
            existing = mcp_path.read_text(encoding="utf-8")
            if _has_codex_mcp_section(existing, server_name):
                result["mcp_backup_path"] = _backup_file(mcp_path)
                stripped = _strip_codex_mcp_section(existing, server_name)
                _write_private_atomic(mcp_path, f"{stripped}\n" if stripped else "")
                result["mcp_removed"] = True
        else:
            data = _read_json_strict(mcp_path)
            servers = data.get("mcpServers")
            if isinstance(servers, dict) and server_name in servers:
                result["mcp_backup_path"] = _backup_file(mcp_path)
                del servers[server_name]
                if not servers:
                    del data["mcpServers"]
                _write_private_atomic(mcp_path, json.dumps(data, indent=2) + "\n")
                result["mcp_removed"] = True

    if remove_skill and skill_path.exists():
        skill_path.unlink(missing_ok=True)
        try:
            if not any(skill_path.parent.iterdir()):
                skill_path.parent.rmdir()
        except OSError:
            pass
        result["skill_removed"] = True

    return result


def get_mcp_client_status(
    harness: str,
    *,
    workspace: bool = False,
    cwd: Path | None = None,
    home_dir: Path | None = None,
    env: dict[str, str] | None = None,
    server_name: str = MCP_SERVER_NAME,
) -> dict[str, Any]:
    target = resolve_mcp_targets(harness, workspace=workspace, cwd=cwd, home_dir=home_dir, env=env)
    mcp_path: Path = target["mcp_path"]
    skill_path: Path = target["skill_path"]
    mcp_installed = False
    mcp_url: str | None = None

    if mcp_path.exists():
        if target["format"] == "codex-toml":
            raw = mcp_path.read_text(encoding="utf-8")
            mcp_installed = _has_codex_mcp_section(raw, server_name)
            if mcp_installed:
                esc = re.escape(server_name)
                sec = re.search(rf'^\[mcp_servers\."?{esc}"?\]\s*$([\s\S]*?)(?:^\[|\Z)', raw, re.M)
                if sec:
                    m = re.search(r'^\s*url\s*=\s*"([^"]+)"', sec.group(1), re.M)
                    mcp_url = m.group(1) if m else None
        else:
            try:
                data = _read_json_strict(mcp_path)
                entry = (data.get("mcpServers") or {}).get(server_name)
                if isinstance(entry, dict):
                    mcp_installed = True
                    mcp_url = entry.get(target["url_field"]) or entry.get("url") or entry.get("serverUrl")
            except Exception:
                mcp_installed = False

    return {
        "harness": target["harness"],
        "label": target["label"],
        "mcp_path": mcp_path,
        "skill_path": skill_path,
        "mcp_installed": mcp_installed,
        "mcp_url": mcp_url,
        "skill_installed": skill_path.exists(),
    }


def add_mcp_install_flags(parser: Any) -> None:
    parser.add_argument("--with-mcp", action="store_true", default=False, help="Register AnoSys Public MCP server & SKILL.md")
    parser.add_argument("--with-skill", action="store_true", default=False, help="Install portable SKILL.md without requiring MCP key")
    parser.add_argument("--skill-only", action="store_true", default=False, help="Install only SKILL.md (no MCP key required)")
    parser.add_argument("--no-skill", action="store_true", default=False, help="Skip writing SKILL.md when registering MCP")
    parser.add_argument("--mcp-key", default="", help="Scoped AnoSys MCP API key (ak_mcp_..., NOT ingestion UUID)")
    parser.add_argument("--mcp-url", default=DEFAULT_MCP_URL, help=f"MCP endpoint URL (default: {DEFAULT_MCP_URL})")


def resolve_mcp_key_from_env(env: dict[str, str] | None = None) -> str:
    """Resolve scoped AnoSys MCP API key from ANOSYS_MCP_API_KEY or ANOSYS_MCP_KEY."""
    source = os.environ if env is None else env
    return (source.get("ANOSYS_MCP_API_KEY", "") or source.get("ANOSYS_MCP_KEY", "")).strip()


def prompt_hidden_mcp_key(prompt_text: str) -> str:
    """Prompt for an MCP key without echoing on interactive TTYs."""
    try:
        if sys.stdin.isatty():
            return getpass.getpass(prompt_text).strip()
    except Exception:
        pass
    try:
        return input(prompt_text).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def mcp_install_notes(res: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    if res.get("key_from_env"):
        notes.append(f"  The project config reads the key from ${MCP_KEY_ENV}; the key itself is not written to the project.")
        notes.append(f"  Export {MCP_KEY_ENV} in the shell that starts {res.get('label')}.")
    if res.get("mcp_global_only"):
        notes.append(
            f"  {res.get('label')} cannot read the key from the environment, so the MCP server was "
            f"registered in your user config ({res.get('mcp_path')}), not in the project."
        )
    return notes


def apply_install_mcp_flags(harness: str, args: Any, prompt_fn: Any = None, *, workspace: bool = False) -> dict[str, Any] | None:
    resolved_key = (getattr(args, "mcp_key", "") or resolve_mcp_key_from_env()).strip()
    skill_only = bool(getattr(args, "skill_only", False))
    no_skill = bool(getattr(args, "no_skill", False))
    want_mcp = bool(not skill_only and (getattr(args, "with_mcp", False) or resolved_key))
    explicit_skill = bool(getattr(args, "with_skill", False) or skill_only)
    want_skill = bool(explicit_skill or (want_mcp and not no_skill))
    if not want_mcp and not explicit_skill:
        return None

    non_interactive = bool(getattr(args, "yes", False))
    effective_prompt = prompt_fn if callable(prompt_fn) else prompt_hidden_mcp_key
    prompted_blank_for_skill_only = False
    if want_mcp and not resolved_key and not non_interactive:
        resolved_key = effective_prompt("AnoSys MCP API key (ak_mcp_..., leave blank for skill only): ").strip()
        if not resolved_key and not no_skill:
            prompted_blank_for_skill_only = True

    do_mcp = bool(want_mcp and resolved_key)
    if want_mcp and not resolved_key and not explicit_skill and not prompted_blank_for_skill_only:
        raise ValueError("Missing --mcp-key (ak_mcp_...). Mint one at https://console.anosys.ai or pass --with-skill.")
    if want_mcp and not resolved_key and (explicit_skill or prompted_blank_for_skill_only):
        print("⚠️  No MCP key provided; installing SKILL.md only. Re-run with --mcp-key ak_mcp_... when ready.")

    effective_workspace = bool(workspace or getattr(args, "workspace", False))
    res = install_mcp_client(
        harness,
        mcp_key=resolved_key,
        mcp_url=getattr(args, "mcp_url", DEFAULT_MCP_URL) or DEFAULT_MCP_URL,
        workspace=effective_workspace,
        install_mcp=do_mcp,
        install_skill=want_skill,
    )
    if res["mcp_updated"]:
        print(f"  MCP server '{MCP_SERVER_NAME}' -> {res['mcp_path']} ({res['mcp_url']})")
        for line in mcp_install_notes(res):
            print(line)
    if res["skill_updated"]:
        print(f"  AI Skill '{SKILL_NAME}' -> {res['skill_path']}")
    return res


def add_mcp_subparser(subparsers: Any, default_harness: str, prompt_fn: Any = None) -> None:
    import argparse

    p_mcp = subparsers.add_parser("mcp", help="Configure AnoSys Public MCP server and SKILL.md")
    mcp_sub = p_mcp.add_subparsers(dest="mcp_command", help="MCP actions")

    p_inst = mcp_sub.add_parser("install", help="Install Public MCP server and SKILL.md")
    p_inst.add_argument("--mcp-key", default="", help="Scoped AnoSys MCP API key (or set ANOSYS_MCP_API_KEY / ANOSYS_MCP_KEY)")
    p_inst.add_argument("--mcp-url", default=DEFAULT_MCP_URL, help="MCP endpoint URL")
    p_inst.add_argument("--target", default=default_harness, help="Harness (claude-code, codex, antigravity, cursor, all)")
    p_inst.add_argument("--workspace", action="store_true", default=False)
    p_inst.add_argument("--skill-only", action="store_true", default=False)
    p_inst.add_argument("--no-skill", action="store_true", default=False)
    p_inst.add_argument("-y", "--yes", action="store_true", default=False)

    p_un = mcp_sub.add_parser("uninstall", help="Remove AnoSys Public MCP server and SKILL.md")
    p_un.add_argument("--target", default=default_harness)
    p_un.add_argument("--workspace", action="store_true", default=False)

    p_st = mcp_sub.add_parser("status", help="Show AnoSys Public MCP & SKILL.md status")
    p_st.add_argument("--target", default=default_harness)
    p_st.add_argument("--workspace", action="store_true", default=False)

    def _run_mcp(ns: argparse.Namespace) -> None:
        raw_targets = [x.strip() for x in (getattr(ns, "target", default_harness) or default_harness).split(",") if x.strip()]
        targets = supported_mcp_harnesses() if "all" in raw_targets else raw_targets
        cmd = ns.mcp_command
        if cmd == "install":
            key = (ns.mcp_key or resolve_mcp_key_from_env()).strip()
            effective_prompt = prompt_fn if callable(prompt_fn) else prompt_hidden_mcp_key
            fallback_skill_only = bool(ns.skill_only)
            if not fallback_skill_only and not key and not ns.yes:
                key = effective_prompt("AnoSys MCP API key (ak_mcp_..., leave blank for --skill-only): ").strip()
                if not key and not ns.no_skill:
                    fallback_skill_only = True
                    print("⚠️  No MCP key provided; installing SKILL.md only. Re-run with --mcp-key ak_mcp_... when ready.")
            do_mcp = not fallback_skill_only and bool(key or ns.mcp_key)
            if not fallback_skill_only and not key:
                raise SystemExit("Error: Missing --mcp-key (ak_mcp_...). Pass --skill-only to install only SKILL.md.")
            for h in targets:
                res = install_mcp_client(
                    h,
                    mcp_key=key,
                    mcp_url=ns.mcp_url,
                    workspace=ns.workspace,
                    install_mcp=do_mcp,
                    install_skill=not ns.no_skill,
                )
                print(f"✅ [{res['label']}]")
                if res["mcp_updated"]:
                    print(f"   MCP config: {res['mcp_path']} -> {res['mcp_url']}")
                    for line in mcp_install_notes(res):
                        print(f" {line}")
                if res["skill_updated"]:
                    print(f"   SKILL.md:   {res['skill_path']}")
        elif cmd == "uninstall":
            for h in targets:
                res = uninstall_mcp_client(h, workspace=ns.workspace)
                print(f"[{h}] mcp_removed={res['mcp_removed']} skill_removed={res['skill_removed']}")
        elif cmd == "status":
            for h in targets:
                st = get_mcp_client_status(h, workspace=ns.workspace)
                print(f"[{st['label']}]")
                mcp_txt = f"✅ {st['mcp_url']}" if st["mcp_installed"] else "❌ not configured"
                sk_txt = "✅ installed" if st["skill_installed"] else "❌ not installed"
                print(f"  MCP server: {mcp_txt} ({st['mcp_path']})")
                print(f"  SKILL.md:   {sk_txt} ({st['skill_path']})")
        else:
            p_mcp.print_help()
            raise SystemExit(1)

    p_mcp.set_defaults(func=_run_mcp)

