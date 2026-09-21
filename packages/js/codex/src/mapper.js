'use strict';

const path = require('path');
const os = require('os');

const INTEGRATION_VERSION = require('../package.json').version || '0.1.0';
const OS_USER = os.userInfo().username || 'unknown';

const OPENAI_PRICING = {
  'gpt-4o': { input: 2.50 / 1e6, output: 10.00 / 1e6, cached: 1.25 / 1e6 },
  'gpt-4o-mini': { input: 0.15 / 1e6, output: 0.60 / 1e6, cached: 0.075 / 1e6 },
  'o1': { input: 15.00 / 1e6, output: 60.00 / 1e6, cached: 7.50 / 1e6 },
  'o1-mini': { input: 1.10 / 1e6, output: 4.40 / 1e6, cached: 0.55 / 1e6 },
  'o3': { input: 15.00 / 1e6, output: 60.00 / 1e6, cached: 7.50 / 1e6 },
  'o3-mini': { input: 1.10 / 1e6, output: 4.40 / 1e6, cached: 0.55 / 1e6 },
  'default': { input: 2.50 / 1e6, output: 10.00 / 1e6, cached: 1.25 / 1e6 }
};

function calculateCost(model, inputTokens, outputTokens, cachedTokens = 0) {
  const m = (model || '').toLowerCase();
  let rates = OPENAI_PRICING.default;
  for (const [k, r] of Object.entries(OPENAI_PRICING)) {
    if (m.includes(k)) {
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

function transformCodexTurn(turn, sessionId, turnId, incrementalTokens = null, redact = null) {
  const envRedaction = (process.env.REDACTION || 'false').toLowerCase() === 'true';
  const doRedact = redact !== null ? redact : envRedaction;

  const model = turn.model || 'unknown';
  const provider = turn.model_provider || 'openai';
  const cwd = turn.cwd || '';
  const project = cwd ? path.basename(cwd) : null;

  let userPrompt = turn.user_prompt || '';
  let assistantText = turn.assistant_output || '';

  if (doRedact) {
    userPrompt = '[REDACTED]';
    assistantText = '[REDACTED]';
  }

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
    if (doRedact) {
      c.args = '[REDACTED]';
      c.output = '[REDACTED]';
    }
    return c;
  });

  const toolDurations = toolCalls
    .map(tc => (tc.end_ts && tc.start_ts && tc.end_ts >= tc.start_ts ? (tc.end_ts - tc.start_ts) : 0))
    .filter(d => d > 0);
  const toolDurationMs = toolDurations.length ? toolDurations.reduce((a, b) => a + b, 0) : null;

  const startTs = turn.turn_start_ms || Date.now();
  const durationMs = turn.duration_ms !== undefined ? turn.duration_ms : null;

  const payload = {
    sessionId: sessionId,
    uuid: turnId,
    eventId: turnId,
    timestamp: startTs,
    userPrompt: userPrompt,
    assistantText: assistantText,
    model: model,
    model_provider: provider,
    cwd: cwd || null,
    project: project,
    permissionMode: turn.permission_mode || null,
    sandbox_mode: turn.sandbox_mode || null,
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
    tools_used: toolCalls.map(tc => tc.tool).filter(Boolean),
    commands: commands.length ? commands : null,
    written_paths: writtenPaths.length ? writtenPaths : null,
    has_thinking: reasoningTokens > 0,
    integration_version: INTEGRATION_VERSION,
    os_user: OS_USER,
    cvs199: JSON.stringify(cleanToolCalls),
    cvs200: 'CodexHook'
  };

  // Remove null/undefined properties
  const cleanPayload = {};
  for (const [k, v] of Object.entries(payload)) {
    if (v !== null && v !== undefined) {
      cleanPayload[k] = v;
    }
  }
  return cleanPayload;
}

module.exports = {
  calculateCost,
  extractCommandsAndPaths,
  transformCodexTurn
};
