'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const os = require('os');

const {
  calculateCost,
  extractCommandsAndPaths,
  transformCodexTurn
} = require('../src/mapper');

const {
  HOOK_COMMAND,
  backup,
  hasAnosysHook,
  loadToml,
  updateCodexConfig,
  removeCodexConfig,
  updateCodexEnv
} = require('../src/installer');

const {
  extractTurnFromRollout,
  extractTurnFallback
} = require('../src/hookRunner');

test('calculateCost calculates correct OpenAI pricing', () => {
  const cost4o = calculateCost('gpt-4o', 1000, 1000, 500);
  assert.ok(cost4o > 0);

  const costO3 = calculateCost('o3-mini', 2000, 500, 0);
  assert.ok(costO3 > 0);
});

test('extractCommandsAndPaths parses tools correctly', () => {
  const tools = [
    { tool: 'shell', args: JSON.stringify({ command: 'npm test' }) },
    { tool: 'apply_patch', args: JSON.stringify({ path: 'src/index.js' }) },
    { tool: 'web_search', args: 'node docs' }
  ];
  const { commands, writtenPaths } = extractCommandsAndPaths(tools);
  assert.ok(commands.includes('npm test'));
  assert.ok(writtenPaths.includes('src/index.js'));
});

test('transformCodexTurn matches AnoSys schema', () => {
  const turn = {
    turn_id: 'turn-js-1',
    model: 'gpt-4o',
    model_provider: 'openai',
    cwd: '/project/app',
    permission_mode: 'auto',
    user_prompt: 'Run build',
    assistant_output: 'Build successful.',
    turn_start_ms: 1700000000000,
    turn_end_ms: 1700000004000,
    duration_ms: 4000,
    tokens: {
      input_tokens: 1200,
      output_tokens: 250,
      total_tokens: 1450,
      cached_input_tokens: 400,
      reasoning_output_tokens: 50
    },
    tool_calls: [
      {
        tool: 'shell',
        args: JSON.stringify({ command: 'npm run build' }),
        output: 'Done',
        call_id: 'c_build',
        start_ts: 1700000001000,
        end_ts: 1700000002000
      }
    ]
  };

  const mapped = transformCodexTurn(turn, 'session-js', 'turn-js-1');

  assert.equal(mapped.cvs200, 'CodexHook');
  assert.equal(mapped.sessionId, 'session-js');
  assert.equal(mapped.uuid, 'turn-js-1');
  assert.equal(mapped.userPrompt, 'Run build');
  assert.equal(mapped.assistantText, 'Build successful.');
  assert.equal(mapped.model, 'gpt-4o');
  assert.equal(mapped.project, 'app');
  assert.equal(mapped.input_tokens, 1200);
  assert.equal(mapped.output_tokens, 250);
  assert.equal(mapped.cache_read, 400);
  assert.equal(mapped.reasoning_tokens, 50);
  assert.equal(mapped.has_thinking, true);
  assert.equal(mapped.tool_count, 1);
  assert.ok(mapped.commands.includes('npm run build'));
  assert.ok(mapped.cvs199);
});

test('transformCodexTurn handles content redaction', () => {
  const turn = {
    turn_id: 'turn-redact',
    model: 'o1',
    user_prompt: 'Confidential project details',
    assistant_output: 'Here is the confidential response',
    tokens: { input_tokens: 10, output_tokens: 10 },
    tool_calls: [{ tool: 'shell', args: 'cat secret.key', output: 'secret' }]
  };

  const mapped = transformCodexTurn(turn, 'sess-redact', 'turn-redact', null, true);

  assert.equal(mapped.userPrompt, '[REDACTED]');
  assert.equal(mapped.assistantText, '[REDACTED]');
  assert.ok(mapped.cvs199.includes('[REDACTED]'));
});

