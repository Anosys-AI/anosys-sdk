import { extractGenAiSpanInfo, flattenMessages, spanToJson } from './genai.js';
import { ANTHROPIC_KEY_MAPPING, ANTHROPIC_STARTING_INDICES } from './mapping.js';

// Source tag stored in cvs200
export const ANTHROPIC_SOURCE = 'AnthropicTelemetry';

// OpenTelemetry instrumentation scope of the Anthropic SDK's own spans
export const ANTHROPIC_SCOPE_PREFIX = 'com.anthropic';

// Scope of the spans exported by anosys-sdk-claude-agents (never exported twice)
export const CLAUDE_AGENTS_SCOPE = 'anosys.claude_agents';

const NON_ANTHROPIC_SCOPE_PREFIXES = [
  'traceai_',
  'openinference.instrumentation.',
  'opentelemetry.instrumentation.openai',
  '@opentelemetry/instrumentation-openai',
  'openai',
];

/**
 * Spans the Anthropic exporter sends: the Anthropic SDK's own spans, plus GenAI
 * spans the application creates around them (agent loops, tool calls), which
 * carry `gen_ai.operation.name`. Other spans on a shared provider are skipped.
 */
export function isAnthropicSpan(scopeOrSpan, attributes = {}) {
  let name = '';
  let attrs = attributes ?? {};
  if (scopeOrSpan && typeof scopeOrSpan === 'object') {
    name = String(
      scopeOrSpan.instrumentationScope?.name ??
      scopeOrSpan.instrumentationLibrary?.name ??
      scopeOrSpan.instrumentation_scope?.name ??
      '',
    );
    attrs = scopeOrSpan.attributes ?? attributes ?? {};
  } else {
    name = String(scopeOrSpan ?? '');
  }
  if (name.startsWith(ANTHROPIC_SCOPE_PREFIX)) return true;
  if (name === CLAUDE_AGENTS_SCOPE || NON_ANTHROPIC_SCOPE_PREFIXES.some((p) => name.startsWith(p))) {
    return false;
  }
  if (attrs?.['gen_ai.operation.name'] === undefined) return false;
  const system = String(attrs['gen_ai.provider.name'] ?? attrs['gen_ai.system'] ?? attrs['llm.system'] ?? '').toLowerCase();
  return !system || system === 'anthropic';
}

export { flattenMessages, spanToJson };

/**
 * Extract and transform an Anthropic span into AnoSys format.
 * The Anthropic SDK emits GenAI semantic-convention spans natively, so this is
 * the shared GenAI extractor with the Anthropic source tag.
 *
 * @param {object} span  `to_json()`-shaped span (see `spanToJson`)
 */
export function extractSpanInfo(span) {
  return extractGenAiSpanInfo(span, {
    fromSource: ANTHROPIC_SOURCE,
    provider: 'anthropic',
    keyMapping: ANTHROPIC_KEY_MAPPING,
    startingIndices: ANTHROPIC_STARTING_INDICES,
  });
}
