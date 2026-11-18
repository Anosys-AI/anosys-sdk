from __future__ import annotations

import json
from pathlib import Path

import pytest

from anosys_sdk_core.mcp_installer import (
    DEFAULT_MCP_URL,
    MCP_SERVER_NAME,
    SKILL_NAME,
    apply_install_mcp_flags,
    get_mcp_client_status,
    install_mcp_client,
    resolve_mcp_key_from_env,
    uninstall_mcp_client,
    validate_mcp_key_format,
)


def test_validate_mcp_key_rejects_uuid_ingestion_key():
    ok, code, msg = validate_mcp_key_format("550e8400-e29b-41d4-a716-446655440000")
    assert not ok
    assert code == "INGESTION_KEY_NOT_SUPPORTED"
    assert "ak_mcp_" in (msg or "")

    ok2, code2, key2 = validate_mcp_key_format("ak_mcp_py_123")
    assert ok2
    assert code2 is None
    assert key2 == "ak_mcp_py_123"


def test_python_install_status_uninstall_claude_and_codex(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "repo"
    cwd.mkdir()

    # Claude Code preserves existing keys/servers
    claude_cfg = home / ".claude.json"
    claude_cfg.write_text(json.dumps({"mcpServers": {"other": {"url": "http://x"}}, "keep": True}), encoding="utf-8")

    res = install_mcp_client("claude-code", mcp_key="ak_mcp_py_claude", home_dir=home, cwd=cwd)
    assert res["mcp_updated"] and res["skill_updated"]
    data = json.loads(claude_cfg.read_text(encoding="utf-8"))
    assert data["keep"] is True
    assert "other" in data["mcpServers"]
    assert data["mcpServers"][MCP_SERVER_NAME]["url"] == DEFAULT_MCP_URL
    assert "enc2:" in (home / ".claude" / "skills" / SKILL_NAME / "SKILL.md").read_text(encoding="utf-8")

    st = get_mcp_client_status("claude-code", home_dir=home, cwd=cwd)
    assert st["mcp_installed"] and st["skill_installed"]

    un = uninstall_mcp_client("claude-code", home_dir=home, cwd=cwd)
    assert un["mcp_removed"] and un["skill_removed"]

    # Codex TOML preserves notify hook
    codex_cfg = home / ".codex" / "config.toml"
    codex_cfg.parent.mkdir(parents=True)
    codex_cfg.write_text('notify = ["anosys-codex", "run"]\n', encoding="utf-8")

    install_mcp_client("codex", mcp_key="ak_mcp_py_codex", home_dir=home, env={})
    raw = codex_cfg.read_text(encoding="utf-8")
    assert 'notify = ["anosys-codex", "run"]' in raw
    assert f"[mcp_servers.{MCP_SERVER_NAME}]" in raw

    uninstall_mcp_client("codex", home_dir=home, env={})
    after = codex_cfg.read_text(encoding="utf-8")
    assert 'notify = ["anosys-codex", "run"]' in after
    assert f"[mcp_servers.{MCP_SERVER_NAME}]" not in after

    with pytest.raises(ValueError, match="INGESTION_KEY_NOT_SUPPORTED"):
        install_mcp_client("claude-code", mcp_key="550e8400-e29b-41d4-a716-446655440000", home_dir=home)


def test_python_antigravity_paths_use_gemini_config_and_agents(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "repo"
    cwd.mkdir()

    ag_global = install_mcp_client("antigravity", mcp_key="ak_mcp_py_ag", home_dir=home, cwd=cwd)
    assert Path(ag_global["mcp_path"]) == home / ".gemini" / "config" / "mcp_config.json"
    assert Path(ag_global["skill_path"]) == home / ".gemini" / "config" / "skills" / SKILL_NAME / "SKILL.md"
    ag_cfg = json.loads(Path(ag_global["mcp_path"]).read_text(encoding="utf-8"))
    assert ag_cfg["mcpServers"][MCP_SERVER_NAME]["serverUrl"] == DEFAULT_MCP_URL
    assert "url" not in ag_cfg["mcpServers"][MCP_SERVER_NAME]

    ag_ws = install_mcp_client("antigravity", mcp_key="ak_mcp_py_ag_ws", workspace=True, home_dir=home, cwd=cwd)
    # The MCP server (with its key) stays in the user config; only SKILL.md goes to the project.
    assert Path(ag_ws["mcp_path"]) == home / ".gemini" / "config" / "mcp_config.json"
    assert ag_ws["mcp_global_only"] is True
    assert not (cwd / ".agents" / "mcp_config.json").exists()
    assert Path(ag_ws["skill_path"]) == cwd / ".agents" / "skills" / SKILL_NAME / "SKILL.md"
    skill_md = (cwd / ".agents" / "skills" / SKILL_NAME / "SKILL.md").read_text(encoding="utf-8")
    assert "cvn*" in skill_md
    assert "get_cardinalities" in skill_md
    assert "get_auth_and_health" in skill_md
    assert "My Profile -> MCP Keys" in skill_md
    assert "load_skill" in skill_md
    assert "otel_trace_id" in skill_md
    assert "TIMESTAMP_SUB" in skill_md
    for legacy in ("UPSTREAM_TOKEN_EXPIRED", "synced_access_token", "Sync My Session", "dead-letter"):
        assert legacy not in skill_md


def test_python_env_key_resolution_supports_both_var_names(tmp_path: Path, monkeypatch):
    assert resolve_mcp_key_from_env({"ANOSYS_MCP_API_KEY": "ak_mcp_1", "ANOSYS_MCP_KEY": "ak_mcp_2"}) == "ak_mcp_1"
    assert resolve_mcp_key_from_env({"ANOSYS_MCP_KEY": "  ak_mcp_2  "}) == "ak_mcp_2"
    assert resolve_mcp_key_from_env({}) == ""

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ANOSYS_MCP_API_KEY", raising=False)
    monkeypatch.setenv("ANOSYS_MCP_KEY", "ak_mcp_py_env_alias")

    class Args:
        with_mcp = True
        with_skill = False
        mcp_key = ""
        mcp_url = DEFAULT_MCP_URL
        yes = True

    res = apply_install_mcp_flags("claude-code", Args())
    assert res is not None and res["mcp_updated"] is True
    cfg = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
    assert cfg["mcpServers"][MCP_SERVER_NAME]["headers"]["Authorization"] == "Bearer ak_mcp_py_env_alias"

    # Interactive blank prompt falls back to installing SKILL.md only
    monkeypatch.delenv("ANOSYS_MCP_KEY", raising=False)

    class InteractiveBlankArgs:
        with_mcp = True
        with_skill = False
        skill_only = False
        no_skill = False
        mcp_key = ""
        mcp_url = DEFAULT_MCP_URL
        yes = False

    blank_res = apply_install_mcp_flags("cursor", InteractiveBlankArgs(), prompt_fn=lambda _q: "")
    assert blank_res is not None
    assert blank_res["mcp_updated"] is False
    assert blank_res["skill_updated"] is True


def test_workspace_configs_reference_key_from_environment(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "repo"
    cwd.mkdir()

    cc = install_mcp_client("claude-code", mcp_key="ak_mcp_py_cc_ws", workspace=True, home_dir=home, cwd=cwd)
    raw = Path(cc["mcp_path"]).read_text(encoding="utf-8")
    assert Path(cc["mcp_path"]) == cwd / ".mcp.json"
    assert cc["key_from_env"] is True
    assert "ak_mcp_py_cc_ws" not in raw
    assert json.loads(raw)["mcpServers"][MCP_SERVER_NAME]["headers"]["Authorization"] == "Bearer ${ANOSYS_MCP_API_KEY}"

    cur = install_mcp_client("cursor", mcp_key="ak_mcp_py_cur_ws", workspace=True, home_dir=home, cwd=cwd)
    raw = Path(cur["mcp_path"]).read_text(encoding="utf-8")
    assert "ak_mcp_py_cur_ws" not in raw
    assert json.loads(raw)["mcpServers"][MCP_SERVER_NAME]["headers"]["Authorization"] == "Bearer ${env:ANOSYS_MCP_API_KEY}"

    cx = install_mcp_client("codex", mcp_key="ak_mcp_py_cx_ws", workspace=True, home_dir=home, cwd=cwd, env={})
    raw = Path(cx["mcp_path"]).read_text(encoding="utf-8")
    assert Path(cx["mcp_path"]) == cwd / ".codex" / "config.toml"
    assert "ak_mcp_py_cx_ws" not in raw
    assert 'bearer_token_env_var = "ANOSYS_MCP_API_KEY"' in raw
    assert "http_headers" not in raw

    # Global installs still hold the key in the user's own (0600) config file.
    g = install_mcp_client("claude-code", mcp_key="ak_mcp_py_cc_global", home_dir=home, cwd=cwd)
    assert g["key_from_env"] is False
    assert "ak_mcp_py_cc_global" in Path(g["mcp_path"]).read_text(encoding="utf-8")
