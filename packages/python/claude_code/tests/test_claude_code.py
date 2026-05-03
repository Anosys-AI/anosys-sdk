"""Basic smoke tests for anosys-claude-code."""

from anosys_sdk_claude_code.mapper import transform_record, to_unix_ms, INTEGRATION_VERSION
from anosys_sdk_claude_code.installer import (
    update_env,
    update_stop_hooks,
    remove_stop_hooks,
    has_anosys_hook,
    get_anosys_hook_command,
)


def test_version():
    assert INTEGRATION_VERSION == "0.2.0"


def test_to_unix_ms_valid():
    ms = to_unix_ms("2024-01-15T12:00:00Z")
    assert isinstance(ms, int)
    assert ms > 0


def test_to_unix_ms_invalid():
    import time
    before = int(time.time() * 1000)
    ms = to_unix_ms("not-a-date")
    after = int(time.time() * 1000)
    assert before <= ms <= after


def test_transform_record_user():
    record = {
        "type": "user",
        "uuid": "test-uuid-123",
        "sessionId": "sess-abc",
        "timestamp": "2024-01-15T12:00:00Z",
        "message": {"content": "Hello Claude"},
    }
    payload = transform_record(record)
    assert payload["event_type"] == "claude_code_user"
    assert payload["user_prompt"] == "Hello Claude"
    assert payload["event_id"] == "test-uuid-123"
    assert payload["session_id"] == "sess-abc"
    assert payload["cvs200"] == "ClaudeCodeHook"


def test_transform_record_assistant_tokens():
    record = {
        "type": "assistant",
        "uuid": "asst-uuid-456",
        "sessionId": "sess-abc",
        "timestamp": "2024-01-15T12:01:00Z",
        "message": {
            "id": "msg_001",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "Hello!"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    }
    payload = transform_record(record)
    assert payload["event_type"] == "claude_code_assistant"
    assert payload["input_tokens"] == 10
    assert payload["output_tokens"] == 5
    assert payload["primary_model"] == "claude-sonnet-4-6"


def test_transform_record_filters_sentinel():
    record = {"type": "tombstone", "uuid": "tomb-1", "sessionId": "sess-xyz", "timestamp": "2024-01-15T12:00:00Z"}
    payload = transform_record(record)
    # Sentinel values (U) must not appear in output
    for v in payload.values():
        assert v is not None


def test_update_env_merges():
    settings: dict = {"env": {"EXISTING_KEY": "existing"}}
    new_env = {"ANOSYS_HOOK_ENDPOINT_URL": "https://example.com"}
    result = update_env(settings, new_env)
    assert result["env"]["ANOSYS_HOOK_ENDPOINT_URL"] == "https://example.com"
    assert result["env"]["EXISTING_KEY"] == "existing"


def test_update_env_strips_old_anosys_keys():
    settings: dict = {"env": {"ANOSYS_HOOK_ENDPOINT_URL": "old", "ANOSYS_HOOK_API_KEY": "old-key"}}
    result = update_env(settings, {"ANOSYS_HOOK_ENDPOINT_URL": "new"})
    assert result["env"]["ANOSYS_HOOK_ENDPOINT_URL"] == "new"
    assert "ANOSYS_HOOK_API_KEY" not in result["env"]


def test_hook_install_uninstall_roundtrip():
    settings: dict = {}
    assert not has_anosys_hook(settings)
    settings = update_stop_hooks(settings, "anosys-claude-code run")
    assert has_anosys_hook(settings)
    assert get_anosys_hook_command(settings) == "anosys-claude-code run"
    settings = remove_stop_hooks(settings)
    assert not has_anosys_hook(settings)


def test_hook_install_idempotent():
    settings: dict = {}
    settings = update_stop_hooks(settings, "anosys-claude-code run")
    settings = update_stop_hooks(settings, "anosys-claude-code run")
    # Should only have one AnoSys group
    anosys_count = sum(
        1
        for group in settings.get("hooks", {}).get("Stop", [])
        for h in group.get("hooks", [])
        if isinstance(h, dict) and h.get("owner") == "anosys"
    )
    assert anosys_count == 1


def test_hook_preserves_other_hooks():
    settings: dict = {
        "hooks": {
            "Stop": [
                {"hooks": [{"type": "command", "command": "other-hook"}]}
            ]
        }
    }
    settings = update_stop_hooks(settings, "anosys-claude-code run")
    stop_groups = settings["hooks"]["Stop"]
    commands = [h["command"] for g in stop_groups for h in g.get("hooks", []) if "command" in h]
    assert "other-hook" in commands
    assert "anosys-claude-code run" in commands
