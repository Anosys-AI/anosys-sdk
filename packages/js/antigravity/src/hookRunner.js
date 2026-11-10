/**
 * Hook runner for Google Antigravity PreInvocation and Stop events (JavaScript).
 */

const fs = require('fs');
const path = require('path');
const {
  FULL, OFF, RANK, PendingQueue, createHookLog, deliver, effectiveLevel, encryptPayload, filterFields, isPaused, prepareHookRecord, scrubSecrets, writePrivateFile,
} = require('anosys-sdk-core');
const { GLOBAL_CONFIG_DIR, GLOBAL_ENV_FILE, DEFAULT_INGESTION_URL } = require('./constants');
const { parseTranscript } = require('./transcript');
const { METADATA_FIELDS, transformAntigravityTurn } = require('./mapper');

const STATE_DIR = path.join(GLOBAL_CONFIG_DIR, 'state');
const PENDING_FILE = path.join(STATE_DIR, 'pending_records.jsonl');
const PAUSE_FILE = path.join(STATE_DIR, 'anosys_paused.json');
const LOG_FILE = path.join(STATE_DIR, 'anosys_hook.log');


try {
  fs.mkdirSync(STATE_DIR, { recursive: true });
} catch {}

// The hook log records ids, sizes and status codes only, never prompts or payloads.
const log = createHookLog(LOG_FILE);

// A workspace file is part of the repository, so anyone who can commit to it
// controls it. It may choose which AnoSys key the records are filed under and
// lower collection; it can never raise the level, point at a consent file,
// change the endpoint, encryption, proxies or certificates.
const WORKSPACE_ALLOWED_KEYS = new Set([
  'ANOSYS_HOOK_APIKEY', 'ANOSYS_HOOK_API_KEY', 'ANOSYS_HOOK_DRY_RUN',
  'REDACTION', 'ANOSYS_DISABLE', 'ANOSYS_COLLECTION_LEVEL',
]);
const WORKSPACE_LEVELS = new Set(['off', 'metadata']); // ANOSYS_COLLECTION_LEVEL may only lower

let _workspaceCeiling = null;

function loadEnvConfig(envPath = GLOBAL_ENV_FILE, allowed = null) {
  if (!fs.existsSync(envPath)) return;
  try {
    const raw = fs.readFileSync(envPath, 'utf-8');
    const data = JSON.parse(raw);
    if (data && typeof data === 'object') {
      for (const [k, v] of Object.entries(data)) {
        if (allowed && (!allowed.has(k)
            || (k === 'ANOSYS_COLLECTION_LEVEL' && !WORKSPACE_LEVELS.has(String(v).trim().toLowerCase())))) {
          log('WARNING', `Ignored ${k} from the workspace settings file (not allowed there)`);
          continue;
        }
        if (allowed && v !== undefined && v !== null) {
          const valLower = String(v).trim().toLowerCase();
          if (k === 'ANOSYS_DISABLE' && ['1', 'true', 'yes'].includes(valLower)) {
            _workspaceCeiling = 'off';
          } else if (k === 'ANOSYS_COLLECTION_LEVEL' && WORKSPACE_LEVELS.has(valLower)) {
            if (_workspaceCeiling !== 'off') _workspaceCeiling = valLower;
          } else if (k === 'REDACTION' && ['1', 'true', 'yes'].includes(valLower)) {
            if (_workspaceCeiling === null) _workspaceCeiling = 'metadata';
          }
        }
        if (!process.env[k] && v !== undefined && v !== null) {
          process.env[k] = String(v);
        }
      }
    }
  } catch (err) {
    log('WARNING', `Failed to load env config from ${envPath}: ${err.name}`);
  }
}

function loadRuntimeEnvironment(startDir = null) {
  loadEnvConfig();
  let directory = startDir ? path.resolve(String(startDir)) : process.cwd();
  while (true) {
    const workspaceConfig = path.join(directory, '.agents', 'anosys-env.json');
    if (fs.existsSync(workspaceConfig)) {
      loadEnvConfig(workspaceConfig, WORKSPACE_ALLOWED_KEYS);
      break;
    }
    const parent = path.dirname(directory);
    if (parent === directory) break;
    directory = parent;
  }
}

loadRuntimeEnvironment();

function getConfig() {
  return {
    ingestion_url: process.env.ANOSYS_HOOK_ENDPOINT_URL || DEFAULT_INGESTION_URL,
    api_key: process.env.ANOSYS_HOOK_APIKEY || process.env.ANOSYS_HOOK_API_KEY || process.env.ANOSYS_API_KEY || '',
    dry_run: (process.env.ANOSYS_HOOK_DRY_RUN || 'false').toLowerCase() === 'true',
  };
}

function getSessionStateFile(sessionId) {
  const safeId = String(sessionId).replace(/[^a-zA-Z0-9\-_]/g, '_');
  return path.join(STATE_DIR, `state_${safeId}.json`);
}

function loadState(sessionId) {
  const sf = getSessionStateFile(sessionId);
  if (!fs.existsSync(sf)) {
    return { session_id: sessionId, last_emitted_turn: -1, processed_turns: [] };
  }
  try {
    const raw = fs.readFileSync(sf, 'utf-8');
    return JSON.parse(raw);
  } catch {
    return { session_id: sessionId, last_emitted_turn: -1, processed_turns: [] };
  }
}

function saveState(sessionId, state) {
  try {
    const sf = getSessionStateFile(sessionId);
    writePrivateFile(sf, JSON.stringify(state, null, 2)); // 0600
  } catch (err) {
    log('ERROR', `Failed to save state for ${sessionId}: ${err.name}`);
  }
}

