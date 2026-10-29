"""
AnoSys SDK for Claude Agents - Automatic tracing for the Claude Agent SDK.

This package traces every agent run (agent, tool and subagent spans) of the
Claude Agent SDK and sends them to AnoSys.
"""

from anosys_sdk_claude_agents.instrumentor import (
    AnosysClaudeAgentsLogger,
    setup_tracing,
    trace_messages,
    uninstrument,
    wrap_query,
)

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
    encrypt,
    decrypt,
    ANOSYS_ENCRYPTION_PREFIX,
    DEFAULT_ENCRYPTED_COLUMNS,
)

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("anosys-sdk-claude-agents")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "AnosysClaudeAgentsLogger",
    "setup_tracing",
    "trace_messages",
    "uninstrument",
    "wrap_query",
    # Re-exports from core
    "anosys_logger",
    "anosys_raw_logger",
    "setup_api",
    "setup_decorator",
    "encrypt_payload",
    "get_encryption_key",
    "get_target_columns",
    "derive_256_bit_key",
    "encrypt",
    "decrypt",
    "ANOSYS_ENCRYPTION_PREFIX",
    "DEFAULT_ENCRYPTED_COLUMNS",
]
