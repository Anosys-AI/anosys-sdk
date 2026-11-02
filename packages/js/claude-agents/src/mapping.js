import { CLAUDE_KEY_MAPPING, CLAUDE_STARTING_INDICES } from 'anosys-sdk-anthropic';

// Claude Agents key mapping — the shared Claude mapping, so agent and tool spans
// land in the same columns as Anthropic client SDK spans (aligned with Python).
export const CLAUDE_AGENTS_KEY_MAPPING = { ...CLAUDE_KEY_MAPPING };
export const CLAUDE_AGENTS_STARTING_INDICES = { ...CLAUDE_STARTING_INDICES };

// Source tag stored in cvs200
export const CLAUDE_AGENTS_SOURCE = 'ClaudeAgentsTelemetry';

// OpenTelemetry instrumentation scope of the spans this package creates
export const CLAUDE_AGENTS_SCOPE = 'anosys.claude_agents';
