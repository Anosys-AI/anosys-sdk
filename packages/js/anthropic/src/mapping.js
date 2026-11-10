// Key-to-column mapping for the Anthropic package. The tables (including the
// Claude extension: cache_read=cvn4, cache_creation=cvn5, cost=cvn7, has_thinking=cvb3)
// and the assign / reassign helpers live in anosys-sdk-core, kept equal to the
// Python tables by the shared fixture; this module re-exports them.
import {
  BASE_KEY_MAPPING,
  CLAUDE_KEY_MAPPING,
  CLAUDE_STARTING_INDICES,
  CLAUDE_VALID_TYPES,
  DEFAULT_STARTING_INDICES,
  OTEL_AI_VALID_TYPES,
  assign,
  getTypeKey,
  reassign as coreReassign,
} from 'anosys-sdk-core';

export {
  BASE_KEY_MAPPING, CLAUDE_KEY_MAPPING, CLAUDE_STARTING_INDICES, CLAUDE_VALID_TYPES,
  DEFAULT_STARTING_INDICES, OTEL_AI_VALID_TYPES, assign, getTypeKey,
};

export const ANTHROPIC_KEY_MAPPING = { ...CLAUDE_KEY_MAPPING };
export const ANTHROPIC_STARTING_INDICES = { ...CLAUDE_STARTING_INDICES };

export function reassign(data, keyToCvs = ANTHROPIC_KEY_MAPPING, startingIndices = null, validTypes = null) {
  return coreReassign(data, keyToCvs, startingIndices ?? ANTHROPIC_STARTING_INDICES, validTypes);
}
