import json
import os
import tempfile
from pathlib import Path

import pytest

from anosys_sdk_codex.installer import (
    HOOK_COMMAND,
    backup,
    has_anosys_hook,
    load_toml,
    remove_codex_config,
    update_codex_config,
    update_codex_env,
)
from anosys_sdk_codex.mapper import (
    calculate_cost,
    extract_commands_and_paths,
    transform_codex_turn,
)
from anosys_sdk_codex.hook_runner import (
    extract_turn_from_rollout,
    _extract_turn_fallback,
)


def test_calculate_cost():
    # 1000 input, 1000 output with 500 cached for gpt-4o
    cost = calculate_cost("gpt-4o", input_tokens=1000, output_tokens=1000, cached_tokens=500)
    assert cost > 0
    # o3-mini cost calculation
    cost_o3 = calculate_cost("o3-mini", input_tokens=2000, output_tokens=500, cached_tokens=0)
    assert cost_o3 > 0


def test_extract_commands_and_paths():
    tools = [
        {"tool": "shell", "args": json.dumps({"command": "git status"})},
        {"tool": "apply_patch", "args": json.dumps({"path": "src/main.py"})},
        {"tool": "web_search", "args": "python documentation"},
    ]
    commands, paths = extract_commands_and_paths(tools)
    assert "git status" in commands
    assert "src/main.py" in paths


def test_transform_codex_turn():
    turn = {
        "turn_id": "turn-123",
        "model": "gpt-4o",
        "model_provider": "openai",
        "cwd": "/workspace/project",
        "permission_mode": "auto",
        "user_prompt": "Refactor auth logic",
        "assistant_output": "Refactoring complete.",
        "turn_start_ms": 1700000000000,
        "turn_end_ms": 1700000005000,
        "duration_ms": 5000,
        "tokens": {
            "input_tokens": 1500,
            "output_tokens": 300,
            "total_tokens": 1800,
            "cached_input_tokens": 500,
            "cache_write_input_tokens": 0,
            "reasoning_output_tokens": 100,
        },
        "tool_calls": [
            {
                "tool": "shell",
                "args": json.dumps({"command": "pytest"}),
                "output": "1 passed",
                "call_id": "call_1",
                "start_ts": 1700000001000,
                "end_ts": 1700000002000,
            }
        ],
    }

    mapped = transform_codex_turn(turn, session_id="session-abc", turn_id="turn-123")

    assert mapped["cvs200"] == "CodexHook"
    assert mapped["sessionId"] == "session-abc"
    assert mapped["uuid"] == "turn-123"
    assert mapped["userPrompt"] == "Refactor auth logic"
    assert mapped["assistantText"] == "Refactoring complete."
    assert mapped["model"] == "gpt-4o"
    assert mapped["project"] == "project"
    assert mapped["input_tokens"] == 1500
    assert mapped["output_tokens"] == 300
    assert mapped["cache_read"] == 500
    assert mapped["reasoning_tokens"] == 100
    assert mapped["has_thinking"] is True
    assert mapped["tool_count"] == 1
    assert "pytest" in mapped["commands"]
    assert "cvs199" in mapped


def test_transform_codex_turn_redaction():
    turn = {
        "turn_id": "turn-999",
        "model": "o3-mini",
        "user_prompt": "Secret API password is ABC",
        "assistant_output": "Got your password ABC",
        "tokens": {"input_tokens": 10, "output_tokens": 10},
        "tool_calls": [{"tool": "shell", "args": "echo secret", "output": "secret"}],
    }

    mapped = transform_codex_turn(turn, session_id="session-sec", turn_id="turn-999", redact=True)

    assert mapped["userPrompt"] == "[REDACTED]"
    assert mapped["assistantText"] == "[REDACTED]"
    assert "[REDACTED]" in mapped["cvs199"]