/** Apply the collection level, scrub secrets at `full`, then encrypt. */
function prepareRecord(mapped, level) {
  // Level filter, secret scrubbing and encryption: the shared core step
  return prepareHookRecord(mapped, level, METADATA_FIELDS);
}

/** Deliver records (and queued retries) within the size limit. Resolves to the count accepted. */
async function send(records, config, options = {}) {
  if (config.dry_run) {
    log('INFO', `[DRY RUN] Would send ${records.length} record(s)`);
    return records.length;
  }
  const headers = { 'Content-Type': 'application/json' };
  if (config.api_key) headers['anosys-apikey'] = config.api_key;
  return deliver(config.ingestion_url, records, new PendingQueue(PENDING_FILE), PAUSE_FILE, { headers, metadataFields: METADATA_FIELDS, ...options });
}

function readStdin() {
  return new Promise(resolve => {
    if (process.stdin.isTTY) return resolve({});
    let data = '';
    process.stdin.setEncoding('utf-8');
    process.stdin.on('data', chunk => { data += chunk; });
    process.stdin.on('end', () => {
      try {
        resolve(data.trim() ? JSON.parse(data.trim()) : {});
      } catch {
        resolve({});
      }
    });
    process.stdin.on('error', () => resolve({}));
  });
}

function printResponse() {
  process.stdout.write(JSON.stringify({}) + '\n');
}

async function processTurns(eventName, inputJson, config, level = 'metadata') {
  const cfg = config || getConfig();
  const transcriptPath = inputJson.transcriptPath;
  if (!transcriptPath) {
    log('INFO', 'No transcriptPath provided in hook input; skipping.');
    return;
  }

  const sessionId = inputJson.conversationId || path.basename(path.dirname(transcriptPath)) || 'unknown_session';
  const turns = parseTranscript(transcriptPath);
  if (!turns || turns.length === 0) {
    log('INFO', `No turns parsed from the transcript of session ${sessionId}`);
    return;
  }

  const state = loadState(sessionId);
  const lastTurn = typeof state.last_emitted_turn === 'number' ? state.last_emitted_turn : -1;
  const processedTurns = Array.isArray(state.processed_turns) ? state.processed_turns : [];

  const isStop = String(eventName).toLowerCase() === 'stop';
  const finalIdx = turns.length - 1;

  const recordsToSend = [];
  const turnIndicesEmitted = [];

  for (let i = 0; i < turns.length; i++) {
    const turn = turns[i];
    const isFinal = (i === finalIdx);
    if (isFinal && !isStop) {
      continue;
    }
    if (i <= lastTurn) {
      continue;
    }

    const turnId = `${sessionId}_${i}`;
    if (processedTurns.includes(turnId)) {
      continue;
    }

    const hookMeta = { ...inputJson, hook_name: isStop ? 'Stop' : 'PreInvocation' };
    const payload = transformAntigravityTurn(
      turn,
      sessionId,
      turnId,
      hookMeta
    );

    recordsToSend.push(prepareRecord(payload, level));
    turnIndicesEmitted.push(i);
    processedTurns.push(turnId);
  }

  if (recordsToSend.length > 0) {
    const wsPaths = Array.isArray(inputJson.workspacePaths) ? inputJson.workspacePaths : [];
    const wsCwd = wsPaths[0] || inputJson.cwd || null;
    // Failed records go to the bounded queue; turns are marked processed either way
    const sent = await send(recordsToSend, cfg, { cwd: wsCwd });
    log('INFO', `Session ${sessionId} at '${level}': ${recordsToSend.length} turn(s), ${sent} accepted`);
    state.last_emitted_turn = Math.max(...turnIndicesEmitted);
    state.processed_turns = processedTurns.slice(-500);
    state.last_updated = new Date().toISOString();
    saveState(sessionId, state);
  }
}

async function run() {
  let eventName = 'stop';
  const args = process.argv.slice(2);
  if (args.length > 0 && args[0] !== 'run') {
    eventName = args[0].toLowerCase();
  } else if (args.length > 1) {
    eventName = args[1].toLowerCase();
  }

  try {
    const inputJson = await readStdin();
    const wsPaths = Array.isArray(inputJson.workspacePaths) ? inputJson.workspacePaths : [];
    const wsCwd = wsPaths[0] || inputJson.cwd || null;
    if (wsCwd) loadRuntimeEnvironment(wsCwd);
    let { level, source } = effectiveLevel(null, wsCwd);
    if (_workspaceCeiling && (RANK[_workspaceCeiling] ?? 0) < (RANK[level] ?? 0)) {
      level = _workspaceCeiling;
      source = 'workspace ceiling';
    }
    if (level === OFF) {
      log('INFO', `Collection is off (${source}); nothing sent`);
    } else if (isPaused(PAUSE_FILE)) {
      log('INFO', 'Collection paused after an authorization error; nothing sent');
    } else {
      await processTurns(eventName, inputJson, getConfig(), level);
    }
  } catch (err) {
    log('ERROR', `Hook runner error on ${eventName}: ${err.name}`);
  } finally {
    printResponse();
  }
}

if (require.main === module) {
  run();
}

module.exports = {
  run,
  processTurns,
  prepareRecord,
  send,
  loadState,
  saveState,
  readStdin,
  printResponse,
  getConfig,
  LOG_FILE,
  PENDING_FILE,
  PAUSE_FILE,
  STATE_DIR,
};
