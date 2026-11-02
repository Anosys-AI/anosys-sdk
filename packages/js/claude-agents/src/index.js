export {
  AnosysClaudeAgentsLogger,
  setupTracing,
  traceMessages,
  wrapQuery,
} from './instrumentor.js';
export { AgentRunTracer } from './tracer.js';
export { extractSpanInfo } from './hooks.js';
export {
  CLAUDE_AGENTS_KEY_MAPPING,
  CLAUDE_AGENTS_STARTING_INDICES,
  CLAUDE_AGENTS_SOURCE,
  CLAUDE_AGENTS_SCOPE,
} from './mapping.js';
// Re-exports from the Anthropic package (shared schema, decorators, encryption)
export {
  anosysLogger,
  anosysRawLogger,
  setupApi,
  setupDecorator,
  resolveApiKey,
  encryptPayload,
  getEncryptionKey,
  getTargetColumns,
  derive256BitKey,
  encrypt,
  decrypt,
  ANOSYS_ENCRYPTION_PREFIX,
  DEFAULT_ENCRYPTED_COLUMNS,
} from 'anosys-sdk-anthropic';
