"""
Key mapping configuration for Claude Agent SDK spans.

Uses the shared Claude mapping from the core package, so agent and tool spans
land in the same columns as Anthropic client SDK spans.
"""

from anosys_sdk_core.models import CLAUDE_KEY_MAPPING, CLAUDE_STARTING_INDICES

# Claude Agents key mapping (extends core)
CLAUDE_AGENTS_KEY_MAPPING = CLAUDE_KEY_MAPPING.copy()

# Claude Agents starting indices (copy to avoid mutation)
CLAUDE_AGENTS_STARTING_INDICES = CLAUDE_STARTING_INDICES.copy()

# Source tag stored in cvs200
CLAUDE_AGENTS_SOURCE = "ClaudeAgentsTelemetry"

# OpenTelemetry instrumentation scope of the spans this package creates
CLAUDE_AGENTS_SCOPE = "anosys.claude_agents"
