"""
Span extraction hooks for AnoSys Claude Agents SDK.

Agent, tool and chat spans follow the OpenTelemetry GenAI semantic
conventions, so extraction is the shared GenAI extractor from the core package.
"""

from typing import Any, Dict

from anosys_sdk_core.genai import extract_genai_span_info, flatten_messages
from anosys_sdk_claude_agents.mapping import (
    CLAUDE_AGENTS_KEY_MAPPING,
    CLAUDE_AGENTS_SOURCE,
    CLAUDE_AGENTS_STARTING_INDICES,
)

__all__ = ["extract_span_info", "flatten_messages"]


def extract_span_info(span: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and transform a Claude Agent SDK span into AnoSys format.

    Args:
        span: Span dictionary from to_json()

    Returns:
        Transformed dictionary ready for AnoSys API
    """
    return extract_genai_span_info(
        span,
        from_source=CLAUDE_AGENTS_SOURCE,
        provider="anthropic",
        key_mapping=CLAUDE_AGENTS_KEY_MAPPING,
        starting_indices=CLAUDE_AGENTS_STARTING_INDICES,
    )
