'use strict';

// Privacy and delivery tests for the Codex hook (mirrors Python tests/test_privacy_levels.py).

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const tmpHome = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-privacy-'));
process.env.CODEX_HOME = path.join(tmpHome, '.codex');
process.env.ANOSYS_CONSENT_FILE = path.join(tmpHome, 'consent.json');
for (const v of ['ANOSYS_DISABLE', 'ANOSYS_COLLECTION_LEVEL', 'REDACTION', 'ANOSYS_ENCRYPTION_KEY', 'ANOSYS_HOOK_DRY_RUN']) delete process.env[v];

const { FULL, METADATA, OFF, POLICY_VERSION, PendingQueue, decrypt, deriveKeys, writeConsent } = require('anosys-sdk-core');
const { transformCodexTurn } = require('../src/mapper');
const hookRunner = require('../src/hookRunner');
const { updateCodexConfig, removeCodexConfig, loadToml, hasAnosysHook } = require('../src/installer');

const TURN = {
  turn_id: 'turn-1', model: 'gpt-5', cwd: '/Users/dev/project',
  user_prompt: 'Deploy with key sk-proj-abcdefghijklmnopqrstuvwxyz', assistant_output: 'Done',
  tokens: { input_tokens: 10, output_tokens: 5, total_tokens: 15 },
  tool_calls: [{ tool: 'shell', args: JSON.stringify({ command: 'echo $TOKEN' }), output: 'secret' }],
  raw: { events: [{ payload: { output: 'file contents' } }] },
};
// Same golden set as Python
const METADATA_KEYS = [
  'session_id', 'sessionId', 'uuid', 'eventId', 'event_id', 'event_type', 'event_source_name',
  'timestamp', 'user_timestamp', 'debug', 'model', 'primary_model', 'model_provider', 'cwd', 'project',
  'input_tokens', 'output_tokens', 'total_tokens', 'cache_read', 'cache_creation', 'reasoning_tokens',
  'cost_estimate', 'incremental_input', 'incremental_output', 'incremental_total', 'incremental_cost',
  'incremental_cache_read', 'incremental_cache_creation', 'tool_count', 'has_thinking',
  'integration_version', 'os_user', 'consent', 'cvs198',
  'cvs1', 'cvs2', 'cvs9', 'cvs12', 'cvs19', 'cvs32', 'cvs33', 'cvn1', 'cvn2', 'cvn3', 'cvn4', 'cvn5', 'cvn7',
  'cvs200',
].sort();
const CONTENT_KEYS = ['user_prompt', 'userPrompt', 'assistant_text', 'assistantText', 'cvs4', 'cvs5', 'commands', 'cvs199'];
const mapped = () => transformCodexTurn(TURN, 's1', 't1');

function reset() {
  for (const f of [process.env.ANOSYS_CONSENT_FILE, hookRunner.PENDING_FILE, hookRunner.PAUSE_FILE, hookRunner.STATE_FILE]) {
    try { fs.unlinkSync(f); } catch { /* absent */ }
  }
}

function fakePost(...statuses) {
  const bodies = [];
  const post = async (url, body) => { bodies.push(body); return { status: statuses.length ? statuses.shift() : 200 }; };
  post.bodies = bodies;
  return post;
}
const event = (turnId) => JSON.stringify({ type: 'agent-turn-complete', 'thread-id': 's1', 'turn-id': turnId,
  'input-messages': ['hello'], 'last-assistant-message': 'hi' });

test('metadata is the default and sends no content (same keys as Python)', () => {
  reset();
  const record = hookRunner.prepareRecord(mapped(), METADATA);
  assert.deepEqual(Object.keys(record).sort(), METADATA_KEYS);
  assert.equal(record.consent, 'metadata;none');
  assert.equal(record.cvs198, 'metadata;none');
  for (const k of CONTENT_KEYS) assert.ok(!(k in record));
});

test('off sends nothing; full keeps content and scrubs secrets', () => {
  assert.deepEqual(hookRunner.prepareRecord(mapped(), OFF), {});
  const record = hookRunner.prepareRecord(mapped(), FULL);
  assert.equal(record.consent, `full;${POLICY_VERSION}`);
  assert.ok(record.user_prompt.includes('[SECRET]') && !record.user_prompt.includes('sk-proj-abcdef'));
  assert.ok(!record.cvs199.includes('sk-proj-abcdef'));
});

