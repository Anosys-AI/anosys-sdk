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
