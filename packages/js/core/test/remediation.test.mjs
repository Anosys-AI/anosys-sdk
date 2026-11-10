import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

import {
  BASE_KEY_MAPPING,
  JSON_COLUMNS,
  createDecorators,
  encryptPayload,
  getTargetColumns,
  reassign,
  scrubSecrets,
} from '../src/index.js';

const { anosysLogger } = createDecorators();

const require = createRequire(import.meta.url);
const { calculateCost: codexCalculateCost } = require('../../codex/src/mapper.js');
const { isAnthropicSpan } = require('../../anthropic/src/hooks.js');
const { extractGenAiSpanInfo } = require('../../anthropic/src/genai.js');
const { extractToolDetails, transformAntigravityTurn } = require('../../antigravity/src/mapper.js');
const { buildTurn } = require('../../antigravity/src/transcript.js');

test('reassign handles non-finite numbers and updates keyToCvs in-place', () => {
  const keyToCvs = { ...BASE_KEY_MAPPING };
  const payload = {
    'service.name': 'remediation-test',
    custom_mapping: '{}',
    finite_val: 12,
    inf_val: Infinity,
    nan_val: NaN,
    custom_unmapped_field: 'hello',
  };
  const res = reassign(payload, keyToCvs);
  for (const [k, v] of Object.entries(res)) {
    if (k.startsWith('cvn') && typeof v === 'number') {
      assert.ok(Number.isFinite(v), `non-finite value in ${k}`);
    }
  }
  assert.ok(Object.keys(keyToCvs).includes('custom_unmapped_field'));
  assert.ok(res.otel_schema_url.includes('custom_unmapped_field'));
});

test('JSON_COLUMNS includes GenAI array/JSON columns and getTargetColumns mirrors cvs199', () => {
  for (const col of [
    'gen_ai_input_messages',
    'gen_ai_output_messages',
    'gen_ai_system_instructions',
    'gen_ai_tool_definitions',
  ]) {
    assert.ok(JSON_COLUMNS.has(col), `missing ${col}`);
  }

  const prevKey = process.env.ANOSYS_ENCRYPTION_KEY;
  const prevCols = process.env.ANOSYS_ENCRYPTED_COLUMNS;
  process.env.ANOSYS_ENCRYPTION_KEY = 'test-passphrase-123';
  process.env.ANOSYS_ENCRYPTED_COLUMNS = 'user_prompt';
  try {
    const cols = getTargetColumns({ user_prompt: 'hi', cvs199: '{}', otel_events: '[]' });
    assert.ok(cols.has('user_prompt'));
    assert.ok(cols.has('cvs199'));
    assert.ok(cols.has('otel_events'));

    delete process.env.ANOSYS_ENCRYPTED_COLUMNS;
    const enc = encryptPayload({
      gen_ai_input_messages: JSON.stringify([{ role: 'user', content: 'secret' }]),
    });
    const parsed = JSON.parse(enc.gen_ai_input_messages);
    assert.equal(typeof parsed, 'string');
    assert.ok(parsed.startsWith('enc2:'));
  } finally {
    if (prevKey === undefined) delete process.env.ANOSYS_ENCRYPTION_KEY;
    else process.env.ANOSYS_ENCRYPTION_KEY = prevKey;
    if (prevCols === undefined) delete process.env.ANOSYS_ENCRYPTED_COLUMNS;
    else process.env.ANOSYS_ENCRYPTED_COLUMNS = prevCols;
  }
});

test('scrubSecrets redacts GitHub OAuth, GitLab PAT, private keys, and URL basic auth', () => {
  const input = [
    'gho_1234567890abcdefghijklmnopqrstuvwx',
    'glpat-1234567890abcdefghij',
    'https://admin:supersecretpassword@db.internal.example.com/prod',
    '-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA0123456789abcdef\n-----END RSA PRIVATE KEY-----',
  ].join(' ');
  const out = scrubSecrets(input);
  assert.ok(!out.includes('gho_12345'));
  assert.ok(!out.includes('glpat-12345'));
  assert.ok(!out.includes('supersecretpassword'));
  assert.ok(!out.includes('MIIEpAIBAAKCAQEA0123456789abcdef'));
});

test('anosysLogger preserves sync and async generator functions', async () => {
  const syncGen = anosysLogger(function* (n) {
    for (let i = 0; i < n; i++) yield i + 1;
  });
  assert.equal(syncGen.constructor.name, 'GeneratorFunction');
  assert.deepEqual([...syncGen(3)], [1, 2, 3]);

  const asyncGen = anosysLogger(async function* (n) {
    for (let i = 0; i < n; i++) yield i * 10;
  });
  assert.equal(asyncGen.constructor.name, 'AsyncGeneratorFunction');
  const items = [];
  for await (const x of asyncGen(3)) items.push(x);
  assert.deepEqual(items, [0, 10, 20]);
});

test('codex calculateCost matches -mini models before prefix models', () => {
  assert.equal(codexCalculateCost('gpt-4o', 1_000_000, 0), 2.5);
  assert.equal(codexCalculateCost('gpt-4o-mini', 1_000_000, 0), 0.15);
  assert.equal(codexCalculateCost('o1', 1_000_000, 0), 15.0);
  assert.equal(codexCalculateCost('o1-mini', 1_000_000, 0), 1.1);
  assert.equal(codexCalculateCost('o3', 1_000_000, 0), 15.0);
  assert.equal(codexCalculateCost('o3-mini', 1_000_000, 0), 1.1);
});

