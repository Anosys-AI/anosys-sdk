// anosysLogger / anosysRawLogger: the shared implementation in anosys-sdk-core,
// bound to this package's key mapping.
import { createDecorators } from 'anosys-sdk-core';
import { log } from './config.js';
import { ANTHROPIC_KEY_MAPPING, ANTHROPIC_STARTING_INDICES } from './mapping.js';

export const { setupApi, setupDecorator, anosysLogger, anosysRawLogger, getLogApiUrl } = createDecorators({
  keyToCvs: ANTHROPIC_KEY_MAPPING, startingIndices: ANTHROPIC_STARTING_INDICES, log,
});
