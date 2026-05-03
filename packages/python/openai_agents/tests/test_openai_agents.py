"""
Tests for anosys-sdk-openai-agents package.
"""


def test_mapping_imports():
    """Test that mapping module can be imported."""
    from anosys_sdk_openai_agents.mapping import (
        AGENTS_KEY_MAPPING,
        AGENTS_STARTING_INDICES,
        span2json,
        deserialize_attributes,
    )
    assert isinstance(AGENTS_KEY_MAPPING, dict)
    assert isinstance(AGENTS_STARTING_INDICES, dict)
    assert callable(span2json)
    assert callable(deserialize_attributes)


def test_processor_imports():
    """Test that processor module can be imported."""
    from anosys_sdk_openai_agents.processor import AnosysOpenAIAgentsLogger
    assert callable(AnosysOpenAIAgentsLogger)


def test_span2json_basic():
    """Test span2json with minimal input."""
    from anosys_sdk_openai_agents.mapping import span2json
    
    span = {
        "data": {
            "id": "test-span-id",
            "trace_id": "test-trace-id",
            "span_data": {
                "type": "agent",
                "name": "TestAgent",
            }
        },
        "timestamp": "2024-01-01T00:00:00Z",
        "user_context": {}
    }
    
    result = span2json(span)
    assert isinstance(result, dict)
    assert result.get("otel_span_id") == "test-span-id"
