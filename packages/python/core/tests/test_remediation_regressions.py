"""Regression tests for end-to-end audit remediation across AnoSys SDK packages."""

import inspect
import json

from anosys_sdk_anthropic.instrumentor import _is_anthropic_span
from anosys_sdk_antigravity.mapper import extract_tool_details, transform_antigravity_turn
from anosys_sdk_antigravity.transcript import build_turn
from anosys_sdk_claude_code.mapper import transform_record
from anosys_sdk_codex.mapper import calculate_cost as codex_calculate_cost
from anosys_sdk_core.decorators import anosys_logger
from anosys_sdk_core.encryption import JSON_COLUMNS, encrypt_payload, get_target_columns
from anosys_sdk_core.genai import extract_genai_span_info
from anosys_sdk_core.models import BASE_KEY_MAPPING
from anosys_sdk_core.redaction import scrub_secrets
from anosys_sdk_core.util.batching import reassign
from anosys_sdk_openai.hooks import extract_span_info as openai_extract_span_info
from anosys_sdk_openai_agents.mapping import flatten_messages as agents_flatten_messages


def test_batching_handles_non_finite_floats_and_hook_tags():
    mapping = dict(BASE_KEY_MAPPING)
    mapping["cvs1"] = "cvs1"
    payload = {
        "cvs200": "CodexHook",
        "cvs1": "sess-1",
        "custom_mapping": "{}",
        "finite_num": 42.5,
        "inf_val": float("inf"),
        "nan_val": float("nan"),
    }
    res = reassign(payload, mapping)
    assert res["cvs1"] == "sess-1"
    assert "finite_num" in res["otel_schema_url"]
    # Non-finite numbers must not be placed into numeric cvn* columns
    for k, v in res.items():
        if k.startswith("cvn") and isinstance(v, (int, float)):
            assert v not in (float("inf"), float("-inf"))
            assert v == v  # not NaN


def test_encryption_json_columns_and_custom_mirror_columns(monkeypatch):
    for col in (
        "gen_ai_input_messages",
        "gen_ai_output_messages",
        "gen_ai_system_instructions",
        "gen_ai_tool_definitions",
    ):
        assert col in JSON_COLUMNS

    monkeypatch.setenv("ANOSYS_ENCRYPTION_KEY", "test-passphrase-123")
    monkeypatch.setenv("ANOSYS_ENCRYPTED_COLUMNS", "user_prompt")
    cols = get_target_columns({"user_prompt": "hi", "cvs199": "{}", "otel_events": "[]"})
    assert "user_prompt" in cols
    assert "cvs199" in cols
    assert "otel_events" in cols

    rec = {
        "gen_ai_input_messages": json.dumps([{"role": "user", "content": "secret"}]),
        "user_prompt": "secret",
    }
    monkeypatch.delenv("ANOSYS_ENCRYPTED_COLUMNS", raising=False)
    enc = encrypt_payload(rec)
    # JSON_COLUMNS must remain valid JSON strings after encryption
    parsed = json.loads(enc["gen_ai_input_messages"])
    assert isinstance(parsed, str) and parsed.startswith("enc2:")


def test_scrub_secrets_expanded_patterns():
    sample = (
        "gho_1234567890abcdefghijklmnopqrstuvwx "
        "glpat-1234567890abcdefghij "
        "https://admin:supersecretpassword@db.internal.example.com/prod "
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA0123456789abcdef\n-----END RSA PRIVATE KEY-----"
    )
    scrubbed = scrub_secrets(sample)
    assert "gho_12345" not in scrubbed
    assert "glpat-12345" not in scrubbed
    assert "supersecretpassword" not in scrubbed
    assert "MIIEpAIBAAKCAQEA0123456789abcdef" not in scrubbed


def test_anosys_logger_preserves_sync_generator():
    @anosys_logger(source="gen-test")
    def my_gen(n):
        for i in range(n):
            yield i * 2

    assert inspect.isgeneratorfunction(my_gen)
    gen = my_gen(3)
    assert inspect.isgenerator(gen)
    assert list(gen) == [0, 2, 4]


def test_openai_and_agents_extract_span_info_list_messages_and_system_instructions():
    span_data = {
        "name": "ChatCompletion",
        "context": {"trace_id": "t1", "span_id": "s1"},
        "attributes": {
            "llm.input_messages.0.message.role": "user",
            "llm.input_messages.0.message.content": "Hello from list",
            "llm.output_messages.0.message.role": "assistant",
            "llm.output_messages.0.message.content": "Reply from list",
            "input.value": "Plain user input",
            "output.value": "Plain assistant output",
        },
    }
    res_openai = openai_extract_span_info(span_data)
    assert "Hello from list" in res_openai["gen_ai_input_messages"]
    assert "Reply from list" in res_openai["gen_ai_output_messages"]
    assert res_openai.get("gen_ai_system_instructions") is None

    flattened = agents_flatten_messages([{"message": {"role": "user", "content": "Hello from list"}}])
    assert "Hello from list" in flattened


