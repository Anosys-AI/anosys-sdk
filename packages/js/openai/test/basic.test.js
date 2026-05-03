import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import { reassign, assign, BASE_KEY_MAPPING, DEFAULT_STARTING_INDICES } from '../src/mapping.js';
import { extractSpanInfo } from '../src/hooks.js';
import { anosysLogger } from '../src/decorators.js';

describe('mapping', () => {
  it('assign skips null/undefined', () => {
    const v = {};
    assign(v, 'x', null);
    assign(v, 'y', undefined);
    assert.deepEqual(v, {});
  });

  it('assign preserves numbers', () => {
    const v = {};
    assign(v, 'x', 42);
    assert.equal(v.x, 42);
  });

  it('reassign maps known keys', () => {
    const result = reassign({ source: 'test' }, BASE_KEY_MAPPING, { ...DEFAULT_STARTING_INDICES });
    assert.equal(result.cvs200, 'test');
  });

  it('reassign allocates dynamic CVS slots for unknown keys', () => {
    const result = reassign({ unknown_key: 'hello' }, BASE_KEY_MAPPING, { ...DEFAULT_STARTING_INDICES });
    assert.ok(Object.keys(result).some(k => k.startsWith('cvs1')));
  });
});

describe('hooks.extractSpanInfo', () => {
  it('returns an object with otel_record_type', () => {
    const span = {
      name: 'test-span',
      context: { trace_id: 'abc', span_id: 'def' },
      start_time: new Date().toISOString(),
      end_time: new Date().toISOString(),
      attributes: {},
      status: { status_code: 'OK' },
    };
    const result = extractSpanInfo(span);
    assert.equal(result.otel_record_type, 'AnoSys Trace');
    assert.equal(result.otel_name, 'test-span');
  });
});

describe('decorators.anosysLogger', () => {
  it('returns decorated function that runs the original', async () => {
    const fn = anosysLogger('test')(async (x) => x * 2);
    const result = await fn(5).catch(() => null); // may fail to POST in test — that's OK
    assert.equal(result, 10);
  });

  it('propagates errors from wrapped function', async () => {
    const fn = anosysLogger('test')(async () => { throw new Error('boom'); });
    await assert.rejects(fn(), /boom/);
  });
});
