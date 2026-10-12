import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import {
  span2json,
  reassign,
  assign,
  extractOtelSpanInfo,
  AGENTS_KEY_MAPPING,
  AGENTS_STARTING_INDICES,
  DEFAULT_STARTING_INDICES,
} from '../src/mapping.js';
import { safeSerialize, cleanNulls } from '../src/utils.js';
import { anosysLogger } from '../src/decorators.js';

// ── helpers ──────────────────────────────────────────────────────────────────

function makeSpan(type, extraSpanData = {}) {
  return {
    timestamp: new Date().toISOString(),
    user_context: { session_id: 'sess-1' },
    data: {
      id: `span-${type}`,
      trace_id: 'trace-1',
      object: 'trace.span',
      started_at: new Date().toISOString(),
      ended_at: new Date().toISOString(),
      span_data: { type, ...extraSpanData },
    },
  };
}

// ── mapping.reassign ─────────────────────────────────────────────────────────

describe('mapping.reassign', () => {
  it('maps known keys correctly', () => {
    const result = reassign({ source: 'agents_test' }, AGENTS_KEY_MAPPING, { ...DEFAULT_STARTING_INDICES });
    assert.equal(result.cvs200, 'agents_test');
  });

  it('allocates dynamic CVS slots for unknown string keys', () => {
    const result = reassign({ unknown_field: 'hello' }, AGENTS_KEY_MAPPING, { ...DEFAULT_STARTING_INDICES });
    assert.ok(Object.keys(result).some(k => k.startsWith('cvs')));
  });

  it('allocates dynamic CVN slots for unknown numeric keys', () => {
    const result = reassign({ mystery_count: 42 }, AGENTS_KEY_MAPPING, { ...DEFAULT_STARTING_INDICES });
    assert.ok(Object.keys(result).some(k => k.startsWith('cvn')));
  });

  it('allocates dynamic CVB slots for unknown boolean keys', () => {
    const result = reassign({ mystery_flag: true }, AGENTS_KEY_MAPPING, { ...DEFAULT_STARTING_INDICES });
    assert.ok(Object.keys(result).some(k => k.startsWith('cvb')));
  });

  it('skips null/undefined values', () => {
    const result = reassign({ skip_me: null, keep_me: 'hi' }, AGENTS_KEY_MAPPING, { ...DEFAULT_STARTING_INDICES });
    const values = Object.values(result);
    assert.ok(!values.includes(null));
    assert.ok(!values.includes(undefined));
  });

  it('coerces numeric strings to numbers for cvn slots', () => {
    const result = reassign({ 'gen_ai.usage.input_tokens': '42' }, AGENTS_KEY_MAPPING, { ...DEFAULT_STARTING_INDICES });
    assert.equal(result['gen_ai_usage_input_tokens'], 42);
  });
});

// ── mapping.assign ────────────────────────────────────────────────────────────

describe('mapping.assign', () => {
  it('skips null and undefined values', () => {
    const vars = {};
    assign(vars, 'key', null);
    assign(vars, 'key2', undefined);
    assert.equal(Object.keys(vars).length, 0);
  });

  it('assigns finite numbers', () => {
    const vars = {};
    assign(vars, 'count', 42);
    assert.equal(vars.count, 42);
  });

  it('assigns boolean values', () => {
    const vars = {};
    assign(vars, 'flag', true);
    assert.equal(vars.flag, true);
  });

  it('assigns strings', () => {
    const vars = {};
    assign(vars, 'name', 'hello');
    assert.equal(vars.name, 'hello');
  });

  it('converts numeric strings to numbers', () => {
    const vars = {};
    assign(vars, 'n', '99');
    assert.equal(vars.n, 99);
  });
});

// ── mapping.span2json ─────────────────────────────────────────────────────────

