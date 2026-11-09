/**
 * Hook runner for Google Antigravity PreInvocation and Stop events (JavaScript).
 */

const fs = require('fs');
const path = require('path');
const {
  FULL, OFF, PendingQueue, createHookLog, deliver, effectiveLevel, encryptPayload, filterFields,
  isPaused, scrubSecrets,
} = require('anosys-sdk-core');
const { GLOBAL_CONFIG_DIR, GLOBAL_ENV_FILE, DEFAULT_INGESTION_URL } = require('./constants');
const { parseTranscript } = require('./transcript');
const { METADATA_FIELDS, transformAntigravityTurn } = require('./mapper');

const STATE_DIR = path.join(GLOBAL_CONFIG_DIR, 'state');
const PENDING_FILE = path.join(STATE_DIR, 'pending_records.jsonl');
const PAUSE_FILE = path.join(STATE_DIR, 'anosys_paused.json');
const LOG_FILE = path.join(STATE_DIR, 'anosys_hook.log');

// Content fields scrubbed for secrets before sending at `full`
const CONTENT_FIELDS = ['user_prompt', 'userPrompt', 'assistant_text', 'assistantText', 'cvs4', 'cvs5',
  'commands', 'cvs90', 'cvs199', 'searched_queries', 'cvs77'];

try {
  fs.mkdirSync(STATE_DIR, { recursive: true });
} catch {}

// The hook log records ids, sizes and status codes only, never prompts or payloads.
const log = createHookLog(LOG_FILE);

function loadEnvConfig(envPath = GLOBAL_ENV_FILE) {
  if (!fs.existsSync(envPath)) return;
  try {
    const raw = fs.readFileSync(envPath, 'utf-8');
    const data = JSON.parse(raw);
    if (data && typeof data === 'object') {
      for (const [k, v] of Object.entries(data)) {
        if (!process.env[k] && v !== undefined && v !== null) {
          process.env[k] = String(v);
        }
      }
    }
  } catch (err) {
    log('WARNING', `Failed to load env config from ${envPath}: ${err.name}`);
  }
}

function loadRuntimeEnvironment() {
  let directory = process.cwd();
  while (true) {
    const workspaceConfig = path.join(directory, '.agents', 'anosys-env.json');
    if (fs.existsSync(workspaceConfig)) {
      loadEnvConfig(workspaceConfig);
      break;
    }
    const parent = path.dirname(directory);
    if (parent === directory) break;
    directory = parent;
  }
  loadEnvConfig();
}

loadRuntimeEnvironment();

function getConfig() {
  return {
    ingestion_url: process.env.ANOSYS_HOOK_ENDPOINT_URL || DEFAULT_INGESTION_URL,
    api_key: process.env.ANOSYS_HOOK_APIKEY || process.env.ANOSYS_API_KEY || '',
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
    fs.writeFileSync(sf, JSON.stringify(state, null, 2), 'utf-8');
  } catch (err) {
    log('ERROR', `Failed to save state for ${sessionId}: ${err.name}`);
  }
}

/** Apply the collection level, scrub secrets at `full`, then encrypt. */
function prepareRecord(mapped, level) {
  const record = filterFields(mapped, level, METADATA_FIELDS);
  if (level === FULL) {
    for (const field of CONTENT_FIELDS) {
      if (record[field] !== undefined && record[field] !== null) record[field] = scrubSecrets(record[field]);
    }
  }
  return encryptPayload(record);
}

/** Deliver records (and queued retries) within the size limit. Resolves to the count accepted. */
async function send(records, config, options = {}) {
  if (config.dry_run) {
    log('INFO', `[DRY RUN] Would send ${records.length} record(s)`);
    return records.length;
  }
  const headers = { 'Content-Type': 'application/json' };
  if (config.api_key) headers['anosys-apikey'] = config.api_key;
  return deliver(config.ingestion_url, records, new PendingQueue(PENDING_FILE), PAUSE_FILE, { headers, ...options });
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
    // Failed records go to the bounded queue; turns are marked processed either way
    const sent = await send(recordsToSend, cfg);
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
    const { level, source } = effectiveLevel();
    if (level === OFF) {
      log('INFO', `Collection is off (${source}); nothing sent`);
    } else if (isPaused(PAUSE_FILE)) {
      log('INFO', 'Collection paused after an authorization error; nothing sent');
    } else {
      await processTurns(eventName, await readStdin(), getConfig(), level);
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
