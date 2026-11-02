"""
Tests for the OpenTelemetry GenAI span extractor (anosys_sdk_core.genai).

Covers:
- base fields (ids, timing, status) and the Claude extension slots
- usage normalisation (cache tokens, totals, llm_token_count)
- content flattening (parts-based messages, reasoning, tool calls)
- tool spans (arguments in, result out)
"""

import json

from anosys_sdk_core.genai import extract_genai_span_info, flatten_messages
from anosys_sdk_core.models import BASE_KEY_MAPPING, CLAUDE_KEY_MAPPING, CLAUDE_STARTING_INDICES


def _span(attributes, name="anthropic.messages.create", status="OK"):
    return {
        "name": name,
        "context": {"trace_id": "0xabc", "span_id": "0xdef", "trace_state": "[]"},
        "kind": "SpanKind.CLIENT",
        "parent_id": None,
        "start_time": "2026-10-29T10:00:00.000000Z",
        "end_time": "2026-10-29T10:00:01.500000Z",
        "status": {"status_code": status},
        "attributes": attributes,
        "events": [],
        "links": [],
        "resource": {"attributes": {"service.name": "svc"}, "schema_url": ""},
    }


CHAT_ATTRS = {
    "gen_ai.provider.name": "anthropic",
    "gen_ai.operation.name": "chat",
    "gen_ai.request.model": "claude-sonnet-4-5",
    "gen_ai.request.max_tokens": 100,
    "gen_ai.request.stop_sequences": ["END"],
    "gen_ai.response.id": "msg_1",
    "gen_ai.response.model": "claude-sonnet-4-5",
    "anthropic.message.stop_reason": "end_turn",
    "gen_ai.usage.input_tokens": 132,
    "gen_ai.usage.output_tokens": 7,
    "gen_ai.usage.cache_read.input_tokens": 100,
    "gen_ai.usage.cache_write.input_tokens": 20,
    "gen_ai.system_instructions": json.dumps([{"type": "text", "content": "Be terse."}]),
    "gen_ai.input.messages": json.dumps([{"role": "user", "parts": [{"type": "text", "content": "Hi"}]}]),
    "gen_ai.output.messages": json.dumps([{"role": "assistant", "parts": [
        {"type": "reasoning", "content": "hmm"},
        {"type": "text", "content": "Hello!"},
    ]}]),
}


def test_claude_mapping_extends_base_without_changing_it():
    for key, column in BASE_KEY_MAPPING.items():
        assert CLAUDE_KEY_MAPPING[key] == column
    assert CLAUDE_KEY_MAPPING["gen_ai.usage.cache_read.input_tokens"] == "cvn4"
    assert CLAUDE_KEY_MAPPING["gen_ai.usage.cache_creation.input_tokens"] == "cvn5"
    assert CLAUDE_KEY_MAPPING["gen_ai.usage.cost"] == "cvn7"
    assert CLAUDE_KEY_MAPPING["has_thinking"] == "cvb3"


def test_dynamic_slots_start_above_fixed_claude_slots():
    assert CLAUDE_STARTING_INDICES["number"] > 7
    assert CLAUDE_STARTING_INDICES["bool"] > 3


def test_chat_span_base_fields():
    out = extract_genai_span_info(_span(CHAT_ATTRS), from_source="AnthropicTelemetry")
    assert out["cvs200"] == "AnthropicTelemetry"
    assert out["otel_name"] == "anthropic.messages.create"
    assert out["otel_duration_ms"] == 1500
    assert out["otel_status_code"] == "OK"
    assert out["gen_ai_system"] == "anthropic"
    assert out["gen_ai_operation_name"] == "chat"
    assert out["cvs19"] == "LLM"
    assert out["gen_ai_request_model"] == "claude-sonnet-4-5"
    assert json.loads(out["gen_ai_response_finish_reasons"]) == ["end_turn"]
    assert out["otel_status_message"] == "msg_1"


def test_chat_span_usage_and_cache_slots():
    out = extract_genai_span_info(_span(CHAT_ATTRS), from_source="AnthropicTelemetry")
    assert out["gen_ai_usage_input_tokens"] == 132
    assert out["gen_ai_usage_output_tokens"] == 7
    assert out["gen_ai_usage_total_tokens"] == 139
    assert out["cvn4"] == 100
    assert out["cvn5"] == 20
    tokens = json.loads(out["llm_token_count"])
    assert tokens["cache_creation_input_tokens"] == 20


def test_chat_span_content_and_thinking():
    out = extract_genai_span_info(_span(CHAT_ATTRS), from_source="AnthropicTelemetry")
    assert out["llm_input"] == "System: Be terse.\n\nUser: Hi"
    assert out["llm_output"] == "Assistant: [Thinking] hmm\nHello!"
    assert out["llm_system"] == "Be terse."
    assert out["cvb3"] is True


def test_metadata_only_span_has_no_content():
    attrs = {k: v for k, v in CHAT_ATTRS.items() if "messages" not in k and "instructions" not in k}
    out = extract_genai_span_info(_span(attrs), from_source="AnthropicTelemetry")
    assert "llm_input" not in out
    assert "llm_output" not in out
    assert "cvb3" not in out


def test_tool_span_uses_arguments_and_result():
    attrs = {
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": "Bash",
        "gen_ai.tool.call.arguments": json.dumps({"command": "ls"}),
        "gen_ai.tool.call.result": "a.txt",
    }
    out = extract_genai_span_info(_span(attrs, name="execute_tool Bash"), from_source="ClaudeAgentsTelemetry")
    assert out["cvs19"] == "TOOL"
    assert json.loads(out["llm_input"]) == {"command": "ls"}
    assert out["llm_output"] == "a.txt"


def test_agent_span_sets_agent_fields_and_cost():
    attrs = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": "claude_agent",
        "gen_ai.conversation.id": "sess-1",
        "gen_ai.usage.cost": 0.0123,
    }
    out = extract_genai_span_info(_span(attrs, name="invoke_agent claude_agent"), from_source="ClaudeAgentsTelemetry")
    assert out["cvs19"] == "AGENT"
    assert out["cvb1"] is True
    assert out["gen_ai_conversation_id"] == "sess-1"
    assert out["cvn7"] == 0.0123


def test_error_status_is_named():
    out = extract_genai_span_info(_span({"error.type": "RateLimitError"}, status=2), from_source="x")
    assert out["otel_status_code"] == "ERROR"
    assert out["cvs10"] == "RateLimitError"


def test_flatten_messages_shapes():
    assert flatten_messages(None) is None
    assert flatten_messages([{"role": "user", "content": "Hello"}]) == "User: Hello"
    text = flatten_messages([{"role": "assistant", "parts": [
        {"type": "tool_call", "name": "get_weather", "arguments": {"city": "Paris"}},
    ]}])
    assert text == 'Assistant: [Tool Call: get_weather] {"city":"Paris"}'
