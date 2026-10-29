import { extractGenAiSpanInfo, flattenMessages, spanToJson } from './genai.js';
import { ANTHROPIC_KEY_MAPPING, ANTHROPIC_STARTING_INDICES } from './mapping.js';

// Source tag stored in cvs200
export const ANTHROPIC_SOURCE = 'AnthropicTelemetry';

// OpenTelemetry instrumentation scope of the Anthropic SDK's own spans
export const ANTHROPIC_SCOPE_PREFIX = 'com.anthropic';

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