def test_installer_config_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.toml"
        env_path = Path(tmpdir) / "anosys-env.sh"

        # 1. Update config
        updated = update_codex_config(HOOK_COMMAND, path=config_path)
        assert updated is True
        assert config_path.is_file()

        data = load_toml(config_path)
        assert has_anosys_hook(data) is True
        assert HOOK_COMMAND in data["notify"]

        # 2. Idempotent check
        updated_again = update_codex_config(HOOK_COMMAND, path=config_path)
        assert updated_again is False

        # 3. Backup
        bk = backup(config_path)
        assert bk is not None and bk.is_file()

        # 4. Update env
        update_codex_env(api_key="test-api-key", redaction=True, path=env_path)
        assert env_path.is_file()
        env_content = env_path.read_text(encoding="utf-8")
        assert "test-api-key" in env_content
        assert 'REDACTION="true"' in env_content

        # 5. Remove config
        removed = remove_codex_config(config_path)
        assert removed is True
        data_after = load_toml(config_path)
        assert has_anosys_hook(data_after) is False


def test_extract_turn_from_rollout():
    with tempfile.TemporaryDirectory() as tmpdir:
        rollout_path = Path(tmpdir) / "rollout-test-session.jsonl"
        lines = [
            {"type": "session_meta", "payload": {"model_provider": "openai"}},
            {"type": "turn_context", "payload": {"turn_id": "turn-1", "model": "gpt-4o", "cwd": "/home/dev/app", "approval_policy": "never"}},
            {"type": "event_msg", "timestamp": "2026-05-20T10:00:00Z", "payload": {"type": "task_started", "turn_id": "turn-1", "started_at": 1700000000}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": "hello codex"}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120, "cached_input_tokens": 50, "reasoning_output_tokens": 0}}}},
            {"type": "response_item", "timestamp": "2026-05-20T10:00:01Z", "payload": {"type": "function_call", "name": "shell", "call_id": "c1", "arguments": "{\"command\":\"ls\"}"}},
            {"type": "response_item", "timestamp": "2026-05-20T10:00:02Z", "payload": {"type": "function_call_output", "call_id": "c1", "output": "file.txt"}},
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "I listed the files."}},
            {"type": "event_msg", "payload": {"type": "task_complete", "completed_at": 1700000003, "duration_ms": 3000}},
        ]
        with open(rollout_path, "w", encoding="utf-8") as fh:
            for item in lines:
                fh.write(json.dumps(item) + "\n")

        turn = extract_turn_from_rollout(rollout_path, "turn-1")
        assert turn is not None
        assert turn["turn_id"] == "turn-1"
        assert turn["user_prompt"] == "hello codex"
        assert turn["assistant_output"] == "I listed the files."
        assert turn["model"] == "gpt-4o"
        assert turn["cwd"] == "/home/dev/app"
        assert turn["tokens"]["input_tokens"] == 100
        assert turn["tokens"]["output_tokens"] == 20
        assert turn["tokens"]["cached_input_tokens"] == 50
        assert len(turn["tool_calls"]) == 1
        assert turn["tool_calls"][0]["tool"] == "shell"
        assert turn["tool_calls"][0]["output"] == "file.txt"


def test_fallback_turn():
    event = {
        "last-assistant-message": "fallback answer",
        "input-messages": ["fallback prompt"],
        "cwd": "/test/cwd",
        "model": "gpt-4o-mini",
    }
    fb = _extract_turn_fallback(event, "sess-1", "turn-1")
    assert fb["turn_id"] == "turn-1"
    assert fb["user_prompt"] == "fallback prompt"
    assert fb["assistant_output"] == "fallback answer"
    assert fb["model"] == "gpt-4o-mini"


def test_cmd_install_non_interactive(monkeypatch, tmp_path):
    from unittest.mock import patch
    from anosys_sdk_codex.cli import main
    
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    
    with patch("anosys_sdk_codex.cli.validate_api_key", return_value=True):
        main(["install", "--api-key", "test-py-key-12345", "-y"])
        
    env_file = tmp_path / ".codex" / "anosys-env.sh"
    assert env_file.is_file()
    assert "test-py-key-12345" in env_file.read_text(encoding="utf-8")
