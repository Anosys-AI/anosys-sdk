const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const os = require('os');

const {
  isoToMs,
  extractUserRequest,
  extractMetadataFields,
  extractSettingsChange,
  parseTranscript,
} = require('../src/transcript');
const {
  extractToolDetails,
  transformAntigravityTurn,
} = require('../src/mapper');
const {
  hasAnosysHook,
  updateHooksConfig,
  removeHooksConfig,
  updateEnvConfig,
  removeEnvConfig,
  validateApiKey,
} = require('../src/installer');
const { HOOK_NAME, INTEGRATION_VERSION } = require('../src/constants');

test('transcript.isoToMs parses timestamps', () => {
  assert.ok(isoToMs('2026-09-21T19:57:09Z') > 0);
  assert.ok(isoToMs('2026-09-21T19:57:09+03:00') > 0);
  assert.equal(isoToMs(''), 0);
  assert.equal(isoToMs('invalid'), 0);
});

test('transcript.extractUserRequest extracts clean request', () => {
  const content = `
<USER_REQUEST>
Build Antigravity telemetry
</USER_REQUEST>
<ADDITIONAL_METADATA>
The current local time is: 2026-09-21T19:57:09+03:00.
</ADDITIONAL_METADATA>`;
  assert.equal(extractUserRequest(content), 'Build Antigravity telemetry');

  // Fallback
  assert.equal(extractUserRequest('Simple prompt without tags'), 'Simple prompt without tags');
});

test('transcript.extractMetadataFields extracts IDE context', () => {
  const content = `
<ADDITIONAL_METADATA>
The current local time is: 2026-09-21T19:57:09+03:00.
Active Document: C:\\workspace\\app.js (LANGUAGE_JAVASCRIPT)
Cursor is on line: 120
</ADDITIONAL_METADATA>`;
  const meta = extractMetadataFields(content);
  assert.equal(meta.active_document, 'C:\\workspace\\app.js');
  assert.equal(meta.active_document_language, 'LANGUAGE_JAVASCRIPT');
  assert.equal(meta.cursor_line, 120);
  assert.equal(meta.client_timestamp_iso, '2026-09-21T19:57:09+03:00');
});

test('transcript.extractSettingsChange extracts model', () => {
  const content = `
<USER_SETTINGS_CHANGE>
The user changed setting \`Model Selection\` from None to gemini-2.5-flash.
</USER_SETTINGS_CHANGE>`;
  const s = extractSettingsChange(content);
  assert.equal(s.model_name, 'gemini-2.5-flash');
  assert.ok(s.user_settings_change.includes('Model Selection'));
});

test('transcript.parseTranscript parses turn records', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ag-test-'));
  const transcriptFile = path.join(tmpDir, 'transcript_full.jsonl');

  const records = [
    {
      step_index: 1,
      type: 'USER_INPUT',
      source: 'USER_EXPLICIT',
      created_at: '2026-09-21T19:57:00Z',
      content: '<USER_REQUEST>Test everything</USER_REQUEST>\n<ADDITIONAL_METADATA>\nActive Document: /test.js (LANGUAGE_JAVASCRIPT)\nCursor is on line: 10\n</ADDITIONAL_METADATA>',
    },
    {
      step_index: 2,
      type: 'PLANNER_RESPONSE',
      created_at: '2026-09-21T19:57:02Z',
      content: 'Running tests now.',
      thinking: 'Thinking about the suite.',
      tool_calls: [{ name: 'run_command', args: { CommandLine: 'npm test' } }],
    },
    {
      step_index: 3,
      type: 'TOOL_RESULT',
      created_at: '2026-09-21T19:57:03Z',
      status: 'DONE',
      content: 'Created At: 2026-09-21T19:57:02Z\nCompleted At: 2026-09-21T19:57:04Z\nPASS',
    },
    {
      step_index: 4,
      type: 'PLANNER_RESPONSE',
      created_at: '2026-09-21T19:57:05Z',
      content: 'Done running tests.',
    },
  ];

  fs.writeFileSync(transcriptFile, records.map(r => JSON.stringify(r)).join('\n') + '\n');
  const turns = parseTranscript(transcriptFile);
  assert.equal(turns.length, 1);
  const t = turns[0];
  assert.equal(t.user_input, 'Test everything');
  assert.equal(t.final_response, 'Done running tests.');
  assert.equal(t.has_thinking, true);
  assert.equal(t.tool_steps.length, 1);
  assert.equal(t.tool_steps[0].name, 'run_command');
  assert.equal(t.tool_steps[0].duration_ms, 2000);

  fs.rmSync(tmpDir, { recursive: true, force: true });
});

test('mapper.extractToolDetails categorizes invocations', () => {
  const steps = [
    { name: 'run_command', args: { CommandLine: 'npm run dev' }, duration_ms: 500 },
    { name: 'write_to_file', args: { TargetFile: '/src/code.js' }, duration_ms: 100 },
    { name: 'view_file', args: { AbsolutePath: '/doc.md' }, duration_ms: 50 },
    { name: 'search_web', args: { query: 'antigravity tracing' }, duration_ms: 600 },
    { name: 'browser_subagent', args: { TaskName: 'Login test' }, duration_ms: 3000 },
  ];
  const details = extractToolDetails(steps);
  assert.equal(details.tool_count, 5);
  assert.ok(details.commands.includes('npm run dev'));
  assert.ok(details.written_paths.includes('/src/code.js'));
  assert.ok(details.viewed_paths.includes('/doc.md'));
  assert.ok(details.searched_queries.includes('antigravity tracing'));
  assert.ok(details.subagents_spawned.includes('Login test'));
  assert.equal(details.tool_duration_ms, 4250);
});

