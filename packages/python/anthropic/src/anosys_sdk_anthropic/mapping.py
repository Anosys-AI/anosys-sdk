"""
Key mapping configuration for Anthropic spans.

Uses the shared Claude mapping from the core package (the base mapping plus
the fixed Claude slots for cache tokens, cost and thinking).
"""

from anosys_sdk_core.models import CLAUDE_KEY_MAPPING, CLAUDE_STARTING_INDICES

# Anthropic-specific key mapping (extends core)
ANTHROPIC_KEY_MAPPING = CLAUDE_KEY_MAPPING.copy()

# Anthropic starting indices (copy to avoid mutation)
ANTHROPIC_STARTING_INDICES = CLAUDE_STARTING_INDICES.copy()

# Source tag stored in cvs200
ANTHROPIC_SOURCE = "AnthropicTelemetry"

# OpenTelemetry instrumentation scope of the Anthropic SDK's own spans
ANTHROPIC_SCOPE_PREFIX = "com.anthropic"

# Scope of the spans exported by anosys-sdk-claude-agents (never exported twice)
CLAUDE_AGENTS_SCOPE = "anosys.claude_agents"
