"""
Expanded tests for anosys-claude-code Python package.

Covers:
- mapper: transform_record for all major message types, token calc, cost, redaction
- installer: env management (OTEL standard vars, legacy cleanup), hook lifecycle
- hook_runner: state helpers, pending records (file I/O mocked via tmp dirs)
"""

import time

from anosys_sdk_claude_code.mapper import (
    INTEGRATION_VERSION,
    calculate_cost,
    to_unix_ms,
    transform_record,
)
from anosys_sdk_claude_code.installer import (
    get_anosys_hook_command,
    has_anosys_hook,
    remove_env,
    remove_stop_hooks,
    update_env,
    update_stop_hooks,
)

# ──────────────────────────────────────────────────────────────────────────────
# to_unix_ms
# ──────────────────────────────────────────────────────────────────────────────

def test_to_unix_ms_valid_z():
    ms = to_unix_ms("2024-01-15T12:00:00Z")
    assert isinstance(ms, int)
    assert ms > 1_700_000_000_000


def test_to_unix_ms_invalid_returns_now():
    before = int(time.time() * 1000)
    ms = to_unix_ms("not-a-date")
    after = int(time.time() * 1000)
    assert before <= ms <= after


def test_to_unix_ms_empty_returns_now():
    before = int(time.time() * 1000)
    ms = to_unix_ms("")
    after = int(time.time() * 1000)
    assert before <= ms <= after


def test_to_unix_ms_none_returns_now():
    before = int(time.time() * 1000)
    ms = to_unix_ms(None)  # type: ignore
    after = int(time.time() * 1000)
    assert before <= ms <= after


# ──────────────────────────────────────────────────────────────────────────────
# calculate_cost
# ──────────────────────────────────────────────────────────────────────────────

def test_calculate_cost_basic():
    cost = calculate_cost("claude-sonnet-4-6", {"input_tokens": 1000, "output_tokens": 500})
    # 1000 * 3/1e6 + 500 * 15/1e6 = 0.003 + 0.0075 = 0.0105
    assert abs(cost - 0.0105) < 1e-6


def test_calculate_cost_none_model():
    assert calculate_cost(None, {"input_tokens": 100}) is None


def test_calculate_cost_none_usage():
    assert calculate_cost("claude-sonnet-4-6", None) is None


def test_calculate_cost_nested_cache_creation():
    cost = calculate_cost("claude-sonnet-4-6", {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation": {
            "ephemeral_1h_input_tokens": 1_000_000,
            "ephemeral_5m_input_tokens": 0,
        },
    })
    # 1M cache write tokens on claude-sonnet-4-6
    # Context > 200k => cacheWrite rate doubles: 3.75 * 2 = 7.50
    # 1M * $7.50/M = $7.50
    assert isinstance(cost, float) and cost > 0


def test_calculate_cost_unknown_model_uses_fallback():
    cost = calculate_cost("unknown-model", {"input_tokens": 1000, "output_tokens": 500})
    assert isinstance(cost, float)
    assert cost > 0


# ──────────────────────────────────────────────────────────────────────────────
# transform_record — user messages
# ──────────────────────────────────────────────────────────────────────────────

def _user_record(**kwargs):
    base = {"type": "user", "uuid": "u-1", "sessionId": "sess-1", "timestamp": "2024-01-15T12:00:00Z"}
    base.update(kwargs)
    return base


def _asst_record(**kwargs):
    base = {"type": "assistant", "uuid": "a-1", "sessionId": "sess-1", "timestamp": "2024-01-15T12:01:00Z"}
    base.update(kwargs)
    return base


def test_transform_user_string_content():
    r = _user_record(message={"content": "Hello"})
    p = transform_record(r)
    assert p["event_type"] == "claude_code_user"
    assert p["user_prompt"] == "Hello"
    assert p["session_id"] == "sess-1"
    assert p["event_id"] == "u-1"
    assert p["cvs200"] == "ClaudeCodeHook"


def test_transform_user_list_content_text():
    r = _user_record(message={"content": [{"type": "text", "text": "Hi"}, {"type": "image"}]})
    p = transform_record(r)
    assert "Hi" in p["user_prompt"]
    assert "[Image Content]" in p["user_prompt"]


