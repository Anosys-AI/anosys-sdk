"""
AnoSys SDK Core - Shared utilities for AnoSys integrations.

This package provides core functionality shared across all AnoSys SDK packages:
- Configuration and API key management
- HTTP client for Anosys API
- Function decorators for logging
- Data transformation utilities
"""

from anosys_sdk_core.config import get_api_url, get_env_bool, resolve_api_key
from anosys_sdk_core.client import AnosysClient
from anosys_sdk_core.decorators import anosys_logger, anosys_raw_logger, setup_api
from anosys_sdk_core.context import get_user_context, set_user_context
from anosys_sdk_core.models import BASE_KEY_MAPPING

__version__ = "1.0.0"

__all__ = [
    # Config
    "get_api_url",
    "get_env_bool",
    "resolve_api_key",
    # Client
    "AnosysClient",
    # Decorators
    "anosys_logger",
    "anosys_raw_logger",
    "setup_api",
    # Context
    "get_user_context",
    "set_user_context",
    # Models
    "BASE_KEY_MAPPING",
]
