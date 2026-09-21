/**
 * Hook runner for Google Antigravity PreInvocation and Stop events (JavaScript).
 */

const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');
const { GLOBAL_CONFIG_DIR, GLOBAL_ENV_FILE, DEFAULT_INGESTION_URL } = require('./constants');
const { parseTranscript } = require('./transcript');
const { transformAntigravityTurn } = require('./mapper');

const STATE_DIR = path.join(GLOBAL_CONFIG_DIR, 'state');
const PENDING_FILE = path.join(STATE_DIR, 'pending_records.jsonl');
const LOG_FILE = path.join(STATE_DIR, 'anosys_hook.log');

try {
  fs.mkdirSync(STATE_DIR, { recursive: true });
} catch {}

function log(level, message, ...args) {
  const ts = new Date().toISOString();
  const formatted = `[${ts}] [${level}] ${message} ${args.length ? JSON.stringify(args) : ''}\n`;
  try {
    fs.appendFileSync(LOG_FILE, formatted, 'utf-8');
  } catch {}
  if (level === 'ERROR' || process.env.ANOSYS_VERBOSE === 'true') {
    process.stderr.write(formatted);
  }
}

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
    log('WARN', `Failed to load env config from ${envPath}: ${err.message}`);
  }
}

loadEnvConfig();

function getConfig() {
  return {
    ingestion_url: process.env.ANOSYS_HOOK_ENDPOINT_URL || DEFAULT_INGESTION_URL,
    api_key: process.env.ANOSYS_HOOK_APIKEY || process.env.ANOSYS_API_KEY || '',
    dry_run: (process.env.ANOSYS_HOOK_DRY_RUN || 'false').toLowerCase() === 'true',
    redaction: (process.env.REDACTION || 'false').toLowerCase() === 'true',
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
    log('ERROR', `Failed to save state for ${sessionId}: ${err.message}`);
  }
}

function loadPendingRecords() {
  if (!fs.existsSync(PENDING_FILE)) return [];
  const records = [];
  try {
    const lines = fs.readFileSync(PENDING_FILE, 'utf-8').split('\n');
    for (let line of lines) {
      line = line.trim();
      if (line) {
        records.push(JSON.parse(line));
      }
    }
  } catch (err) {
    log('ERROR', `Failed to load pending records: ${err.message}`);
  }
  return records;
}

function savePendingRecords(records, overwrite = false) {
  try {
    const mode = overwrite ? 'w' : 'a';
    const content = records.map(r => JSON.stringify(r)).join('\n') + '\n';
    if (overwrite) {
      fs.writeFileSync(PENDING_FILE, content, 'utf-8');
    } else {
      fs.appendFileSync(PENDING_FILE, content, 'utf-8');
    }
  } catch (err) {
    log('ERROR', `Failed to save pending records: ${err.message}`);
  }
}

function clearPendingRecords() {
  try {
    if (fs.existsSync(PENDING_FILE)) {
      fs.unlinkSync(PENDING_FILE);
    }
  } catch (err) {
    log('ERROR', `Failed to clear pending records: ${err.message}`);
  }
}

function postChunk(chunk, config) {
  return new Promise((resolve) => {
    if (config.dry_run) {
      log('INFO', `[DRY RUN] Would POST ${chunk.length} records to ${config.ingestion_url}`);
      return resolve({ success: true, records: chunk });
    }

    try {
      const url = new URL(config.ingestion_url);
      const dataStr = JSON.stringify(chunk);
      const isHttps = url.protocol === 'https:';
      const client = isHttps ? https : http;

      const headers = {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(dataStr),
        'User-Agent': 'anosys-antigravity-hook-js/0.1.0',
      };
      if (config.api_key) {
        headers['anosys-apikey'] = config.api_key;
        headers['x-api-key'] = config.api_key;
      }

      const req = client.request(
        {
          hostname: url.hostname,
          port: url.port || (isHttps ? 443 : 80),
          path: url.pathname + url.search,
          method: 'POST',
          headers,
          timeout: 10000,
        },
        res => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            log('INFO', `Batch POST success — sent ${chunk.length} records`);
            resolve({ success: true, records: chunk });
          } else {
            log('ERROR', `Batch POST failed with status ${res.statusCode}`);
            resolve({ success: false, records: chunk });
          }
        }
      );

      req.on('error', err => {
        log('ERROR', `Batch POST request error: ${err.message}`);
        resolve({ success: false, records: chunk });
      });

      req.on('timeout', () => {
        req.destroy();
        log('ERROR', 'Batch POST request timed out');
        resolve({ success: false, records: chunk });
      });

      req.write(dataStr);
      req.end();
    } catch (err) {
      log('ERROR', `Batch POST unexpected error: ${err.message}`);
      resolve({ success: false, records: chunk });
    }
  });
}

async function postRecordsBatch(payloads, config) {
  if (!payloads || payloads.length === 0) return [];
  const failed = [];
  const batchSize = 100;

  for (let i = 0; i < payloads.length; i += batchSize) {
    const chunk = payloads.slice(i, i + batchSize);
    const res = await postChunk(chunk, config);
    if (!res.success) {
      failed.push(...chunk);
    }
  }

  return failed;
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

async function processTurns(eventName, inputJson, config) {
  const cfg = config || getConfig();
  const transcriptPath = inputJson.transcriptPath;
  if (!transcriptPath) {
    log('INFO', 'No transcriptPath provided in hook input; skipping.');
    return;
  }

  const sessionId = inputJson.conversationId || path.basename(path.dirname(transcriptPath)) || 'unknown_session';
  const turns = parseTranscript(transcriptPath);
  if (!turns || turns.length === 0) {
    log('INFO', `No turns parsed from transcript: ${transcriptPath}`);
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
      hookMeta,
      cfg.redaction
    );

    recordsToSend.push(payload);
    turnIndicesEmitted.push(i);
    processedTurns.push(turnId);
  }

  if (recordsToSend.length > 0) {
    const failed = await postRecordsBatch(recordsToSend, cfg);
    if (failed.length > 0) {
      log('WARN', `Saving ${failed.length} failed records to pending queue`);
      savePendingRecords(failed);
    } else {
      const maxIdx = Math.max(...turnIndicesEmitted);
      log('INFO', `Successfully emitted ${recordsToSend.length} turns up to index ${maxIdx}`);
      state.last_emitted_turn = maxIdx;
      state.processed_turns = processedTurns;
      state.last_updated = new Date().toISOString();
      saveState(sessionId, state);
    }
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
    const cfg = getConfig();
    const pending = loadPendingRecords();
    if (pending.length > 0) {
      log('INFO', `Retrying ${pending.length} pending records...`);
      const stillFailed = await postRecordsBatch(pending, cfg);
      if (stillFailed.length === 0) {
        clearPendingRecords();
        log('INFO', 'Successfully flushed pending records.');
      } else {
        savePendingRecords(stillFailed, true);
      }
    }

    const inputJson = await readStdin();
    await processTurns(eventName, inputJson, cfg);
  } catch (err) {
    log('ERROR', `Hook runner error on ${eventName}: ${err.message}`);
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
  loadState,
  saveState,
  loadPendingRecords,
  savePendingRecords,
  clearPendingRecords,
  postRecordsBatch,
  readStdin,
  printResponse,
  getConfig,
};