test('mapper.transformAntigravityTurn matches AnoSys schema', () => {
  const turn = {
    user_input: 'Write a unit test',
    final_response: 'Unit test written and passed.',
    model_name: 'gemini-2.5-pro',
    start_ms: 1700000000000,
    end_ms: 1700000005000,
    active_document: '/test/suite.js',
    active_document_language: 'LANGUAGE_JAVASCRIPT',
    cursor_line: 55,
    client_timestamp_iso: '2026-09-21T19:57:09+03:00',
    has_thinking: true,
    step_count: 5,
    max_step_index: 4,
    llm_steps: [{ content: 'Writing test...', start_ms: 1700000000000, end_ms: 1700000002000 }],
    tool_steps: [
      { name: 'write_to_file', args: { TargetFile: '/test/suite.js' }, duration_ms: 150 }
    ],
  };

  const payload = transformAntigravityTurn(
    turn,
    'conv-js-123',
    'conv-js-123_0',
    { workspacePaths: ['/workspace/my-app'], terminationReason: 'model_stop' },
    false
  );

  // Named variables
  assert.equal(payload.session_id, 'conv-js-123');
  assert.equal(payload.sessionId, 'conv-js-123');
  assert.equal(payload.uuid, 'conv-js-123_0');
  assert.equal(payload.event_type, 'antigravity_turn');
  assert.equal(payload.event_source_name, 'antigravity');
  assert.equal(payload.user_prompt, 'Write a unit test');
  assert.equal(payload.assistant_text, 'Unit test written and passed.');
  assert.equal(payload.model, 'gemini-2.5-pro');
  assert.equal(payload.model_provider, 'google');
  assert.equal(payload.cwd, '/workspace/my-app');
  assert.equal(payload.project, 'my-app');
  assert.equal(payload.active_document, '/test/suite.js');
  assert.equal(payload.duration_ms, 5000);
  assert.equal(payload.has_thinking, true);
  assert.equal(payload.tool_count, 1);
  assert.equal(payload.integration_version, INTEGRATION_VERSION);

  // CV columns
  assert.equal(payload.cvs1, 'conv-js-123');
  assert.equal(payload.cvs2, 'my-app');
  assert.equal(payload.cvs4, 'Write a unit test');
  assert.equal(payload.cvs5, 'Unit test written and passed.');
  assert.equal(payload.cvs6, 'model_stop');
  assert.equal(payload.cvs9, 'gemini-2.5-pro');
  assert.equal(payload.cvs12, '/workspace/my-app');
  assert.equal(payload.cvs17, 'google');
  assert.equal(payload.cvs70, '/test/suite.js');
  assert.equal(payload.cvs71, 'LANGUAGE_JAVASCRIPT');
  assert.equal(payload.cvn25, 55);
  assert.equal(payload.cvn6, 5000);
  assert.equal(payload.cvn41, 1);
  assert.equal(payload.cvb2, true);
  assert.equal(payload.cvs200, 'AntigravityHook');
});

test('mapper.transformAntigravityTurn handles content redaction', () => {
  const turn = {
    user_input: 'Top secret secret_key_456',
    final_response: 'Stored secret_key_456 safely.',
    tool_steps: [],
  };

  const payload = transformAntigravityTurn(turn, 'c1', 'c1_0', {}, true);
  assert.equal(payload.user_prompt, '[REDACTED]');
  assert.equal(payload.assistant_text, '[REDACTED]');
  assert.equal(payload.cvs4, '[REDACTED]');
  assert.equal(payload.cvs5, '[REDACTED]');
  assert.ok(!payload.cvs199.includes('secret_key_456'));
});

test('installer manages hooks.json lifecycle idempotently and preserves existing hooks', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ag-hooks-'));
  const hooksFile = path.join(tmpDir, 'hooks.json');

  // Pre-existing hook
  fs.writeFileSync(hooksFile, JSON.stringify({ 'other-hook': { Stop: [] } }));

  assert.equal(hasAnosysHook({}), false);

  updateHooksConfig(hooksFile, 'anosys-antigravity run');
  const data = JSON.parse(fs.readFileSync(hooksFile, 'utf-8'));
  assert.equal(hasAnosysHook(data), true);
  assert.ok(data['other-hook']);
  assert.ok(data[HOOK_NAME].PreInvocation);
  assert.ok(data[HOOK_NAME].Stop);

  // Uninstall
  const removed = removeHooksConfig(hooksFile);
  assert.equal(removed, true);
  const dataAfter = JSON.parse(fs.readFileSync(hooksFile, 'utf-8'));
  assert.equal(hasAnosysHook(dataAfter), false);
  assert.ok(dataAfter['other-hook']);

  fs.rmSync(tmpDir, { recursive: true, force: true });
});

test('installer manages anosys-env.json lifecycle', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ag-env-'));
  const envFile = path.join(tmpDir, 'anosys-env.json');

  updateEnvConfig(envFile, { apiKey: 'key-123', endpointUrl: 'https://test/ingest', redaction: true });
  const data = JSON.parse(fs.readFileSync(envFile, 'utf-8'));
  assert.equal(data.ANOSYS_HOOK_APIKEY, 'key-123');
  assert.equal(data.ANOSYS_HOOK_ENDPOINT_URL, 'https://test/ingest');
  assert.equal(data.REDACTION, 'true');

  assert.equal(removeEnvConfig(envFile), true);
  assert.equal(fs.existsSync(envFile), false);

  fs.rmSync(tmpDir, { recursive: true, force: true });
});

test('validateApiKey rejects empty key', async () => {
  const res = await validateApiKey('');
  assert.equal(res, false);
});
