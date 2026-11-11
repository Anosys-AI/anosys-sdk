'use strict';

// Privacy tests for the Antigravity hook: golden key sets per level and the absolute hook command.

const fs = require('fs');
const os = require('os');
const path = require('path');

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-ag-privacy-'));
process.env.HOME = TMP;
process.env.ANOSYS_CONSENT_FILE = path.join(TMP, 'consent.json');
process.env.ANOSYS_HOOK_DRY_RUN = 'true';
for (const v of ['ANOSYS_DISABLE', 'ANOSYS_COLLECTION_LEVEL', 'REDACTION', 'ANOSYS_ENCRYPTION_KEY']) delete process.env[v];
process.chdir(TMP);

const test = require('node:test');
const assert = require('node:assert/strict');
const { FULL, METADATA, OFF, POLICY_VERSION } = require('anosys-sdk-core');
const hookRunner = require('../src/hookRunner');
const { loadJson, updateHooksConfig } = require('../src/installer');
const { HOOK_COMMAND } = require('../src/constants');
const { transformAntigravityTurn } = require('../src/mapper');

const TURN = {
  user_input: 'Rotate token ghp_abcdefghijklmnopqrstuvwxyz0123456789',
  final_response: 'Rotated',
  model_name: 'gemini-3-pro',
  start_ms: 1000, end_ms: 2500,
  active_document: '/Users/dev/app/secrets.env',
  tool_steps: [{ tool: 'run_command', args: { CommandLine: 'cat .env' }, output: 'API_KEY=abc' }],
};
const CONTENT = ['user_prompt', 'userPrompt', 'assistant_text', 'assistantText', 'cvs4', 'cvs5',
  'commands', 'cvs90', 'cvs199', 'active_document', 'cvs70'];

const mapped = () => transformAntigravityTurn(TURN, 's1', 's1_0', { workspacePaths: ['/Users/dev/app'] });

test('metadata by default sends no content', () => {
  const out = hookRunner.prepareRecord(mapped(), METADATA);
  for (const k of CONTENT) assert.ok(!(k in out), k);
  assert.equal(out.cvs198, 'metadata;none');
  assert.equal(out.cvs198, 'metadata;none');
  assert.equal(out.model, 'gemini-3-pro');
  const text = JSON.stringify(out);
  assert.ok(!text.includes('ghp_') && !text.includes('API_KEY'));
});

test('off sends nothing and full scrubs secrets', () => {
  assert.deepEqual(hookRunner.prepareRecord(mapped(), OFF), {});
  const out = hookRunner.prepareRecord(mapped(), FULL);
  assert.equal(out.cvs198, `full;${POLICY_VERSION}`);
  assert.ok(!out.user_prompt.includes('ghp_abcdef') && out.user_prompt.includes('[SECRET]'));
});

test('the hook command is absolute', () => {
  const hooks = path.join(TMP, 'hooks.json');
  updateHooksConfig(hooks, HOOK_COMMAND);
  const command = JSON.stringify(loadJson(hooks));
  assert.ok(command.includes(process.execPath.replace(/\\/g, '\\\\')) && command.includes('cli.js'));
});

test('the hook log never holds prompt text', async () => {
  const transcript = path.join(TMP, 'brain', 's2', 'transcript.jsonl');
  fs.mkdirSync(path.dirname(transcript), { recursive: true });
  fs.writeFileSync(transcript, '');
  await hookRunner.processTurns('stop', { transcriptPath: transcript, conversationId: 's2' }, hookRunner.getConfig(), METADATA);
  if (fs.existsSync(hookRunner.LOG_FILE)) {
    assert.ok(!fs.readFileSync(hookRunner.LOG_FILE, 'utf8').includes(transcript));
    if (process.platform !== 'win32') {
      assert.equal(fs.statSync(hookRunner.LOG_FILE).mode & 0o777, 0o600);
    }
  }
});
