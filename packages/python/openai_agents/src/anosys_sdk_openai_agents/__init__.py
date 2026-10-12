"""
AnoSys SDK for OpenAI Agents - Automatic instrumentation for OpenAI Agents SDK.

This package provides automatic tracing and logging of OpenAI Agents
using the TracingProcessor interface.
"""

from anosys_sdk_openai_agents.processor import AnosysOpenAIAgentsLogger, setup_tracing

# Re-export core decorators and encryption for convenience
from anosys_sdk_core import (
    anosys_logger,
    anosys_raw_logger,
    setup_api,
    setup_decorator,
    encrypt_payload,
    get_encryption_key,
    get_target_columns,
    derive_256_bit_key,
    decrypt,
    ANOSYS_ENCRYPTION_PREFIX,
    DEFAULT_ENCRYPTED_COLUMNS,
)

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("anosys-sdk-openai-agents")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "AnosysOpenAIAgentsLogger",
    "setup_tracing",
    # Re-exports from core
    "anosys_logger",
    "anosys_raw_logger",
    "setup_api",
    "setup_decorator",
    "encrypt_payload",
    "get_encryption_key",
    "get_target_columns",
    "derive_256_bit_key",
    "decrypt",
    "ANOSYS_ENCRYPTION_PREFIX",
    "DEFAULT_ENCRYPTED_COLUMNS",
]