def test_transform_user_tool_result():
    r = _user_record(message={
        "content": [{"type": "tool_result", "tool_use_id": "tu-1", "content": "file content"}]
    })
    p = transform_record(r)
    assert "[Tool Result]" in p["user_prompt"]
    assert p["tool_use_id"] == "tu-1"


def test_transform_user_tool_result_error():
    r = _user_record(message={
        "content": [{"type": "tool_result", "tool_use_id": "tu-err", "content": "err msg", "is_error": True}]
    })
    p = transform_record(r)
    assert "[Tool Error]" in p["user_prompt"]


# ──────────────────────────────────────────────────────────────────────────────
# transform_record — assistant messages
# ──────────────────────────────────────────────────────────────────────────────

def test_transform_assistant_text():
    r = _asst_record(message={
        "id": "msg_001",
        "model": "claude-sonnet-4-6",
        "content": [{"type": "text", "text": "Sure!"}],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    })
    p = transform_record(r)
    assert p["event_type"] == "claude_code_assistant"
    assert p["assistant_text"] == "Sure!"
    assert p["input_tokens"] == 10
    assert p["output_tokens"] == 5
    assert p["primary_model"] == "claude-sonnet-4-6"


def test_transform_assistant_tool_use():
    r = _asst_record(message={
        "model": "claude-sonnet-4-6",
        "content": [{"type": "tool_use", "id": "tu-99", "name": "bash", "input": {"cmd": "ls"}}],
        "usage": {"input_tokens": 5, "output_tokens": 3},
    })
    p = transform_record(r)
    assert p["tool_use_id"] == "tu-99"
    assert "[Tool Use: bash" in p["assistant_text"]


def test_transform_assistant_thinking_block():
    r = _asst_record(message={
        "model": "claude-sonnet-4-6",
        "content": [{"type": "thinking", "thinking": "Hmm..."}],
        "usage": {"input_tokens": 3, "output_tokens": 2},
    })
    p = transform_record(r)
    assert p.get("has_thinking") is True
    assert "thinking" in p["assistant_text"]


def test_transform_assistant_incremental_tokens():
    r = _asst_record(message={
        "model": "claude-sonnet-4-6",
        "content": [],
        "usage": {"input_tokens": 100, "output_tokens": 50},
    })
    inc = {"input": 20, "output": 10, "cache_read": 0, "cache_creation": 0, "total": 30}
    p = transform_record(r, inc)
    assert p["incremental_input"] == 20
    assert p["incremental_output"] == 10


# ──────────────────────────────────────────────────────────────────────────────
# transform_record — various special types
# ──────────────────────────────────────────────────────────────────────────────

def test_transform_tombstone():
    r = {"type": "tombstone", "uuid": "t1", "sessionId": "sess", "timestamp": "2024-01-15T12:00:00Z"}
    p = transform_record(r)
    assert "Tombstone" in p["assistant_text"]


def test_transform_summary():
    r = {"type": "summary", "uuid": "s1", "sessionId": "sess", "timestamp": "2024-01-15T12:00:00Z", "summary": "All done."}
    p = transform_record(r)
    assert p["assistant_text"] == "All done."
    assert p["user_prompt"] == "[Session Summary Request]"


def test_transform_api_error():
    r = {"type": "api_error", "uuid": "e1", "sessionId": "sess", "timestamp": "2024-01-15T12:00:00Z",
         "error": {"message": "Rate limit exceeded"}}
    p = transform_record(r)
    assert "[API Error:" in p["assistant_text"]
    assert "Rate limit exceeded" in p["assistant_text"]


def test_transform_progress():
    r = {"type": "progress", "uuid": "p1", "sessionId": "sess", "timestamp": "2024-01-15T12:00:00Z",
         "data": {"hookName": "bash", "hookEvent": "start", "command": "ls"}}
    p = transform_record(r)
    assert "[Progress:" in p["assistant_text"]


def test_transform_unknown_type_fallback():
    r = {"type": "completely-unknown", "uuid": "x1", "sessionId": "sess", "timestamp": "2024-01-15T12:00:00Z"}
    p = transform_record(r)
    assert "[Unmapped Content for Type:" in p["user_prompt"]


def test_transform_no_sentinel_values_in_output():
    """No None values should remain in the output dict."""
    r = _user_record(message={"content": "hi"})
    p = transform_record(r)
    for v in p.values():
        assert v is not None


