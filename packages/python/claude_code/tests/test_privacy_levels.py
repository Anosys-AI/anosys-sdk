"""
Privacy tests for the Claude Code hook: golden key sets per level (both
layouts), no history backfill, hook detection, scrubbing and encryption.
"""

import json
import sys

import pytest

from anosys_sdk_core.encryption import ANOSYS_ENCRYPTION_PREFIX, decrypt, derive_keys
from anosys_sdk_core.privacy import FULL, METADATA, OFF, POLICY_VERSION
from anosys_sdk_claude_code import hook_runner
from anosys_sdk_claude_code.installer import (
    has_anosys_hook, hook_command, remove_env, remove_stop_hooks, update_stop_hooks,
)
from anosys_sdk_claude_code.mapper import CV_METADATA_FIELDS, transform_record

USER = {"type": "user", "uuid": "u1", "sessionId": "s1", "cwd": "/Users/dev/app", "gitBranch": "main",
        "message": {"role": "user", "content": "Use key sk-ant-api03-abcdefghijklmnopqrstuvwxyz please"}}
ASSISTANT = {"type": "assistant", "uuid": "a1", "sessionId": "s1", "aiTitle": "Fix the billing bug",
             "message": {"id": "m1", "model": "claude-sonnet-5-5", "role": "assistant",
                         "content": [{"type": "text", "text": "Done"},
                                     {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}],
                         "usage": {"input_tokens": 10, "output_tokens": 4}},
             "toolUseResult": {"stdout": "secret file contents"}}
CONTENT_KEYS = {"user_prompt", "assistant_text", "tool_use_result", "cvs199", "ai_title"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("ANOSYS_CONSENT_FILE", str(tmp_path / "consent.json"))
    for var in ("ANOSYS_DISABLE", "ANOSYS_COLLECTION_LEVEL", "REDACTION", "ANOSYS_ENCRYPTION_KEY", "ANOSYS_CLAUDE_PIXEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize("record", [USER, ASSISTANT])
def test_metadata_sends_no_content(record):
    out = hook_runner.prepare_record(transform_record(record), METADATA)
    assert out["consent"] == "metadata;none"
    assert not CONTENT_KEYS & set(out)
    assert {"session_id", "event_id", "timestamp", "cvs200"} <= set(out)
    assert "sk-ant" not in json.dumps(out) and "secret file" not in json.dumps(out)


def test_metadata_keeps_usage_numbers():
    out = hook_runner.prepare_record(transform_record(ASSISTANT), METADATA)
    assert out["input_tokens"] == 10 and out["output_tokens"] == 4
    assert out["primary_model"] == "claude-sonnet-5-5"


def test_legacy_cv_layout_metadata(monkeypatch):
    monkeypatch.setenv("ANOSYS_CLAUDE_PIXEL", "false")
    out = hook_runner.prepare_record(transform_record(ASSISTANT), METADATA)
    for content_col in ("cvs4", "cvs5", "cvs26", "cvs41", "cvs199"):
        assert content_col not in out
    assert set(out) - {"consent", "timestamp", "user_timestamp", "event_id", "event_type",
                       "event_source_name", "debug", "cvs200"} <= CV_METADATA_FIELDS


def test_off_and_full():
    assert hook_runner.prepare_record(transform_record(USER), OFF) == {}
    out = hook_runner.prepare_record(transform_record(USER), FULL)
    assert out["consent"] == f"full;{POLICY_VERSION}"
    assert "[SECRET]" in out["user_prompt"] and "sk-ant-api03" not in out["user_prompt"]
    assert "sk-ant-api03" not in out["cvs199"]


def test_full_with_encryption(monkeypatch):
    monkeypatch.setenv("ANOSYS_ENCRYPTION_KEY", "pass")
    monkeypatch.setenv("ANOSYS_ENCRYPTION_SALT", "ws")
    out = hook_runner.prepare_record(transform_record(ASSISTANT), FULL)
    keys = derive_keys("pass", "ws")
    assert out["assistant_text"].startswith(ANOSYS_ENCRYPTION_PREFIX)
    assert out["tool_use_result"].startswith('"' + ANOSYS_ENCRYPTION_PREFIX)   # JSON column
    assert "secret file contents" in decrypt(out["tool_use_result"], keys)
    assert out["ai_title"].startswith(ANOSYS_ENCRYPTION_PREFIX)


def test_only_current_session_is_read(tmp_path):
    project = tmp_path / "projects" / "app"
    (project / "s1" / "subagents").mkdir(parents=True)
    current = project / "s1.jsonl"
    current.write_text("{}\n")
    (project / "s1" / "subagents" / "agent-a.jsonl").write_text("{}\n")
    (project / "old-session.jsonl").write_text("{}\n")
    (project / "old-session" / "subagents").mkdir(parents=True)
    (project / "old-session" / "subagents" / "agent-b.jsonl").write_text("{}\n")
    primary = hook_runner.TranscriptInfo(path=current, state_key="s1", session_id="s1", is_agent=False)
    found = [t.path.name for t in hook_runner.session_transcripts(primary)]
    assert found == ["s1.jsonl", "agent-a.jsonl"]


def test_unmarked_hook_is_detected_and_removed():
    # the form on real installs before the owner tag existed
    settings = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "anosys-claude-code run"}]},
                                   {"hooks": [{"type": "command", "command": "other-tool"}]}]},
                "env": {"REDACTION": "true", "ANOSYS_HOOK_APIKEY": "k", "KEEP": "1"}}
    assert has_anosys_hook(settings)
    out = remove_env(remove_stop_hooks(settings))
    assert not has_anosys_hook(out)
    assert out["hooks"]["Stop"] == [{"hooks": [{"type": "command", "command": "other-tool"}]}]
    assert out["env"] == {"KEEP": "1"}


def test_hook_command_uses_this_interpreter():
    settings = update_stop_hooks({}, hook_command())
    command = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert command.startswith(f'"{sys.executable}"') and has_anosys_hook(settings)
