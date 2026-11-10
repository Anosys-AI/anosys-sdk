'use strict';

const path = require('path');
const os = require('os');
const {
  BASE_METADATA_FIELDS,
  encryptPayload,
  derive256BitKey,
  encrypt,
  decrypt,
  getEncryptionKey,
  getTargetColumns,
  ANOSYS_ENCRYPTION_PREFIX,
  DEFAULT_ENCRYPTED_COLUMNS,
} = require('anosys-sdk-core');

const INTEGRATION_VERSION = require('../package.json').version || '0.1.0';
const OS_USER = os.userInfo().username || 'unknown';

function isCcPixel() {
  const pt = (process.env.ANOSYS_PIXEL_TYPE || '').trim().toLowerCase();
  if (pt) return ['cc', 'claudecode', 'codex'].includes(pt);
  if ((process.env.ANOSYS_CODEX_PIXEL || '').trim().toLowerCase() === 'false') return false;
  if ((process.env.ANOSYS_CLAUDE_PIXEL || '').trim().toLowerCase() === 'false') return false;
  const url = (process.env.ANOSYS_HOOK_ENDPOINT_URL || '').toLowerCase();
  if (['/g/', '/generic/', '/c/', '/custom/', '/t/', '/otel/'].some((s) => url.includes(s))) {
    return false;
  }
  return true;
}

// Fields sent at the `metadata` level (same as Python mapper.METADATA_FIELDS)
const CV_METADATA_FIELDS = new Set([
  'cvs1', 'cvs2', 'cvs7', 'cvs9', 'cvs12', 'cvs13', 'cvs17', 'cvs19', 'cvs32', 'cvs33',
  'cvn1', 'cvn2', 'cvn3', 'cvn4', 'cvn5', 'cvn6', 'cvn7', 'cvn41',
  'cvb1', 'cvb2',
]);

const METADATA_FIELDS = new Set([
  ...BASE_METADATA_FIELDS,
  ...CV_METADATA_FIELDS,
]);

const OPENAI_PRICING = {
  'gpt-4o-mini': { input: 0.15 / 1e6, output: 0.60 / 1e6, cached: 0.075 / 1e6 },
  'gpt-4o': { input: 2.50 / 1e6, output: 10.00 / 1e6, cached: 1.25 / 1e6 },
  'o1-mini': { input: 1.10 / 1e6, output: 4.40 / 1e6, cached: 0.55 / 1e6 },
  'o1': { input: 15.00 / 1e6, output: 60.00 / 1e6, cached: 7.50 / 1e6 },
  'o3-mini': { input: 1.10 / 1e6, output: 4.40 / 1e6, cached: 0.55 / 1e6 },
  'o3': { input: 15.00 / 1e6, output: 60.00 / 1e6, cached: 7.50 / 1e6 },
  'default': { input: 2.50 / 1e6, output: 10.00 / 1e6, cached: 1.25 / 1e6 }
};

function calculateCost(model, inputTokens, outputTokens, cachedTokens = 0) {
  const m = (model || '').toLowerCase();
  let rates = OPENAI_PRICING.default;
  const sortedEntries = Object.entries(OPENAI_PRICING).sort((a, b) => b[0].length - a[0].length);
  for (const [k, r] of sortedEntries) {
    if (k !== 'default' && m.includes(k)) {
      rates = r;
      break;
    }
  }
  const billableInput = Math.max(0, inputTokens - cachedTokens);
  const cost = (billableInput * rates.input) + (cachedTokens * rates.cached) + (outputTokens * rates.output);
  return Number(cost.toFixed(6));
}

