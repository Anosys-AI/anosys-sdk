"""
Span extraction hooks for AnoSys Anthropic SDK.

The Anthropic SDK emits OpenTelemetry GenAI semantic-convention spans natively,
so extraction is the shared GenAI extractor from the core package.
"""

from typing import Any, Dict

from anosys_sdk_core.genai import extract_genai_span_info, flatten_messages
from anosys_sdk_anthropic.mapping import (
    ANTHROPIC_KEY_MAPPING,
    ANTHROPIC_SOURCE,
    ANTHROPIC_STARTING_INDICES,
)

__all__ = ["extract_span_info", "flatten_messages"]


def extract_span_info(span: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and transform Anthropic span information into AnoSys format.

    Args:
        span: Span dictionary from to_json()

    Returns:
        Transformed dictionary ready for AnoSys API
    """
    return extract_genai_span_info(
        span,
        from_source=ANTHROPIC_SOURCE,
        provider="anthropic",
        key_mapping=ANTHROPIC_KEY_MAPPING,
        starting_indices=ANTHROPIC_STARTING_INDICES,
    )
