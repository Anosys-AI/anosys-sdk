import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { reassign, BASE_KEY_MAPPING } from '../src/mapping.js';

describe('reassign dynamic columns', () => {
  it('never puts two attributes in one column and skips fixed ones', () => {
    // server.port is fixed to cvn3, which is also the dynamic number start
    const out = reassign({ retries: 4, 'server.port': 443, attr_a: 'x', attr_b: 'y' }, BASE_KEY_MAPPING);
    assert.equal(out.cvn3, 443);
    const cols = Object.keys(out);
    assert.equal(new Set(cols).size, cols.length);
    assert.equal(Object.values(out).filter((v) => v === 4).length, 1);
  });

  it('protects reserved columns and drops attributes once columns run out', () => {
    const data = Object.fromEntries(Array.from({ length: 250 }, (_, i) => [`k${i}`, `v${i}`]));
    const out = reassign(data, {}, { string: 100, number: 1, bool: 1 });
    for (const reserved of ['cvs198', 'cvs199', 'cvs200']) assert.equal(out[reserved], undefined);
    assert.equal(Object.keys(out).length, 98); // cvs100..cvs197
  });
});