test('isAnthropicSpan rejects OpenAI spans and extractGenAiSpanInfo extracts tool metadata', () => {
  assert.equal(
    isAnthropicSpan('openinference.instrumentation.openai', {
      'gen_ai.operation.name': 'chat',
      'gen_ai.request.model': 'gpt-4o',
    }),
    false,
  );
  assert.equal(
    isAnthropicSpan('custom', {
      'gen_ai.operation.name': 'chat',
      'gen_ai.system': 'openai',
      'gen_ai.request.model': 'gpt-4o',
    }),
    false,
  );
  assert.equal(
    isAnthropicSpan('custom', {
      'gen_ai.operation.name': 'chat',
      'gen_ai.system': 'anthropic',
      'gen_ai.request.model': 'claude-sonnet-4-6',
    }),
    true,
  );

  const info = extractGenAiSpanInfo(
    {
      name: 'execute_tool bash',
      context: { trace_id: 't1', span_id: 's1' },
      attributes: {
        'gen_ai.operation.name': 'execute_tool',
        'gen_ai.tool.name': 'bash',
        'gen_ai.tool.call.id': 'call_1',
        'gen_ai.tool.type': 'function',
      },
    },
    'AnthropicTelemetry',
  );
  const schema = JSON.parse(info.otel_schema_url);
  assert.equal(info[schema['gen_ai.tool.name']], 'bash');
  assert.equal(info[schema['gen_ai.tool.call.id']], 'call_1');
  assert.equal(info[schema['gen_ai.tool.type']], 'function');
});

test('antigravity serializes error objects and pairs tool durations across SYSTEM steps', () => {
  const records = [
    { step_index: 1, type: 'USER_INPUT', created_at: '2026-09-21T19:57:00Z', content: 'Run check' },
    {
      step_index: 2,
      type: 'PLANNER_RESPONSE',
      created_at: '2026-09-21T19:57:01Z',
      content: 'Checking',
      tool_calls: [{ name: 'run_command', args: { CommandLine: 'pytest' } }],
    },
    { step_index: 3, type: 'SYSTEM', created_at: '2026-09-21T19:57:02Z', content: 'checkpoint' },
    {
      step_index: 4,
      type: 'TOOL_RESULT',
      created_at: '2026-09-21T19:57:05Z',
      status: 'DONE',
      content: 'Created At: 2026-09-21T19:57:01Z\nCompleted At: 2026-09-21T19:57:05Z\n0 errors found',
    },
  ];
  const turn = buildTurn(records);
  assert.equal(turn.tool_steps.length, 1);
  assert.equal(turn.tool_steps[0].duration_ms, 4000);

  const details = extractToolDetails(turn.tool_steps);
  assert.deepEqual(details.tool_errors, []);

  const mapped = transformAntigravityTurn(turn, 's1', 's1_0', {
    error: { code: 500, message: 'boom' },
  });
  assert.deepEqual(JSON.parse(mapped.error_obj), { code: 500, message: 'boom' });
});

test('prepareAppRecord scrubs secrets at full level', () => {
  const { prepareAppRecord } = require('../src/capture.js');
  const record = {
    otel_name: 'chat',
    llm_input: 'my secret is sk-ant-api03-abcdefghijklmnopqrstuvwxyz and bearer token: Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-IDcSemACt8x4iTMCda8Yhe3iZaWbvV5XKSTbuAn0M',
    gen_ai_request_model: 'claude-sonnet-4-6',
  };
  const prepared = prepareAppRecord(record, 'full');
  assert.ok(!prepared.llm_input.includes('sk-ant-api03'));
  assert.ok(prepared.llm_input.includes('[SECRET]'));
  assert.equal(prepared.gen_ai_request_model, 'claude-sonnet-4-6');
});

test('codex and antigravity align thinking in cvb1 and error in cvb2', () => {
  const { transformCodexTurn } = require('../../codex/src/mapper.js');
  const prevCodex = process.env.ANOSYS_CODEX_PIXEL;
  const prevAg = process.env.ANOSYS_ANTIGRAVITY_PIXEL;
  process.env.ANOSYS_CODEX_PIXEL = 'false';
  process.env.ANOSYS_ANTIGRAVITY_PIXEL = 'false';
  try {
    const cTurn = {
      model: 'o3',
      tokens: { reasoning_output_tokens: 150 },
    };
    const cMapped = transformCodexTurn(cTurn, 's1', 't1');
    assert.equal(cMapped.cvb1, true);
    assert.equal(cMapped.cvb2, false);

    const agTurn = {
      has_thinking: true,
      llm_steps: [],
      tool_steps: [],
    };
    const agMapped = transformAntigravityTurn(agTurn, 's1', 't1', {});
    assert.equal(agMapped.cvb1, true);
    assert.equal(agMapped.cvb2, false);
  } finally {
    if (prevCodex === undefined) delete process.env.ANOSYS_CODEX_PIXEL;
    else process.env.ANOSYS_CODEX_PIXEL = prevCodex;
    if (prevAg === undefined) delete process.env.ANOSYS_ANTIGRAVITY_PIXEL;
    else process.env.ANOSYS_ANTIGRAVITY_PIXEL = prevAg;
  }
});