describe('mapping.span2json — common fields', () => {
  it('returns otel_record_type', () => {
    const result = span2json(makeSpan('agent', { name: 'A' }));
    assert.equal(result.otel_record_type, 'AnoSys Agentic Trace');
  });

  it('returns cvs200 source tag', () => {
    const result = span2json(makeSpan('agent', { name: 'A' }));
    assert.equal(result.cvs200, 'openAI_Agents_Traces');
  });

  it('sets otel_span_id from data.id', () => {
    const result = span2json(makeSpan('agent', { name: 'A' }));
    assert.equal(result.otel_span_id, 'span-agent');
  });

  it('sets cvb1 = true', () => {
    const result = span2json(makeSpan('agent', { name: 'A' }));
    assert.equal(result.cvb1, true);
  });

  it('does not include null values', () => {
    const result = span2json(makeSpan('agent', { name: 'A' }));
    for (const v of Object.values(result)) {
      assert.notEqual(v, null);
    }
  });
});

describe('mapping.span2json — all span types', () => {
  const types = ['agent', 'function', 'mcp_tools', 'guardrail', 'generation',
    'custom', 'transcription', 'speech', 'speechgroup',
    'MCPListTools', 'response', 'handoff'];
  for (const type of types) {
    it(`does not throw for type: ${type}`, () => {
      assert.doesNotThrow(() => span2json(makeSpan(type)));
    });
  }

  it('agent: sets otel_name from spanData.name', () => {
    const result = span2json(makeSpan('agent', { name: 'TriageAgent', handoffs: ['sales'], tools: [] }));
    assert.equal(result.otel_name, 'TriageAgent');
    assert.ok(result.cvs62?.includes('sales'));
  });

  it('function: sets llm_input and llm_output', () => {
    const result = span2json(makeSpan('function', { name: 'fn1', input: 'arg', output: 'res' }));
    assert.equal(result.llm_input, 'arg');
    assert.equal(result.llm_output, 'res');
  });

  it('generation: extracts usage tokens', () => {
    const result = span2json(makeSpan('generation', {
      input: 'q', output: 'a', model: 'gpt-4',
      usage: { input_tokens: 10, output_tokens: 5 },
    }));
    assert.equal(result.gen_ai_usage_input_tokens, 10);
    assert.equal(result.gen_ai_usage_output_tokens, 5);
    assert.equal(result.cvs69, 'gpt-4');
  });

  it('handoff: sets from/to agent', () => {
    const result = span2json(makeSpan('handoff', { from_agent: 'AgentA', to_agent: 'AgentB' }));
    assert.equal(result.cvs78, 'AgentA');
    assert.equal(result.cvs79, 'AgentB');
  });

  it('response: extracts response_id to cvs77', () => {
    const result = span2json(makeSpan('response', { response_id: 'resp-xyz' }));
    assert.equal(result.cvs77, 'resp-xyz');
  });

  it('MCPListTools: sets server and result', () => {
    const result = span2json(makeSpan('MCPListTools', { server: 'srv', result: ['t1', 't2'] }));
    assert.equal(result.cvs75, 'srv');
    assert.ok(result.cvs76 != null);
  });

  it('guardrail: sets name and triggered flag', () => {
    const result = span2json(makeSpan('guardrail', { name: 'filter', triggered: true }));
    assert.equal(result.otel_name, 'filter');
    assert.ok(result.cvs68 != null);
  });
});

describe('mapping.span2json — model_config id extraction', () => {
  it('extracts id from model_config dict', () => {
    const result = span2json(makeSpan('generation', { model_config: { id: 'cfg-abc' } }));
    assert.equal(result.cvs77, 'cfg-abc');
  });

  it('extracts id from model_config JSON string', () => {
    const result = span2json(makeSpan('generation', { model_config: JSON.stringify({ id: 'cfg-json' }) }));
    assert.equal(result.cvs77, 'cfg-json');
  });
});

// ── utils.safeSerialize ──────────────────────────────────────────────────────

describe('utils.safeSerialize', () => {
  it('handles plain objects', () => {
    assert.deepEqual(safeSerialize({ a: 1, b: 'two' }), { a: 1, b: 'two' });
  });

  it('handles nested objects', () => {
    assert.deepEqual(safeSerialize({ nested: { x: 42 } }), { nested: { x: 42 } });
  });

  it('returns null for null input', () => {
    assert.equal(safeSerialize(null), null);
  });
});

