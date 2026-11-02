"""
Constants for Google Antigravity AnoSys SDK.
"""

from __future__ import annotations

from pathlib import Path

INTEGRATION_VERSION = "0.1.0"
HARNESS_NAME = "antigravity"
HOOK_NAME = "anosys-tracing"
HOOK_COMMAND = "anosys-antigravity run"

GLOBAL_CONFIG_DIR = Path.home() / ".gemini" / "config"
GLOBAL_HOOKS_FILE = GLOBAL_CONFIG_DIR / "hooks.json"
GLOBAL_ENV_FILE = GLOBAL_CONFIG_DIR / "anosys-env.json"

DEFAULT_INGESTION_URL = "https://api.anosys.ai/ingestion"
HOOK_TIMEOUT_SECONDS = 30

EVENTS = ["PreInvocation", "Stop"]
