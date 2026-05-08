import { assign, reassign, OPENAI_KEY_MAPPING, OPENAI_STARTING_INDICES } from './mapping.js';

// ── Helpers ───────────────────────────────────────────────────────────────────

function toTimestamp(dtStr) {
  if (!dtStr) return null;
  try { return Math.floor(new Date(dtStr).getTime()); } catch { return null; }
}

function setNested(obj, path, value) {
  const parts = path.split('.');
  let current = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    const part = parts[i];
    const idx = parseInt(part, 10);
    if (!isNaN(idx)) {
      if (!Array.isArray(current)) current = [];
      while (current.length <= idx) current.push({});
      current = current[idx];
    } else {
      if (!current[part] || typeof current[part] !== 'object') current[part] = {};
      current = current[part];
    }
  }
  const finalKey = parts[parts.length - 1];
  if (typeof value === 'string' && (value.trim().startsWith('{') || value.trim().startsWith('['))) {
    try { value = JSON.parse(value); } catch { /* keep as string */ }
  }
  current[finalKey] = value;
}

function deserializeAttributes(attributes) {
  const result = {};
  for (const [key, value] of Object.entries(attributes)) {
    setNested(result, key, value);
  }
  return result;
}

function toStrOrNull(val) {
  if (val === null || val === undefined) return null;
  if (typeof val === 'object') {
    try { return JSON.stringify(val); } catch { return String(val); }
  }
  return String(val);
}

// ── Main span extraction ──────────────────────────────────────────────────────

