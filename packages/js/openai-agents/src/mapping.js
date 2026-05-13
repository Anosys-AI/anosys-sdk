// ── Shared base mapping (mirrors Python BASE_KEY_MAPPING) ────────────────────

export const DEFAULT_STARTING_INDICES = { string: 100, number: 3, bool: 1 };

export const BASE_KEY_MAPPING = {
  custom_mapping: 'otel_schema_url', otel_observed_timestamp: 'otel_observed_timestamp',
  otel_record_type: 'otel_record_type', cvn1: 'cvn1', cvn2: 'cvn2',
  otel_duration_ms: 'otel_duration_ms', name: 'otel_name', trace_id: 'otel_trace_id',
  span_id: 'otel_span_id', trace_state: 'otel_trace_flags', parent_id: 'otel_parent_span_id',
  start_time: 'otel_start_time', end_time: 'otel_end_time', kind: 'otel_kind',
  status: 'otel_status', status_code: 'otel_status_code', resp_id: 'otel_status_message',
  otel_resource: 'otel_resource',
  'gen_ai.system': 'gen_ai_system', 'gen_ai.provider.name': 'gen_ai_provider_name',
  'gen_ai.operation.name': 'gen_ai_operation_name', 'server.address': 'cvs14',
  'server.port': 'cvn3', 'error.type': 'cvs10',
  'gen_ai.request.model': 'gen_ai_request_model', 'gen_ai.request.temperature': 'gen_ai_request_temperature',
  'gen_ai.request.top_p': 'gen_ai_request_top_p', 'gen_ai.request.top_k': 'gen_ai_request_top_k',
  'gen_ai.request.max_tokens': 'gen_ai_request_max_tokens',
  'gen_ai.request.frequency_penalty': 'gen_ai_request_frequency_penalty',
  'gen_ai.request.presence_penalty': 'gen_ai_request_presence_penalty',
  'gen_ai.request.stop_sequences': 'gen_ai_request_stop_sequences',
  'gen_ai.request.seed': 'gen_ai_request_seed', 'gen_ai.request.choice.count': 'gen_ai_request_choice_count',
  'gen_ai.request.encoding_formats': 'gen_ai_request_encoding_formats',
  'gen_ai.response.model': 'gen_ai_response_model', 'gen_ai.response.id': 'gen_ai_response_id',
  'gen_ai.response.finish_reasons': 'gen_ai_response_finish_reasons',
  'gen_ai.usage.input_tokens': 'gen_ai_usage_input_tokens',
  'gen_ai.usage.output_tokens': 'gen_ai_usage_output_tokens',
  'gen_ai.usage.total_tokens': 'gen_ai_usage_total_tokens',
  'gen_ai.output.type': 'gen_ai_output_type',
  'gen_ai.input.messages': 'gen_ai_input_messages', 'gen_ai.output.messages': 'gen_ai_output_messages',
  'gen_ai.system_instructions': 'gen_ai_system_instructions', 'gen_ai.tool.definitions': 'gen_ai_tool_definitions',
  'gen_ai.agent.id': 'gen_ai_agent_id', 'gen_ai.agent.name': 'gen_ai_agent_name',
  'gen_ai.agent.description': 'gen_ai_agent_description', 'gen_ai.conversation.id': 'gen_ai_conversation_id',
  'gen_ai.data_source.id': 'gen_ai_data_source_id',
  'gen_ai.embeddings.dimension.count': 'gen_ai_embeddings_dimension_count',
  llm_tools: 'llm_tools', llm_system: 'llm_system', llm_input: 'llm_input',
  llm_output: 'llm_output', llm_model: 'llm_model',
  llm_invocation_parameters: 'llm_invocation_parameters', llm_token_count: 'llm_token_count',
  llm_input_messages: 'gen_ai_input_messages', llm_output_messages: 'gen_ai_output_messages',
  input: 'llm_input', output: 'llm_output', error: 'cvs3', caller: 'cvs4',
  error_type: 'cvs10', error_message: 'cvs11', error_stack: 'cvs12',
  raw: 'cvs199', from_source: 'cvs200', source: 'cvs200', is_streaming: 'cvb2',
  is_agent: 'cvb1', events: 'otel_events',
  llm_model_name: 'cvs16', 'gen_ai.request.tool_choice': 'cvs15',
};

// Validation maps per source based on Protobuf schemas
export const OTEL_AI_VALID_TYPES = {
  timestamp: 'timestamp', user_timestamp: 'double', risk_score: 'double',
  is_anomaly: 'boolean', debug: 'boolean', otel_observed_timestamp: 'timestamp',
  otel_resource: 'json', otel_start_time: 'timestamp', otel_end_time: 'timestamp',
  otel_duration_ms: 'double', otel_attributes: 'json', otel_events: 'json',
  otel_links: 'json', otel_severity_number: 'double', otel_value: 'double',
  otel_labels: 'json', otel_histogram_bucket_counts: 'json',
  otel_histogram_bucket_bounds: 'json', otel_summary_count: 'double',
  otel_summary_sum: 'double', llm_tools: 'json', llm_token_count: 'json',
  llm_invocation_parameters: 'json', gen_ai_request_temperature: 'double',
  gen_ai_request_top_p: 'double', gen_ai_request_top_k: 'double',
  gen_ai_request_max_tokens: 'double', gen_ai_request_frequency_penalty: 'double',
  gen_ai_request_presence_penalty: 'double', gen_ai_request_seed: 'double',
  gen_ai_request_choice_count: 'double', gen_ai_usage_input_tokens: 'double',
  gen_ai_usage_output_tokens: 'double', gen_ai_usage_total_tokens: 'double',
  gen_ai_embeddings_dimension_count: 'double', gen_ai_request_stop_sequences: 'json',
  gen_ai_request_encoding_formats: 'json', gen_ai_response_finish_reasons: 'json',
  gen_ai_input_messages: 'json', gen_ai_output_messages: 'json',
  gen_ai_system_instructions: 'json', gen_ai_tool_definitions: 'json',
};

