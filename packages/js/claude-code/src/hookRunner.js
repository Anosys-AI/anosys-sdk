#!/usr/bin/env node
/**
 * anosys_claude_hook.js — Claude Code "Stop" hook.
 *
 * Reads the latest JSONL transcript, incrementally processes new messages,
 * maps them as individual records through mapper.transformRecord(),
 * and POSTs them as a batch to the configured endpoint.
 *
 * Configuration (env vars):
 *   ANOSYS_HOOK_ENDPOINT_URL  — Target URL to POST records to
 *   ANOSYS_HOOK_API_KEY       — Optional Bearer token for the endpoint
 *   ANOSYS_HOOK_DRY_RUN       — Set to "true" to log payloads instead of POSTing
 *   ANOSYS_HOOK_TRANSCRIPT    — Optional: explicit .jsonl path (skips auto-detection)
 *
 * State is persisted in:  ~/.claude/state/hook_state.json
 * Logs are written to:    ~/.claude/state/hook.log
 *
 * Exact JS clone of anosys_claude_hook.py
 */

'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const { transformRecord } = require('./mapper');

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
const INGESTION_URL = 'https://api.anosys.ai/ingestion';
const API_KEY = process.env.ANOSYS_HOOK_APIKEY || '';
const DRY_RUN = (process.env.ANOSYS_HOOK_DRY_RUN || 'false').toLowerCase() === 'true';
const EXPLICIT_TRANSCRIPT = process.env.ANOSYS_HOOK_TRANSCRIPT || '';

const STATE_DIR = path.join(os.homedir(), '.claude', 'state');
const STATE_FILE = path.join(STATE_DIR, 'hook_state.json');
const PENDING_RECORDS_FILE = path.join(STATE_DIR, 'pending_records.jsonl');
const LOG_FILE = path.join(STATE_DIR, 'hook.log');

// ---------------------------------------------------------------------------
// Logging (mirrors Python's logging.basicConfig → file + stderr)
// ---------------------------------------------------------------------------
fs.mkdirSync(STATE_DIR, { recursive: true });

function _formatLogLine(level, msg) {
  const ts = new Date().toISOString().replace('T', ' ').replace('Z', '');
  return `${ts} [${level}] ${msg}`;
}

const log = {
  _write(line) {
    try { fs.appendFileSync(LOG_FILE, line + '\n', 'utf8'); } catch (_) { }
  },
  debug(msg, ...args) {
    const line = _formatLogLine('DEBUG', _sprintf(msg, args));
    this._write(line);
  },
  info(msg, ...args) {
    const line = _formatLogLine('INFO', _sprintf(msg, args));
    this._write(line);
    process.stderr.write(line + '\n');
  },
  warning(msg, ...args) {
    const line = _formatLogLine('WARNING', _sprintf(msg, args));
    this._write(line);
    process.stderr.write(line + '\n');
  },
  error(msg, ...args) {
    const line = _formatLogLine('ERROR', _sprintf(msg, args));
    this._write(line);
    process.stderr.write(line + '\n');
  },
};

