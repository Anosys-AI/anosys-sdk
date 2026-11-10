
// Key-to-column tables and the assign / reassign helpers live in anosys-sdk-core
// (one implementation, kept equal to the Python tables by the shared fixture).
import {
  AGENTS_KEY_MAPPING,
  BASE_KEY_MAPPING,
  CLAUDE_VALID_TYPES,
  DEFAULT_STARTING_INDICES,
  OTEL_AI_VALID_TYPES,
  assign,
  reassign as coreReassign,
  spanToJson,
} from 'anosys-sdk-core';

export { AGENTS_KEY_MAPPING, BASE_KEY_MAPPING, CLAUDE_VALID_TYPES, DEFAULT_STARTING_INDICES, OTEL_AI_VALID_TYPES, assign };

export const AGENTS_STARTING_INDICES = { ...DEFAULT_STARTING_INDICES };

export function reassign(data, keyToCvs = AGENTS_KEY_MAPPING, startingIndices = null, validTypes = null) {
  return coreReassign(data, keyToCvs, startingIndices ?? AGENTS_STARTING_INDICES, validTypes);
}

function toStr(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === 'object') { try { return JSON.stringify(value); } catch { return String(value); } }
  return String(value);
}

function formatTimestamp(val) {
  if (!val) return null;
  let iso;
  if (val instanceof Date) {
    iso = val.toISOString();
  } else {
    iso = String(val);
  }
  // Replace +00:00 with Z if present, and ensure it ends with Z if it's a timestamp
  return iso.replace(/\+00:00$/, 'Z').replace(/([^Z])$/, (m, p) => (iso.includes('T') && !iso.includes('+') ? p + 'Z' : p));
}

export { toStr as toStrOrNull };

// ── span2json — mirrors Python mapping.py span2json ──────────────────────────

function toTimestamp(dtStr) {
  if (!dtStr) return null;
  try { return Math.floor(new Date(dtStr).getTime()); } catch { return null; }
}

