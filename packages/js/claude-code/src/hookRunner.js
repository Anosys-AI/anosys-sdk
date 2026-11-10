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
const {
  FULL, OFF, PendingQueue, createHookLog, deliver, effectiveLevel, encryptPayload, filterFields, isPaused, prepareHookRecord, scrubSecrets, writePrivateFile,
} = require('anosys-sdk-core');
const { METADATA_FIELDS, UNHANDLED_COUNTS, transformRecord } = require('./mapper');

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
const INGESTION_URL = process.env.ANOSYS_HOOK_ENDPOINT_URL || 'https://api.anosys.ai/ingestion';
const API_KEY = process.env.ANOSYS_HOOK_APIKEY || process.env.ANOSYS_HOOK_API_KEY || '';
const DRY_RUN = (process.env.ANOSYS_HOOK_DRY_RUN || 'false').toLowerCase() === 'true';
const EXPLICIT_TRANSCRIPT = process.env.ANOSYS_HOOK_TRANSCRIPT || '';

const STATE_DIR = path.join(os.homedir(), '.claude', 'state');
const STATE_FILE = path.join(STATE_DIR, 'hook_state.json');
const PENDING_RECORDS_FILE = path.join(STATE_DIR, 'pending_records.jsonl');
const LOG_FILE = path.join(STATE_DIR, 'hook.log');
const PAUSE_FILE = path.join(STATE_DIR, 'anosys_paused.json');


// ---------------------------------------------------------------------------
// Logging (mirrors Python's logging.basicConfig → file + stderr)
// ---------------------------------------------------------------------------
try { fs.mkdirSync(STATE_DIR, { recursive: true }); } catch { /* read-only home: run without state */ }

// The hook log records ids, sizes and status codes only, never prompts or payloads.
const writeLog = createHookLog(LOG_FILE);
const log = {
  debug() { /* debug lines are not written */ },
  info(msg, ...args) { writeLog('INFO', _sprintf(msg, args)); },
  warning(msg, ...args) { writeLog('WARNING', _sprintf(msg, args)); },
  error(msg, ...args) { writeLog('ERROR', _sprintf(msg, args)); },
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
/** Every transcript on disk; used only to locate the current session's file. */
function findAllTranscripts() {
  try {
    return scanTranscripts(path.join(os.homedir(), '.claude', 'projects'));
  } catch (e) { // unreadable or vanished folder: no transcripts, never a crash
    log.warning('Could not list Claude Code transcripts (%s)', e.code || e.name);
    return [];
  }
}

function scanTranscripts(projectsDir) {
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
    const data = fs.readFileSync(0, 'utf8'); // fd 0 works on every platform (/dev/stdin does not exist on Windows)
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
  try {
    fs.mkdirSync(STATE_DIR, { recursive: true });
    writePrivateFile(STATE_FILE, JSON.stringify(state, null, 2)); // 0600
  } catch (e) {
    log.warning('Could not save hook state (%s)', e.code || e.name);
  }
}

/**
 * Load pending records from the local storage file.
 * @returns {object[]}
 */
/** The current session's transcript and its subagents. Never other sessions. */
function sessionTranscripts(primary) {
  const results = [primary];
  const subagentsDir = path.join(primary.path.replace(/\.jsonl$/, ''), 'subagents');
  if (fs.existsSync(subagentsDir) && fs.statSync(subagentsDir).isDirectory()) {
    for (const f of fs.readdirSync(subagentsDir).filter(n => n.endsWith('.jsonl')).sort()) {
      const agentId = path.basename(f, '.jsonl');
      const meta = _loadAgentMeta(path.join(subagentsDir, `${agentId}.meta.json`));
      results.push({
        path: path.join(subagentsDir, f),
        state_key: `${primary.session_id}:subagent:${agentId}`,
        session_id: primary.session_id,
        is_agent: true,
        agent_id: agentId,
        agent_type: meta.agentType,
        agent_description: meta.description,
      });
    }
  }
  return results;
}

/** Apply the collection level, scrub secrets at `full`, then encrypt. */
function prepareRecord(mapped, level) {
  // Level filter, secret scrubbing and encryption: the shared core step
  return prepareHookRecord(mapped, level, METADATA_FIELDS);
}

/** Deliver records (and queued retries) within the size limit. Resolves to the count accepted. */
async function send(records, options = {}) {
  if (DRY_RUN) {
    log.info('[DRY RUN] Would send %s record(s)', records.length);
    return records.length;
  }
  const headers = { 'Content-Type': 'application/json' };
  if (API_KEY) headers['anosys-apikey'] = API_KEY;
  return deliver(INGESTION_URL, records, new PendingQueue(PENDING_RECORDS_FILE), PAUSE_FILE, { headers, metadataFields: METADATA_FIELDS, ...options });
}

async function main(options = {}) {
  // Add a small delay to ensure Claude Code has finished flushing logs to disk.
  await new Promise(r => setTimeout(r, options.delayMs ?? 500));

  const { level, source } = effectiveLevel();
  if (level === OFF) {
    log.info('Collection is off (%s); nothing sent', source);
    return;
  }
  if (isPaused(PAUSE_FILE)) {
    log.info('Collection paused after an authorization error; nothing sent');
    return;
  }

  const stdinCtx = options.stdinCtx !== undefined ? options.stdinCtx : getStdinContext();

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

  // In DRY_RUN mode ignore persisted state so every record is processed from scratch.
  const state = DRY_RUN ? {} : loadState();
  let sessionState = {};

  // Only this session and its subagents: past sessions are never uploaded
  const transcripts = sessionTranscripts(primaryTranscript);
  log.info("Session %s at '%s' (%s): %s transcript(s)", currentSessionId, level, source, transcripts.length);

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
      log.error('Failed to read transcript %s: %s', transcript.state_key, e.name);
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
        log.error('Failed to map record in %s at line %s: %s', sessionId, i, e.name);
      }
    }

    if (sessionMapped.length) {
      for (const m of sessionMapped) {
        const record = prepareRecord(m, level);
        if (Object.keys(record).length) allMappedPayloads.push(record);
      }

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

  if (!DRY_RUN) {
    saveState(state);
  } else {
    log.info('[DRY RUN] Skipping state save — state file unchanged.');
  }

  if (Object.keys(UNHANDLED_COUNTS).length) {
    log.info('Unrecognized record types (counted, not stored): %s', JSON.stringify(UNHANDLED_COUNTS));
  }

  // Also flushes queued retries; failed records go to the bounded queue
  const sent = await send(allMappedPayloads, options);
  log.info('Session %s: %s record(s) mapped, %s accepted', currentSessionId, allMappedPayloads.length, sent);
}

// ═══════════════════════════════════════════════════════════════════════════
if (require.main === module) {
  main()
    .catch(e => {
      log.error('Unhandled exception (%s)', e.code || e.name);
    })
    .finally(() => {
      process.exit(0);
    });
}

module.exports = {
  main, findAllTranscripts, findLatestTranscript, loadState, saveState, sessionTranscripts, prepareRecord,
  LOG_FILE, PENDING_RECORDS_FILE, PAUSE_FILE, STATE_FILE,
};
