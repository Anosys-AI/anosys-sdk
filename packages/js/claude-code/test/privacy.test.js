'use strict';

// Privacy tests for the Claude Code hook: golden key sets per level (both layouts),
// no history backfill, hook detection, scrubbing and encryption. Mirrors the Python tests.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-cc-privacy-'));
process.env.HOME = TMP;
process.env.ANOSYS_CONSENT_FILE = path.join(TMP, 'consent.json');
process.env.ANOSYS_HOOK_DRY_RUN = 'true'; // read at load: the hook never posts in tests
for (const v of ['ANOSYS_DISABLE', 'ANOSYS_COLLECTION_LEVEL', 'REDACTION', 'ANOSYS_ENCRYPTION_KEY', 'ANOSYS_CLAUDE_PIXEL']) {
  delete process.env[v];
}
process.chdir(TMP);

const { describe, it, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const { ANOSYS_ENCRYPTION_PREFIX, FULL, METADATA, OFF, POLICY_VERSION, decrypt, deriveKeys } = require('anosys-sdk-core');
const hookRunner = require('../src/hookRunner');
const { hasAnosysHook, hookCommand, removeEnv, removeStopHooks, updateStopHooks } = require('../src/installer');
const { transformRecord } = require('../src/mapper');

const USER = {
  type: 'user', uuid: 'u1', sessionId: 's1', cwd: '/Users/dev/app', gitBranch: 'main',
  message: { role: 'user', content: 'Use key sk-ant-api03-abcdefghijklmnopqrstuvwxyz please' },
};
const ASSISTANT = {
  type: 'assistant', uuid: 'a1', sessionId: 's1', aiTitle: 'Fix the billing bug',
  message: {
    id: 'm1', model: 'claude-sonnet-5-5', role: 'assistant',
    content: [{ type: 'text', text: 'Done' }, { type: 'tool_use', id: 't1', name: 'Bash', input: { command: 'ls' } }],
    usage: { input_tokens: 10, output_tokens: 4 },
  },
  toolUseResult: { stdout: 'secret file contents' },
};
const CONTENT_KEYS = ['user_prompt', 'assistant_text', 'tool_use_result', 'cvs199', 'ai_title'];

afterEach(() => {
  delete process.env.ANOSYS_ENCRYPTION_KEY;
  delete process.env.ANOSYS_ENCRYPTION_SALT;
});

describe('collection levels', () => {
  for (const [name, record] of [['user', USER], ['assistant', ASSISTANT]]) {
    it(`metadata sends no content (${name})`, () => {
      const out = hookRunner.prepareRecord(transformRecord(record), METADATA);
      assert.equal(out.cvs198, 'metadata;none');
      for (const k of CONTENT_KEYS) assert.ok(!(k in out), k);
      for (const k of ['session_id', 'event_id', 'timestamp', 'cvs200']) assert.ok(k in out, k);
      const text = JSON.stringify(out);
      assert.ok(!text.includes('sk-ant') && !text.includes('secret file'));
    });
  }

  it('metadata keeps usage numbers', () => {
    const out = hookRunner.prepareRecord(transformRecord(ASSISTANT), METADATA);
    assert.equal(out.input_tokens, 10);
    assert.equal(out.output_tokens, 4);
    assert.equal(out.primary_model, 'claude-sonnet-5-5');
  });

  it('legacy CV layout at metadata sends only CV metadata columns', () => {
    const script = `
      const { METADATA } = require('anosys-sdk-core');
      const h = require(${JSON.stringify(path.join(__dirname, '..', 'src', 'hookRunner'))});
      const m = require(${JSON.stringify(path.join(__dirname, '..', 'src', 'mapper'))});
      process.stdout.write(JSON.stringify(h.prepareRecord(m.transformRecord(${JSON.stringify(ASSISTANT)}), METADATA)));`;
    const out = JSON.parse(execFileSync(process.execPath, ['-e', script], {
      cwd: path.join(__dirname, '..'), env: { ...process.env, ANOSYS_CLAUDE_PIXEL: 'false' },
    }).toString());
    const { CV_METADATA_FIELDS } = require('../src/mapper');
    for (const col of ['cvs4', 'cvs5', 'cvs26', 'cvs41', 'cvs199']) assert.ok(!(col in out), col);
    const allowed = new Set(['cvs198', 'timestamp', 'user_timestamp', 'event_id', 'event_type',
      'event_source_name', 'debug', 'cvs200', ...CV_METADATA_FIELDS]);
    for (const k of Object.keys(out)) assert.ok(allowed.has(k), k);
  });

  it('off sends nothing and full scrubs secrets', () => {
    assert.deepEqual(hookRunner.prepareRecord(transformRecord(USER), OFF), {});
    const out = hookRunner.prepareRecord(transformRecord(USER), FULL);
    assert.equal(out.cvs198, `full;${POLICY_VERSION}`);
    assert.ok(out.user_prompt.includes('[SECRET]') && !out.user_prompt.includes('sk-ant-api03'));
    assert.ok(!out.cvs199.includes('sk-ant-api03'));
  });

  it('full with encryption uses enc2 and JSON columns stay valid JSON', () => {
    process.env.ANOSYS_ENCRYPTION_KEY = 'pass';
    process.env.ANOSYS_ENCRYPTION_SALT = 'ws';
    const out = hookRunner.prepareRecord(transformRecord(ASSISTANT), FULL);
    const keys = deriveKeys('pass', 'ws');
    assert.ok(out.assistant_text.startsWith(ANOSYS_ENCRYPTION_PREFIX));
    assert.ok(out.tool_use_result.startsWith('"' + ANOSYS_ENCRYPTION_PREFIX));
    assert.ok(decrypt(out.tool_use_result, keys).includes('secret file contents'));
    assert.ok(out.ai_title.startsWith(ANOSYS_ENCRYPTION_PREFIX));
  });
});

describe('transcripts', () => {
  it('reads only the current session and its subagents', () => {
    const project = path.join(TMP, 'projects', 'app');
    fs.mkdirSync(path.join(project, 's1', 'subagents'), { recursive: true });
    fs.mkdirSync(path.join(project, 'old-session', 'subagents'), { recursive: true });
    fs.writeFileSync(path.join(project, 's1.jsonl'), '{}\n');
    fs.writeFileSync(path.join(project, 's1', 'subagents', 'agent-a.jsonl'), '{}\n');
    fs.writeFileSync(path.join(project, 'old-session.jsonl'), '{}\n');
    fs.writeFileSync(path.join(project, 'old-session', 'subagents', 'agent-b.jsonl'), '{}\n');
    const primary = { path: path.join(project, 's1.jsonl'), state_key: 's1', session_id: 's1', is_agent: false };
    const found = hookRunner.sessionTranscripts(primary).map(t => path.basename(t.path));
    assert.deepEqual(found, ['s1.jsonl', 'agent-a.jsonl']);
  });

  it('the hook log never holds prompt text', async () => {
    const transcript = path.join(TMP, 'projects', 'app', 'logged.jsonl');
    fs.writeFileSync(transcript, JSON.stringify({ ...USER, sessionId: 'logged' }) + '\n');
    await hookRunner.main({ delayMs: 0, stdinCtx: { transcript_path: transcript, session_id: 'logged' } });
    const log = fs.readFileSync(hookRunner.LOG_FILE, 'utf8');
    assert.ok(log.includes('[DRY RUN]') && log.includes("at 'metadata'"));
    assert.ok(!log.includes('sk-ant') && !log.includes('Use key'));
    assert.equal(fs.statSync(hookRunner.LOG_FILE).mode & 0o777, 0o600);
  });

  it('advances watermark when collection level is off (B3 fix)', async () => {
    const transcript = path.join(TMP, 'projects', 'app', 'off-session.jsonl');
    const lines = [
      JSON.stringify({ uuid: 'u1', type: 'user', message: { content: 'secret 1' } }),
      JSON.stringify({ uuid: 'u2', type: 'assistant', message: { content: 'secret 2' } }),
    ];
    fs.writeFileSync(transcript, lines.join('\n') + '\n');

    const origDisable = process.env.ANOSYS_DISABLE;
    const origDryRun = hookRunner.DRY_RUN;
    try {
      process.env.ANOSYS_DISABLE = '1';
      hookRunner.DRY_RUN = false;

      await hookRunner.main({ delayMs: 0, dryRun: false, stdinCtx: { transcript_path: transcript, session_id: 'off-session' } });

      const state = hookRunner.loadState();
      assert.ok(state['off-session'], 'state must record off-session');
      assert.equal(state['off-session'].last_line, 2);
      assert.equal(state['off-session'].last_message_uuid, 'u2');
    } finally {
      if (origDisable !== undefined) process.env.ANOSYS_DISABLE = origDisable; else delete process.env.ANOSYS_DISABLE;
      hookRunner.DRY_RUN = origDryRun;
    }
  });
});

describe('installer', () => {
  it('detects and removes an unmarked hook', () => {
    const settings = {
      hooks: { Stop: [
        { hooks: [{ type: 'command', command: 'npx anosys-sdk-claude-code run' }] },
        { hooks: [{ type: 'command', command: 'other-tool' }] },
      ] },
      env: { REDACTION: 'true', ANOSYS_HOOK_APIKEY: 'k', KEEP: '1' },
    };
    assert.ok(hasAnosysHook(settings));
    const out = removeEnv(removeStopHooks(settings));
    assert.ok(!hasAnosysHook(out));
    assert.deepEqual(out.hooks.Stop, [{ hooks: [{ type: 'command', command: 'other-tool' }] }]);
    assert.deepEqual(out.env, { KEEP: '1' });
  });

  it('the hook command uses this Node by absolute path', () => {
    const settings = updateStopHooks({}, hookCommand());
    const command = settings.hooks.Stop[0].hooks[0].command;
    assert.ok(command.startsWith(`"${process.execPath}"`) && hasAnosysHook(settings));
  });
});
