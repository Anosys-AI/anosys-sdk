'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const {
  FULL, OFF, PendingQueue, createHookLog, deliver, effectiveLevel, encryptPayload, filterFields, isPaused, prepareHookRecord, scrubSecrets,
} = require('anosys-sdk-core');

const { PREVIOUS_NOTIFY_FLAG, getCodexHome, getEnvPath } = require('./installer');
const { METADATA_FIELDS, transformCodexTurn } = require('./mapper');

const CODEX_HOME = getCodexHome();
const STATE_DIR = path.join(CODEX_HOME, 'state');
const STATE_FILE = path.join(STATE_DIR, 'anosys_state.json');
const PENDING_FILE = path.join(STATE_DIR, 'pending_records.jsonl');
const PAUSE_FILE = path.join(STATE_DIR, 'anosys_paused.json');
const LOG_FILE = path.join(STATE_DIR, 'anosys_hook.log');

// The hook log records ids, sizes and status codes only, never prompts or payloads.
const writeLog = createHookLog(LOG_FILE);
const log = (msg, level = 'INFO') => writeLog(level, msg);


function loadEnvFile() {
  const envPath = getEnvPath();
  if (!fs.existsSync(envPath)) return;
  try {
    const lines = fs.readFileSync(envPath, 'utf8').split('\n');
    for (let l of lines) {
      l = l.trim();
      if (!l || l.startsWith('#')) continue;
      if (l.startsWith('export ')) l = l.slice(7).trim();
      const idx = l.indexOf('=');
      if (idx === -1) continue;
      const k = l.slice(0, idx).trim();
      const v = l.slice(idx + 1).trim().replace(/^["']|["']$/g, '');
      if (k && !process.env[k]) {
        process.env[k] = v;
      }
    }
  } catch (err) {
    log(`Failed to load env file: ${err.name}`, 'WARNING');
  }
}

loadEnvFile();

const INGESTION_URL = process.env.ANOSYS_HOOK_ENDPOINT_URL || 'https://api.anosys.ai/ingestion';
const API_KEY = process.env.ANOSYS_HOOK_APIKEY || '';
const DRY_RUN = (process.env.ANOSYS_HOOK_DRY_RUN || 'false').toLowerCase() === 'true';

function loadState() {
  if (!fs.existsSync(STATE_FILE)) return {};
  try {
    return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
  } catch (_) {
    return {};
  }
}

function saveState(state) {
  try {
    fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2), 'utf8');
  } catch (err) {
    log(`Failed to save state: ${err.name}`, 'ERROR');
  }
}

function headers() {
  const h = { 'Content-Type': 'application/json', 'User-Agent': 'anosys-codex-hook/0.2.0' };
  if (API_KEY) {
    h['anosys-apikey'] = API_KEY;
    h['x-api-key'] = API_KEY;
  }
  return h;
}

/** Apply the collection level, scrub secrets at `full`, then encrypt. */
function prepareRecord(mapped, level) {
  // Level filter, secret scrubbing and encryption: the shared core step
  return prepareHookRecord(mapped, level, METADATA_FIELDS);
}

/** Deliver records (and queued retries) within the size limit. Resolves to the count accepted. */
async function send(records, options = {}) {
  if (DRY_RUN) {
    log(`[DRY RUN] Would send ${records.length} record(s)`);
    return records.length;
  }
  return deliver(INGESTION_URL, records, new PendingQueue(PENDING_FILE), PAUSE_FILE, { headers: headers(), metadataFields: METADATA_FIELDS, ...options });
}

function findRolloutFile(sessionId) {
  const sessionsDir = path.join(CODEX_HOME, 'sessions');
  if (!fs.existsSync(sessionsDir) || !sessionId) return null;

  function walk(dir) {
    try {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const e of entries) {
        const full = path.join(dir, e.name);
        if (e.isDirectory()) {
          const res = walk(full);
          if (res) return res;
        } else if (e.isFile() && e.name.includes(sessionId) && e.name.endsWith('.jsonl')) {
          return full;
        }
      }
    } catch (_) {}
    return null;
  }

  return walk(sessionsDir);
}

function extractTextFromContent(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content.map(c => {
      if (typeof c === 'string') return c;
      if (c && typeof c === 'object') return c.text || c.content || '';
      return '';
    }).join('');
  }
  if (content && typeof content === 'object') {
    return content.text || content.content || '';
  }
  return '';
}

