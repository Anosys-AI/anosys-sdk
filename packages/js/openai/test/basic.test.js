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
    process.env.ANOSYS_ENCRYPTION_KEY = 'secret-123';
    try {
      const payload = {
        llm_input: 'Tell me a joke',
        llm_output: 'Why did the chicken cross the road?',
        session_id: 'sess-abc',
        cvs199: '{"span":"data"}',
      };
      const res = encryptPayload(payload);
      assert.ok(res.llm_input.startsWith(ANOSYS_ENCRYPTION_PREFIX));
      assert.ok(res.llm_output.startsWith(ANOSYS_ENCRYPTION_PREFIX));
      assert.ok(res.cvs199.startsWith(ANOSYS_ENCRYPTION_PREFIX));
      assert.equal(res.session_id, 'sess-abc');

      const key = derive256BitKey('secret-123');
      assert.equal(decrypt(res.llm_input, key), 'Tell me a joke');
      assert.equal(decrypt(res.llm_output, key), 'Why did the chicken cross the road?');
      assert.equal(decrypt(res.cvs199, key), '{"span":"data"}');
    } finally {
      if (oldKey) process.env.ANOSYS_ENCRYPTION_KEY = oldKey;
      else delete process.env.ANOSYS_ENCRYPTION_KEY;
    }
  });

  it('supports ANOSYS_ENCRYPTED_COLUMNS and typo alias ANOSYS_ENCRYPTES_COLUMNS override', () => {
    const oldKey = process.env.ANOSYS_ENCRYPTION_KEY;
    const oldCols = process.env.ANOSYS_ENCRYPTES_COLUMNS;
    process.env.ANOSYS_ENCRYPTION_KEY = 'secret-123';
    process.env.ANOSYS_ENCRYPTES_COLUMNS = 'custom_field, other_field';
    try {
      const payload = {
        llm_input: 'not encrypted now',
        custom_field: 'secret data',
        other_field: 'more secret data',
      };
      const res = encryptPayload(payload);
      assert.equal(res.llm_input, 'not encrypted now');
      assert.ok(res.custom_field.startsWith(ANOSYS_ENCRYPTION_PREFIX));
      assert.ok(res.other_field.startsWith(ANOSYS_ENCRYPTION_PREFIX));
    } finally {
      if (oldKey) process.env.ANOSYS_ENCRYPTION_KEY = oldKey;
      else delete process.env.ANOSYS_ENCRYPTION_KEY;
      if (oldCols) process.env.ANOSYS_ENCRYPTES_COLUMNS = oldCols;
      else delete process.env.ANOSYS_ENCRYPTES_COLUMNS;
    }
  });

  it('warns on non-string column and skips encryption', () => {
    const oldKey = process.env.ANOSYS_ENCRYPTION_KEY;
    process.env.ANOSYS_ENCRYPTION_KEY = 'secret-123';
    let warned = false;
    const originalWarn = console.warn;
    console.warn = (...args) => {
      warned = true;
      originalWarn(...args);
    };
    try {
      const payload = {
        llm_input: 12345,
        cvs199: { complex: 'object' },
      };
      const res = encryptPayload(payload);
      assert.equal(res.llm_input, 12345);
      assert.deepEqual(res.cvs199, { complex: 'object' });
      assert.ok(warned);
    } finally {
      console.warn = originalWarn;
      if (oldKey) process.env.ANOSYS_ENCRYPTION_KEY = oldKey;
      else delete process.env.ANOSYS_ENCRYPTION_KEY;
    }
  });

  it('is idempotent and does not re-encrypt already encrypted fields', () => {
    const oldKey = process.env.ANOSYS_ENCRYPTION_KEY;
    process.env.ANOSYS_ENCRYPTION_KEY = 'secret-123';
    try {
      const payload = {
        llm_input: 'Hello',
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

