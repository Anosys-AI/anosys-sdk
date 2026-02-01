"""
Tests for anosys-sdk-openai package.
"""


def test_hooks_imports():
    """Test that hooks module can be imported."""
    from anosys_sdk_openai.hooks import (
        extract_span_info,
        deserialize_attributes,
    )
    assert callable(extract_span_info)
    assert callable(deserialize_attributes)


def test_mapping_imports():
    """Test that mapping module can be imported."""
    from anosys_sdk_openai.mapping import OPENAI_KEY_MAPPING, OPENAI_STARTING_INDICES
    assert isinstance(OPENAI_KEY_MAPPING, dict)
    assert isinstance(OPENAI_STARTING_INDICES, dict)


def test_streaming_imports():
    """Test that streaming module can be imported."""
    from anosys_sdk_openai.streaming import StreamingAggregator, aggregate_stream
    assert callable(StreamingAggregator)
    assert callable(aggregate_stream)


def test_instrumentor_imports():
    """Test that instrumentor module can be imported."""
    from anosys_sdk_openai.instrumentor import AnosysOpenAILogger
    assert callable(AnosysOpenAILogger)


def test_streaming_aggregator():
    """Test StreamingAggregator basic functionality."""
    from anosys_sdk_openai.streaming import StreamingAggregator
    
    aggregator = StreamingAggregator()
    assert aggregator.get_content() == ""
    assert aggregator.get_chunks() == []

