'use strict';

/**
 * Client-side encryption of content columns (format `enc2`) — JS port of
 * Python `anosys_sdk_core/encryption.py`. Both produce identical ciphertext,
 * and the AnoSys console decrypts it in the browser.
 *
 *   k_enc, k_nonce = PBKDF2-HMAC-SHA256(passphrase, "anosys-enc2:" + salt, 600,000, 64 bytes)
 *   nonce          = HMAC-SHA256(k_nonce, plaintext)[:12]
 *   value          = "enc2:" + base64(nonce + AES-256-GCM(k_enc, nonce, plaintext) + tag)
 *
 * Deterministic: the same value encrypts identically in every column and table
 * of a workspace, so GROUP BY, COUNT DISTINCT and joins keep working.
 */

const crypto = require('node:crypto');

const ANOSYS_ENCRYPTION_PREFIX = 'enc2:';
const KDF_ITERATIONS = 600000;
const KDF_SALT_PREFIX = 'anosys-enc2:';
const DEFAULT_SALT = 'anosys';

const DEFAULT_ENCRYPTED_COLUMNS = [
  // prompts, completions and messages
  'llm_input', 'llm_output', 'llm_system',
  'gen_ai_input_messages', 'gen_ai_output_messages', 'gen_ai_system_instructions',
  'user_prompt', 'userPrompt', 'assistant_text', 'assistantText', 'last_prompt',
  'cvs4', 'cvs5', 'cvs24',
  // raw records and attribute blobs (they repeat the content)
  'cvs199', 'cvs18', 'otel_events',
  // tool and file data
  'tool_use_result', 'cvs26', 'commands', 'written_paths', 'file_states',
  'ide_diagnostics', 'cvs30', 'file_attachments', 'hook_specific_output', 'mcp_meta',
  // model-written summaries, task text and errors
  'custom_title', 'ai_title', 'cvs40', 'cvs41', 'agent_description', 'cvs35',
  'summary_content', 'task_description', 'cvs65', 'origami_summary',
  'status_message', 'error_details', 'api_error', 'error_obj', 'cvs25', 'cause',
  'research',
];

// Columns stored as JSON in BigQuery: an encrypted value must stay valid JSON
const JSON_COLUMNS = new Set([
  'tool_use_result', 'error_obj', 'ide_diagnostics', 'hook_specific_output',
  'file_states', 'worktree_session', 'staged_nodes', 'iterations', 'research',
  'mcp_meta', 'summarize_metadata', 'compact_metadata', 'microcompact_metadata',
  'cause', 'api_error', 'origin', 'image_paste_ids', 'file_attachments',
  'written_paths', 'commands', 'server_tool_use',
  'otel_resource', 'otel_attributes', 'otel_events', 'otel_links', 'otel_labels',
  'otel_log_attributes', 'llm_tools', 'llm_token_count', 'llm_invocation_parameters',
  'gen_ai_input_messages', 'gen_ai_output_messages', 'gen_ai_system_instructions',
  'gen_ai_tool_definitions', 'gen_ai_request_stop_sequences',
  'gen_ai_request_encoding_formats', 'gen_ai_response_finish_reasons',
  'otel_histogram_bucket_counts', 'otel_histogram_bucket_bounds',
]);

const keyCache = new Map();
let warnedDefaultSalt = false;

function warn(message) {
  console.warn(message);
}

/** Workspace salt from ANOSYS_ENCRYPTION_SALT (default "anosys", warned once). */
function getEncryptionSalt() {
  const salt = (process.env.ANOSYS_ENCRYPTION_SALT || '').trim();
  if (salt) return salt;
  if (!warnedDefaultSalt) {
    warnedDefaultSalt = true;
    warn('[ANOSYS] ANOSYS_ENCRYPTION_SALT is not set; using the default salt. Set it to the salt shown in the AnoSys console.');
  }
  return DEFAULT_SALT;
}

/** Derive { kEnc, kNonce } (32 bytes each) from a passphrase and workspace salt. */
function deriveKeys(passphrase, salt = null) {
  const s = salt ?? getEncryptionSalt();
  const cacheKey = `${passphrase}\u0000${s}`;
  if (!keyCache.has(cacheKey)) {
    const material = crypto.pbkdf2Sync(
      Buffer.from(passphrase, 'utf8'),
      Buffer.from(KDF_SALT_PREFIX + s, 'utf8'),
      KDF_ITERATIONS, 64, 'sha256',
    );
    keyCache.set(cacheKey, { kEnc: material.subarray(0, 32), kNonce: material.subarray(32) });
  }
  return keyCache.get(cacheKey);
}

/** The 32-byte encryption key for a passphrase (kept for API compatibility). */
function derive256BitKey(passphrase, salt = null) {
  return deriveKeys(passphrase, salt).kEnc;
}

/** Encrypt text deterministically; returns `enc2:` + base64(nonce + ciphertext + tag). */
function encrypt(text, keys) {
  if (!keys || !keys.kEnc || !keys.kNonce) throw new TypeError('encrypt needs both keys: use deriveKeys(passphrase, salt)');
  const data = Buffer.from(text, 'utf8');
  const nonce = crypto.createHmac('sha256', keys.kNonce).update(data).digest().subarray(0, 12);
  const cipher = crypto.createCipheriv('aes-256-gcm', keys.kEnc, nonce);
  const sealed = Buffer.concat([cipher.update(data), cipher.final(), cipher.getAuthTag()]);
  return ANOSYS_ENCRYPTION_PREFIX + Buffer.concat([nonce, sealed]).toString('base64');
}

