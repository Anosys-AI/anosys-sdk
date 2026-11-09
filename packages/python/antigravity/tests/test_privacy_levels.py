"""Privacy tests for the Antigravity hook: golden key sets per level and the absolute hook command."""

import json
import sys

import pytest

from anosys_sdk_core.privacy import FULL, METADATA, OFF, POLICY_VERSION
from anosys_sdk_antigravity import hook_runner
from anosys_sdk_antigravity.installer import load_json, update_hooks_config
from anosys_sdk_antigravity.mapper import transform_antigravity_turn

TURN = {
    "user_input": "Rotate token ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    "final_response": "Rotated",
    "model_name": "gemini-3-pro",
    "start_ms": 1000, "end_ms": 2500,
    "active_document": "/Users/dev/app/secrets.env",
    "tool_steps": [{"tool": "run_command", "args": {"CommandLine": "cat .env"}, "output": "API_KEY=abc"}],
}
CONTENT = {"user_prompt", "userPrompt", "assistant_text", "assistantText", "cvs4", "cvs5",
           "commands", "cvs90", "cvs199", "active_document", "cvs70"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("ANOSYS_CONSENT_FILE", str(tmp_path / "consent.json"))
    for var in ("ANOSYS_DISABLE", "ANOSYS_COLLECTION_LEVEL", "REDACTION", "ANOSYS_ENCRYPTION_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)


def mapped():
    return transform_antigravity_turn(TURN, session_id="s1", turn_id="s1_0",
                                      hook_metadata={"workspacePaths": ["/Users/dev/app"]})


def test_metadata_default_sends_no_content():
    out = hook_runner.prepare_record(mapped(), METADATA)
    assert not CONTENT & set(out)
    assert out["consent"] == "metadata;none" and out["cvs198"] == "metadata;none" and out["model"] == "gemini-3-pro"
    assert "ghp_" not in json.dumps(out) and "API_KEY" not in json.dumps(out)


def test_off_and_full():
    assert hook_runner.prepare_record(mapped(), OFF) == {}
    out = hook_runner.prepare_record(mapped(), FULL)
    assert out["consent"] == f"full;{POLICY_VERSION}"
    assert "ghp_abcdef" not in out["user_prompt"] and "[SECRET]" in out["user_prompt"]


def test_hook_command_is_absolute(tmp_path):
    hooks = tmp_path / "hooks.json"
    update_hooks_config(hooks)
    command = json.dumps(load_json(hooks))
    assert sys.executable in command and "anosys_sdk_antigravity.cli run" in command