function extractTurnFromRollout(rolloutPath, turnId, fallbackEvent = null) {
  if (!fs.existsSync(rolloutPath)) return null;

  const tokenFields = [
    'input_tokens',
    'output_tokens',
    'total_tokens',
    'cached_input_tokens',
    'cache_write_input_tokens',
    'reasoning_output_tokens'
  ];
  const tokenSums = {
    input_tokens: 0,
    output_tokens: 0,
    total_tokens: 0,
    cached_input_tokens: 0,
    cache_write_input_tokens: 0,
    reasoning_output_tokens: 0
  };
  let observedTokens = false;
  let prevTotalTokens = null;

  let inTurn = false;
  let turnStartMs = 0;
  let turnEndMs = 0;
  let durationMs = null;
  let userPrompt = '';
  let assistantOutput = '';
  let model = '';
  let modelProvider = 'openai';
  let cwd = '';
  let permissionMode = '';
  let sandboxMode = '';

  const toolCalls = [];
  const pendingFunc = {};
  const pendingCustom = {};
  let pendingSearchEnd = null;

  const rawEvents = [];

  try {
    const content = fs.readFileSync(rolloutPath, 'utf8');
    const lines = content.split('\n');

    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line) continue;
      let obj;
      try { obj = JSON.parse(line); } catch (_) { continue; }

      const outer = obj.type;
      const payload = (obj.payload && typeof obj.payload === 'object') ? obj.payload : {};
      const ptype = payload.type;
      const tsMs = obj.timestamp ? new Date(obj.timestamp.replace('Z', '+00:00')).getTime() : 0;

      if (outer === 'session_meta') {
        modelProvider = payload.model_provider || modelProvider;
        continue;
      }

      if (outer === 'turn_context') {
        if (payload.turn_id === turnId) {
          rawEvents.push(obj);
          model = payload.model || model;
          cwd = payload.cwd || cwd;
          permissionMode = payload.approval_policy || permissionMode;
          if (payload.sandbox_policy) sandboxMode = payload.sandbox_policy.type || sandboxMode;
        }
        continue;
      }

      if (outer === 'event_msg' && ptype === 'task_started') {
        if (inTurn) break; // next turn
        if (payload.turn_id === turnId) {
          inTurn = true;
          rawEvents.push(obj);
          turnStartMs = typeof payload.started_at === 'number' ? (payload.started_at * 1000) : tsMs;
        }
        continue;
      }

      if (!inTurn) continue;
      rawEvents.push(obj);

      if (outer === 'event_msg' && ptype === 'item_completed' && payload.item) {
        const item = payload.item;
        if (item.type === 'UserMessage') {
          const t = extractTextFromContent(item.content);
          if (t) userPrompt = t;
        } else if (item.type === 'AgentMessage') {
          const t = extractTextFromContent(item.content);
          if (t) assistantOutput = t;
        } else if (item.type === 'CommandExecution') {
          const cmd = Array.isArray(item.command) ? item.command.join(' ') : String(item.command || '');
          toolCalls.push({
            tool: 'exec',
            args: cmd,
            output: item.stdout || item.aggregated_output || '',
            call_id: item.id || '',
            start_ts: payload.started_at_ms || tsMs,
            end_ts: payload.completed_at_ms || tsMs
          });
        }
        continue;
      }

      if (outer === 'response_item' && ptype === 'message') {
        if (payload.role === 'user') {
          const t = extractTextFromContent(payload.content);
          if (t) userPrompt = t;
        } else if (payload.role === 'assistant') {
          const t = extractTextFromContent(payload.content);
          if (t) assistantOutput = t;
        }
        continue;
      }

      if (outer === 'event_msg' && ptype === 'user_message') {
        userPrompt = payload.message || userPrompt;
        continue;
      }

      if (outer === 'event_msg' && (ptype === 'agent_message' || ptype === 'task_complete')) {
        if (payload.message) assistantOutput = payload.message;
        if (payload.last_agent_message) assistantOutput = payload.last_agent_message;
        if (typeof payload.completed_at === 'number') turnEndMs = payload.completed_at * 1000;
        if (typeof payload.duration_ms === 'number') durationMs = payload.duration_ms;
        continue;
      }

      if (outer === 'token_usage_record') {
        const usage = payload.turn_token_usage || payload.usage || {};
        for (const k of tokenFields) {
          if (typeof usage[k] === 'number') {
            tokenSums[k] = usage[k];
            observedTokens = true;
          }
        }
        continue;
      }

      if (outer === 'event_msg' && ptype === 'token_count') {
        const info = payload.info || {};
        const total = info.total_token_usage;
        // Avoid double-counting rate-limit-only rebroadcasts (openai/codex#14489)
        if (total && prevTotalTokens && JSON.stringify(total) === JSON.stringify(prevTotalTokens)) {
          continue;
        }
        if (total) {
          prevTotalTokens = total;
        }
        const last = info.last_token_usage || {};
        for (const k of tokenFields) {
          if (typeof last[k] === 'number') {
            tokenSums[k] += last[k];
            observedTokens = true;
          }
        }
        continue;
      }

      if (outer === 'response_item' && ptype === 'function_call') {
        const callId = payload.call_id || '';
        const entry = {
          tool: payload.name || 'function_call',
          args: payload.arguments || '',
          output: '',
          call_id: callId,
          start_ts: tsMs,
          end_ts: tsMs
        };
        toolCalls.push(entry);
        if (callId) pendingFunc[callId] = entry;
        continue;
      }

      if (outer === 'response_item' && ptype === 'function_call_output') {
        const callId = payload.call_id || '';
        const pending = pendingFunc[callId];
        if (pending) {
          pending.output = payload.output || '';
          pending.end_ts = tsMs || pending.end_ts;
        }
        continue;
      }

      if (outer === 'response_item' && ptype === 'custom_tool_call') {
        const callId = payload.call_id || '';
        const entry = {
          tool: payload.name || 'custom_tool_call',
          args: payload.input || '',
          output: '',
          call_id: callId,
          start_ts: tsMs,
          end_ts: tsMs
        };
        toolCalls.push(entry);
        if (callId) pendingCustom[callId] = entry;
        continue;
      }

      if (outer === 'response_item' && ptype === 'custom_tool_call_output') {
        const callId = payload.call_id || '';
        const pending = pendingCustom[callId];
        if (pending) {
          pending.output = payload.output || '';
          pending.end_ts = tsMs || pending.end_ts;
        }
        continue;
      }

      if (outer === 'event_msg' && ptype === 'web_search_end') {
        pendingSearchEnd = { call_id: payload.call_id || '', ts_ms: tsMs };
        continue;
      }

      if (outer === 'response_item' && ptype === 'web_search_call') {
        const action = payload.action || {};
        const actionType = action.type || 'search';
        const toolName = actionType === 'open_page' ? 'open_page' : 'web_search';
        const args = actionType === 'open_page' ? (action.url || '') : (action.query || '');
        let callId = '';
        let startTs = tsMs;
        if (pendingSearchEnd) {
          callId = pendingSearchEnd.call_id;
          startTs = pendingSearchEnd.ts_ms || startTs;
          pendingSearchEnd = null;
        }
        toolCalls.push({
          tool: toolName,
          args: args,
          output: payload.status || '',
          call_id: callId,
          start_ts: startTs,
          end_ts: tsMs
        });
        continue;
      }
    }
  } catch (err) {
    log(`Failed to read rollout JSONL (${err.code || err.name})`);
    return null;
  }

  if (!inTurn) return null;

  if (!turnEndMs) {
    const ends = toolCalls.map(tc => tc.end_ts).filter(Boolean);
    turnEndMs = ends.length ? Math.max(...ends) : (turnStartMs || Date.now());
  }

  if (durationMs === null && turnStartMs && turnEndMs >= turnStartMs) {
    durationMs = turnEndMs - turnStartMs;
  }

  if (!userPrompt && fallbackEvent) {
    const userMsgs = fallbackEvent['input-messages'] || fallbackEvent.input_messages || '';
    if (Array.isArray(userMsgs) && userMsgs.length) {
      const last = userMsgs[userMsgs.length - 1];
      userPrompt = typeof last === 'string' ? last : (last.content || '');
    } else if (typeof userMsgs === 'string') {
      userPrompt = userMsgs;
    }
  }

  if (!assistantOutput && fallbackEvent) {
    const ast = fallbackEvent['last-assistant-message'] || fallbackEvent.last_assistant_message || '';
    if (typeof ast === 'object' && ast !== null) {
      assistantOutput = ast.text || ast.content || '';
    } else if (typeof ast === 'string') {
      assistantOutput = ast;
    }
  }

  return {
    turn_id: turnId,
    model: model,
    model_provider: modelProvider,
    cwd: cwd,
    permission_mode: permissionMode,
    sandbox_mode: sandboxMode,
    user_prompt: userPrompt,
    assistant_output: assistantOutput,
    turn_start_ms: turnStartMs,
    turn_end_ms: turnEndMs,
    duration_ms: durationMs || 0,
    tokens: observedTokens ? tokenSums : {},
    tool_calls: toolCalls,
    raw: {
      hook_event: fallbackEvent || null,
      events: rawEvents
    }
  };
}