export const CLAUDE_VALID_TYPES = {
  timestamp: 'timestamp', user_timestamp: 'double', risk_score: 'double',
  is_anomaly: 'boolean', debug: 'boolean', input_tokens: 'double',
  output_tokens: 'double', total_tokens: 'double', cache_read: 'double',
  cache_creation: 'double', duration_ms: 'double', cost_estimate: 'double',
  incremental_input: 'double', incremental_output: 'double',
  incremental_total: 'double', incremental_cost: 'double', hook_count: 'double',
  max_retries: 'double', retry_attempt: 'double', retry_in_ms: 'double',
  log_index: 'double', has_thinking: 'boolean', is_api_error_message: 'boolean',
  is_meta: 'boolean', is_sidechain: 'boolean', is_snapshot_update: 'boolean',
  has_output: 'boolean', prevented_continuation: 'boolean', is_agent: 'boolean',
};

// Agents-specific additions (mirrors Python AGENTS_KEY_MAPPING)
export const AGENTS_KEY_MAPPING = {
  ...BASE_KEY_MAPPING,
  g1: 'g1', cvs3: 'cvs3', cvs60: 'cvs60', cvs61: 'cvs61',
  cvs62: 'cvs62', cvs63: 'cvs63', cvs64: 'cvs64', cvs65: 'cvs65',
  cvs66: 'cvs66', cvs67: 'cvs67', cvs68: 'cvs68', cvs69: 'cvs69',
  cvs70: 'cvs70', cvs71: 'cvs71', cvs72: 'cvs72', cvs73: 'cvs73',
  cvs74: 'cvs74', cvs75: 'cvs75', cvs76: 'cvs76', cvs77: 'cvs77',
  cvs78: 'cvs78', cvs79: 'cvs79',
};

export const AGENTS_STARTING_INDICES = { ...DEFAULT_STARTING_INDICES };

// ── CVS utilities ─────────────────────────────────────────────────────────────

function getTypeKey(value) {
  if (typeof value === 'boolean') return 'bool';
  if (typeof value === 'number' && Number.isFinite(value)) return 'number';
  return 'string';
}

function getPrefixAndIndexKey(typeKey) {
  if (typeKey === 'bool')   return ['cvb', 'bool'];
  if (typeKey === 'number') return ['cvn', 'number'];
  return ['cvs', 'string'];
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

export function assign(variables, key, value) {
  if (value === null || value === undefined) return;
  if (typeof value === 'number' && Number.isFinite(value)) { variables[key] = value; return; }
  if (typeof value === 'boolean') { variables[key] = value; return; }
  if (typeof value === 'string') {
    const n = Number(value);
    variables[key] = (!isNaN(n) && value.trim() !== '') ? n : value;
    return;
  }
  const s = toStr(value);
  if (s !== null) variables[key] = s;
}

export function reassign(data, keyToCvs = AGENTS_KEY_MAPPING, startingIndices = null, validTypes = null) {
  const indices = { ...AGENTS_STARTING_INDICES, ...(startingIndices ?? {}) };
  const result = {};
  const sourceData = typeof data === 'string' ? (() => { try { return JSON.parse(data); } catch { return {}; } })() : data;

  // Detect source and use appropriate valid types if not provided
  if (!validTypes) {
    const source = sourceData.from_source || sourceData.source || sourceData.cvs200;
    validTypes = (source === 'ClaudeCodeHook') ? CLAUDE_VALID_TYPES : OTEL_AI_VALID_TYPES;
  }

  for (const [key, rawValue] of Object.entries(sourceData)) {
    if (rawValue === null || rawValue === undefined) continue;

    const cvsVar = keyToCvs[key] || (() => {
      const typeKey = getTypeKey(rawValue);
      const [prefix, indexKey] = getPrefixAndIndexKey(typeKey);
      return `${prefix}${indices[indexKey]++}`;
    })();

    const expectedType = validTypes[cvsVar] || validTypes[key];

    // Coerce value based on expected type or CVS prefix
    if (expectedType === 'double') {
      const asNum = Number(rawValue);
      result[cvsVar] = isNaN(asNum) ? 0.0 : asNum;
    } else if (expectedType === 'boolean') {
      if (typeof rawValue === 'string') {
        result[cvsVar] = ['true', '1', 'yes'].includes(rawValue.toLowerCase());
      } else {
        result[cvsVar] = Boolean(rawValue);
      }
    } else if (expectedType === 'json') {
      result[cvsVar] = (typeof rawValue === 'object') ? JSON.stringify(rawValue) : String(rawValue);
    } else if (cvsVar.startsWith('cvs')) {
      result[cvsVar] = (typeof rawValue === 'object') ? JSON.stringify(rawValue) : String(rawValue);
    } else if (cvsVar.startsWith('cvn')) {
      const asNum = Number(rawValue);
      result[cvsVar] = isNaN(asNum) ? 0 : asNum;
    } else if (cvsVar.startsWith('cvb')) {
      result[cvsVar] = Boolean(rawValue);
    } else {
      result[cvsVar] = (typeof rawValue === 'object') ? JSON.stringify(rawValue) : rawValue;
    }
  }
  return result;
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
    cvs3: 'user context', cvs60: 'object type', cvs61: 'source',
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
    cvs3:                     toStr(userCtx),
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
  assign(variables, 'raw', JSON.stringify(span));

  return reassign(variables, keyToCvs, { ...AGENTS_STARTING_INDICES });
}