export function extractSpanInfo(span) {
  const variables = {};
  const keyToCvs = { ...OPENAI_KEY_MAPPING };

  assign(variables, 'otel_record_type', 'AnoSys Trace');
  assign(variables, 'custom_mapping', JSON.stringify(keyToCvs));

  // IDs and trace context
  const ctx = span.context ?? span.spanContext ?? {};
  assign(variables, 'trace_id', toStrOrNull(ctx.trace_id ?? ctx.traceId));
  assign(variables, 'span_id',  toStrOrNull(ctx.span_id  ?? ctx.spanId));
  assign(variables, 'kind', String(span.kind ?? 'INTERNAL').split('.').pop().toUpperCase());
  assign(variables, 'trace_state', toStrOrNull(ctx.trace_state ?? ctx.traceState));
  assign(variables, 'parent_id', toStrOrNull(span.parent_id ?? span.parentSpanId));
  assign(variables, 'name', toStrOrNull(span.name));

  // Timestamps
  const startMs = toTimestamp(span.start_time);
  const endMs   = toTimestamp(span.end_time);
  assign(variables, 'otel_observed_timestamp', new Date().toISOString());
  if (span.start_time) assign(variables, 'start_time', span.start_time);
  if (span.end_time)   assign(variables, 'end_time', span.end_time);
  assign(variables, 'cvn1', startMs);
  assign(variables, 'cvn2', endMs);
  if (startMs != null && endMs != null) assign(variables, 'otel_duration_ms', endMs - startMs);

  // Status
  const status = span.status ?? {};
  assign(variables, 'status_code', toStrOrNull(status.status_code ?? status.code));

  // Resource
  if (span.resource?.attributes) {
    assign(variables, 'otel_resource', JSON.stringify(span.resource.attributes));
  }

  // Attributes
  const raw = span.attributes ?? {};
  const attrs = deserializeAttributes(raw);

  const genAi  = attrs.gen_ai ?? {};
  const llm    = attrs.llm ?? {};
  const req    = genAi.request ?? {};
  const resp   = genAi.response ?? {};
  const usage  = genAi.usage ?? {};

  // System / operation / server
  assign(variables, 'gen_ai.system',         toStrOrNull(genAi.system ?? llm.vendor ?? genAi.provider?.name ?? 'openai'));
  assign(variables, 'gen_ai.provider.name',  toStrOrNull(genAi.provider?.name ?? 'openai'));
  
  if (span.name) {
    const op = span.name.includes('.') ? span.name.split('.')[0] : span.name;
    assign(variables, 'gen_ai.operation.name', op);
  }

  const resAttrs = span.resource?.attributes ?? {};
  assign(variables, 'server.address', toStrOrNull(attrs.server?.address ?? resAttrs['server.address'] ?? 'api.openai.com'));
  assign(variables, 'server.port',    toStrOrNull(attrs.server?.port ?? resAttrs['server.port'] ?? 443));

  // Request parameters
  assign(variables, 'gen_ai.request.model',              toStrOrNull(req.model ?? req.parameters?.model ?? llm.model_name));
  assign(variables, 'gen_ai.request.temperature',        toStrOrNull(req.temperature ?? llm.invocation_parameters?.temperature));
  assign(variables, 'gen_ai.request.top_p',              toStrOrNull(req.top_p));
  assign(variables, 'gen_ai.request.top_k',              toStrOrNull(req.top_k));
  assign(variables, 'gen_ai.request.max_tokens',         toStrOrNull(req.max_tokens ?? llm.invocation_parameters?.max_tokens));
  assign(variables, 'gen_ai.request.frequency_penalty',  toStrOrNull(req.frequency_penalty));
  assign(variables, 'gen_ai.request.presence_penalty',   toStrOrNull(req.presence_penalty));
  assign(variables, 'gen_ai.request.stop_sequences',     toStrOrNull(req.stop_sequences));
  assign(variables, 'gen_ai.request.seed',               toStrOrNull(req.seed));
  assign(variables, 'gen_ai.request.choice.count',       toStrOrNull(req.choice?.count));
  assign(variables, 'gen_ai.request.encoding_formats',   toStrOrNull(req.encoding_formats));
  assign(variables, 'gen_ai.request.tool_choice',        toStrOrNull(req.tool_choice ?? req.parameters?.tool_choice));

  // Response
  assign(variables, 'gen_ai.response.model',          toStrOrNull(resp.model));
  assign(variables, 'gen_ai.response.id',             toStrOrNull(resp.id));
  assign(variables, 'gen_ai.response.finish_reasons', toStrOrNull(resp.finish_reasons));
  assign(variables, 'gen_ai.output.type',             toStrOrNull(genAi.output?.type));

  // Usage / tokens
  const tokenCount = llm.token_count?.total_tokens ?? llm.usage?.total_tokens;
  assign(variables, 'gen_ai.usage.input_tokens',  usage.input_tokens  ?? llm.token_count?.prompt_tokens);
  assign(variables, 'gen_ai.usage.output_tokens', usage.output_tokens ?? llm.token_count?.completion_tokens);
  assign(variables, 'gen_ai.usage.total_tokens',  usage.total_tokens  ?? tokenCount);

  // Messages and content
  function flattenMessages(msgs) {
    if (!msgs) return null;
    const messages = Array.isArray(msgs) ? msgs : (msgs.messages || null);
    if (Array.isArray(messages)) {
      return messages.map(m => {
        const content = m.message?.content || m.content;
        if (content) return content;
        if (m.message?.tool_calls) return JSON.stringify(m.message.tool_calls);
        return JSON.stringify(m);
      }).filter(Boolean).join('\n---\n');
    }
    return msgs;
  }

  const inputMsgs  = attrs.input?.value ?? flattenMessages(genAi.input?.messages) ?? llm.input_messages;
  const outputMsgs = attrs.output?.value ?? flattenMessages(genAi.output?.messages) ?? llm.output_messages;
  assign(variables, 'gen_ai.input.messages',      toStrOrNull(inputMsgs));
  assign(variables, 'gen_ai.output.messages',     toStrOrNull(outputMsgs));
  assign(variables, 'gen_ai.system_instructions', toStrOrNull(genAi.system_instructions ?? llm.system));
  assign(variables, 'gen_ai.tool.definitions',    toStrOrNull(genAi.tool?.definitions ?? llm.tools));

  // User context and Model Config
  const userCtx = attrs.user_context ?? attrs.anosys?.user_context;
  if (userCtx) assign(variables, 'user_context', userCtx);

  const modelConfig = req.parameters ?? llm.invocation_parameters;
  if (modelConfig) assign(variables, 'llm_invocation_parameters', modelConfig);

  // Streaming
  const isStreaming = !!(raw['llm.is_streaming'] ?? raw['gen_ai.is_streaming'] ?? req.parameters?.stream);
  assign(variables, 'is_streaming', isStreaming);

  // Source tag
  assign(variables, 'from_source', 'openAI_Traces');

  // Events
  if (span.events && span.events.length > 0) {
    assign(variables, 'events', JSON.stringify(span.events));
  }
  
  // Backwards compatibility for old names
  assign(variables, 'llm_model_name', toStrOrNull(req.model ?? llm.model_name));
  assign(variables, 'llm_token_count', usage.total_tokens ?? tokenCount);

  // Raw data capture - ALWAYS mandatory
  assign(variables, 'raw', JSON.stringify(span));

  return reassign(variables, keyToCvs, { ...OPENAI_STARTING_INDICES });
}