export function span2json(span) {
  const data      = span.data ?? {};
  const spanData  = data.span_data ?? {};
  const source    = data.source;
  const timestamp = span.timestamp;
  const userCtx   = JSON.stringify(span.user_context ?? {});

  const startTs = toTimestamp(data.started_at);
  const endTs   = toTimestamp(data.ended_at);

  const mapping = {
    otel_record_type: 'record type (AnoSys Agentic Trace)',
    otel_schema_url: 'schema URL (custom_mapping)',
    otel_observed_timestamp: 'creation timestamp',
    g1: 'creation timestamp (numeric)',
    otel_span_id: 'span id', otel_trace_id: 'trace id',
    otel_parent_span_id: 'parent span id', otel_start_time: 'span start time',
    cvn1: 'start time (numeric)', otel_end_time: 'span end time',
    cvn2: 'end time (numeric)', otel_exception_message: 'error message',
    cvs5: 'user context', cvs60: 'object type', cvs61: 'source',
    otel_name: 'span name', otel_duration_ms: 'duration in ms',
  };

  const base = {
    otel_record_type:         'AnoSys Agentic Trace',
    otel_schema_url:          JSON.stringify(mapping),
    otel_observed_timestamp:  formatTimestamp(timestamp),
    g1:                       toTimestamp(timestamp),
    otel_span_id:             toStr(data.id),
    otel_trace_id:            toStr(data.trace_id ?? data.id),
    otel_parent_span_id:      toStr(data.parent_id),
    otel_start_time:          formatTimestamp(data.started_at),
    cvn1:                     startTs,
    otel_end_time:            formatTimestamp(data.ended_at),
    cvn2:                     endTs,
    otel_duration_ms:         (startTs != null && endTs != null) ? endTs - startTs : null,
    otel_exception_message:   toStr(data.error),
    cvs5:                     toStr(userCtx),
    cvs60:                    toStr(data.object),
    cvs61:                    toStr(source),
  };

  const type = spanData.type;

  function extractIdFromConfig(config) {
    if (!config) return {};
    if (typeof config === 'object' && config.id) return { cvs77: toStr(config.id) };
    if (typeof config === 'string') {
      try {
        const parsed = JSON.parse(config);
        if (parsed && typeof parsed === 'object' && parsed.id) return { cvs77: toStr(parsed.id) };
      } catch (e) {}
    }
    return {};
  }

  const extended = {
    agent:        () => ({ otel_name: toStr(spanData.name), cvs62: toStr((spanData.handoffs ?? []).join(', ')), llm_tools: toStr(spanData.tools ?? []), cvs64: toStr(spanData.output_type) }),
    function:     () => ({ otel_name: toStr(spanData.name), llm_input: toStr(spanData.input), llm_output: toStr(spanData.output), cvs67: toStr(spanData.mcp_data) }),
    mcp_tools:    () => ({ otel_name: toStr(spanData.name), llm_input: toStr(spanData.input), llm_output: toStr(spanData.output), cvs67: toStr(spanData.mcp_data) }),
    guardrail:    () => ({ otel_name: toStr(spanData.name), cvs68: toStr(spanData.triggered) }),
    generation:   () => ({ llm_input: toStr(spanData.input), llm_output: toStr(spanData.output), cvs69: toStr(spanData.model), llm_invocation_parameters: toStr(spanData.model_config), llm_token_count: toStr(spanData.usage), ...extractIdFromConfig(spanData.model_config) }),
    custom:       () => ({ otel_name: toStr(spanData.name), cvs72: toStr(spanData.data) }),
    transcription:() => ({ cvs72: toStr(spanData.input?.data), cvs73: toStr(spanData.input?.format), llm_output: toStr(spanData.output), cvs69: toStr(spanData.model), llm_invocation_parameters: toStr(spanData.model_config), ...extractIdFromConfig(spanData.model_config) }),
    speech:       () => ({ llm_input: toStr(spanData.input), cvs72: toStr(spanData.output?.data), cvs73: toStr(spanData.output?.format), cvs69: toStr(spanData.model), llm_invocation_parameters: toStr(spanData.model_config), cvs74: toStr(spanData.first_content_at), ...extractIdFromConfig(spanData.model_config) }),
    speechgroup:  () => ({ llm_input: toStr(spanData.input) }),
    MCPListTools: () => ({ cvs75: toStr(spanData.server), cvs76: toStr(spanData.result) }),
    response:     () => ({ cvs77: toStr(spanData.response_id) }),
    handoff:      () => ({ cvs78: toStr(spanData.from_agent), cvs79: toStr(spanData.to_agent) }),
  };

  const result = {
    ...base,
    otel_kind:  toStr(type),
    cvb1:       true,
    cvs199:     JSON.stringify(span),
    cvs200:     'openAI_Agents_Traces',
    ...(extended[type]?.() ?? {}),
  };

  // Extract usage tokens into standard columns if present
  const usage = spanData.usage ?? spanData.data?.usage;
  if (usage) {
    if (usage.input_tokens) result['gen_ai_usage_input_tokens'] = usage.input_tokens;
    if (usage.output_tokens) result['gen_ai_usage_output_tokens'] = usage.output_tokens;
    if (usage.total_tokens) result['gen_ai_usage_total_tokens'] = usage.total_tokens;
    else if (usage.input_tokens && usage.output_tokens) {
      result['gen_ai_usage_total_tokens'] = usage.input_tokens + usage.output_tokens;
    }
  }

  // Remove nulls
  return Object.fromEntries(Object.entries(result).filter(([, v]) => v != null));
}

// ── OTel ReadableSpan extraction (mirrors Python extract_otel_span_info) ─────

function setNested(obj, path, value) {
  const parts = path.split('.');
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    const p = parts[i];
    if (!cur[p] || typeof cur[p] !== 'object') cur[p] = {};
    cur = cur[p];
  }
  const last = parts[parts.length - 1];
  if (typeof value === 'string' && (value.trim().startsWith('{') || value.trim().startsWith('['))) {
    try { value = JSON.parse(value); } catch { /* keep as string */ }
  }
  cur[last] = value;
}

