// CVS starting indices — aligned with Python DEFAULT_STARTING_INDICES
export const DEFAULT_STARTING_INDICES = { string: 100, number: 3, bool: 1 };

// Base key-to-CVS mapping — aligned with Python BASE_KEY_MAPPING in models.py
export const BASE_KEY_MAPPING = {
  // Schema and metadata
  custom_mapping:             'otel_schema_url',
  otel_observed_timestamp:    'otel_observed_timestamp',
  otel_record_type:           'otel_record_type',

  // Timing
  cvn1:                       'cvn1',
  cvn2:                       'cvn2',
  otel_duration_ms:           'otel_duration_ms',

  // Trace/Span identifiers
  name:                       'otel_name',
  trace_id:                   'otel_trace_id',
  span_id:                    'otel_span_id',
  trace_state:                'otel_trace_flags',
  parent_id:                  'otel_parent_span_id',
  start_time:                 'otel_start_time',
  end_time:                   'otel_end_time',
  kind:                       'otel_kind',

  // Status
  status:                     'otel_status',
  status_code:                'otel_status_code',
  resp_id:                    'otel_status_message',

  // Resources
  otel_resource:              'otel_resource',

  // Gen AI — general
  'gen_ai.system':                        'gen_ai_system',
  'gen_ai.provider.name':                 'gen_ai_provider_name',
  'gen_ai.operation.name':                'gen_ai_operation_name',
  'server.address':                       'server_address',
  'server.port':                          'server_port',
  'error.type':                           'error_type',

  // Gen AI — request
  'gen_ai.request.model':                 'gen_ai_request_model',
  'gen_ai.request.temperature':           'gen_ai_request_temperature',
  'gen_ai.request.top_p':                 'gen_ai_request_top_p',
  'gen_ai.request.top_k':                 'gen_ai_request_top_k',
  'gen_ai.request.max_tokens':            'gen_ai_request_max_tokens',
  'gen_ai.request.frequency_penalty':     'gen_ai_request_frequency_penalty',
  'gen_ai.request.presence_penalty':      'gen_ai_request_presence_penalty',
  'gen_ai.request.stop_sequences':        'gen_ai_request_stop_sequences',
  'gen_ai.request.seed':                  'gen_ai_request_seed',
  'gen_ai.request.choice.count':          'gen_ai_request_choice_count',
  'gen_ai.request.encoding_formats':      'gen_ai_request_encoding_formats',

  // Gen AI — response & usage
  'gen_ai.response.model':                'gen_ai_response_model',
  'gen_ai.response.id':                   'gen_ai_response_id',
  'gen_ai.response.finish_reasons':       'gen_ai_response_finish_reasons',
  'gen_ai.usage.input_tokens':            'gen_ai_usage_input_tokens',
  'gen_ai.usage.output_tokens':           'gen_ai_usage_output_tokens',
  'gen_ai.usage.total_tokens':            'gen_ai_usage_total_tokens',
  'gen_ai.output.type':                   'gen_ai_output_type',

  // Gen AI — content
  'gen_ai.input.messages':               'gen_ai_input_messages',
  'gen_ai.output.messages':              'gen_ai_output_messages',
  'gen_ai.system_instructions':          'gen_ai_system_instructions',
  'gen_ai.tool.definitions':             'gen_ai_tool_definitions',

  // Gen AI — agents & frameworks
  'gen_ai.agent.id':                     'gen_ai_agent_id',
  'gen_ai.agent.name':                   'gen_ai_agent_name',
  'gen_ai.agent.description':            'gen_ai_agent_description',
  'gen_ai.conversation.id':              'gen_ai_conversation_id',
  'gen_ai.data_source.id':               'gen_ai_data_source_id',
  'gen_ai.embeddings.dimension.count':   'gen_ai_embeddings_dimension_count',

  // Legacy LLM fields
  llm_tools:                'llm_tools',
  llm_system:               'llm_system',
  llm_input:                'llm_input',
  llm_output:               'llm_output',
  llm_model:                'llm_model',
  llm_invocation_parameters:'llm_invocation_parameters',
  llm_token_count:          'llm_token_count',
  llm_input_messages:       'cvs1',
  llm_output_messages:      'cvs2',

  // Decorator-specific
  input:          'cvs1',
  output:         'cvs2',
  error:          'cvs3',
  caller:         'cvs4',
  error_type:     'cvs10',
  error_message:  'cvs11',
  error_stack:    'cvs12',

  // Source tracking
  raw:         'cvs199',
  from_source: 'cvs200',
  source:      'cvs200',
  is_streaming:'cvb2',
};

export const OPENAI_KEY_MAPPING = { ...BASE_KEY_MAPPING };
export const OPENAI_STARTING_INDICES = { ...DEFAULT_STARTING_INDICES };

// ── CVS type utilities ────────────────────────────────────────────────────────

export function getTypeKey(value) {
  if (typeof value === 'boolean') return 'bool';
  if (typeof value === 'number' && Number.isFinite(value)) return 'number';
  return 'string';
}

function getPrefixAndIndexKey(typeKey) {
  switch (typeKey) {
    case 'bool':   return ['cvb', 'bool'];
    case 'number': return ['cvn', 'number'];
    default:       return ['cvs', 'string'];
  }
}

function stringifyIfNeeded(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === 'object') {
    try { return JSON.stringify(value); } catch { return String(value); }
  }
  return value;
}

export function assign(variables, key, value) {
  if (value === null || value === undefined) return;

  if (typeof value === 'number' && Number.isFinite(value)) {
    variables[key] = value;
    return;
  }
  if (typeof value === 'boolean') {
    variables[key] = value;
    return;
  }
  if (typeof value === 'string') {
    const asNum = Number(value);
    if (!isNaN(asNum) && value.trim() !== '') {
      variables[key] = asNum;
      return;
    }
    variables[key] = value;
    return;
  }
  variables[key] = stringifyIfNeeded(value);
}

export function reassign(data, keyToCvs = OPENAI_KEY_MAPPING, startingIndices = null) {
  const indices = { ...OPENAI_STARTING_INDICES, ...(startingIndices ?? {}) };
  const result = {};

  const source = typeof data === 'string' ? (() => { try { return JSON.parse(data); } catch { return {}; } })() : data;

  for (const [key, rawValue] of Object.entries(source)) {
    if (rawValue === null || rawValue === undefined) continue;

    const value = stringifyIfNeeded(rawValue);
    if (value === null) continue;

    if (keyToCvs[key]) {
      result[keyToCvs[key]] = value;
      continue;
    }

    const typeKey = getTypeKey(rawValue);
    const [prefix, indexKey] = getPrefixAndIndexKey(typeKey);
    const idx = indices[indexKey]++;
    result[`${prefix}${idx}`] = value;
  }

  return result;
}