/** Decrypt an `enc2:` value (also accepts the JSON-string form `"enc2:..."`). Throws if tampered. */
/** The AES key from deriveKeys(), derive256BitKey() or a passphrase. */
function decryptionKey(keys) {
  if (Buffer.isBuffer(keys)) return keys;
  if (typeof keys === 'string') return deriveKeys(keys).kEnc;
  if (keys && keys.kEnc) return keys.kEnc;
  throw new TypeError('keys must be deriveKeys(...), derive256BitKey(...) or the passphrase');
}

/**
 * Decrypt an `enc2:` value (also the JSON-string form). `keys` may be deriveKeys(passphrase, salt),
 * derive256BitKey(passphrase, salt) or the passphrase itself (salt from ANOSYS_ENCRYPTION_SALT).
 */
function decrypt(value, keys) {
  let v = value;
  if (v.startsWith('"')) v = JSON.parse(v);
  if (v.startsWith(ANOSYS_ENCRYPTION_PREFIX)) v = v.slice(ANOSYS_ENCRYPTION_PREFIX.length);
  const raw = Buffer.from(v, 'base64');
  const nonce = raw.subarray(0, 12);
  const tag = raw.subarray(raw.length - 16);
  const body = raw.subarray(12, raw.length - 16);
  const decipher = crypto.createDecipheriv('aes-256-gcm', decryptionKey(keys), nonce);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(body), decipher.final()]).toString('utf8');
}

/** The passphrase from ANOSYS_ENCRYPTION_KEY, or null when encryption is off. */
function getEncryptionKey() {
  const key = process.env.ANOSYS_ENCRYPTION_KEY;
  if (!key || !key.trim() || ['null', 'none', 'undefined'].includes(key.trim().toLowerCase())) return null;
  return key.trim();
}

/** Columns to encrypt: ANOSYS_ENCRYPTED_COLUMNS (or the typo alias) when set, else the defaults. */
/** ANOSYS_ENCRYPTED_COLUMNS (or the ANOSYS_ENCRYPTES_COLUMNS alias), when set. */
function explicitTargetColumns() {
  const raw = process.env.ANOSYS_ENCRYPTED_COLUMNS || process.env.ANOSYS_ENCRYPTES_COLUMNS;
  if (raw && raw.trim()) {
    const cols = raw.split(',').map(c => c.trim()).filter(Boolean);
    if (cols.length) return new Set(cols);
  }
  return null;
}

/**
 * Columns to encrypt (same rules as Python get_target_columns):
 * ANOSYS_ENCRYPTED_COLUMNS when set; with `keep` (the integration's metadata
 * allowlist), every other column holding text, an array or an object; otherwise
 * DEFAULT_ENCRYPTED_COLUMNS. Numbers and booleans stay readable.
 */
function getTargetColumns(data = null, keep = null) {
  const explicit = explicitTargetColumns();
  if (explicit) {
    if (data && typeof data === 'object') {
      for (const mirror of ['cvs199', 'cvs18', 'otel_events']) {
        if (mirror in data) explicit.add(mirror);
      }
    }
    return explicit;
  }
  if (keep && data) {
    const kept = keep instanceof Set ? keep : new Set(keep);
    return new Set(Object.entries(data)
      .filter(([k, v]) => v !== null && v !== undefined && !kept.has(k) && k !== 'cvs198'
        && typeof v !== 'number' && typeof v !== 'boolean')
      .map(([k]) => k));
  }
  return new Set(DEFAULT_ENCRYPTED_COLUMNS);
}

function isEncrypted(value) {
  return typeof value === 'string'
    && (value.startsWith(ANOSYS_ENCRYPTION_PREFIX) || value.startsWith(`"${ANOSYS_ENCRYPTION_PREFIX}`));
}

/** Encrypt one column value; objects and arrays are serialized first. */
function encryptValue(column, value, keys) {
  if (value === null || value === undefined || isEncrypted(value)) return value;
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  const sealed = encrypt(text, keys);
  return JSON_COLUMNS.has(column) ? JSON.stringify(sealed) : sealed;
}

/**
 * Encrypt the targeted columns of a payload (or array of payloads) when
 * ANOSYS_ENCRYPTION_KEY is set. Fails closed: a column that cannot be
 * encrypted is dropped rather than sent in plaintext.
 */
function encryptPayload(data, keep = null) {
  if (data === null || data === undefined) return data;
  if (Array.isArray(data)) return data.map((item) => encryptPayload(item, keep));
  if (typeof data !== 'object') return data;

  const passphrase = getEncryptionKey();
  if (!passphrase) return data;

  let keys = null;
  try {
    keys = deriveKeys(passphrase);
  } catch (e) {
    warn(`[ANOSYS] Warning: Failed to derive encryption key (${e.message}); encrypted columns are dropped.`);
  }
  for (const col of getTargetColumns(data, keep)) {
    if (!(col in data) || data[col] === null || data[col] === undefined) continue;
    if (!keys) { data[col] = null; continue; }
    try {
      data[col] = encryptValue(col, data[col], keys);
    } catch (e) {
      warn(`[ANOSYS] Warning: Failed to encrypt column '${col}' (${e.message}); it is dropped.`);
      data[col] = null;
    }
  }
  return data;
}

module.exports = {
  ANOSYS_ENCRYPTION_PREFIX,
  KDF_ITERATIONS,
  KDF_SALT_PREFIX,
  DEFAULT_SALT,
  DEFAULT_ENCRYPTED_COLUMNS,
  JSON_COLUMNS,
  getEncryptionSalt,
  deriveKeys,
  derive256BitKey,
  encrypt,
  decrypt,
  getEncryptionKey,
  getTargetColumns,
  encryptValue,
  encryptPayload,
};
