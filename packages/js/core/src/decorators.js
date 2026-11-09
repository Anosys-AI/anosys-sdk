'use strict';

/**
 * anosysLogger / anosysRawLogger for the JS application SDKs — one implementation
 * (the JS side of Python `anosys_sdk_core/decorators.py`). Each package creates its
 * own instance with its key mapping: `createDecorators({ keyToCvs, startingIndices, log })`.
 *
 * Records follow the shared collection level (capture.js), are sent in the
 * background (sender.js) and never delay or change the decorated function's result.
 */

const { reassign, BASE_KEY_MAPPING, DEFAULT_STARTING_INDICES } = require('./mapping.js');
const { currentAppLevel, prepareAppRecord } = require('./capture.js');
const { resolveApiKey, createLogger } = require('./config.js');
const { sendAppRecord } = require('./sender.js');

function toStrOrNull(val) {
  if (val === null || val === undefined) return null;
  if (typeof val === 'object') { try { return JSON.stringify(val); } catch { return String(val); } }
  return String(val);
}

function getCallerInfo() {
  const lines = new Error().stack?.split('\n') ?? [];
  const frame = lines[3] ?? '';
  const match = frame.match(/at\s+(\S+)\s+\((.+):(\d+):\d+\)/) ?? frame.match(/at\s+(.+):(\d+):\d+/);
  if (match) return { function: match[1] ?? 'unknown', file: match[2] ?? 'unknown', line: parseInt(match[3] ?? '0', 10) };
  return { function: 'unknown', file: 'unknown', line: 0 };
}

function createDecorators({ keyToCvs = BASE_KEY_MAPPING, startingIndices = DEFAULT_STARTING_INDICES, log = createLogger('sdk') } = {}) {
  let logApiUrl = null;
  const mapping = { ...keyToCvs };
  const indices = { ...startingIndices };

  async function setupApi({ path = null, startingIndices: extra = null } = {}) {
    if (extra) Object.assign(indices, extra);
    logApiUrl = path ?? await resolveApiKey();
  }

  function send(record) {
    const prepared = prepareAppRecord(reassign(record, mapping, { ...indices }), currentAppLevel().level);
    if (prepared) sendAppRecord(logApiUrl, prepared);
  }

  function logPayload(source, args, output, errorInfo, callerInfo) {
    try {
      const variables = { source: toStrOrNull(source), input: toStrOrNull(args), caller: toStrOrNull(callerInfo) };
      if (errorInfo) {
        Object.assign(variables, {
          error: true, error_type: errorInfo.type, error_message: errorInfo.message,
          error_stack: errorInfo.stack, output: null,
        });
      } else {
        variables.output = toStrOrNull(output);
      }
      variables.raw = JSON.stringify(variables); // raw record, always included (as in Python)
      send(variables);
    } catch (e) {
      log.error(`AnoSys logging failed (${e?.name || 'Error'})`);
    }
  }

  function anosysLogger(source = null) {
    return function decorator(fn) {
      const callerInfo = getCallerInfo();
      return async function wrapped(...args) {
        let output = null;
        let errorInfo = null;
        try {
          output = await fn(...args);
          return output;
        } catch (e) {
          errorInfo = { type: e?.constructor?.name ?? 'Error', message: e?.message, stack: e?.stack ?? '' };
          throw e;
        } finally {
          logPayload(source ?? fn.name ?? 'anonymous', args, output, errorInfo, callerInfo);
        }
      };
    };
  }

  async function anosysRawLogger(data = {}) {
    try {
      const record = { ...data };
      if (!record.raw) record.raw = JSON.stringify(record);
      send(record);
    } catch (e) {
      log.error(`AnoSys raw logging failed (${e?.name || 'Error'})`);
    }
  }

  return { setupApi, setupDecorator: setupApi, anosysLogger, anosysRawLogger, getLogApiUrl: () => logApiUrl };
}

module.exports = { createDecorators };