function extractCommandsAndPaths(toolCalls) {
  const commands = [];
  const writtenPaths = [];

  for (const call of (toolCalls || [])) {
    const tool = String(call.tool || '').toLowerCase();
    const args = call.args || '';

    if (['shell', 'bash', 'exec', 'terminal'].includes(tool)) {
      let cmd = '';
      if (typeof args === 'object' && args !== null) {
        cmd = args.command || args.cmd || '';
      } else if (typeof args === 'string') {
        try {
          const parsed = JSON.parse(args);
          if (typeof parsed === 'object' && parsed !== null) {
            cmd = parsed.command || parsed.cmd || '';
          }
        } catch (_) {
          cmd = args;
        }
      }
      if (cmd && typeof cmd === 'string') commands.push(cmd.trim());
    }

    if (['apply_patch', 'write_to_file', 'replace_file_content', 'edit', 'save'].includes(tool)) {
      let fp = '';
      if (typeof args === 'object' && args !== null) {
        fp = args.path || args.target_file || args.file || '';
      } else if (typeof args === 'string') {
        try {
          const parsed = JSON.parse(args);
          if (typeof parsed === 'object' && parsed !== null) {
            fp = parsed.path || parsed.target_file || parsed.file || '';
          }
        } catch (_) {
          fp = args;
        }
      }
      if (fp && typeof fp === 'string') writtenPaths.push(fp.trim());
    }
  }

  return { commands, writtenPaths };
}