/** Very simple %-style sprintf that handles %s and %d. */
function _sprintf(fmt, args) {
  let i = 0;
  return String(fmt).replace(/%s|%d/g, () => (args[i++] != null ? String(args[i - 1]) : ''));
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. Find the latest transcript
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Holds path and optional agent metadata for a transcript.
 * @typedef {{ path: string, state_key: string, session_id: string, is_agent: boolean, agent_id?: string, agent_type?: string, agent_description?: string }} TranscriptInfo
 */

/**
 * Load and return agent meta JSON; returns empty dict on failure.
 * @param {string} metaPath
 * @returns {object}
 */
function _loadAgentMeta(metaPath) {
  try {
    return JSON.parse(fs.readFileSync(metaPath, 'utf8'));
  } catch (_) {
    return {};
  }
}

/**
 * Return all transcripts (regular + subagent) across ~/.claude/projects/.
 * @returns {TranscriptInfo[]}
 */
function findAllTranscripts() {
  const projectsDir = path.join(os.homedir(), '.claude', 'projects');
  // const projectsDir = path.join(".", 'playground', 'logs_from_claude');
  if (!fs.existsSync(projectsDir)) return [];

  const results = [];

  for (const entry of fs.readdirSync(projectsDir)) {
    const projectDir = path.join(projectsDir, entry);
    if (!fs.statSync(projectDir).isDirectory()) continue;

    // Regular session transcripts: <project>/<sessionId>.jsonl
    for (const f of fs.readdirSync(projectDir)) {
      if (!f.endsWith('.jsonl')) continue;
      const transcriptPath = path.join(projectDir, f);
      const sessionId = path.basename(f, '.jsonl');
      results.push({
        path: transcriptPath,
        state_key: sessionId,
        session_id: sessionId,
        is_agent: false,
      });
    }

    // Agent transcripts: <project>/<sessionId>/subagents/agent-<agentId>.jsonl
    for (const sub of fs.readdirSync(projectDir)) {
      const subDir = path.join(projectDir, sub);
      if (!fs.statSync(subDir).isDirectory()) continue;
      const subagentsDir = path.join(subDir, 'subagents');
      if (!fs.existsSync(subagentsDir)) continue;
      const sessionId = sub; // parent folder name is the session ID
      for (const af of fs.readdirSync(subagentsDir)) {
        if (!af.endsWith('.jsonl')) continue;
        const agentJsonl = path.join(subagentsDir, af);
        const agentId = path.basename(af, '.jsonl'); // e.g. "agent-a4eb6799e46ab0db5"
        const metaPath = agentJsonl.replace(/\.jsonl$/, '.meta.json');
        const meta = _loadAgentMeta(metaPath);
        const stateKey = `${sessionId}:subagent:${agentId}`;
        results.push({
          path: agentJsonl,
          state_key: stateKey,
          session_id: sessionId,
          is_agent: true,
          agent_id: agentId,
          agent_type: meta.agentType,
          agent_description: meta.description,
        });
      }
    }
  }

  return results;
}

/**
 * Return the most recently modified regular (non-agent) transcript.
 * @returns {TranscriptInfo|null}
 */
function findLatestTranscript() {
  const transcripts = findAllTranscripts();
  const regular = transcripts.filter(t => !t.is_agent);
  if (!regular.length) return null;
  return regular.reduce((best, t) => {
    const mtime = fs.statSync(t.path).mtimeMs;
    const bestMtime = fs.statSync(best.path).mtimeMs;
    return mtime > bestMtime ? t : best;
  });
}

/**
 * Try to read JSON context from stdin. In Node we read synchronously
 * (the hook is a short-lived process, stdin arrives immediately).
 * Returns null if stdin is empty or fails to parse.
 * @returns {object|null}
 */
function getStdinContext() {
  try {
    // Check if stdin has data (non-TTY = piped input)
    if (process.stdin.isTTY) return null;
    const data = fs.readFileSync('/dev/stdin', 'utf8');
    if (!data || !data.trim()) return null;
    return JSON.parse(data);
  } catch (_) {
    return null;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 2. State management (incremental processing)
// ═══════════════════════════════════════════════════════════════════════════
function loadState() {
  try {
    if (fs.existsSync(STATE_FILE)) {
      return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
    }
  } catch (_) { }
  return {};
}

function saveState(state) {
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2), 'utf8');
}

/**
 * Load pending records from the local storage file.
 * @returns {object[]}
 */
function loadPendingRecords() {
  if (!fs.existsSync(PENDING_RECORDS_FILE)) return [];
  const records = [];
  try {
    const lines = fs.readFileSync(PENDING_RECORDS_FILE, 'utf8').split('\n');
    for (const line of lines) {
      if (line.trim()) {
        records.push(JSON.parse(line));
      }
    }
  } catch (e) {
    log.error('Failed to load pending records: %s', e);
  }
  return records;
}

/**
 * Save records to the pending storage file (append by default).
 * @param {object[]} records
 * @param {boolean} overwrite
 */
function savePendingRecords(records, overwrite = false) {
  try {
    const mode = overwrite ? 'w' : 'a';
    const flag = overwrite ? 'w' : 'a';
    const content = records.map(r => JSON.stringify(r)).join('\n') + '\n';
    fs.writeFileSync(PENDING_RECORDS_FILE, content, { encoding: 'utf8', flag });
    log.info(
      'Saved %s records to pending storage (%s): %s',
      records.length,
      overwrite ? 'overwrite' : 'append',
      PENDING_RECORDS_FILE
    );
  } catch (e) {
    log.error('Failed to save pending records: %s', e);
  }
}

/**
 * Clear the pending storage file after successful upload.
 */
function clearPendingRecords() {
  try {
    if (fs.existsSync(PENDING_RECORDS_FILE)) {
      fs.unlinkSync(PENDING_RECORDS_FILE);
      log.info('Cleared pending records.');
    }
  } catch (e) {
    log.error('Failed to clear pending records: %s', e);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 3. POST records to endpoint
// ═══════════════════════════════════════════════════════════════════════════

/**
 * POST mapped record payloads in batches of 100.
 * Returns a list of records that failed to post.
 *
 * Uses Node's built-in https/http module to avoid external dependencies.
 * @param {object[]} payloads
 * @returns {Promise<object[]>} failed records
 */
async function postRecordsBatch(payloads) {
  if (!payloads.length) return [];

  const headers = { 'Content-Type': 'application/json' };
  if (API_KEY) {
    headers['anosys-apikey'] = API_KEY;
  }

  const failedRecords = [];
  const batchSize = 100;

  for (let i = 0; i < payloads.length; i += batchSize) {
    const chunk = payloads.slice(i, i + batchSize);

    if (DRY_RUN) {
      log.info('[DRY RUN] Would POST chunk of %s records', chunk.length);
      continue;
    }

    try {
      await _httpPost(INGESTION_URL, chunk, headers);
      log.info('Batch POST success — sent %s records', chunk.length);
    } catch (e) {
      log.error('Batch POST failed — trying to send %s records: %s', chunk.length, e);
      failedRecords.push(...chunk);
    }
  }

  return failedRecords;
}

/**
 * Minimal HTTP(S) POST helper using Node built-ins.
 * @param {string} url
 * @param {object} bodyObj
 * @param {object} headers
 * @returns {Promise<void>}
 */
function _httpPost(url, bodyObj, headers) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify(bodyObj);
    const parsed = new URL(url);
    const lib = parsed.protocol === 'https:' ? require('https') : require('http');

    const req = lib.request(
      {
        hostname: parsed.hostname,
        port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
        path: parsed.pathname + (parsed.search || ''),
        method: 'POST',
        headers: {
          ...headers,
          'Content-Length': Buffer.byteLength(body),
        },
        timeout: 15000,
      },
      (res) => {
        let data = '';
        res.on('data', (chunk) => (data += chunk));
        res.on('end', () => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve();
          } else {
            reject(new Error(`HTTP ${res.statusCode}: ${data}`));
          }
        });
      }
    );

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Request timed out'));
    });

    req.write(body);
    req.end();
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// 4. Main
// ═══════════════════════════════════════════════════════════════════════════
async function main() {
  // Add a small delay to ensure Claude Code has finished flushing logs to disk.
  await new Promise(r => setTimeout(r, 500));

  log.info('='.repeat(60));
  log.info('anosys_claude_hook.js invoked at %s', new Date().toISOString());

  // -- 1. Resend pending records first ----------------------------------
  const pending = loadPendingRecords();
  if (pending.length) {
    log.info('Found %s pending records from previous runs. Attempting resend...', pending.length);
    const failedPending = await postRecordsBatch(pending);
    if (!failedPending.length) {
      clearPendingRecords();
    } else {
      log.warning('%s records still failed after resend. Updating storage.', failedPending.length);
      savePendingRecords(failedPending, true); // overwrite
    }
  }

  // -- 2. Identify primary transcript ----------------------------------
  const stdinCtx = getStdinContext();
  if (stdinCtx) {
    log.info('Received context from stdin: %s', JSON.stringify(stdinCtx));
  }

  // Priority: 1. Explicit Env Var, 2. stdin transcriptPath/sessionId, 3. Automatic detection
  let providedPath = EXPLICIT_TRANSCRIPT;
  if (!providedPath && stdinCtx) {
    providedPath = stdinCtx.transcriptPath || stdinCtx.transcript_path || '';
    if (!providedPath) {
      const sid = stdinCtx.sessionId || stdinCtx.session_id;
      if (sid) {
        for (const t of findAllTranscripts()) {
          if (t.session_id === sid && !t.is_agent) {
            providedPath = t.path;
            break;
          }
        }
      }
    }
  }

  let primaryTranscript;
  if (providedPath) {
    const sessionId = path.basename(providedPath, '.jsonl');
    primaryTranscript = {
      path: providedPath,
      state_key: sessionId,
      session_id: sessionId,
      is_agent: false,
    };
  } else {
    primaryTranscript = findLatestTranscript();
  }

  if (!primaryTranscript) {
    log.warning('No transcript found to process.');
    return;
  }

  const currentSessionId = primaryTranscript.session_id;
  log.info('Targeting transcript: %s (Session: %s)', primaryTranscript.path, currentSessionId);

  // In DRY_RUN mode ignore persisted state so every record is processed from scratch.
  let state = DRY_RUN ? {} : loadState();
  let sessionState = state[currentSessionId] || {};

  // Check if we should do a full scan (once per session "startup")
  const fullScanDone = sessionState.full_scan_done || false;

  let transcripts;
  if (!fullScanDone) {
    log.info('First run for session %s. Performing global transcript scan...', currentSessionId);
    transcripts = findAllTranscripts();
  } else {
    // Process current session's transcript AND any of its subagent transcripts
    const allKnown = findAllTranscripts();
    transcripts = [primaryTranscript, ...allKnown.filter(
      t => t.is_agent && t.session_id === currentSessionId
    )];
  }

  log.info(
    'Processing %s transcript(s) (%s agent(s)).',
    transcripts.length,
    transcripts.filter(t => t.is_agent).length
  );

  // -- 3. Process each transcript ---------------------------------------
  const allMappedPayloads = [];
  const sessionUpdates = []; // Track which sessions to update state for

  for (const transcript of transcripts) {
    const stateKey = transcript.state_key;
    const sessionId = transcript.session_id;
    sessionState = state[stateKey] || {};
    let lastLine = sessionState.last_line || 0;
    const lastMessageUuid = sessionState.last_message_uuid || null;

    let content;
    try {
      content = fs.readFileSync(transcript.path, 'utf8');
    } catch (e) {
      log.error('Failed to read transcript %s: %s', transcript.path, e);
      continue;
    }

    const allLines = content.trim().split('\n');
    if (!allLines.length || !allLines[0]) {
      log.debug('Transcript %s is empty.', sessionId);
      continue;
    }

    const totalLines = allLines.length;
    log.info(
      'Processing %s%s: %s total lines, previously saw %s lines',
      stateKey,
      transcript.is_agent ? ' [AGENT]' : '',
      totalLines,
      lastLine
    );

    // Pre-parse lines
    const parsedItems = allLines.map(line => {
      line = line.trim();
      if (!line) return null;
      try {
        const msg = JSON.parse(line);
        const uuid = msg.uuid || msg.messageId || msg.id;
        return [msg, uuid];
      } catch (_) {
        return null;
      }
    });

    // Resync
    if (lastLine > 0 && lastMessageUuid) {
      const expectedPrevLine = lastLine - 1;
      let matches = false;
      if (expectedPrevLine < totalLines) {
        const item = parsedItems[expectedPrevLine];
        if (item && item[1] === lastMessageUuid) {
          matches = true;
        }
      }

      if (!matches) {
        let foundIdx = -1;
        for (let i = totalLines - 1; i >= 0; i--) {
          const item = parsedItems[i];
          if (item && item[1] === lastMessageUuid) {
            foundIdx = i;
            break;
          }
        }
        if (foundIdx !== -1) {
          lastLine = foundIdx + 1;
        } else {
          lastLine = 0;
        }
      }
    }

    if (lastLine >= totalLines) {
      log.debug('No new lines to process in %s.', sessionId);
      continue;
    }

    log.info('Mapping lines %s to %s for session %s', lastLine, totalLines, sessionId);

    // Map new records
    const sessionMapped = [];

    // Track maximum tokens seen so far for each message ID in this session
    const maxTokensById = {};

    // Get transcript file mtime as a fallback
    const fileMtime = fs.statSync(transcript.path).mtimeMs;

    // Context tracking for records missing session metadata
    const currentContext = {
      sessionId: sessionId,
      cwd: null,
      gitBranch: null,
      version: null,
      slug: null,
      permissionMode: null,
      userType: null,
      // Agent-level metadata (injected for every record in an agent transcript)
      is_agent: transcript.is_agent,
      agent_id: transcript.agent_id,
      agent_type: transcript.agent_type,
      agent_description: transcript.agent_description,
      // Fallback timestamps
      file_mtime: fileMtime,
      last_timestamp: null,
    };

    for (let i = lastLine; i < totalLines; i++) {
      const item = parsedItems[i];
      if (!item) continue;

      const [msg, uuid] = item;

      // Update context tracker with sticky session-level fields
      for (const field of ['cwd', 'sessionId', 'gitBranch', 'version', 'slug', 'permissionMode', 'userType']) {
        const val = msg[field];
        if (val) {
          currentContext[field] = val;
        }
      }

      // Update last seen timestamp
      const msgTs = msg.timestamp;
      if (msgTs) {
        currentContext.last_timestamp = msgTs;
      }

      const msgType = msg.type;

      // Calculate incremental tokens for assistant turns with same message.id
      let incremental = null;
      if (msgType === 'assistant' && msg.message && typeof msg.message === 'object') {
        const msgId = msg.message.id;
        if (msgId) {
          const usage = msg.message.usage || {};
          const currIn = parseFloat(usage.input_tokens || 0);
          const currOut = parseFloat(usage.output_tokens || 0);
          const currCacheRead = parseFloat(usage.cache_read_input_tokens || 0);

          // cache_creation may be a nested object or a flat int
          const ccRaw = usage.cache_creation;
          let currCacheCreation;
          if (ccRaw && typeof ccRaw === 'object') {
            currCacheCreation = parseFloat(
              (ccRaw.ephemeral_1h_input_tokens || 0) +
              (ccRaw.ephemeral_5m_input_tokens || 0)
            );
          } else if (typeof ccRaw === 'number') {
            currCacheCreation = parseFloat(ccRaw);
          } else {
            currCacheCreation = parseFloat(usage.cache_creation_input_tokens || 0);
          }

          const prev = maxTokensById[msgId] || { input: 0.0, output: 0.0, cache_read: 0.0, cache_creation: 0.0 };

          // Only count the increase
          const deltaIn = currIn - prev.input;
          const deltaOut = currOut - prev.output;
          const deltaCacheRead = currCacheRead - prev.cache_read;
          const deltaCacheCreation = currCacheCreation - prev.cache_creation;

          maxTokensById[msgId] = {
            input: Math.max(prev.input, currIn),
            output: Math.max(prev.output, currOut),
            cache_read: Math.max(prev.cache_read, currCacheRead),
            cache_creation: Math.max(prev.cache_creation, currCacheCreation),
          };

          incremental = {
            input: deltaIn,
            output: deltaOut,
            cache_read: deltaCacheRead,
            cache_creation: deltaCacheCreation,
            total: deltaIn + deltaOut + deltaCacheRead + deltaCacheCreation,
          };
        }
      }

      try {
        currentContext.log_index = i;
        const mapped = transformRecord(msg, incremental, currentContext);
        sessionMapped.push(mapped);
      } catch (e) {
        log.error('Failed to map record in %s at line %s (UUID %s): %s', sessionId, i, uuid, e);
      }
    }

    if (sessionMapped.length) {
      allMappedPayloads.push(...sessionMapped);

      let finalUuid = null;
      if (totalLines > 0) {
        const lastItem = parsedItems[totalLines - 1];
        if (lastItem) {
          finalUuid = lastItem[1];
        }
      }

      sessionUpdates.push([stateKey, {
        last_line: totalLines,
        last_message_uuid: finalUuid,
        last_run: new Date().toISOString(),
        records_sent_total: (sessionState.records_sent_total || 0) + sessionMapped.length,
        is_agent: transcript.is_agent,
      }]);
    }
  }

  // -- 4. Batch POST or Persist -----------------------------------------
  // Always update state for sessions whose lines were scanned.
  for (const [stateKeyUpd, updateData] of sessionUpdates) {
    const existing = state[stateKeyUpd] || {};
    Object.assign(existing, updateData);
    state[stateKeyUpd] = existing;
  }

  // Always mark the primary session's full scan as done.
  const primaryStateKey = primaryTranscript.state_key;
  if (state[primaryStateKey]) {
    state[primaryStateKey].full_scan_done = true;
  } else {
    state[primaryStateKey] = { full_scan_done: true };
  }

  if (!DRY_RUN) {
    saveState(state);
  } else {
    log.info('[DRY RUN] Skipping state save — state file unchanged.');
  }

  if (!allMappedPayloads.length) {
    log.info('No new records (mapped) to send.');
    return;
  }

  // POST mapped records. If they fail, persist to pending list.
  const failedNew = await postRecordsBatch(allMappedPayloads);

  if (failedNew.length) {
    log.error('%s new records failed to POST. Saving to pending storage.', failedNew.length);
    savePendingRecords(failedNew, false); // Append
  } else {
    log.info('Successfully sent %s new records and updated state.', allMappedPayloads.length);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
if (require.main === module) {
  main()
    .catch(e => {
      log.error('Unhandled exception: %s', e.stack || e);
    })
    .finally(() => {
      process.exit(0);
    });
}

module.exports = { main, findAllTranscripts, findLatestTranscript, loadState, saveState };
