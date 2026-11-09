'use strict';

/**
 * Collection levels and consent — JS port of Python `anosys_sdk_core/privacy.py`.
 *
 * Coding-agent hooks collect `metadata` by default. `full` content needs a
 * consent record for the current POLICY_VERSION. Precedence (strongest first):
 * ANOSYS_DISABLE=1 → off; explicit level (CLI flag); consent file
 * ~/.anosys/consent.json; ANOSYS_COLLECTION_LEVEL; legacy REDACTION=true →
 * metadata; default metadata. A project `.anosys` file can only lower the level.
 */

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const OFF = 'off';
const METADATA = 'metadata';
const FULL = 'full';
const LEVELS = [OFF, METADATA, FULL];
const RANK = { off: 0, metadata: 1, full: 2 };

const POLICY_VERSION = '2026-11-09';
const POLICY_URL = 'https://github.com/anosys-ai/anosys-sdk/blob/main/PRIVACY.md';
// Every record carries its collection level and accepted policy version in
// cvs198, a column present in every AnoSys schema (no migration needed).
const CONSENT_COLUMN = 'cvs198';
const CONSENT_FIELD = CONSENT_COLUMN; // older name, same column
const PROJECT_FILE = '.anosys';

function consentPath() {
  const custom = (process.env.ANOSYS_CONSENT_FILE || '').trim();
  if (custom) return custom.replace(/^~(?=$|\/)/, os.homedir());
  return path.join(os.homedir(), '.anosys', 'consent.json');
}

function normalize(level) {
  if (level === null || level === undefined) return null;
  const l = String(level).trim().toLowerCase();
  return LEVELS.includes(l) ? l : null;
}