// ── utils.cleanNulls ─────────────────────────────────────────────────────────

describe('utils.cleanNulls', () => {
  it('removes null values', () => {
    assert.deepEqual(cleanNulls({ a: 1, b: null, c: 'ok' }), { a: 1, c: 'ok' });
  });

  it('returns undefined for all-null object', () => {
    assert.equal(cleanNulls({ a: null }), undefined);
  });

  it('keeps zero and false as valid values', () => {
    const result = cleanNulls({ a: 0, b: false, c: null });
    assert.equal(result?.a, 0);
    assert.equal(result?.b, false);
    assert.equal(result?.c, undefined);
  });
});

// ── decorators.anosysLogger ──────────────────────────────────────────────────

describe('decorators.anosysLogger', () => {
  it('returns wrapped function that executes correctly', async () => {
    const fn = anosysLogger('test')(async (x) => x + 1);
    const result = await fn(4).catch(() => null);
    assert.equal(result, 5);
  });

  it('re-throws errors from wrapped function', async () => {
    const fn = anosysLogger('test')(async () => { throw new Error('fail'); });
    await assert.rejects(fn(), /fail/);
  });

  it('passes multiple arguments correctly', async () => {
    const fn = anosysLogger('test')(async (a, b) => a + b);
    const result = await fn(2, 3).catch(() => null);
    assert.equal(result, 5);
  });
});

// ── mapping constants ─────────────────────────────────────────────────────────

describe('mapping constants', () => {
  it('AGENTS_KEY_MAPPING covers gen_ai fields', () => {
    assert.ok('gen_ai.usage.input_tokens' in AGENTS_KEY_MAPPING);
    assert.ok('gen_ai.request.model' in AGENTS_KEY_MAPPING);
    assert.ok('raw' in AGENTS_KEY_MAPPING);
  });

  it('AGENTS_STARTING_INDICES has required keys', () => {
    assert.ok('string' in AGENTS_STARTING_INDICES);
    assert.ok('number' in AGENTS_STARTING_INDICES);
    assert.ok('bool' in AGENTS_STARTING_INDICES);
  });
});

import {
  derive256BitKey,
  encrypt,
  decrypt,
  encryptPayload,
  getEncryptionKey,
  getTargetColumns,
  ANOSYS_ENCRYPTION_PREFIX,
  DEFAULT_ENCRYPTED_COLUMNS,
} from '../src/encryption.js';