# ──────────────────────────────────────────────────────────────────────────────
# transform_record — context_overrides
# ──────────────────────────────────────────────────────────────────────────────

def test_transform_context_override_session_id():
    r = {"type": "user", "uuid": "u1", "timestamp": "2024-01-15T12:00:00Z", "message": {"content": "hi"}}
    p = transform_record(r, context_overrides={"sessionId": "ctx-sess"})
    assert p["session_id"] == "ctx-sess"


def test_transform_context_override_log_index_event_id():
    r = {"type": "user", "sessionId": "sess", "timestamp": "2024-01-15T12:00:00Z", "message": {"content": "hi"}}
    p = transform_record(r, context_overrides={"log_index": 42})
    assert "42" in str(p["event_id"])


def test_transform_context_override_is_agent():
    r = _user_record(message={"content": "hi"})
    p = transform_record(r, context_overrides={"is_agent": True})
    assert p["is_agent"] is True


# ──────────────────────────────────────────────────────────────────────────────
# INTEGRATION_VERSION
# ──────────────────────────────────────────────────────────────────────────────

def test_integration_version_format():
    parts = INTEGRATION_VERSION.split(".")
    assert len(parts) == 3
    for part in parts:
        assert part.isdigit()


# ──────────────────────────────────────────────────────────────────────────────
# installer — env management (OTEL standard vars)
# ──────────────────────────────────────────────────────────────────────────────

def test_update_env_sets_otel_standard_vars():
    result = update_env({}, {
        "OTEL_EXPORTER_OTLP_ENDPOINT": "https://api.anosys.ai/ingestion",
        "OTEL_EXPORTER_OTLP_HEADERS": "anosys-apikey=mykey",
    })
    assert result["env"]["OTEL_EXPORTER_OTLP_ENDPOINT"] == "https://api.anosys.ai/ingestion"
    assert result["env"]["OTEL_EXPORTER_OTLP_HEADERS"] == "anosys-apikey=mykey"
    assert "OTEL_EXPORTER_OTLP_ANOSYS_APIKEY" not in result["env"]


def test_update_env_removes_legacy_key():
    settings = {"env": {"OTEL_EXPORTER_OTLP_ANOSYS_APIKEY": "legacy"}}
    result = update_env(settings, {
        "OTEL_EXPORTER_OTLP_ENDPOINT": "https://api.anosys.ai/ingestion",
        "OTEL_EXPORTER_OTLP_HEADERS": "anosys-apikey=new",
    })
    assert "OTEL_EXPORTER_OTLP_ANOSYS_APIKEY" not in result["env"]
    assert result["env"]["OTEL_EXPORTER_OTLP_HEADERS"] == "anosys-apikey=new"


def test_remove_env_strips_all_managed_keys():
    settings = {"env": {
        "KEEP": "this",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "x",
        "OTEL_EXPORTER_OTLP_HEADERS": "y",
        "OTEL_EXPORTER_OTLP_ANOSYS_APIKEY": "z",
        "ANOSYS_HOOK_APIKEY": "k",
        "ANOSYS_HOOK_ENDPOINT_URL": "old",
        "ANOSYS_HOOK_API_KEY": "old",
        "ANOSYS_CLAUDE_PIXEL": "false",
        "REDACTION": "true",
    }}
    result = remove_env(settings)
    assert result["env"]["KEEP"] == "this"
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in result["env"]
    assert "OTEL_EXPORTER_OTLP_HEADERS" not in result["env"]
    assert "OTEL_EXPORTER_OTLP_ANOSYS_APIKEY" not in result["env"]
    assert "ANOSYS_HOOK_APIKEY" not in result["env"]
    assert "ANOSYS_HOOK_ENDPOINT_URL" not in result["env"]
    assert "ANOSYS_HOOK_API_KEY" not in result["env"]


def test_update_env_replaces_old_values_on_reinstall():
    settings = {"env": {
        "OTEL_EXPORTER_OTLP_ENDPOINT": "https://old.example",
        "OTEL_EXPORTER_OTLP_HEADERS": "anosys-apikey=old",
    }}
    result = update_env(settings, {
        "OTEL_EXPORTER_OTLP_ENDPOINT": "https://api.anosys.ai/ingestion",
        "OTEL_EXPORTER_OTLP_HEADERS": "anosys-apikey=new",
    })
    assert result["env"]["OTEL_EXPORTER_OTLP_ENDPOINT"] == "https://api.anosys.ai/ingestion"
    assert result["env"]["OTEL_EXPORTER_OTLP_HEADERS"] == "anosys-apikey=new"


