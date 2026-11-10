'use strict';

/**
 * Unified capture control for the application SDKs — JS port of Python
 * `anosys_sdk_core/capture.py`.
 *
 * Application SDKs (OpenAI, OpenAI Agents, Anthropic, Claude Agent SDK) are code a
 * developer adds to their own app, so they default to `full` and never read the
 * per-user consent file; their records say `<level>;app` in cvs198 and never claim
 * a policy acceptance. The coding-agent hooks keep `privacy.effectiveLevel`.
 *
 * Precedence (strongest first): ANOSYS_DISABLE=1 -> off; project `.anosys` file
 * (ceiling, only lowers); explicit argument; ANOSYS_COLLECTION_LEVEL; default full.
 *
 * At `metadata` only numbers, booleans and an allowlist of descriptive string
 * columns are sent; every other string, array or object is dropped.
 */

const { CONSENT_COLUMN, FULL, METADATA, OFF, RANK, normalize, projectLevel } = require('./privacy.js');
const { encryptPayload } = require('./encryption.js');

const APP_SOURCE = 'app';

const APP_METADATA_STRING_COLUMNS = new Set([
  'timestamp', 'otel_observed_timestamp', 'otel_record_type', 'otel_schema_url',
  'otel_name', 'otel_trace_id', 'otel_span_id', 'otel_trace_flags',
  'otel_parent_span_id', 'otel_start_time', 'otel_end_time', 'otel_kind',
  'otel_status_code',
  'gen_ai_system', 'gen_ai_provider_name', 'gen_ai_operation_name',
  'gen_ai_request_model', 'gen_ai_response_model', 'gen_ai_response_id',
  'gen_ai_response_finish_reasons', 'gen_ai_output_type',
  'gen_ai_agent_id', 'gen_ai_agent_name', 'gen_ai_conversation_id',
  'gen_ai_data_source_id', 'llm_model', 'llm_token_count',
  'cvs10', 'cvs14', 'cvs16', 'cvs17', 'cvs19',
  CONSENT_COLUMN, 'cvs200',
]);

function normalizeExplicit(level) {
  if (level === null || level === undefined) return null;
  if (typeof level === 'boolean') return level ? FULL : METADATA;
  return normalize(level);
}

/** The level an application SDK collects at, and where it came from. */
function resolveAppLevel(explicit = null, cwd = null) {
  if (['1', 'true', 'yes'].includes(String(process.env.ANOSYS_DISABLE || '').trim().toLowerCase())) {
    return { level: OFF, source: 'ANOSYS_DISABLE' };
  }
  let level = null;
  let source = null;
  for (const [candidate, name] of [
    [normalizeExplicit(explicit), 'argument'],
    [normalize(process.env.ANOSYS_COLLECTION_LEVEL), 'ANOSYS_COLLECTION_LEVEL'],
  ]) {
    if (candidate) { level = candidate; source = name; break; }
  }
  if (!level) { level = FULL; source = 'default'; }
  const project = projectLevel(cwd);
  if (project && RANK[project] < RANK[level]) { level = project; source = '.anosys'; }
  return { level, source };
}

const appConsentValue = (level) => `${level};${APP_SOURCE}`;

/** Keep numbers, booleans and allow-listed string columns; drop everything else. */
function stripContent(record, allowed = APP_METADATA_STRING_COLUMNS) {
  const result = {};
  for (const [key, value] of Object.entries(record)) {
    if (value === null || value === undefined) continue;
    if (typeof value === 'number' || typeof value === 'boolean') result[key] = value;
    else if (allowed.has(key) && (typeof value === 'string' || Array.isArray(value))) result[key] = value;
  }
  return result;
}

/** Apply `level` to one outgoing app record: null at off, content-free at metadata. */
function finalizeAppRecord(record, level, extraAllowed = []) {
  if (level === OFF) return null;
  let result;
  if (level === METADATA) {
    result = stripContent(record, new Set([...APP_METADATA_STRING_COLUMNS, ...extraAllowed]));
  } else {
    result = { ...record };
  }
  delete result.consent;
  result[CONSENT_COLUMN] = appConsentValue(level);
  return result;
}

/** finalizeAppRecord, secret scrubbing, then encryption: the last step before posting an app record. */
function prepareAppRecord(record, level, extraAllowed = []) {
  const result = finalizeAppRecord(record, level, extraAllowed);
  if (result === null) return null;
  const keep = new Set([...APP_METADATA_STRING_COLUMNS, ...extraAllowed]);
  if (level === FULL) {
    const { scrubSecrets } = require('./redaction.js');
    for (const [k, v] of Object.entries(result)) {
      if (!keep.has(k)) {
        result[k] = scrubSecrets(v);
      }
    }
  }
  // content = every column outside the metadata allowlist (descriptive, cvs*, dynamic)
  return encryptPayload(result, keep);
}

let cached = null;
/** resolveAppLevel() for code without an explicit setting, cached per environment and folder. */
function currentAppLevel(cwd = null) {
  const folder = cwd || process.cwd();
  const key = `${process.env.ANOSYS_DISABLE || ''}|${process.env.ANOSYS_COLLECTION_LEVEL || ''}|${folder}`;
  if (!cached || cached.key !== key) cached = { key, value: resolveAppLevel(null, folder) };
  return cached.value;
}

/**
 * Whether an exporter owns `span`: it comes from one of the integration's instrumentation
 * scopes, or it is a GenAI span the application made for that provider. Every other span on
 * a shared tracer provider (HTTP, database, other vendors) is left alone.
 */
function acceptsSpan(span, scopePrefixes, systems) {
  const name = span?.instrumentationScope?.name ?? span?.instrumentationLibrary?.name ?? '';
  if (scopePrefixes.some((p) => name.startsWith(p))) return true;
  const a = span?.attributes ?? {};
  const system = String(a['gen_ai.system'] ?? a['llm.system'] ?? a['gen_ai.provider.name'] ?? '').toLowerCase();
  return systems.includes(system);
}

const USER_CONTEXT_COLUMN = 'cvs5';

/**
 * The cvs5 value for a developer-supplied user context ({ session_id, token }), shared by
 * every application exporter. cvs5 is content: dropped at metadata, encrypted at full.
 */
function userContextValue(ctx) {
  if (!ctx || typeof ctx !== 'object') return null;
  return JSON.stringify({ session_id: ctx.session_id ?? 'unknown_session', token: ctx.token ?? null });
}

module.exports = {
  acceptsSpan,
  USER_CONTEXT_COLUMN,
  userContextValue,
  APP_SOURCE,
  APP_METADATA_STRING_COLUMNS,
  resolveAppLevel,
  appConsentValue,
  stripContent,
  finalizeAppRecord,
  prepareAppRecord,
  currentAppLevel,
};
