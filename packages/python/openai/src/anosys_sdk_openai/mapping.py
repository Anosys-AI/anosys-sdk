"""
Key mapping configuration for OpenAI spans.

Extends the core mapping with OpenAI-specific field mappings.
"""

from anosys_sdk_core.models import BASE_KEY_MAPPING, DEFAULT_STARTING_INDICES

# OpenAI-specific key mapping (extends core)
OPENAI_KEY_MAPPING = BASE_KEY_MAPPING.copy()

# OpenAI starting indices (copy to avoid mutation)
OPENAI_STARTING_INDICES = DEFAULT_STARTING_INDICES.copy()