function extractTurnFallback(inputJson, threadId, turnId) {
  const assistantMsg = inputJson['last-assistant-message'] || inputJson.last_assistant_message || '';
  const userMsgs = inputJson['input-messages'] || inputJson.input_messages || '';
  let userPrompt = '';
  if (Array.isArray(userMsgs) && userMsgs.length) {
    const last = userMsgs[userMsgs.length - 1];
    userPrompt = typeof last === 'string' ? last : (last.content || '');
  } else if (typeof userMsgs === 'string') {
    userPrompt = userMsgs;
  }

  const now = Date.now();
  return {
    turn_id: turnId,
    model: inputJson.model || 'unknown',
    model_provider: 'openai',
    cwd: inputJson.cwd || '',
    user_prompt: String(userPrompt),
    assistant_output: typeof assistantMsg === 'object' ? (assistantMsg.text || assistantMsg.content || '') : String(assistantMsg),
    turn_start_ms: now,
    turn_end_ms: now,
    duration_ms: 0,
    tokens: {},
    tool_calls: [],
    raw: {
      hook_event: inputJson,
      events: []
    }
  };
}

/** Split Codex's argv into { previous, raw }: the chained notify command and the notification JSON. */
function parseArgv(argv) {
  const args = argv.filter(a => a.trim() !== 'run');
  let previous = null;
  const i = args.indexOf(PREVIOUS_NOTIFY_FLAG);
  if (i !== -1) {
    try { previous = JSON.parse(args[i + 1]); } catch { previous = null; }
    args.splice(i, 2);
  }
  const raw = args.find(a => /^\s*[[{]/.test(a)) || args[0] || '{}';
  return { previous, raw: raw.trim() };
}

/** Run the notify command that was configured before AnoSys, unchanged. */
function callPreviousNotify(previous, raw) {
  if (!Array.isArray(previous) || !previous.length) return;
  try {
    spawnSync(String(previous[0]), [...previous.slice(1).map(String), raw], { stdio: 'ignore', timeout: 30000 });
  } catch (e) {
    log(`Previous notify command failed: ${e.name}`, 'WARNING');
  }
}

async function processNotification(rawInput, options = {}) {
  const { level, source } = effectiveLevel();
  if (level === OFF) {
    log(`Collection is off (${source}); nothing sent`);
    return;
  }
  if (isPaused(PAUSE_FILE)) {
    log('Collection paused after an authorization error; nothing sent');
    return;
  }

  let event = {};
  try {
    event = JSON.parse(rawInput);
  } catch {
    log(`Notification is not valid JSON (${rawInput.length} bytes)`, 'ERROR');
    return;
  }

  const eventType = event.type;
  if (eventType && !['agent-turn-complete', 'turn-complete', 'test'].includes(eventType)) {
    log(`Ignoring event type: ${eventType}`);
    return;
  }

  const threadId = event['thread-id'] || event.thread_id || event.threadId || event.sessionId || 'unknown_session';
  const turnId = event['turn-id'] || event.turn_id || event.turnId || `turn_${Date.now()}`;

  const state = loadState();
  state[threadId] = state[threadId] || { processed_turns: [] };
  if (state[threadId].processed_turns.includes(turnId)) {
    log(`Turn ${turnId} already processed for session ${threadId}. Skipping.`);
    return;
  }

  const rolloutPath = findRolloutFile(threadId);
  let turnData = rolloutPath ? extractTurnFromRollout(rolloutPath, turnId, event) : null;
  if (!turnData) {
    log(`Could not extract turn ${turnId} from the rollout file; using the notification`, 'WARNING');
    turnData = extractTurnFallback(event, threadId, turnId);
  }

  const record = prepareRecord(transformCodexTurn(turnData, threadId, turnId), level);
  const sent = await send([record], options);
  log(`Turn ${turnId} (session ${threadId}) at '${level}': ${sent} record(s) accepted`);

  // Mark the turn processed either way: retries live in the bounded queue
  state[threadId].processed_turns = [...state[threadId].processed_turns, turnId].slice(-500);
  state[threadId].last_seen = new Date().toISOString();
  saveState(state);
}

async function run(argv = process.argv.slice(2), options = {}) {
  const { previous, raw } = parseArgv(argv);
  try {
    await processNotification(raw, options);
  } finally {
    callPreviousNotify(previous, raw);
  }
}

module.exports = {
  run,
  parseArgv,
  prepareRecord,
  processNotification,
  LOG_FILE,
  PENDING_FILE,
  PAUSE_FILE,
  STATE_FILE,
  findRolloutFile,
  extractTurnFromRollout,
  extractTurnFallback
};

if (require.main === module) {
  run().catch(err => console.error(err));
}