/** Write a file readable only by the current user (0600). */
function writePrivateFile(file, content) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.tmp`; // unique per process
  fs.writeFileSync(tmp, content, { encoding: 'utf8', mode: 0o600 });
  fs.chmodSync(tmp, 0o600);
  fs.renameSync(tmp, file);
}

/** The stored privacy settings ({} when none). Never throws. */
function readConsent() {
  try {
    const data = JSON.parse(fs.readFileSync(consentPath(), 'utf8'));
    return data && typeof data === 'object' ? data : {};
  } catch {
    return {};
  }
}

/** Store the chosen level; `full` needs acceptPolicy === POLICY_VERSION. */
function writeConsent(level, method, acceptPolicy = null) {
  const l = normalize(level);
  if (!l) throw new Error(`level must be one of ${LEVELS.join(', ')}`);
  if (l === FULL && acceptPolicy !== POLICY_VERSION) {
    throw new Error(`full collection needs acceptance of policy ${POLICY_VERSION} (${POLICY_URL})`);
  }
  const now = new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
  const record = {
    level: l,
    policy_version: l === FULL ? POLICY_VERSION : null,
    accepted_at: l === FULL ? now : null,
    method,
    updated_at: now,
  };
  writePrivateFile(consentPath(), JSON.stringify(record, null, 2));
  return record;
}

function projectLevel(cwd) {
  let dir = path.resolve(cwd || process.cwd());
  for (;;) {
    const candidate = path.join(dir, PROJECT_FILE);
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
      try {
        for (const line of fs.readFileSync(candidate, 'utf8').split(/\r?\n/)) {
          const [key, ...rest] = line.split('=');
          if (key.trim() === 'level') return normalize(rest.join('='));
        }
      } catch { /* unreadable project file: ignore */ }
      return null;
    }
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

/** The level to collect at and where it came from: { level, source }. */
function effectiveLevel(explicit = null, cwd = null) {
  if (['1', 'true', 'yes'].includes((process.env.ANOSYS_DISABLE || '').trim().toLowerCase())) {
    return { level: OFF, source: 'ANOSYS_DISABLE' };
  }
  const consent = readConsent();
  let level = null;
  let source = null;
  for (const [candidate, name] of [
    [normalize(explicit), 'flag'],
    [normalize(consent.level), 'consent'],
    [normalize(process.env.ANOSYS_COLLECTION_LEVEL), 'ANOSYS_COLLECTION_LEVEL'],
  ]) {
    if (candidate) { level = candidate; source = name; break; }
  }
  if (!level) {
    if ((process.env.REDACTION || '').trim().toLowerCase() === 'true') {
      level = METADATA; source = 'REDACTION';
    } else {
      level = METADATA; source = 'default';
    }
  }
  if (level === FULL && consent.policy_version !== POLICY_VERSION) {
    level = METADATA; source += ' (no consent)';
  }
  const project = projectLevel(cwd);
  if (project && RANK[project] < RANK[level]) {
    level = project; source = PROJECT_FILE;
  }
  return { level, source };
}

/** The consent field stored on every hook record, e.g. `full;2026-11-09`. */
function consentValue(level) {
  return level === FULL ? `${FULL};${POLICY_VERSION}` : `${level};none`;
}

// Same allowlist as Python BASE_METADATA_FIELDS
const BASE_METADATA_FIELDS = new Set([
  'timestamp', 'user_timestamp', 'event_id', 'eventId', 'uuid', 'event_type',
  'event_source_name', 'debug', 'session_id', 'sessionId', 'log_index',
  'integration_version', 'consent', 'cvs198',
  'project', 'cwd', 'git_branch', 'os_user', 'slug', 'version', 'entrypoint',
  'original_branch', 'original_head_commit', 'worktree_branch', 'worktree_name',
  'worktree_path', 'worktree_original_cwd', 'tmux_session_name',
  'pr_url', 'pr_repository', 'pr_number',
  'model', 'primary_model', 'model_provider', 'advisor_model', 'service_tier',
  'usage_speed', 'inference_geo', 'permission_mode', 'permissionMode',
  'sandbox_mode', 'session_mode', 'user_type', 'subtype', 'level',
  'stop_reason', 'stop_reason_top', 'stop_sequence',
  'raw_uuid', 'raw_message_id', 'parent_uuid', 'logical_parent_uuid',
  'assistant_msg_id', 'leaf_uuid', 'request_id', 'prompt_id', 'tool_use_id',
  'parent_tool_use_id', 'source_tool_use_id', 'source_tool_assistant_uuid',
  'agent_id', 'agent_type', 'agent_map_name', 'agent_map_color', 'team_name',
  'collapse_id', 'summary_uuid', 'first_archived_uuid', 'last_archived_uuid',
  'hook_name', 'hook_event', 'hook_label', 'task_status', 'task_type',
  'session_tag', 'attribution_surface',
  'input_tokens', 'output_tokens', 'total_tokens', 'cache_read',
  'cache_creation', 'reasoning_tokens', 'cost_estimate', 'incremental_input',
  'incremental_output', 'incremental_total', 'incremental_cost',
  'incremental_cache_read', 'incremental_cache_creation', 'duration_ms',
  'time_saved_ms', 'ttft_ms', 'otps', 'hook_duration_ms', 'turn_duration_ms',
  'tool_duration_ms', 'classifier_duration_ms', 'hook_count', 'max_retries',
  'retry_attempt', 'retry_in_ms', 'exit_code', 'replaced_results_count',
  'last_spawn_tokens', 'prompt_count', 'prompt_count_at_last_commit',
  'permission_prompt_count', 'permission_prompt_count_at_last_commit',
  'escape_count', 'escape_count_at_last_commit', 'web_search_requests',
  'web_fetch_requests', 'budget_tokens', 'budget_limit', 'budget_nudges',
  'message_count', 'tool_count', 'classifier_count', 'config_write_count',
  'tools_used',
  'has_thinking', 'is_api_error_message', 'is_meta', 'is_sidechain',
  'is_snapshot_update', 'has_output', 'prevented_continuation', 'is_agent',
  'hook_based', 'armed', 'is_synthetic', 'is_visible_in_transcript_only',
  'is_virtual', 'is_compact_summary', 'is_p50',
  'cvs200',
]);

/** Keep the fields allowed at `level` (allowlist) and stamp the consent field. */
function filterFields(record, level, metadataFields) {
  if (level === OFF) return {};
  let result;
  if (level === FULL) {
    result = { ...record };
  } else {
    const allowed = metadataFields instanceof Set ? metadataFields : new Set(metadataFields);
    result = Object.fromEntries(Object.entries(record).filter(([k]) => allowed.has(k)));
  }
  delete result.consent;
  result[CONSENT_COLUMN] = consentValue(level);
  return result;
}

/** Set cvs198 for a hook record (level from effectiveLevel when omitted). */
function attachConsent(record, level = null) {
  if (!level) level = effectiveLevel().level;
  delete record.consent;
  record[CONSENT_COLUMN] = consentValue(level);
  return record;
}

module.exports = {
  RANK,
  normalize,
  projectLevel,
  OFF,
  METADATA,
  FULL,
  LEVELS,
  POLICY_VERSION,
  POLICY_URL,
  CONSENT_FIELD,
  CONSENT_COLUMN,
  PROJECT_FILE,
  BASE_METADATA_FIELDS,
  consentPath,
  writePrivateFile,
  readConsent,
  writeConsent,
  effectiveLevel,
  consentValue,
  filterFields,
  attachConsent,
};
