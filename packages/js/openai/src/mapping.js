// Key-to-column mapping for the OpenAI package. The tables and the assign /
// reassign helpers live in anosys-sdk-core (one implementation for every package,
// kept equal to the Python tables by the shared fixture); this module re-exports them.
import {
  BASE_KEY_MAPPING,
  CLAUDE_VALID_TYPES,
  DEFAULT_STARTING_INDICES,
  OTEL_AI_VALID_TYPES,
  assign,
  getTypeKey,
  reassign as coreReassign,
} from 'anosys-sdk-core';

export { BASE_KEY_MAPPING, CLAUDE_VALID_TYPES, DEFAULT_STARTING_INDICES, OTEL_AI_VALID_TYPES, assign, getTypeKey };

export const OPENAI_KEY_MAPPING = { ...BASE_KEY_MAPPING };
export const OPENAI_STARTING_INDICES = { ...DEFAULT_STARTING_INDICES };

export function reassign(data, keyToCvs = OPENAI_KEY_MAPPING, startingIndices = null, validTypes = null) {
  return coreReassign(data, keyToCvs, startingIndices ?? OPENAI_STARTING_INDICES, validTypes);
}
