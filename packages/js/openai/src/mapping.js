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
  'server.address':                       'cvs14',
  'server.port':                          'cvn3',
  'error.type':                           'cvs10',

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
  llm_input_messages:       'gen_ai_input_messages',
  llm_output_messages:      'gen_ai_output_messages',

  // Decorator-specific
  input:          'llm_input',
  output:         'llm_output',
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
  is_agent:    'cvb1',
  events:      'otel_events',
  user_context:'cvs5',
  llm_model_name: 'cvs16',
  'gen_ai.request.tool_choice': 'cvs15',
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
    // Strict number check: only convert if it's purely a decimal number string.
    // This prevents partial parsing of hex IDs (e.g. "3222869c...") as integers.
    if (/^-?\d+(\.\d+)?$/.test(value.trim())) {
      const asNum = Number(value);
      if (!isNaN(asNum)) {
        variables[key] = asNum;
        return;
      }
    }
    variables[key] = value;
    return;
  }
  variables[key] = stringifyIfNeeded(value);
}

export function reassign(data, keyToCvs = OPENAI_KEY_MAPPING, startingIndices = null, validTypes = null) {
  const indices = { ...OPENAI_STARTING_INDICES, ...(startingIndices ?? {}) };
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
      const idx = indices[indexKey]++;
      return `${prefix}${idx}`;
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
      if (typeof rawValue === 'object') {
        result[cvsVar] = JSON.stringify(rawValue);
      } else {
        result[cvsVar] = String(rawValue);
      }
    } else if (cvsVar.startsWith('cvn')) {
      const asNum = Number(rawValue);
      result[cvsVar] = isNaN(asNum) ? 0 : asNum;
    } else if (cvsVar.startsWith('cvb')) {
      result[cvsVar] = Boolean(rawValue);
    } else {
      result[cvsVar] = stringifyIfNeeded(rawValue);
    }
  }

  return result;
}
