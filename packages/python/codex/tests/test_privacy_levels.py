"""
Privacy and delivery tests for the Codex hook.

Golden key sets per level, encryption, argv/notify chaining, delivery
failures and cleanup of the pre-v2 pending file.
"""

import json

import pytest

from anosys_sdk_core.encryption import ANOSYS_ENCRYPTION_PREFIX, decrypt, derive_keys
from anosys_sdk_core.privacy import FULL, METADATA, OFF, POLICY_VERSION, write_consent
from anosys_sdk_codex import hook_runner
from anosys_sdk_codex.mapper import transform_codex_turn
import anosys_sdk_core.transport as transport

_ORIGINAL_SEND = transport.send_records

TURN = {
    "turn_id": "turn-1",
    "model": "gpt-5",
    "cwd": "/Users/dev/project",
    "user_prompt": "Deploy with key sk-proj-abcdefghijklmnopqrstuvwxyz",
    "assistant_output": "Done",
    "tokens": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    "tool_calls": [{"tool": "shell", "args": json.dumps({"command": "echo $TOKEN"}), "output": "secret"}],
    "raw": {"events": [{"payload": {"output": "file contents"}}]},
}

METADATA_KEYS = {
    "session_id", "sessionId", "uuid", "raw_uuid", "eventId", "event_id", "event_type", "event_source_name",
    "timestamp", "user_timestamp", "debug", "model", "primary_model", "model_provider", "cwd", "project",
    "input_tokens", "output_tokens", "total_tokens", "cache_read", "cache_creation", "reasoning_tokens",
    "cost_estimate", "incremental_input", "incremental_output", "incremental_total", "incremental_cost",
    "incremental_cache_read", "incremental_cache_creation", "tool_count", "has_thinking",
    "integration_version", "os_user", "cvs198", "cvs200",
}
CONTENT_KEYS = {"user_prompt", "userPrompt", "assistant_text", "assistantText", "commands", "cvs199"}

