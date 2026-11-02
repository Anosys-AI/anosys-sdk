"""
anosys-antigravity — AnoSys observability hook for Google Antigravity.
"""

from anosys_sdk_antigravity.constants import INTEGRATION_VERSION
from anosys_sdk_antigravity.mapper import transform_antigravity_turn
from anosys_sdk_antigravity.transcript import parse_transcript

__version__ = INTEGRATION_VERSION
__all__ = [
    "INTEGRATION_VERSION",
    "transform_antigravity_turn",
    "parse_transcript",
]