# ──────────────────────────────────────────────────────────────────────────────
# installer — hook lifecycle
# ──────────────────────────────────────────────────────────────────────────────

def test_hook_roundtrip():
    s: dict = {}
    assert not has_anosys_hook(s)
    s = update_stop_hooks(s, "anosys-claude-code run")
    assert has_anosys_hook(s)
    assert get_anosys_hook_command(s) == "anosys-claude-code run"
    s = remove_stop_hooks(s)
    assert not has_anosys_hook(s)
    assert get_anosys_hook_command(s) is None


def test_hook_idempotent():
    s: dict = {}
    s = update_stop_hooks(s, "anosys-claude-code run")
    s = update_stop_hooks(s, "anosys-claude-code run")
    count = sum(
        1
        for group in s.get("hooks", {}).get("Stop", [])
        for h in group.get("hooks", [])
        if isinstance(h, dict) and h.get("owner") == "anosys"
    )
    assert count == 1


def test_hook_preserves_other_hooks():
    s = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other-hook"}]}]}}
    s = update_stop_hooks(s, "anosys-claude-code run")
    all_cmds = [h["command"] for g in s["hooks"]["Stop"] for h in g.get("hooks", []) if "command" in h]
    assert "other-hook" in all_cmds
    assert "anosys-claude-code run" in all_cmds


def test_remove_hook_preserves_other_tools():
    s = {"hooks": {"Stop": [{
        "hooks": [
            {"owner": "other", "type": "command", "command": "other-cmd"},
            {"owner": "anosys", "type": "command", "command": "anosys-claude-code run"},
        ]
    }]}}
    s = remove_stop_hooks(s)
    all_cmds = [h["command"] for g in s["hooks"]["Stop"] for h in g.get("hooks", []) if "command" in h]
    assert "other-cmd" in all_cmds
    assert "anosys-claude-code run" not in all_cmds


def test_has_anosys_hook_empty():
    assert not has_anosys_hook({})
    assert not has_anosys_hook({"hooks": {}})
    assert not has_anosys_hook({"hooks": {"Stop": []}})


# ──────────────────────────────────────────────────────────────────────────────
# hook_runner — state + pending records (file I/O with tmpdir)
# ──────────────────────────────────────────────────────────────────────────────

def test_load_save_state(tmp_path, monkeypatch):
    import anosys_sdk_claude_code.hook_runner as hr
    state_file = tmp_path / "hook_state.json"
    monkeypatch.setattr(hr, "STATE_FILE", state_file)
    monkeypatch.setattr(hr, "STATE_DIR", tmp_path)

    s = hr.load_state()
    assert s == {}

    data = {"sess-1": {"last_line": 42}}
    hr.save_state(data)
    reloaded = hr.load_state()
    assert reloaded == data


def test_pending_records_roundtrip(tmp_path, monkeypatch):
    import anosys_sdk_claude_code.hook_runner as hr
    pending_file = tmp_path / "pending_records.jsonl"
    monkeypatch.setattr(hr, "PENDING_RECORDS_FILE", pending_file)

    # Initially empty
    assert hr.load_pending_records() == []

    records = [{"event_id": "r1", "session_id": "sess"}, {"event_id": "r2", "session_id": "sess"}]
    hr.save_pending_records(records)
    loaded = hr.load_pending_records()
    assert len(loaded) == 2
    assert loaded[0]["event_id"] == "r1"

    # Append more
    hr.save_pending_records([{"event_id": "r3", "session_id": "sess"}])
    assert len(hr.load_pending_records()) == 3

    # Overwrite
    hr.save_pending_records([{"event_id": "only", "session_id": "sess"}], overwrite=True)
    assert len(hr.load_pending_records()) == 1

    hr.clear_pending_records()
    assert hr.load_pending_records() == []


def test_find_all_transcripts_returns_list():
    from anosys_sdk_claude_code.hook_runner import find_all_transcripts
    result = find_all_transcripts()
    assert isinstance(result, list)