CV_METADATA_KEYS = {
    "event_id", "eventId", "uuid", "event_type", "event_source_name",
    "timestamp", "user_timestamp", "debug",
    "cvs1", "cvs2", "cvs9", "cvs12", "cvs13", "cvs17", "cvs19", "cvs32", "cvs33",
    "cvn1", "cvn2", "cvn3", "cvn4", "cvn5", "cvn7", "cvn41", "cvb1", "cvb2",
    "cvs198", "cvs200",
}
CV_CONTENT_KEYS = {"cvs4", "cvs5", "cvs90", "cvs199"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("ANOSYS_CONSENT_FILE", str(tmp_path / "consent.json"))
    for var in ("ANOSYS_DISABLE", "ANOSYS_COLLECTION_LEVEL", "REDACTION", "ANOSYS_ENCRYPTION_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(hook_runner, "PENDING_FILE", tmp_path / "pending_records.jsonl")
    monkeypatch.setattr(hook_runner, "PAUSE_FILE", tmp_path / "paused.json")
    monkeypatch.setattr(hook_runner, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(hook_runner, "LOG_FILE", tmp_path / "anosys_hook.log")
    monkeypatch.setattr(hook_runner, "DRY_RUN", False)
    return tmp_path


def mapped():
    return transform_codex_turn(TURN, session_id="s1", turn_id="t1")


def test_metadata_is_the_default_and_sends_no_content():
    record = hook_runner.prepare_record(mapped(), METADATA)
    assert set(record) == METADATA_KEYS
    assert record["cvs198"] == "metadata;none"
    assert not CONTENT_KEYS & set(record)


def test_legacy_cv_layout_metadata(monkeypatch):
    monkeypatch.setenv("ANOSYS_CODEX_PIXEL", "false")
    record = hook_runner.prepare_record(mapped(), METADATA)
    assert set(record) == CV_METADATA_KEYS
    assert record["cvs198"] == "metadata;none"
    assert not CV_CONTENT_KEYS & set(record)

    full_record = hook_runner.prepare_record(mapped(), FULL)
    assert CV_CONTENT_KEYS <= set(full_record)


def test_off_sends_nothing():
    assert hook_runner.prepare_record(mapped(), OFF) == {}


def test_full_keeps_content_and_scrubs_secrets():
    record = hook_runner.prepare_record(mapped(), FULL)
    assert CONTENT_KEYS <= set(record)
    assert record["cvs198"] == f"full;{POLICY_VERSION}"
    assert "sk-proj-abcdef" not in record["user_prompt"] and "[SECRET]" in record["user_prompt"]
    assert "sk-proj-abcdef" not in record["cvs199"]


def test_full_with_encryption(monkeypatch):
    monkeypatch.setenv("ANOSYS_ENCRYPTION_KEY", "pass")
    monkeypatch.setenv("ANOSYS_ENCRYPTION_SALT", "ws")
    record = hook_runner.prepare_record(mapped(), FULL)
    keys = derive_keys("pass", "ws")
    assert record["user_prompt"].startswith(ANOSYS_ENCRYPTION_PREFIX)
    assert record["commands"].startswith('"' + ANOSYS_ENCRYPTION_PREFIX)  # JSON column stays valid JSON
    assert decrypt(record["assistant_text"], keys) == "Done"
    assert record["input_tokens"] == 10   # metadata stays readable


class Post:
    def __init__(self, *statuses):
        self.statuses = list(statuses)
        self.bodies = []

    def __call__(self, url, json=None, headers=None, timeout=None):
        self.bodies.append(json)

        class R:
            status_code = self.statuses.pop(0) if self.statuses else 200
        return R()


def run_turn(monkeypatch, post, turn_id="t1", argv_extra=()):
    monkeypatch.setattr(transport, "send_records", _bind(_ORIGINAL_SEND, post))
    event = json.dumps({"type": "agent-turn-complete", "thread-id": "s1", "turn-id": turn_id,
                        "input-messages": ["hello"], "last-assistant-message": "hi"})
    hook_runner.run(["run", *argv_extra, event])


def _bind(fn, post):
    def wrapper(*args, **kwargs):
        kwargs["post"] = post
        return fn(*args, **kwargs)
    return wrapper


def test_turn_sent_at_metadata(monkeypatch):
    post = Post(200)
    run_turn(monkeypatch, post)
    (body,) = post.bodies
    assert body[0]["cvs198"] == "metadata;none" and "user_prompt" not in body[0]


def test_level_off_sends_nothing(monkeypatch):
    write_consent(OFF, method="test")
    post = Post()
    run_turn(monkeypatch, post)
    assert post.bodies == []


def test_auth_error_pauses_without_queueing(monkeypatch, isolated):
    run_turn(monkeypatch, Post(403), "t1")
    post = Post()
    run_turn(monkeypatch, post, "t2")
    assert post.bodies == [] and not (isolated / "pending_records.jsonl").exists()


def test_outage_queues_then_drains(monkeypatch, isolated):
    for i in range(3):
        run_turn(monkeypatch, Post(503, 503), f"t{i}")
    assert len(hook_runner.PendingQueue(isolated / "pending_records.jsonl").load()) == 3
    post = Post(200, 200)
    run_turn(monkeypatch, post, "t9")
    assert sum(len(b) for b in post.bodies) == 4
    assert not (isolated / "pending_records.jsonl").exists()


def test_pre_v2_pending_file_is_replaced(monkeypatch, isolated):
    legacy = isolated / "pending_records.jsonl"
    legacy.write_text(json.dumps({"cvs199": "old full content"}) + "\n")
    run_turn(monkeypatch, Post(200))
    assert not legacy.exists()


def test_previous_notify_is_called(monkeypatch):
    calls = []
    monkeypatch.setattr(hook_runner, "call_previous_notify", lambda prev, raw: calls.append((prev, json.loads(raw)["turn-id"])))
    run_turn(monkeypatch, Post(200), "t5", ("--previous-notify", json.dumps(["/bin/echo", "x"])))
    assert calls == [(["/bin/echo", "x"], "t5")]


def test_parse_argv():
    prev, raw = hook_runner.parse_argv(["run", "--previous-notify", '["a","b"]', '{"x":1}'])
    assert prev == ["a", "b"] and json.loads(raw) == {"x": 1}
    prev, raw = hook_runner.parse_argv(['{"x":2}'])
    assert prev is None and json.loads(raw) == {"x": 2}


def test_log_has_no_content(monkeypatch):
    run_turn(monkeypatch, Post(200))
    text = hook_runner.LOG_FILE.read_text(encoding="utf-8") if hook_runner.LOG_FILE.exists() else ""
    assert "hello" not in text and "last-assistant-message" not in text
