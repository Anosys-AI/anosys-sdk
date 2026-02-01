"""
AnoSys SDK for OpenAI Agents - Automatic instrumentation for OpenAI Agents SDK.

This package provides automatic tracing and logging of OpenAI Agents
using the TracingProcessor interface.
"""

from anosys_sdk_openai_agents.processor import AnosysOpenAIAgentsLogger, setup_tracing

# Re-export core decorators for convenience
from anosys_sdk_core import anosys_logger, anosys_raw_logger, setup_api

__version__ = "1.0.0"

__all__ = [
    "AnosysOpenAIAgentsLogger",
    "setup_tracing",
    # Re-exports from core
    "anosys_logger",
    "anosys_raw_logger",
    "setup_api",
]
