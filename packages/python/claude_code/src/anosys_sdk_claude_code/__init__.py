"""
AnoSys Claude Code integration — observability hook for Claude Code sessions.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version
from anosys_sdk_claude_code.installer import update_env, update_stop_hooks
from anosys_sdk_claude_code.mapper import transform_record


try:
    __version__ = version("anosys-claude-code")
except PackageNotFoundError:
    __version__ = "0.0.0"
__all__ = ["transform_record", "update_env", "update_stop_hooks"]
