import axios from 'axios';
import { DEFAULT_API_URL, resolveApiKey, log } from './config.js';
import { reassign, AGENTS_KEY_MAPPING, AGENTS_STARTING_INDICES } from './mapping.js';

let _logApiUrl = DEFAULT_API_URL;
let _keyToCvs = { ...AGENTS_KEY_MAPPING };
let _startingIndices = { ...AGENTS_STARTING_INDICES };

export async function setupApi({ path = null, startingIndices = null } = {}) {
  if (startingIndices) Object.assign(_startingIndices, startingIndices);
  _logApiUrl = path ?? await resolveApiKey();
}

// Backward-compat alias
export const setupDecorator = setupApi;

function getCallerInfo() {
  const err = new Error();
  const lines = err.stack?.split('\n') ?? [];
  const frame = lines[3] ?? '';
  const match = frame.match(/at\s+(\S+)\s+\((.+):(\d+):\d+\)/) ?? frame.match(/at\s+(.+):(\d+):\d+/);
  if (match) {
    return { function: match[1] ?? 'unknown', file: match[2] ?? 'unknown', line: parseInt(match[3] ?? '0', 10) };
  }
  return { function: 'unknown', file: 'unknown', line: 0 };
}

function toStrOrNull(val) {
  if (val === null || val === undefined) return null;
  if (typeof val === 'object') { try { return JSON.stringify(val); } catch { return String(val); } }
  return String(val);
}

async function logPayload(source, args, output, errorInfo, callerInfo) {
  log.debug('Logger source=%s called from %s at %s:%d', source, callerInfo.function, callerInfo.file, callerInfo.line);

  const variables = {};
  variables.source = toStrOrNull(source);
  variables.input  = toStrOrNull(args);
  variables.caller = toStrOrNull(callerInfo);

  if (errorInfo) {
    variables.error         = true;
    variables.error_type    = errorInfo.type;
    variables.error_message = errorInfo.message;
    variables.error_stack   = errorInfo.stack;
    variables.output        = null;
  } else {
    variables.output = toStrOrNull(output);
  }

  try {
    const mapped = reassign(variables, _keyToCvs, { ..._startingIndices });
    await axios.post(_logApiUrl, mapped, { timeout: 5000 });
    log.debug('Logged successfully');
  } catch (e) {
    log.error('POST failed:', e.message);
  }
}

export function anosysLogger(source = null) {
  return function decorator(fn) {
    const callerInfo = getCallerInfo();
    return async function wrapped(...args) {
      let output = null;
      let errorInfo = null;
      try {
        output = await fn(...args);
        return output;
      } catch (e) {
        errorInfo = { type: e.constructor?.name ?? 'Error', message: e.message, stack: e.stack ?? '' };
        throw e;
      } finally {
        await logPayload(source ?? fn.name ?? 'anonymous', args, output, errorInfo, callerInfo);
      }
    };
  };
}

export async function anosysRawLogger(data = {}) {
  try {
    const mapped = reassign(data, _keyToCvs, { ..._startingIndices });
    await axios.post(_logApiUrl, mapped, { timeout: 5000 });
    log.debug('Raw logger: data logged successfully');
  } catch (e) {
    log.error('Raw logger POST failed:', e.message);
  }
}
