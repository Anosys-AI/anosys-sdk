'use strict';

/**
 * Key-to-column mapping shared by the JS application SDKs — the JS side of
 * Python `anosys_sdk_core/models.py` and `util/batching.py`.
 *
 * The mapping tables come from `mappings.json`, which equals the repository
 * fixture `packages/fixtures/mappings.json` generated from the Python tables;
 * tests on both sides compare against that fixture, so Python and JS cannot drift.
 */

const tables = require('./mappings.json');
const { allocateSlot, warnDropped } = require('./slots.js');

const BASE_KEY_MAPPING = Object.freeze({ ...tables.BASE_KEY_MAPPING });
const CLAUDE_KEY_MAPPING = Object.freeze({ ...tables.CLAUDE_KEY_MAPPING });
const AGENTS_KEY_MAPPING = Object.freeze({ ...tables.AGENTS_KEY_MAPPING });
const OTEL_AI_VALID_TYPES = Object.freeze({ ...tables.OTEL_AI_VALID_TYPES });
const CLAUDE_VALID_TYPES = Object.freeze({ ...tables.CLAUDE_VALID_TYPES });
const DEFAULT_STARTING_INDICES = Object.freeze({ ...tables.DEFAULT_STARTING_INDICES });
const CLAUDE_STARTING_INDICES = Object.freeze({ ...tables.CLAUDE_STARTING_INDICES });

/** Type category of a value: 'bool', 'number' or 'string' (as Python _get_type_key). */
function getTypeKey(value) {
  if (typeof value === 'boolean') return 'bool';
  if (typeof value === 'number' && Number.isFinite(value)) return 'number';
  return 'string';
}

function getPrefixAndIndexKey(typeKey) {
  if (typeKey === 'bool') return ['cvb', 'bool'];
  if (typeKey === 'number') return ['cvn', 'number'];
  return ['cvs', 'string'];
}

/**
 * Store a value the way Python `assign` does (empty values are not stored): numbers and booleans as they are,
 * objects as JSON, strings trimmed (JSON-looking strings normalised). Strings are
 * never turned into numbers, so ids and codes such as "00123" keep their form.
 */
function assign(variables, key, value) {
  if (value === null || value === undefined) return; // reassign skips empty values anyway
  if (typeof value === 'boolean' || (typeof value === 'number' && Number.isFinite(value))) {
    variables[key] = value;
    return;
  }
  if (typeof value === 'object') {
    try { variables[key] = JSON.stringify(value); } catch { variables[key] = String(value); }
    return;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      try { variables[key] = JSON.stringify(JSON.parse(trimmed)); return; } catch { /* plain string */ }
    }
    variables[key] = trimmed;
    return;
  }
  variables[key] = String(value);
}

function coerce(value, column, expectedType) {
  const asString = () => (typeof value === 'object' ? JSON.stringify(value) : String(value));
  const asBool = () => (typeof value === 'string' ? ['true', '1', 'yes'].includes(value.toLowerCase()) : Boolean(value));
  const asNumber = (fallback) => {
    if (typeof value === 'string' && value.trim() === '') return fallback;
    const n = Number(value);
    return Number.isNaN(n) ? fallback : n;
  };
  if (expectedType === 'double') return asNumber(0.0);
  if (expectedType === 'boolean') return asBool();
  if (expectedType === 'json' || expectedType === 'array<double>') return asString();
  if (expectedType === 'timestamp') return String(value);
  if (column.startsWith('cvs')) return asString();
  if (column.startsWith('cvn')) return asNumber(0);
  if (column.startsWith('cvb')) return asBool();
  return typeof value === 'object' ? JSON.stringify(value) : value;
}

/**
 * Map a record's keys to columns. Known keys use `keyToCvs`; other keys get the
 * first free custom column of their type (never one another key uses, never a
 * reserved one) and are dropped, warned once, when that type's columns run out.
 */
function reassign(data, keyToCvs = BASE_KEY_MAPPING, startingIndices = null, validTypes = null) {
  const source = typeof data === 'string' ? (() => { try { return JSON.parse(data); } catch { return {}; } })() : (data || {});
  if (!validTypes) {
    const from = source.from_source || source.source || source.cvs200;
    validTypes = from === 'ClaudeCodeHook' ? CLAUDE_VALID_TYPES : OTEL_AI_VALID_TYPES;
  }
  const indices = { ...DEFAULT_STARTING_INDICES, ...(startingIndices || {}) };
  const used = new Set(Object.values(keyToCvs));
  const assigned = {};
  const result = {};

  for (const [key, value] of Object.entries(source)) {
    if (value === null || value === undefined) continue;
    let column = keyToCvs[key] || assigned[key];
    if (!column) {
      const [prefix, indexKey] = getPrefixAndIndexKey(getTypeKey(value));
      column = allocateSlot(prefix, indices[indexKey], used);
      if (!column) { warnDropped(key, prefix); continue; }
      assigned[key] = column;
      indices[indexKey] = Number(column.slice(3)) + 1;
    }
    result[column] = coerce(value, column, validTypes[column] || validTypes[key]);
  }
  return result;
}

module.exports = {
  BASE_KEY_MAPPING,
  CLAUDE_KEY_MAPPING,
  AGENTS_KEY_MAPPING,
  OTEL_AI_VALID_TYPES,
  CLAUDE_VALID_TYPES,
  DEFAULT_STARTING_INDICES,
  CLAUDE_STARTING_INDICES,
  getTypeKey,
  assign,
  reassign,
};
