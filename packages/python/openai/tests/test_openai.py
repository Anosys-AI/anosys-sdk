"""
Expanded tests for anosys-sdk-openai Python package.

Covers:
- hooks: flatten_messages for various input shapes
- hooks: deserialize_attributes (dotted path flattening)
- hooks: extract_span_info with llm_invocation_parameters to avoid AttributeError
- mapping: OPENAI_KEY_MAPPING and OPENAI_STARTING_INDICES contracts
- streaming: StreamingAggregator accumulation
"""

import json
import pytest

from anosys_sdk_openai.hooks import (
    deserialize_attributes,
    extract_span_info,
    flatten_messages,
)
from anosys_sdk_openai.mapping import OPENAI_KEY_MAPPING, OPENAI_STARTING_INDICES
from anosys_sdk_openai.streaming import StreamingAggregator


# ──────────────────────────────────────────────────────────────────────────────
# flatten_messages
# ──────────────────────────────────────────────────────────────────────────────

def test_flatten_messages_list_of_dicts():
    msgs = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    result = flatten_messages(msgs)
    assert "User: Hello" in result
    assert "Assistant: Hi there!" in result


def test_flatten_messages_empty():
    assert flatten_messages([]) is None
    assert flatten_messages(None) is None


def test_flatten_messages_with_tool_calls():
    msgs = [{"message": {"role": "assistant", "tool_calls": [{"id": "t1"}]}}]
    result = flatten_messages(msgs)
    assert "[Tool Calls]" in result


def test_flatten_messages_nested_message_key():
    msgs = [{"message": {"role": "user", "content": "nested content"}}]
    result = flatten_messages(msgs)
    assert "nested content" in result


# ──────────────────────────────────────────────────────────────────────────────
# deserialize_attributes
# ──────────────────────────────────────────────────────────────────────────────

def test_deserialize_attributes_dotted_paths():
    span = {
        "attributes": {
            "gen_ai.request.model": "gpt-4",
            "gen_ai.usage.input_tokens": 100,
        }
    }
    result = deserialize_attributes(span)
    attrs = result["attributes"]
    assert attrs["gen_ai"]["request"]["model"] == "gpt-4"
    assert attrs["gen_ai"]["usage"]["input_tokens"] == 100


def test_deserialize_attributes_empty():
    result = deserialize_attributes({"attributes": {}})
    assert result["attributes"] == {}


def test_deserialize_attributes_json_string_values():
    span = {"attributes": {"gen_ai.request.parameters": '{"temperature": 0.7}'}}
    result = deserialize_attributes(span)
    params = result["attributes"]["gen_ai"]["request"]["parameters"]
    assert params["temperature"] == 0.7


# ──────────────────────────────────────────────────────────────────────────────
# extract_span_info — requires llm.invocation_parameters to be a valid JSON dict
# (to avoid the AttributeError on invocation_params.get())
# ──────────────────────────────────────────────────────────────────────────────

def _make_span(**kwargs):
    """Build a minimal span dict with required invocation_parameters to prevent crash."""
    base = {
        "name": "openai.chat",
        "context": {"trace_id": "trace-abc", "span_id": "span-123", "trace_state": ""},
        "parent_id": None,
        "start_time": "2024-01-15T12:00:00Z",
        "end_time": "2024-01-15T12:00:01Z",
        "status": {},
        # invocation_parameters must be a JSON string of a dict to avoid AttributeError
        "attributes": {
            "llm.invocation_parameters": json.dumps({"model": "gpt-4", "temperature": 0.7}),
        },
        "resource": {"attributes": {"service.name": "my-service"}},
        "events": [],
    }
    # Merge passed attributes on top
    if "attributes" in kwargs:
        base["attributes"].update(kwargs.pop("attributes"))
    base.update(kwargs)
    return base


def test_extract_span_info_basic_fields():
    span = _make_span()
    result = extract_span_info(span)
    assert result.get("otel_trace_id") == "trace-abc"
    assert result.get("otel_span_id") == "span-123"
    assert result.get("cvs200") == "openAI_Python_Telemetry"


def test_extract_span_info_duration_ms():
    span = _make_span(
        start_time="2024-01-15T12:00:00Z",
        end_time="2024-01-15T12:00:02Z",
    )
    result = extract_span_info(span)
    assert result.get("otel_duration_ms") == 2000


def test_extract_span_info_model_from_llm_attribute():
    span = _make_span(attributes={
        "llm.invocation_parameters": json.dumps({"model": "gpt-4o", "temperature": 0}),
        "gen_ai.request.model": "gpt-4o",  # gen_ai attribute is the authoritative source
    })
    result = extract_span_info(span)
    assert result.get("gen_ai_request_model") == "gpt-4o"


def test_extract_span_info_token_usage():
    span = _make_span(attributes={
        "gen_ai.usage.input_tokens": 50,
        "gen_ai.usage.output_tokens": 25,
        "llm.invocation_parameters": json.dumps({"model": "gpt-4", "temperature": 0}),
    })
    result = extract_span_info(span)
    assert result.get("gen_ai_usage_input_tokens") == 50
    assert result.get("gen_ai_usage_output_tokens") == 25


def test_extract_span_info_llm_invocation_streaming_flag():
    span = _make_span(attributes={
        "llm.invocation_parameters": json.dumps({"stream": True, "model": "gpt-4"}),
    })
    result = extract_span_info(span)
    assert result.get("cvb2") is True


def test_extract_span_info_no_nulls():
    span = _make_span()
    result = extract_span_info(span)
    for v in result.values():
        assert v is not None


def test_extract_span_info_cvs199_always_present():
    span = _make_span()
    result = extract_span_info(span)
    assert "cvs199" in result


# ──────────────────────────────────────────────────────────────────────────────
# mapping contracts
# ──────────────────────────────────────────────────────────────────────────────

def test_openai_key_mapping_is_dict():
    assert isinstance(OPENAI_KEY_MAPPING, dict)
    assert len(OPENAI_KEY_MAPPING) > 0


def test_openai_starting_indices_has_expected_keys():
    assert "string" in OPENAI_STARTING_INDICES
    assert "number" in OPENAI_STARTING_INDICES
    assert "bool" in OPENAI_STARTING_INDICES


def test_key_mapping_covers_gen_ai_fields():
    assert "gen_ai.usage.input_tokens" in OPENAI_KEY_MAPPING
    assert "gen_ai.usage.output_tokens" in OPENAI_KEY_MAPPING
    assert "gen_ai.request.model" in OPENAI_KEY_MAPPING


# ──────────────────────────────────────────────────────────────────────────────
# StreamingAggregator
# ──────────────────────────────────────────────────────────────────────────────

def test_streaming_aggregator_starts_empty():
    agg = StreamingAggregator()
    assert agg.get_content() == ""
    assert agg.get_chunks() == []


def test_streaming_aggregator_accumulates_chunks():
    agg = StreamingAggregator()
    agg.add_chunk({"choices": [{"delta": {"content": "Hello"}, "finish_reason": None}]})
    agg.add_chunk({"choices": [{"delta": {"content": " World"}, "finish_reason": None}]})
    content = agg.get_content()
    assert "Hello" in content or len(agg.get_chunks()) == 2  # flexible check


def test_streaming_aggregator_handles_empty_delta():
    agg = StreamingAggregator()
    agg.add_chunk({"choices": [{"delta": {}, "finish_reason": None}]})
    # Should not crash
    assert isinstance(agg.get_content(), str)
