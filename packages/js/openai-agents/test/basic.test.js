import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import { span2json, reassign, assign, AGENTS_KEY_MAPPING, DEFAULT_STARTING_INDICES } from '../src/mapping.js';
import { safeSerialize, cleanNulls } from '../src/utils.js';
import { anosysLogger } from '../src/decorators.js';

describe('mapping.reassign', () => {
  it('maps known keys correctly', () => {
    const result = reassign({ source: 'agents_test' }, AGENTS_KEY_MAPPING, { ...DEFAULT_STARTING_INDICES });
    assert.equal(result.cvs200, 'agents_test');
  });

  it('allocates dynamic CVS slots for unknown keys', () => {
    const result = reassign({ unknown_field: 'hello' }, AGENTS_KEY_MAPPING, { ...DEFAULT_STARTING_INDICES });
    assert.ok(Object.keys(result).some(k => k.startsWith('cvs')));
  });
});

describe('mapping.span2json', () => {
  it('returns otel_record_type for a minimal span', () => {
    const span = {
      timestamp: new Date().toISOString(),
      data: {
        id: 'span-1',
        trace_id: 'trace-1',
        object: 'trace.span',
        span_data: { type: 'agent', name: 'triage_agent', handoffs: [], tools: [] },
      },
    };
    const result = span2json(span);
    assert.equal(result.otel_record_type, 'AnoSys Agentic Trace');
    assert.equal(result.otel_name, 'triage_agent');
    assert.equal(result.cvs200, 'openAI_Agents_Traces');
  });

  it('handles all agent span types without throwing', () => {
    const types = ['agent', 'function', 'mcp_tools', 'guardrail', 'generation',
                   'custom', 'transcription', 'speech', 'speechgroup',
                   'MCPListTools', 'response', 'handoff'];
    for (const type of types) {
      const span = { timestamp: new Date().toISOString(), data: { id: 'x', span_data: { type } } };
      assert.doesNotThrow(() => span2json(span), `span2json threw for type: ${type}`);
    }
  });
});

describe('utils.safeSerialize', () => {
  it('handles plain objects', () => {
    const result = safeSerialize({ a: 1, b: 'two' });
    assert.deepEqual(result, { a: 1, b: 'two' });
  });

  it('handles nested objects', () => {
    const result = safeSerialize({ nested: { x: 42 } });
    assert.deepEqual(result, { nested: { x: 42 } });
  });
});

describe('utils.cleanNulls', () => {
  it('removes null values', () => {
    const result = cleanNulls({ a: 1, b: null, c: 'ok' });
    assert.deepEqual(result, { a: 1, c: 'ok' });
  });

  it('returns undefined for all-null object', () => {
    assert.equal(cleanNulls({ a: null }), undefined);
  });
});

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
});
