import { extractGenAiSpanInfo } from 'anosys-sdk-anthropic';
import {
  CLAUDE_AGENTS_KEY_MAPPING,
  CLAUDE_AGENTS_SOURCE,
  CLAUDE_AGENTS_STARTING_INDICES,
} from './mapping.js';

/**
 * Extract and transform a Claude Agent SDK span into AnoSys format.
 * Agent, tool and chat spans follow the GenAI semantic conventions, so this is
 * the shared GenAI extractor with the Claude Agents source tag.
 *
 * @param {object} span  `to_json()`-shaped span (see `spanToJson`)
 */
export function extractSpanInfo(span) {
  return extractGenAiSpanInfo(span, {
    fromSource: CLAUDE_AGENTS_SOURCE,
    provider: 'anthropic',
    keyMapping: CLAUDE_AGENTS_KEY_MAPPING,
    startingIndices: CLAUDE_AGENTS_STARTING_INDICES,
  });
}