describe('encryption', () => {
  it('matches cross-platform AES-256-CBC test vector exactly', () => {
    const key = derive256BitKey('YOUR_SECRET_KEY_HERE');
    const ciphertext = encrypt('Hello from AnoSys Technologies!', key);
    const prefixed = ANOSYS_ENCRYPTION_PREFIX + ciphertext;

    assert.equal(
      prefixed,
      'enc:J+0Ntn9F5hhtKSBGTFZPce61f8zwRKwrp7bNpwp2Cw4='
    );
    assert.equal(decrypt(prefixed, key), 'Hello from AnoSys Technologies!');
    assert.equal(decrypt(ciphertext, key), 'Hello from AnoSys Technologies!');
  });

  it('noop when ANOSYS_ENCRYPTION_KEY is not set', () => {
    const oldKey = process.env.ANOSYS_ENCRYPTION_KEY;
    delete process.env.ANOSYS_ENCRYPTION_KEY;
    try {
      const payload = { llm_input: 'hello', cvs199: 'raw' };
      const res = encryptPayload(payload);
      assert.deepEqual(res, payload);
    } finally {
      if (oldKey) process.env.ANOSYS_ENCRYPTION_KEY = oldKey;
    }
  });

  it('encrypts default columns when key is set', () => {
    const oldKey = process.env.ANOSYS_ENCRYPTION_KEY;
    process.env.ANOSYS_ENCRYPTION_KEY = 'secret-agents-123';
    try {
      const payload = {
        llm_input: 'Agent instruction',
        llm_output: 'Agent response output',
        otel_name: 'SearchAgent',
        cvs199: '{"span":"details"}',
      };
      const res = encryptPayload(payload);
      assert.ok(res.llm_input.startsWith(ANOSYS_ENCRYPTION_PREFIX));
      assert.ok(res.llm_output.startsWith(ANOSYS_ENCRYPTION_PREFIX));
      assert.ok(res.cvs199.startsWith(ANOSYS_ENCRYPTION_PREFIX));
      assert.equal(res.otel_name, 'SearchAgent');

      const key = derive256BitKey('secret-agents-123');
      assert.equal(decrypt(res.llm_input, key), 'Agent instruction');
      assert.equal(decrypt(res.llm_output, key), 'Agent response output');
      assert.equal(decrypt(res.cvs199, key), '{"span":"details"}');
    } finally {
      if (oldKey) process.env.ANOSYS_ENCRYPTION_KEY = oldKey;
      else delete process.env.ANOSYS_ENCRYPTION_KEY;
    }
  });

  it('supports ANOSYS_ENCRYPTED_COLUMNS and typo alias ANOSYS_ENCRYPTES_COLUMNS override', () => {
    const oldKey = process.env.ANOSYS_ENCRYPTION_KEY;
    const oldCols = process.env.ANOSYS_ENCRYPTES_COLUMNS;
    process.env.ANOSYS_ENCRYPTION_KEY = 'secret-agents-123';
    process.env.ANOSYS_ENCRYPTES_COLUMNS = 'cvs78, cvs79';
    try {
      const payload = {
        llm_input: 'plain input',
        cvs78: 'AgentA',
        cvs79: 'AgentB',
      };
      const res = encryptPayload(payload);
      assert.equal(res.llm_input, 'plain input');
      assert.ok(res.cvs78.startsWith(ANOSYS_ENCRYPTION_PREFIX));
      assert.ok(res.cvs79.startsWith(ANOSYS_ENCRYPTION_PREFIX));
    } finally {
      if (oldKey) process.env.ANOSYS_ENCRYPTION_KEY = oldKey;
      else delete process.env.ANOSYS_ENCRYPTION_KEY;
      if (oldCols) process.env.ANOSYS_ENCRYPTES_COLUMNS = oldCols;
      else delete process.env.ANOSYS_ENCRYPTES_COLUMNS;
    }
  });

  it('warns on non-string column and skips encryption', () => {
    const oldKey = process.env.ANOSYS_ENCRYPTION_KEY;
    process.env.ANOSYS_ENCRYPTION_KEY = 'secret-agents-123';
    let warned = false;
    const originalWarn = console.warn;
    console.warn = (...args) => {
      warned = true;
      originalWarn(...args);
    };
    try {
      const payload = {
        llm_input: 99999,
        cvs199: [1, 2, 3],
      };
      const res = encryptPayload(payload);
      assert.equal(res.llm_input, 99999);
      assert.deepEqual(res.cvs199, [1, 2, 3]);
      assert.ok(warned);
    } finally {
      console.warn = originalWarn;
      if (oldKey) process.env.ANOSYS_ENCRYPTION_KEY = oldKey;
      else delete process.env.ANOSYS_ENCRYPTION_KEY;
    }
  });

  it('is idempotent and does not re-encrypt already encrypted fields', () => {
    const oldKey = process.env.ANOSYS_ENCRYPTION_KEY;
    process.env.ANOSYS_ENCRYPTION_KEY = 'secret-agents-123';
    try {
      const payload = {
        llm_input: 'Agent plan',
      };
      const res1 = encryptPayload(payload);
      const firstCipher = res1.llm_input;
      const res2 = encryptPayload(res1);
      assert.equal(res2.llm_input, firstCipher);
    } finally {
      if (oldKey) process.env.ANOSYS_ENCRYPTION_KEY = oldKey;
      else delete process.env.ANOSYS_ENCRYPTION_KEY;
    }
  });
});