function transformCodexTurn(turn, sessionId, turnId, incrementalTokens = null) {
  const model = turn.model || 'unknown';
  const provider = turn.model_provider || 'openai';
  const cwd = turn.cwd || '';
  const project = cwd ? path.basename(cwd) : null;

  const userPrompt = turn.user_prompt || '';
  const assistantText = turn.assistant_output || '';

  const tokens = turn.tokens || {};
  const inputTokens = Number(tokens.input_tokens || 0);
  const outputTokens = Number(tokens.output_tokens || 0);
  const totalTokens = Number(tokens.total_tokens || (inputTokens + outputTokens));
  const cachedTokens = Number(tokens.cached_input_tokens || 0);
  const cacheWriteTokens = Number(tokens.cache_write_input_tokens || 0);
  const reasoningTokens = Number(tokens.reasoning_output_tokens || 0);

  const costEst = calculateCost(model, inputTokens, outputTokens, cachedTokens);

  const inc = incrementalTokens || {
    input: inputTokens,
    output: outputTokens,
    total: totalTokens,
    cache_read: cachedTokens,
    cache_creation: cacheWriteTokens,
    cost: costEst
  };

  const toolCalls = turn.tool_calls || [];
  const { commands, writtenPaths } = extractCommandsAndPaths(toolCalls);

  const cleanToolCalls = toolCalls.map(tc => {
    const c = Object.assign({}, tc);
    return c;
  });

  const toolDurations = toolCalls
    .map(tc => (tc.end_ts && tc.start_ts && tc.end_ts >= tc.start_ts ? (tc.end_ts - tc.start_ts) : 0))
    .filter(d => d > 0);
  const toolDurationMs = toolDurations.length ? toolDurations.reduce((a, b) => a + b, 0) : null;

  const startTs = turn.turn_start_ms || Date.now();
  const durationMs = turn.duration_ms !== undefined ? turn.duration_ms : null;

  const rawData = turn.raw || {
    hook_event: turn,
    events: []
  };

  const rawToSerialize = rawData;

  let permMode = null;
  if (turn.permission_mode) {
    if (typeof turn.permission_mode === 'string') {
      permMode = turn.permission_mode;
    } else if (typeof turn.permission_mode === 'object') {
      permMode = turn.permission_mode.type || Object.keys(turn.permission_mode)[0] || 'custom';
    }
  }

  let sandboxMode = null;
  if (turn.sandbox_mode) {
    if (typeof turn.sandbox_mode === 'string') {
      sandboxMode = turn.sandbox_mode;
    } else if (typeof turn.sandbox_mode === 'object') {
      sandboxMode = turn.sandbox_mode.type || Object.keys(turn.sandbox_mode)[0] || 'custom';
    }
  }

  const commandsStr = commands.length ? JSON.stringify(commands) : null;
  const writtenPathsStr = writtenPaths.length ? JSON.stringify(writtenPaths) : null;

  const payload = isCcPixel() ? {
    session_id: sessionId,
    sessionId: sessionId,
    uuid: turnId,
    raw_uuid: turnId,
    eventId: turnId,
    event_id: turnId,
    event_type: 'codex_turn',
    event_source_name: 'codex',
    timestamp: startTs,
    user_timestamp: startTs,
    debug: false,
    user_prompt: userPrompt,
    userPrompt: userPrompt,
    assistant_text: assistantText,
    assistantText: assistantText,
    model: model,
    primary_model: model,
    model_provider: provider,
    cwd: cwd || null,
    project: project,
    permission_mode: permMode,
    permissionMode: permMode,
    sandbox_mode: sandboxMode,
    duration_ms: durationMs,
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    total_tokens: totalTokens,
    cache_read: cachedTokens,
    cache_creation: cacheWriteTokens,
    reasoning_tokens: reasoningTokens,
    cost_estimate: costEst,
    incremental_input: inc.input !== undefined ? inc.input : inputTokens,
    incremental_output: inc.output !== undefined ? inc.output : outputTokens,
    incremental_total: inc.total !== undefined ? inc.total : totalTokens,
    incremental_cost: inc.cost !== undefined ? inc.cost : costEst,
    incremental_cache_read: inc.cache_read !== undefined ? inc.cache_read : cachedTokens,
    incremental_cache_creation: inc.cache_creation !== undefined ? inc.cache_creation : cacheWriteTokens,
    tool_count: toolCalls.length,
    tool_duration_ms: toolDurationMs,
    commands: commandsStr,
    written_paths: writtenPathsStr,
    has_thinking: reasoningTokens > 0,
    integration_version: INTEGRATION_VERSION,
    os_user: OS_USER,
    // Raw backup & hook identifiers
    cvs199: JSON.stringify(rawToSerialize),
    cvs200: 'CodexHook'
  } : {
    // Fallback CV mode for generic/custom pixels without native tool/token columns
    timestamp: startTs,
    user_timestamp: startTs,
    event_id: turnId,
    eventId: turnId,
    uuid: turnId,
    event_type: 'codex_turn',
    event_source_name: 'codex',
    debug: false,
    cvs1: sessionId,
    cvs2: project,
    cvs4: userPrompt,
    cvs5: assistantText,
    cvs7: permMode,
    cvs9: model,
    cvs12: cwd,
    cvs13: turnId,
    cvs17: provider,
    cvs19: 'anosys-codex run',
    cvs32: INTEGRATION_VERSION,
    cvs33: OS_USER,
    cvs90: commandsStr,
    cvs91: writtenPathsStr,
    cvn1: inputTokens,
    cvn2: outputTokens,
    cvn3: totalTokens,
    cvn4: cachedTokens,
    cvn5: cacheWriteTokens,
    cvn6: durationMs,
    cvn7: costEst,
    cvn41: toolCalls.length,
    cvb1: false,
    cvb2: reasoningTokens > 0,
    // Raw backup & hook identifiers
    cvs199: JSON.stringify(rawToSerialize),
    cvs200: 'CodexHook'
  };

  // Remove null/undefined properties
  const cleanPayload = {};
  for (const [k, v] of Object.entries(payload)) {
    if (v !== null && v !== undefined) {
      cleanPayload[k] = v;
    }
  }
  // Collection level, secret scrubbing and encryption are applied by the hook runner
  return cleanPayload;
}

module.exports = {
  calculateCost,
  extractCommandsAndPaths,
  transformCodexTurn,
  METADATA_FIELDS,
  encryptPayload,
  derive256BitKey,
  encrypt,
  decrypt,
  getEncryptionKey,
  getTargetColumns,
  ANOSYS_ENCRYPTION_PREFIX,
  DEFAULT_ENCRYPTED_COLUMNS,
};