test('full with encryption keeps JSON columns valid JSON', () => {
  process.env.ANOSYS_ENCRYPTION_KEY = 'pass';
  process.env.ANOSYS_ENCRYPTION_SALT = 'ws';
  const record = hookRunner.prepareRecord(mapped(), FULL);
  delete process.env.ANOSYS_ENCRYPTION_KEY;
  const keys = deriveKeys('pass', 'ws');
  assert.ok(record.user_prompt.startsWith('enc2:'));
  assert.ok(record.commands.startsWith('"enc2:'));
  assert.equal(decrypt(record.assistant_text, keys), 'Done');
  assert.equal(record.input_tokens, 10);
});

test('a turn is sent at metadata; level off sends nothing', async () => {
  reset();
  let post = fakePost(200);
  await hookRunner.run(['run', event('t1')], { post });
  assert.equal(post.bodies.length, 1);
  assert.equal(post.bodies[0][0].consent, 'metadata;none');
  assert.ok(!('user_prompt' in post.bodies[0][0]));
  writeConsent(OFF, 'test');
  post = fakePost();
  await hookRunner.run(['run', event('t2')], { post });
  assert.deepEqual(post.bodies, []);
});

test('outage queues then drains; 403 pauses without queueing', async () => {
  reset();
  for (const i of [1, 2, 3]) await hookRunner.run(['run', event(`o${i}`)], { post: fakePost(503, 503) });
  assert.equal(new PendingQueue(hookRunner.PENDING_FILE).load().length, 3);
  const post = fakePost(200, 200);
  await hookRunner.run(['run', event('o9')], { post });
  assert.equal(post.bodies.flat().length, 4);
  assert.ok(!fs.existsSync(hookRunner.PENDING_FILE));
  reset();
  await hookRunner.run(['run', event('p1')], { post: fakePost(403) });
  const after = fakePost();
  await hookRunner.run(['run', event('p2')], { post: after });
  assert.deepEqual(after.bodies, []);
  assert.ok(!fs.existsSync(hookRunner.PENDING_FILE));
});

test('the log never contains the notification content', async () => {
  reset();
  await hookRunner.run(['run', event('l1')], { post: fakePost(200) });
  const text = fs.readFileSync(hookRunner.LOG_FILE, 'utf8');
  assert.ok(!text.includes('hello') && !text.includes('last-assistant-message'));
  assert.equal(fs.statSync(hookRunner.LOG_FILE).mode & 0o777, 0o600);
});

test('parseArgv separates a chained notify command', () => {
  const { previous, raw } = hookRunner.parseArgv(['run', '--previous-notify', '["a","b"]', '{"x":1}']);
  assert.deepEqual(previous, ['a', 'b']);
  assert.deepEqual(JSON.parse(raw), { x: 1 });
});

test('install keeps another notify and uninstall restores it, also when ours is nested', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'codex-notify-'));
  const cfg = path.join(dir, 'config.toml');
  const wrapper = '/Apps/Codex Computer Use.app/SkyComputerUseClient';
  fs.writeFileSync(cfg, `model = "gpt-5"\nnotify = ["${wrapper}", "turn-ended"]\n\n[tbl]\nx = 1\n`);
  assert.equal(updateCodexConfig(null, cfg), true);
  assert.equal(hasAnosysHook(loadToml(cfg)), true);
  assert.equal(updateCodexConfig(null, cfg), false);
  removeCodexConfig(cfg);
  assert.deepEqual(loadToml(cfg).notify, [wrapper, 'turn-ended']);
  assert.ok(fs.readFileSync(cfg, 'utf8').includes('[tbl]'));
  const nested = JSON.stringify(['/py', '-m', 'anosys_sdk_codex.hook_runner']);
  fs.writeFileSync(cfg, `notify = ${JSON.stringify([wrapper, 'turn-ended', '--previous-notify', nested])}\n`);
  removeCodexConfig(cfg);
  assert.deepEqual(loadToml(cfg).notify, [wrapper, 'turn-ended']);
  fs.writeFileSync(cfg, 'notify = ["anosys-codex", "run"]\nmodel="x"\n');
  removeCodexConfig(cfg);
  assert.equal(loadToml(cfg).notify, undefined);
});
