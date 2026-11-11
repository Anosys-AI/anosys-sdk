/**
 * OpenTelemetry GenAI semantic-convention span extraction for AnoSys.
 *
 * JS port of Python `anosys_sdk_core/genai.py`: both produce the same keys for
 * the same span. The Anthropic SDK emits these spans natively, and the AnoSys
 * Claude Agents integration emits them for agent and tool spans.
 *
 * The input is the `to_json()` span shape (see `spanToJson`): name, context,
 * parent_id, start_time, end_time, status, attributes (flat), events, resource.
 */

import { assign, reassign, CLAUDE_KEY_MAPPING, CLAUDE_STARTING_INDICES } from './mapping.js';

// gen_ai.operation.name -> AnoSys span kind (gen_ai.span.kind / otel_kind)
export const OPERATION_SPAN_KINDS = {
  chat: 'LLM',
  text_completion: 'LLM',
  generate_content: 'LLM',
  embeddings: 'EMBEDDING',
  invoke_agent: 'AGENT',
  create_agent: 'AGENT',
  execute_tool: 'TOOL',
};

// Request parameters copied 1:1 to gen_ai.request.* (and llm_invocation_parameters)
const REQUEST_PARAMETERS = [
  'max_tokens', 'temperature', 'top_p', 'top_k', 'stop_sequences', 'seed',
  'frequency_penalty', 'presence_penalty', 'choice.count', 'tool_choice',
];

const STATUS_CODES = { 0: 'UNSET', 1: 'OK', 2: 'ERROR' };

// ── Helpers ───────────────────────────────────────────────────────────────────

function toTimestamp(dtStr) {
  if (!dtStr) return null;
  const ms = new Date(dtStr).getTime();
  return Number.isNaN(ms) ? null : Math.floor(ms);
}


function toStrOrNull(val) {
  if (val === null || val === undefined) return null;
  if (typeof val === 'object') {
    try { return JSON.stringify(val); } catch { return String(val); }
  }
  return String(val);
}

