/**
 * Client-side encryption utilities for AnoSys SDK.
 *
 * Supports AES-256-CBC encryption of sensitive telemetry columns
 * (prompts, completions, messages, raw context) before sending to AnoSys BE.
 */

import crypto from 'node:crypto';

export const ANOSYS_ENCRYPTION_PREFIX = 'enc:';

export const DEFAULT_ENCRYPTED_COLUMNS = [
  // Primary requested columns
  'llm_input',
  'llm_output',
  'gen_ai_input_messages',
  'gen_ai_output_messages',
  'cvs199',
  // System instructions and legacy system fields
  'gen_ai_system_instructions',
  'llm_system',
  // User prompts and assistant responses across SDKs
  'user_prompt',
  'userPrompt',
  'assistant_text',
  'assistantText',
  'cvs4',
  'cvs5',
  // Multi-turn prompt context and tool execution results
  'last_prompt',
  'cvs24',
  'tool_use_result',
  'cvs26',
  // Additional task / speech prompt fields
  'cvs65',
  'task_description',
  'summary_content',
];

/**
 * Derive a 256-bit (32-byte) key from a passphrase using SHA-256.
 * @param {string} passphrase
 * @returns {Buffer}
 */
export function derive256BitKey(passphrase) {
  return crypto.createHash('sha256').update(String(passphrase), 'utf8').digest();
}

/**
 * Encrypt text with AES-256-CBC using a zero IV and PKCS#7 padding.
 * @param {string} text
 * @param {Buffer} key
 * @returns {string} Base64 ciphertext
 */
export function encrypt(text, key) {
  const iv = Buffer.alloc(16, 0);
  const cipher = crypto.createCipheriv('aes-256-cbc', key, iv);
  let encrypted = cipher.update(String(text), 'utf8', 'base64');
  encrypted += cipher.final('base64');
  return encrypted;
}

/**
 * Decrypt Base64 ciphertext with or without 'enc:' prefix.
 * @param {string} prefixedOrRaw
 * @param {Buffer} key
 * @returns {string} Plaintext utf-8 string
 */
export function decrypt(prefixedOrRaw, key) {
  let rawB64 = prefixedOrRaw;
  if (typeof rawB64 === 'string' && rawB64.startsWith(ANOSYS_ENCRYPTION_PREFIX)) {
    rawB64 = rawB64.slice(ANOSYS_ENCRYPTION_PREFIX.length);
  }
  const iv = Buffer.alloc(16, 0);
  const decipher = crypto.createDecipheriv('aes-256-cbc', key, iv);
  let decrypted = decipher.update(rawB64, 'base64', 'utf8');
  decrypted += decipher.final('utf8');
  return decrypted;
}

/**
 * Retrieve the encryption key from ANOSYS_ENCRYPTION_KEY env var if present and not null.
 * @returns {string|null}
 */
export function getEncryptionKey() {
  const key = process.env.ANOSYS_ENCRYPTION_KEY;
  if (!key || !key.trim()) return null;
  const lower = key.trim().toLowerCase();
  if (lower === 'null' || lower === 'none' || lower === 'undefined') return null;
  return key.trim();
}

/**
 * Retrieve columns to encrypt.
 * If ANOSYS_ENCRYPTED_COLUMNS or ANOSYS_ENCRYPTES_COLUMNS is provided,
 * it overrides the default list.
 * @returns {Set<string>}
 */
export function getTargetColumns() {
  const raw = process.env.ANOSYS_ENCRYPTED_COLUMNS || process.env.ANOSYS_ENCRYPTES_COLUMNS;
  if (raw && raw.trim()) {
    const cols = new Set(
      raw
        .split(',')
        .map(c => c.trim())
        .filter(Boolean)
    );
    if (cols.size > 0) return cols;
  }
  return new Set(DEFAULT_ENCRYPTED_COLUMNS);
}

/**
 * Encrypt targeted fields in a payload dict (or list of dicts) if ANOSYS_ENCRYPTION_KEY is configured.
 * Warns on non-string values and skips them.
 * @param {any} data
 * @returns {any}
 */
export function encryptPayload(data) {
  if (data === null || data === undefined) return data;

  if (Array.isArray(data)) {
    return data.map(item => encryptPayload(item));
  }

  if (typeof data !== 'object') {
    return data;
  }

  const keyStr = getEncryptionKey();
  if (!keyStr) {
    return data;
  }

  let derivedKey;
  try {
    derivedKey = derive256BitKey(keyStr);
  } catch (e) {
    console.warn(`[ANOSYS] Warning: Failed to derive encryption key: ${e.message}`);
    return data;
  }

  const targetColumns = getTargetColumns();
  const result = { ...data };

  for (const col of targetColumns) {
    if (!(col in result)) continue;
    const val = result[col];
    if (val === null || val === undefined) continue;
    if (typeof val !== 'string') {
      console.warn(`[ANOSYS] Warning: Column '${col}' contains non-string data (type: ${typeof val}). Skipping encryption.`);
      continue;
    }
    if (val.startsWith(ANOSYS_ENCRYPTION_PREFIX)) {
      continue;
    }
    try {
      result[col] = `${ANOSYS_ENCRYPTION_PREFIX}${encrypt(val, derivedKey)}`;
    } catch (e) {
      console.warn(`[ANOSYS] Warning: Failed to encrypt column '${col}': ${e.message}`);
    }
  }

  return result;
}
