"""
AnoSys OpenAI Codex CLI integration — observability hook for Codex sessions.
"""

try:
    from importlib.metadata import PackageNotFoundError, version
except ImportError:
    from importlib_metadata import PackageNotFoundError, version

from anosys_sdk_codex.installer import update_codex_config, update_codex_env
from anosys_sdk_codex.mapper import transform_codex_turn

try:
    __version__ = version("anosys-codex")
except PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = ["transform_codex_turn", "update_codex_config", "update_codex_env"]
