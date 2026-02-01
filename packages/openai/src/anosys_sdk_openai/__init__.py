"""
AnoSys SDK for OpenAI - Automatic instrumentation for OpenAI API calls.

This package provides automatic tracing and logging of OpenAI API calls
using OpenTelemetry instrumentation.
"""

from anosys_sdk_openai.instrumentor import AnosysOpenAILogger, setup_tracing

# Re-export core decorators for convenience
from anosys_sdk_core import anosys_logger, anosys_raw_logger, setup_api

__version__ = "1.0.0"

__all__ = [
    "AnosysOpenAILogger",
    "setup_tracing",
    # Re-exports from core
    "anosys_logger",
    "anosys_raw_logger",
    "setup_api",
]