def test_genai_extracts_tool_attributes():
    span_data = {
        "name": "execute_tool bash",
        "context": {"trace_id": "t1", "span_id": "s1"},
        "attributes": {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "bash",
            "gen_ai.tool.call.id": "call_99",
            "gen_ai.tool.type": "function",
            "gen_ai.tool.call.arguments": '{"cmd":"ls"}',
            "gen_ai.tool.call.result": "ok",
        },
    }
    info = extract_genai_span_info(span_data, "AnthropicTelemetry")
    schema = json.loads(info["otel_schema_url"])
    assert info[schema["gen_ai.tool.name"]] == "bash"
    assert info[schema["gen_ai.tool.call.id"]] == "call_99"
    assert info[schema["gen_ai.tool.type"]] == "function"


def test_is_anthropic_span_rejects_openai_spans():
    class FakeScope:
        def __init__(self, name):
            self.name = name

    class FakeSpan:
        def __init__(self, scope_name, attrs):
            self.instrumentation_scope = FakeScope(scope_name)
            self.attributes = attrs

    assert not _is_anthropic_span(
        FakeSpan(
            "openinference.instrumentation.openai",
            {"gen_ai.operation.name": "chat", "gen_ai.request.model": "gpt-4o"},
        )
    )
    assert not _is_anthropic_span(
        FakeSpan(
            "custom.tracer",
            {"gen_ai.operation.name": "chat", "gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o"},
        )
    )
    assert _is_anthropic_span(
        FakeSpan(
            "custom.tracer",
            {
                "gen_ai.operation.name": "chat",
                "gen_ai.system": "anthropic",
                "gen_ai.request.model": "claude-sonnet-4-6",
            },
        )
    )


def test_claude_code_incremental_cost_and_timestamp_fallback():
    record = {
        "type": "assistant",
        "uuid": "a-inc",
        "sessionId": "sess-1",
        "message": {
            "id": "msg_1",
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": "Hello"}],
            "usage": {"input_tokens": 100_000, "output_tokens": 10_000},
        },
    }
    inc = {"input": 1000, "output": 500, "cache_read": 0, "cache_creation": 0, "total": 1500}
    mapped = transform_record(record, inc, {"last_timestamp": "2024-06-01T00:00:00Z"})
    # Incremental cost should be for 1000 in + 500 out ($0.0105), not 100k in + 10k out ($0.45)
    assert abs(mapped["incremental_cost"] - 0.0105) < 1e-6
    assert mapped["cost_estimate"] > 0.4
    assert mapped["user_timestamp"] == 1717200000000


def test_codex_pricing_matches_mini_models():
    cost_4o = codex_calculate_cost("gpt-4o", input_tokens=1_000_000, output_tokens=0)
    cost_4o_mini = codex_calculate_cost("gpt-4o-mini", input_tokens=1_000_000, output_tokens=0)
    assert cost_4o == 2.5
    assert cost_4o_mini == 0.15

    cost_o1 = codex_calculate_cost("o1", input_tokens=1_000_000, output_tokens=0)
    cost_o1_mini = codex_calculate_cost("o1-mini", input_tokens=1_000_000, output_tokens=0)
    assert cost_o1 == 15.0
    assert cost_o1_mini == 1.1

    cost_o3 = codex_calculate_cost("o3", input_tokens=1_000_000, output_tokens=0)
    cost_o3_mini = codex_calculate_cost("o3-mini", input_tokens=1_000_000, output_tokens=0)
    assert cost_o3 == 15.0
    assert cost_o3_mini == 1.1


def test_antigravity_error_serialization_and_tool_pairing():
    records = [
        {"step_index": 1, "type": "USER_INPUT", "created_at": "2026-09-21T19:57:00Z", "content": "Run check"},
        {
            "step_index": 2,
            "type": "PLANNER_RESPONSE",
            "created_at": "2026-09-21T19:57:01Z",
            "content": "Checking",
            "tool_calls": [{"name": "run_command", "args": {"CommandLine": "pytest"}}],
        },
        {"step_index": 3, "type": "SYSTEM", "created_at": "2026-09-21T19:57:02Z", "content": "checkpoint"},
        {
            "step_index": 4,
            "type": "TOOL_RESULT",
            "created_at": "2026-09-21T19:57:05Z",
            "status": "DONE",
            "content": "Created At: 2026-09-21T19:57:01Z\nCompleted At: 2026-09-21T19:57:05Z\n0 errors found",
        },
    ]
    turn = build_turn(records)
    assert len(turn["tool_steps"]) == 1
    assert turn["tool_steps"][0]["duration_ms"] == 4000

    details = extract_tool_details(turn["tool_steps"])
    assert details["tool_errors"] == []

    mapped = transform_antigravity_turn(
        turn,
        session_id="s1",
        turn_id="s1_0",
        hook_metadata={"error": {"code": 500, "message": "boom"}},
    )
    assert json.loads(mapped["error_obj"]) == {"code": 500, "message": "boom"}