test('installer manages config.toml lifecycle idempotently', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-js-test-'));
  const configPath = path.join(tmpDir, 'config.toml');
  const envPath = path.join(tmpDir, 'anosys-env.sh');

  // 1. Update config
  const updated = updateCodexConfig(HOOK_COMMAND, configPath);
  assert.equal(updated, true);
  assert.ok(fs.existsSync(configPath));

  const data = loadToml(configPath);
  assert.equal(hasAnosysHook(data), true);
  assert.ok(data.notify.includes(HOOK_COMMAND));

  // 2. Idempotent check
  const updatedAgain = updateCodexConfig(HOOK_COMMAND, configPath);
  assert.equal(updatedAgain, false);

  // 3. Backup
  const bk = backup(configPath);
  assert.ok(bk && fs.existsSync(bk));

  // 4. Update env
  updateCodexEnv({ apiKey: 'key-123', redaction: true, customPath: envPath });
  assert.ok(fs.existsSync(envPath));
  const envText = fs.readFileSync(envPath, 'utf8');
  assert.ok(envText.includes('key-123'));
  assert.ok(envText.includes('REDACTION="true"'));

  // 5. Remove config
  const removed = removeCodexConfig(configPath);
  assert.equal(removed, true);
  const dataAfter = loadToml(configPath);
  assert.equal(hasAnosysHook(dataAfter), false);

  fs.rmSync(tmpDir, { recursive: true, force: true });
});

test('extractTurnFromRollout extracts structured events', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-rollout-test-'));
  const rolloutPath = path.join(tmpDir, 'rollout-js-session.jsonl');

  const lines = [
    { type: 'session_meta', payload: { model_provider: 'openai' } },
    { type: 'turn_context', payload: { turn_id: 'turn-js', model: 'gpt-4o', cwd: '/workspace/app', approval_policy: 'auto' } },
    { type: 'event_msg', timestamp: '2026-05-20T12:00:00Z', payload: { type: 'task_started', turn_id: 'turn-js', started_at: 1700000000 } },
    { type: 'event_msg', payload: { type: 'user_message', message: 'test user message' } },
    { type: 'event_msg', payload: { type: 'token_count', info: { last_token_usage: { input_tokens: 300, output_tokens: 50, total_tokens: 350, cached_input_tokens: 100 } } } },
    { type: 'response_item', timestamp: '2026-05-20T12:00:01Z', payload: { type: 'function_call', name: 'shell', call_id: 'c_test', arguments: '{"command":"git diff"}' } },
    { type: 'response_item', timestamp: '2026-05-20T12:00:02Z', payload: { type: 'function_call_output', call_id: 'c_test', output: 'diff content' } },
    { type: 'event_msg', payload: { type: 'agent_message', message: 'test assistant message' } },
    { type: 'event_msg', payload: { type: 'task_complete', completed_at: 1700000005, duration_ms: 5000 } }
  ];

  fs.writeFileSync(rolloutPath, lines.map(l => JSON.stringify(l)).join('\n') + '\n', 'utf8');

  const turn = extractTurnFromRollout(rolloutPath, 'turn-js');
  assert.ok(turn);
  assert.equal(turn.turn_id, 'turn-js');
  assert.equal(turn.user_prompt, 'test user message');
  assert.equal(turn.assistant_output, 'test assistant message');
  assert.equal(turn.model, 'gpt-4o');
  assert.equal(turn.tokens.input_tokens, 300);
  assert.equal(turn.tokens.output_tokens, 50);
  assert.equal(turn.tokens.cached_input_tokens, 100);
  assert.equal(turn.tool_calls.length, 1);
  assert.equal(turn.tool_calls[0].tool, 'shell');
  assert.equal(turn.tool_calls[0].output, 'diff content');

  fs.rmSync(tmpDir, { recursive: true, force: true });
});

test('extractTurnFallback extracts fallback data', () => {
  const event = {
    'last-assistant-message': 'fallback ans',
    'input-messages': ['fallback q'],
    model: 'o3-mini'
  };
  const fb = extractTurnFallback(event, 'sess-fb', 'turn-fb');
  assert.equal(fb.turn_id, 'turn-fb');
  assert.equal(fb.user_prompt, 'fallback q');
  assert.equal(fb.assistant_output, 'fallback ans');
  assert.equal(fb.model, 'o3-mini');
});

test('cmdInstall runs non-interactively with -y and --api-key', async () => {
  const { cmdInstall } = require('../src/cli');
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-cli-test-'));
  const origHome = process.env.HOME;
  const origUserProfile = process.env.USERPROFILE;
  process.env.HOME = tmpDir;
  process.env.USERPROFILE = tmpDir;

  try {
    // Should complete cleanly without any prompts
    await cmdInstall(['install', '--api-key', 'test-api-key-12345', '-y']);
    const envFile = path.join(tmpDir, '.codex', 'anosys-env.sh');
    assert.ok(fs.existsSync(envFile));
    const envContent = fs.readFileSync(envFile, 'utf8');
    assert.ok(envContent.includes('test-api-key-12345'));
  } finally {
    process.env.HOME = origHome;
    process.env.USERPROFILE = origUserProfile;
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});
