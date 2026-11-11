'use strict';

/** Secret-shaped strings scrubbed from hook content even at `full` (best effort). Mirrors Python redaction.py. */

const SECRET_REPLACEMENT = '[SECRET]';

const SECRET_PATTERNS = [
  /sk-ant-[A-Za-z0-9_-]{20,}/g,
  /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}/g,
  /\bAKIA[0-9A-Z]{16}\b/g,
  /\bASIA[0-9A-Z]{16}\b/g,
  /\bgh[pousr]_[A-Za-z0-9]{30,}\b/g,
  /\bgithub_pat_[A-Za-z0-9_]{30,}\b/g,
  /\bglpat-[A-Za-z0-9_-]{20,}\b/g,
  /\bxox[abpr]-[A-Za-z0-9-]{10,}\b/g,
  /\bAIza[0-9A-Za-z_-]{35}\b/g,
  /-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----/g,
  /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g,
];
const URL_BASIC_AUTH = /(:\/\/[^/\s:@]+:)[^/\s@]{6,}(?=@)/g;
// key = value assignments: keep the key, replace the value (handles plain and JSON-escaped quotes)
const ASSIGNMENT = /((?:api[_-]?key|apikey|secret|password|passwd|token|authorization)\\?["']?\s*[:=]\s*\\?["']?(?:bearer\s+)?)[A-Za-z0-9_\-/+=.]{12,}/gi;

/** Replace secret-shaped substrings in a string, or in every string inside an object/array. */
function scrubSecrets(value) {
  if (typeof value === 'string') {
    let out = value;
    for (const pattern of SECRET_PATTERNS) out = out.replace(pattern, SECRET_REPLACEMENT);
    out = out.replace(URL_BASIC_AUTH, (_, prefix) => prefix + SECRET_REPLACEMENT);
    return out.replace(ASSIGNMENT, (_, prefix) => prefix + SECRET_REPLACEMENT);
  }
  if (Array.isArray(value)) return value.map(scrubSecrets);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, scrubSecrets(v)]));
  }
  return value;
}

// PII patterns (pii_redaction), same as Python redaction.PATTERNS
const PII_PATTERNS = {
  email: /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g,
  phone: /\b\d{3}[-.]?\d{3}[-.]?\d{4}\b/g,
  ssn: /\b\d{3}-\d{2}-\d{4}\b/g,
  credit_card: /\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b/g,
  api_key: /\b(?:sk|pk|rk)-[A-Za-z0-9_-]{20,}|\bapi[-_]?key[A-Za-z0-9_-]{20,}/gi,
};
const REDACTED = '[REDACTED]';

/** Replace PII-shaped substrings (Python redact_string). Best effort. */
function redactPii(text, patterns = null) {
  if (typeof text !== 'string') return text;
  let out = text;
  for (const name of patterns ?? Object.keys(PII_PATTERNS)) {
    if (PII_PATTERNS[name]) out = out.replace(PII_PATTERNS[name], REDACTED);
  }
  return out;
}

module.exports = {
  REDACTED,
  redactPii,
  SECRET_REPLACEMENT,
  scrubSecrets,
};
