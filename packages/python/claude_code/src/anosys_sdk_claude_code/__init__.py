"""
AnoSys Claude Code integration — observability hook for Claude Code sessions.
"""

from anosys_sdk_claude_code.installer import update_env, update_stop_hooks
from anosys_sdk_claude_code.mapper import transform_record

__version__ = "0.2.1"
__all__ = ["transform_record", "update_env", "update_stop_hooks"]
