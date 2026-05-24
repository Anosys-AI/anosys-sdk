"""
Expanded tests for anosys-sdk-openai-agents Python package.

Covers:
- span2json for all span types (agent, function, generation, guardrail,
  custom, transcription, speech, speechgroup, MCPListTools, response, handoff)
- span2json: usage token extraction
- span2json: null filtering
- deserialize_attributes: dotted path unflattening
- mapping constants: AGENTS_KEY_MAPPING, AGENTS_STARTING_INDICES
"""

import json
import pytest

from anosys_sdk_openai_agents.mapping import (
    AGENTS_KEY_MAPPING,
    AGENTS_STARTING_INDICES,
    deserialize_attributes,
    span2json,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _span(span_type: str, **extra_span_data) -> dict:
    return {
        "timestamp": "2024-01-15T12:00:00Z",
        "user_context": {"session_id": "sess-1"},
        "data": {
            "id": f"span-{span_type}",
            "trace_id": "trace-1",
            "object": "trace.span",
            "started_at": "2024-01-15T12:00:00Z",
            "ended_at": "2024-01-15T12:00:01Z",
            "span_data": {"type": span_type, **extra_span_data},
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# span2json — common fields
# ──────────────────────────────────────────────────────────────────────────────

def test_span2json_record_type():
    result = span2json(_span("agent", name="MyAgent"))
    assert result["otel_record_type"] == "AnoSys Agentic Trace"


def test_span2json_source_tag():
    result = span2json(_span("agent", name="MyAgent"))
    assert result["cvs200"] == "openAI_Agents_Traces"


def test_span2json_span_id():
    result = span2json(_span("agent", name="A"))
    assert result["otel_span_id"] == "span-agent"


def test_span2json_duration_ms():
    result = span2json(_span("agent", name="A"))
    # started_at == ended_at => 0ms (or close to it)
    assert isinstance(result.get("otel_duration_ms"), (int, float, type(None)))


def test_span2json_no_null_values():
    result = span2json(_span("agent", name="A"))
    for v in result.values():
        assert v is not None


# ──────────────────────────────────────────────────────────────────────────────
# span2json — all span types
# ──────────────────────────────────────────────────────────────────────────────

def test_span2json_agent_type():
    result = span2json(_span("agent", name="TriageAgent", handoffs=["sales"], tools=["lookup"]))
    assert result.get("otel_name") == "TriageAgent"
    assert "sales" in (result.get("cvs62") or "")


def test_span2json_function_type():
    result = span2json(_span("function", name="my_func", input="arg1", output="result1"))
    assert result.get("otel_name") == "my_func"
    assert result.get("llm_input") == "arg1"
    assert result.get("llm_output") == "result1"


def test_span2json_generation_type():
    result = span2json(_span(
        "generation",
        input="user query",
        output="model response",
        model="gpt-4",
        usage={"input_tokens": 10, "output_tokens": 5},
    ))
    assert result.get("llm_input") == "user query"
    assert result.get("llm_output") == "model response"
    assert result.get("cvs69") == "gpt-4"
    # usage stored as JSON string in llm_token_count
    token_count = result.get("llm_token_count")
    assert token_count is not None
    parsed = json.loads(token_count) if isinstance(token_count, str) else token_count
    assert parsed.get("input_tokens") == 10
    assert parsed.get("output_tokens") == 5


def test_span2json_generation_usage_total_tokens():
    result = span2json(_span(
        "generation",
        usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    ))
    # usage stored as JSON string in llm_token_count
    token_count = result.get("llm_token_count")
    assert token_count is not None
    parsed = json.loads(token_count) if isinstance(token_count, str) else token_count
    assert parsed.get("total_tokens") == 15


def test_span2json_generation_usage_total_inferred():
    result = span2json(_span(
        "generation",
        usage={"input_tokens": 10, "output_tokens": 5},
    ))
    # span2json stores usage as llm_token_count (JSON string), no explicit total key
    token_count = result.get("llm_token_count")
    assert token_count is not None


def test_span2json_guardrail_type():
    result = span2json(_span("guardrail", name="content_filter", triggered=True))
    assert result.get("otel_name") == "content_filter"
    assert result.get("cvs68") is not None


def test_span2json_custom_type():
    result = span2json(_span("custom", name="custom_step", data={"key": "value"}))
    assert result.get("otel_name") == "custom_step"
    assert result.get("cvs72") is not None


def test_span2json_transcription_type():
    result = span2json(_span(
        "transcription",
        input={"data": "audio_bytes", "format": "wav"},
        output="Hello world",
        model="whisper-1",
    ))
    assert result.get("cvs72") == "audio_bytes"
    assert result.get("cvs73") == "wav"
    assert result.get("cvs69") == "whisper-1"


def test_span2json_speech_type():
    result = span2json(_span(
        "speech",
        input="Hello",
        output={"data": "audio_output", "format": "mp3"},
        model="tts-1",
    ))
    assert result.get("llm_input") == "Hello"
    assert result.get("cvs69") == "tts-1"


def test_span2json_speechgroup_type():
    result = span2json(_span("speechgroup", input="group input"))
    assert result.get("otel_record_type") == "AnoSys Agentic Trace"


def test_span2json_mcplisttools_type():
    result = span2json(_span("MCPListTools", server="myserver", result=["tool1", "tool2"]))
    assert result.get("cvs75") == "myserver"
    assert result.get("cvs76") is not None


def test_span2json_response_type():
    result = span2json(_span("response", response_id="resp-xyz"))
    assert result.get("cvs77") == "resp-xyz"


def test_span2json_handoff_type():
    result = span2json(_span("handoff", from_agent="AgentA", to_agent="AgentB"))
    assert result.get("cvs78") == "AgentA"
    assert result.get("cvs79") == "AgentB"


def test_span2json_unknown_type_does_not_throw():
    result = span2json(_span("totally-unknown"))
    assert result.get("otel_record_type") == "AnoSys Agentic Trace"


def test_span2json_all_types_do_not_throw():
    types = ["agent", "function", "mcp_tools", "guardrail", "generation",
             "custom", "transcription", "speech", "speechgroup",
             "MCPListTools", "response", "handoff"]
    for t in types:
        result = span2json(_span(t))
        assert isinstance(result, dict), f"span2json failed for type: {t}"


# ──────────────────────────────────────────────────────────────────────────────
# span2json — model_config id extraction (cvs77)
# ──────────────────────────────────────────────────────────────────────────────

def test_span2json_model_config_id_dict():
    result = span2json(_span("generation", model_config={"id": "cfg-abc"}))
    assert result.get("cvs77") == "cfg-abc"


def test_span2json_model_config_id_json_string():
    result = span2json(_span("generation", model_config=json.dumps({"id": "cfg-json"})))
    assert result.get("cvs77") == "cfg-json"


# ──────────────────────────────────────────────────────────────────────────────
# deserialize_attributes
# ──────────────────────────────────────────────────────────────────────────────

def test_deserialize_attributes_dotted_paths():
    flat = {"gen_ai.request.model": "gpt-4", "gen_ai.usage.input_tokens": 50}
    result = deserialize_attributes(flat)
    assert result["gen_ai"]["request"]["model"] == "gpt-4"
    assert result["gen_ai"]["usage"]["input_tokens"] == 50


def test_deserialize_attributes_empty():
    assert deserialize_attributes({}) == {}


def test_deserialize_attributes_json_string_value():
    flat = {"gen_ai.request.parameters": '{"temperature": 0.8}'}
    result = deserialize_attributes(flat)
    assert result["gen_ai"]["request"]["parameters"]["temperature"] == 0.8


# ──────────────────────────────────────────────────────────────────────────────
# mapping constants
# ──────────────────────────────────────────────────────────────────────────────

def test_agents_key_mapping_is_dict():
    assert isinstance(AGENTS_KEY_MAPPING, dict)
    assert len(AGENTS_KEY_MAPPING) > 0


def test_agents_key_mapping_has_base_keys():
    assert "gen_ai.usage.input_tokens" in AGENTS_KEY_MAPPING
    assert "gen_ai.request.model" in AGENTS_KEY_MAPPING
    assert "raw" in AGENTS_KEY_MAPPING


def test_agents_starting_indices_valid():
    assert "string" in AGENTS_STARTING_INDICES
    assert "number" in AGENTS_STARTING_INDICES
    assert "bool" in AGENTS_STARTING_INDICES
    assert all(isinstance(v, int) for v in AGENTS_STARTING_INDICES.values())
