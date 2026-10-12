"""
AnoSys Claude Code integration — observability hook for Claude Code sessions.
"""

try:
    from importlib.metadata import PackageNotFoundError, version
except ImportError:
    # Fallback to the backport library for Python < 3.8
    from importlib_metadata import PackageNotFoundError, version

from anosys_sdk_claude_code.installer import update_env, update_stop_hooks
from anosys_sdk_claude_code.mapper import transform_record
from anosys_sdk_claude_code.encryption import (
    ANOSYS_ENCRYPTION_PREFIX,
    DEFAULT_ENCRYPTED_COLUMNS,
    derive_256_bit_key,
    encrypt,
    decrypt,
    get_encryption_key,
    get_target_columns,
    encrypt_payload,
)

try:
    __version__ = version("anosys-claude-code")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "transform_record",
    "update_env",
    "update_stop_hooks",
    "ANOSYS_ENCRYPTION_PREFIX",
    "DEFAULT_ENCRYPTED_COLUMNS",
    "derive_256_bit_key",
    "encrypt",
    "decrypt",
    "get_encryption_key",
    "get_target_columns",
    "encrypt_payload",
]