function parseJson(value) {
  if (typeof value === 'string' && /^\s*[[{]/.test(value)) {
    try { return JSON.parse(value); } catch { return value; }
  }
  return value;
}

function toNumber(value) {
  if (value === null || value === undefined || typeof value === 'boolean') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/**
 * Convert an OTel ReadableSpan to the shape of Python's `ReadableSpan.to_json()`,
 * so both languages feed the extractor the same structure.
 */
// One implementation in anosys-sdk-core (no circular serialisation of SDK 2.x spans)
export { spanToJson } from 'anosys-sdk-core';

function partText(part) {
  if (!part || typeof part !== 'object') return typeof part === 'string' ? part : null;
  const type = part.type;
  if (type === 'text') {
    return part.text ?? part.content ?? null;
  }
  if (type === 'reasoning' || type === 'thinking') {
    const content = part.thinking ?? part.content;
    return content ? `[Thinking] ${content}` : null;
  }
  if (type === 'tool_call' || type === 'tool_use') {
    const name = part.name ?? part.tool_name ?? '';
    const args = part.input ?? part.arguments;
    const argsStr = typeof args === 'object' ? JSON.stringify(args) : args;
    return `[Tool Call: ${name}] ${argsStr ?? ''}`.trimEnd();
  }
  if (type === 'tool_call_response' || type === 'tool_result') {
    const resp = typeof part.content === 'object' ? JSON.stringify(part.content) : (part.content ?? part.response);
    return `[Tool Result] ${resp ?? ''}`.trimEnd();
  }
  if (part.text) return part.text;
  if (part.content) return typeof part.content === 'string' ? part.content : JSON.stringify(part.content);
  return null;
}

/**
 * Flatten GenAI messages into a readable string ("Role: text" blocks).
 * Accepts the parts-based convention and the classic {role, content} shape.
 */
export function flattenMessages(messages) {
  messages = parseJson(messages);
  if (!messages || (Array.isArray(messages) && messages.length === 0)) return null;
  if (typeof messages === 'string') return messages;
  if (!Array.isArray(messages)) return String(messages);

  const blocks = [];
  for (const message of messages) {
    if (!message || typeof message !== 'object') continue;
    if (message.type && !message.role) {
      const text = partText(message);
      if (text) blocks.push(text);
      continue;
    }
    const role = message.role;
    let text;
    if (Array.isArray(message.parts)) {
      text = message.parts.filter(p => p && typeof p === 'object').map(partText).filter(Boolean).join('\n');
    } else if (Array.isArray(message.content)) {
      text = message.content.filter(p => p && typeof p === 'object').map(partText).filter(Boolean).join('\n');
    } else {
      text = typeof message.content === 'string' ? message.content : toStrOrNull(message.content);
    }
    if (text) {
      const label = role ? `${role.charAt(0).toUpperCase()}${role.slice(1).toLowerCase()}: ` : '';
      blocks.push(`${label}${text}`);
    }
  }
  return blocks.length ? blocks.join('\n\n') : null;
}

function systemText(systemInstructions) {
  systemInstructions = parseJson(systemInstructions);
  if (Array.isArray(systemInstructions)) {
    const texts = systemInstructions.filter(p => p && p.content).map(p => p.content);
    return texts.length ? texts.join('\n') : null;
  }
  return toStrOrNull(systemInstructions);
}

function hasReasoning(messages) {
  messages = parseJson(messages);
  if (!Array.isArray(messages)) return false;
  return messages.some(m => {
    if (m?.type === 'reasoning' || m?.type === 'thinking') return true;
    const blocks = Array.isArray(m?.parts) ? m.parts : (Array.isArray(m?.content) ? m.content : null);
    return Array.isArray(blocks) && blocks.some(p => p?.type === 'reasoning' || p?.type === 'thinking');
  });
}

// ── Main span extraction ──────────────────────────────────────────────────────

/**
 * Extract and transform a GenAI semantic-convention span into AnoSys format.
 *
 * @param {object} span  `to_json()`-shaped span (use `spanToJson` for a ReadableSpan)
 * @param {object} opts  { fromSource, provider, keyMapping, startingIndices }
 */
export function extractGenAiSpanInfo(span, {
  fromSource,
  provider = 'anthropic',
  keyMapping = CLAUDE_KEY_MAPPING,
  startingIndices = CLAUDE_STARTING_INDICES,
} = {}) {
  const variables = {};
  const keyToCvs = { ...keyMapping };
  const attributes = { ...(span.attributes ?? {}) };
  const resourceAttrs = span.resource?.attributes ?? {};
  const context = span.context ?? {};

  // Top-level metadata
  assign(variables, 'otel_record_type', 'AnoSys Trace');
  assign(variables, 'custom_mapping', JSON.stringify(keyToCvs, null, 4));
  assign(variables, 'otel_observed_timestamp', new Date().toISOString());
  assign(variables, 'name', toStrOrNull(span.name));
  assign(variables, 'trace_id', toStrOrNull(context.trace_id));
  assign(variables, 'span_id', toStrOrNull(context.span_id));
  assign(variables, 'trace_state', toStrOrNull(context.trace_state) || null);
  assign(variables, 'parent_id', toStrOrNull(span.parent_id));
  assign(variables, 'start_time', toStrOrNull(span.start_time));
  assign(variables, 'end_time', toStrOrNull(span.end_time));

  const startTs = toTimestamp(span.start_time);
  const endTs = toTimestamp(span.end_time);
  assign(variables, 'cvn1', startTs);
  assign(variables, 'cvn2', endTs);
  if (startTs != null && endTs != null) assign(variables, 'otel_duration_ms', endTs - startTs);

  // Status
  const status = span.status ?? {};
  if (Object.keys(status).length) {
    assign(variables, 'status', toStrOrNull(status));
    if (status.status_code != null) {
      assign(variables, 'status_code', STATUS_CODES[status.status_code] ?? String(status.status_code));
    }
  }

  // Gen AI - System & operation
  const providerName = attributes['gen_ai.provider.name'] ?? attributes['gen_ai.system'] ?? provider;
  const operation = attributes['gen_ai.operation.name'];
  assign(variables, 'gen_ai.system', providerName);
  assign(variables, 'gen_ai.provider.name', providerName);
  assign(variables, 'gen_ai.operation.name', toStrOrNull(operation));

  const kindVal = operation ? (OPERATION_SPAN_KINDS[operation] ?? null) : null;
  assign(variables, 'gen_ai.span.kind', kindVal);
  assign(variables, 'kind', kindVal);

  assign(variables, 'server.address', attributes['server.address'] ?? resourceAttrs['server.address']);
  assign(variables, 'server.port', attributes['server.port'] ?? resourceAttrs['server.port']);
  assign(variables, 'error.type', toStrOrNull(attributes['error.type']));
  assign(variables, 'service.name', resourceAttrs['service.name'] ?? 'unknown_service');
  assign(variables, 'attributes', attributes);

  // Request configuration
  const model = attributes['gen_ai.request.model'];
  assign(variables, 'gen_ai.request.model', toStrOrNull(model));
  const invocationParams = {};
  if (model) invocationParams.model = model;
  for (const param of REQUEST_PARAMETERS) {
    let value = attributes[`gen_ai.request.${param}`];
    if (value === null || value === undefined) continue;
    value = parseJson(value);
    invocationParams[param] = value;
    assign(variables, `gen_ai.request.${param}`, param === 'tool_choice' ? toStrOrNull(value) : value);
  }

  // Response
  const responseId = attributes['gen_ai.response.id'];
  let finishReasons = parseJson(attributes['gen_ai.response.finish_reasons']);
  if ((!finishReasons || finishReasons.length === 0) && attributes['anthropic.message.stop_reason']) {
    finishReasons = [attributes['anthropic.message.stop_reason']];
  }
  if (typeof finishReasons === 'string') finishReasons = [finishReasons];
  assign(variables, 'gen_ai.response.model', toStrOrNull(attributes['gen_ai.response.model']));
  assign(variables, 'gen_ai.response.id', toStrOrNull(responseId));
  assign(variables, 'gen_ai.response.finish_reasons', finishReasons?.length ? [...finishReasons] : null);
  assign(variables, 'gen_ai.output.type', toStrOrNull(attributes['gen_ai.output.type']));
  assign(variables, 'resp_id', toStrOrNull(responseId));

  // Usage. gen_ai.usage.input_tokens is the full prompt (cache reads/writes
  // included), matching the OpenAI meaning of prompt tokens.
  const inputTokens = toNumber(attributes['gen_ai.usage.input_tokens']);
  const outputTokens = toNumber(attributes['gen_ai.usage.output_tokens']);
  let totalTokens = toNumber(attributes['gen_ai.usage.total_tokens']);
  const cacheRead = toNumber(
    attributes['gen_ai.usage.cache_read.input_tokens'] ?? attributes['gen_ai.usage.cache_read_input_tokens'],
  );
  const cacheCreation = toNumber(
    attributes['gen_ai.usage.cache_creation.input_tokens']
      ?? attributes['gen_ai.usage.cache_creation_input_tokens']
      ?? attributes['gen_ai.usage.cache_write.input_tokens'],
  );
  const reasoningTokens = toNumber(attributes['gen_ai.usage.reasoning.output_tokens']);
  if (totalTokens == null && inputTokens != null && outputTokens != null) totalTokens = inputTokens + outputTokens;
  const cost = toNumber(attributes['gen_ai.usage.cost']);

  assign(variables, 'gen_ai.usage.input_tokens', inputTokens);
  assign(variables, 'gen_ai.usage.output_tokens', outputTokens);
  assign(variables, 'gen_ai.usage.total_tokens', totalTokens);
  assign(variables, 'gen_ai.usage.cache_read.input_tokens', cacheRead);
  assign(variables, 'gen_ai.usage.cache_creation.input_tokens', cacheCreation);
  assign(variables, 'gen_ai.usage.cost', cost);

  const tokenCount = Object.fromEntries([
    ['input_tokens', inputTokens],
    ['output_tokens', outputTokens],
    ['total_tokens', totalTokens],
    ['cache_read_input_tokens', cacheRead],
    ['cache_creation_input_tokens', cacheCreation],
    ['reasoning_output_tokens', reasoningTokens],
  ].filter(([, v]) => v != null));
  assign(variables, 'llm_token_count', Object.keys(tokenCount).length ? tokenCount : null);

  // Content
  const inputMessages = parseJson(attributes['gen_ai.input.messages']);
  const outputMessages = parseJson(attributes['gen_ai.output.messages']);
  const systemInstructions = parseJson(attributes['gen_ai.system_instructions']);
  const toolDefinitions = parseJson(attributes['gen_ai.tool.definitions']);
  assign(variables, 'gen_ai.input.messages', inputMessages);
  assign(variables, 'gen_ai.output.messages', outputMessages);
  assign(variables, 'gen_ai.system_instructions', systemInstructions);
  assign(variables, 'gen_ai.tool.definitions', toolDefinitions);
  if (Boolean(attributes?.has_thinking) || Boolean(attributes?.['gen_ai.thinking']) || hasReasoning(outputMessages)) assign(variables, 'has_thinking', true);

  // Agents & Tools
  assign(variables, 'gen_ai.agent.id', toStrOrNull(attributes['gen_ai.agent.id'] ?? attributes['anthropic.agent.id']));
  assign(variables, 'gen_ai.agent.name', toStrOrNull(attributes['gen_ai.agent.name'] ?? attributes['anthropic.agent.name']));
  assign(variables, 'gen_ai.agent.description', toStrOrNull(attributes['gen_ai.agent.description'] ?? attributes['anthropic.agent.description']));
  assign(variables, 'gen_ai.conversation.id', toStrOrNull(attributes['gen_ai.conversation.id']));
  if (kindVal === 'AGENT') assign(variables, 'is_agent', true);
  if (kindVal === 'TOOL') {
    assign(variables, 'gen_ai.tool.name', toStrOrNull(attributes['gen_ai.tool.name']));
    assign(variables, 'gen_ai.tool.call.id', toStrOrNull(attributes['gen_ai.tool.call.id']));
    assign(variables, 'gen_ai.tool.type', toStrOrNull(attributes['gen_ai.tool.type']));
  }

  // Legacy LLM fields
  const sysText = systemText(systemInstructions);
  assign(variables, 'llm_model', toStrOrNull(model ?? attributes['gen_ai.response.model']));
  assign(variables, 'llm_system', sysText);
  assign(variables, 'llm_tools', toolDefinitions);
  assign(variables, 'llm_invocation_parameters', Object.keys(invocationParams).length ? invocationParams : null);

  let inputVal;
  let outputVal;
  if (kindVal === 'TOOL') {
    // Tool spans: arguments in, result out (same as OpenAI Agents function spans)
    inputVal = toStrOrNull(parseJson(attributes['gen_ai.tool.call.arguments']));
    outputVal = toStrOrNull(parseJson(
      attributes['gen_ai.tool.call.result'] ?? attributes['anthropic.tool_result.content'],
    ));
  } else {
    const inputParts = [];
    if (sysText) inputParts.push(`System: ${sysText}`);
    const flattenedInput = flattenMessages(inputMessages);
    if (flattenedInput) inputParts.push(flattenedInput);
    inputVal = inputParts.length ? inputParts.join('\n\n') : null;
    outputVal = flattenMessages(outputMessages);
  }
  assign(variables, 'llm_input', inputVal);
  assign(variables, 'llm_output', outputVal);

  // Resource, source, streaming, events, raw
  assign(variables, 'otel_resource', JSON.stringify(resourceAttrs));
  assign(variables, 'from_source', fromSource);
  if (attributes['gen_ai.request.stream'] || attributes['anthropic.request.stream']) {
    assign(variables, 'is_streaming', true);
  }
  if (span.events?.length) assign(variables, 'events', JSON.stringify(span.events));
  assign(variables, 'raw', JSON.stringify(span));

  return reassign(variables, keyToCvs, { ...startingIndices });
}
