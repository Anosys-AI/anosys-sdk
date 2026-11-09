/** Secret-shaped strings scrubbed from hook content even at `full` (best effort). Mirrors Python redaction.py. */

export const SECRET_REPLACEMENT = '[SECRET]';

const SECRET_PATTERNS = [
  /sk-ant-[A-Za-z0-9_-]{20,}/g,
  /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}/g,
  /\bAKIA[0-9A-Z]{16}\b/g,
  /\bASIA[0-9A-Z]{16}\b/g,
  /\bghp_[A-Za-z0-9]{30,}\b/g,
  /\bgithub_pat_[A-Za-z0-9_]{30,}\b/g,
  /\bxox[abpr]-[A-Za-z0-9-]{10,}\b/g,
  /\bAIza[0-9A-Za-z_-]{35}\b/g,
  /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g,
  /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g,
];
// key = value assignments: keep the key, replace the value
const ASSIGNMENT = /((?:api[_-]?key|apikey|secret|password|passwd|token|authorization)["']?\s*[:=]\s*["']?(?:bearer\s+)?)[A-Za-z0-9_\-/+=.]{12,}/gi;

/** Replace secret-shaped substrings in a string, or in every string inside an object/array. */
export function scrubSecrets(value) {
  if (typeof value === 'string') {
    let out = value;
    for (const pattern of SECRET_PATTERNS) out = out.replace(pattern, SECRET_REPLACEMENT);
    return out.replace(ASSIGNMENT, (_, prefix) => prefix + SECRET_REPLACEMENT);
  }
  if (Array.isArray(value)) return value.map(scrubSecrets);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, scrubSecrets(v)]));
  }
  return value;
}