function deserializeAttributes(attrs) {
  const result = {};
  for (const [k, v] of Object.entries(attrs)) setNested(result, k, v);
  return result;
}

export function extractOtelSpanInfo(span) {
  const variables = {};
  const keyToCvs = { ...AGENTS_KEY_MAPPING };

  // 1. Timestamps: handle array [s, ns] or unix_nano number
  let startMs = null;
  if (span.startTime) {
    startMs = Math.floor(Number(span.startTime[0]) * 1e3 + Number(span.startTime[1]) / 1e6);
  } else if (span.start_time_unix_nano) {
    startMs = Math.floor(Number(span.start_time_unix_nano) / 1e6);
  }

  let endMs = null;
  if (span.endTime) {
    endMs = Math.floor(Number(span.endTime[0]) * 1e3 + Number(span.endTime[1]) / 1e6);
  } else if (span.end_time_unix_nano) {
    endMs = Math.floor(Number(span.end_time_unix_nano) / 1e6);
  }

  assign(variables, 'otel_record_type', 'AnoSys Trace');
  assign(variables, 'custom_mapping', JSON.stringify(keyToCvs));
  assign(variables, 'otel_observed_timestamp', formatTimestamp(new Date()));
  assign(variables, 'name', span.name);

  // 2. Trace Context: handle function or plain object
  const ctx = (typeof span.spanContext === 'function' ? span.spanContext() : null) ?? span.context ?? {};
  assign(variables, 'trace_id', ctx.traceId ?? ctx.trace_id);
  assign(variables, 'span_id', ctx.spanId ?? ctx.span_id);

  // 3. Parent ID
  const parentId = span.parentSpanId ?? span.parent_id;
  if (parentId) assign(variables, 'parent_id', parentId);

  if (startMs != null) { variables.start_time = formatTimestamp(new Date(startMs)); assign(variables, 'cvn1', startMs); }
  if (endMs != null) { variables.end_time = formatTimestamp(new Date(endMs)); assign(variables, 'cvn2', endMs); }
  if (startMs != null && endMs != null) assign(variables, 'otel_duration_ms', endMs - startMs);

  // 4. Attributes: handle attributes or attributes_json
  const rawAttrs = span.attributes_json ?? span.attributes ?? {};
  const attrs = deserializeAttributes(Object.fromEntries(Object.entries(rawAttrs)));

  assign(variables, 'gen_ai.system', toStr(attrs.gen_ai?.system ?? 'openai'));
  assign(variables, 'gen_ai.request.model', toStr(attrs.gen_ai?.request?.model ?? attrs.llm?.model_name));
  
  const params = attrs.gen_ai?.request?.parameters ?? attrs.llm?.invocation_parameters;
  if (params !== undefined) {
    assign(variables, 'llm_invocation_parameters', toStr(params));
    if (typeof params === 'object' && params !== null && params.id) {
      assign(variables, 'cvs77', toStr(params.id));
    } else if (typeof params === 'string') {
      try {
        const parsedParams = JSON.parse(params);
        if (parsedParams && typeof parsedParams === 'object' && parsedParams.id) {
          assign(variables, 'cvs77', toStr(parsedParams.id));
        }
      } catch (e) {}
    }
  }

  assign(variables, 'kind', String(span.kind ?? '').replace('SpanKind.', '').toUpperCase());

  if (span.resource?.attributes) {
    assign(variables, 'otel_resource', JSON.stringify(Object.fromEntries(Object.entries(span.resource.attributes))));
  }

  const userCtx = span.user_context ?? span.userContext;
  if (userCtx) assign(variables, 'user_context', userCtx);

  assign(variables, 'from_source', 'openAI_Agents_Telemetry');

  // Raw data capture - ALWAYS mandatory
  // spanToJson reads fields only: SDK 2.x spans reference their processors (circular)
  assign(variables, 'raw', JSON.stringify(spanToJson(span)));

  return reassign(variables, keyToCvs, { ...AGENTS_STARTING_INDICES });
}
