import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';

import {
  ANOSYS_ENCRYPTION_PREFIX, DEFAULT_ENCRYPTED_COLUMNS, JSON_COLUMNS,
  deriveKeys, encrypt, decrypt, encryptPayload, getEncryptionKey, getTargetColumns,
} from '../src/encryption.js';

// Shared with Python tests and the console: all three must agree.
const PASSPHRASE = 'YOUR_SECRET_KEY_HERE';
const SALT = 'workspace-123';
const SAMPLE_TEXT = 'Hello from AnoSys Technologies!';
const SAMPLE_CIPHERTEXT = 'enc2:QwYbSu12pZL4oSf17Bb5zJUkGjoRc3wL66HwlsbjlJ5sLJWIHWGlgz7f+PXh4yem/EvB20sQjSg+R4A=';
const keys = deriveKeys(PASSPHRASE, SALT);

describe('enc2 format', () => {
  it('matches the shared key and ciphertext vectors', () => {
    assert.equal(keys.kEnc.toString('hex'), '965524765751a794f7875a9204f50c7b2970260ecf1f280fed1f317f3ea19493');
    assert.equal(keys.kNonce.toString('hex'), 'b758d25c8ede925a56cd6af9c51967d453ae5152f9fab13c1fa9619ee1bfe55b');
    assert.equal(encrypt(SAMPLE_TEXT, keys), SAMPLE_CIPHERTEXT);
    assert.equal(decrypt(SAMPLE_CIPHERTEXT, keys), SAMPLE_TEXT);
  });

  it('is deterministic, so grouping and joins work', () => {
    assert.equal(encrypt('same prompt', keys), encrypt('same prompt', keys));
    assert.notEqual(encrypt('same prompt', keys), encrypt('other prompt', keys));
  });

  it('round-trips unicode and empty strings', () => {
    for (const text of ['', 'ünïcödé ✓ 日本語', 'x'.repeat(10000)]) assert.equal(decrypt(encrypt(text, keys), keys), text);
  });

  it('detects tampering', () => {
    const tampered = SAMPLE_CIPHERTEXT.slice(0, -6) + 'AAAA==';
    assert.throws(() => decrypt(tampered, keys));
  });
});

describe('encryptPayload', () => {
  beforeEach(() => {
    process.env.ANOSYS_ENCRYPTION_KEY = PASSPHRASE;
    process.env.ANOSYS_ENCRYPTION_SALT = SALT;
    delete process.env.ANOSYS_ENCRYPTED_COLUMNS;
  });

  it('is off without a key', () => {
    delete process.env.ANOSYS_ENCRYPTION_KEY;
    assert.equal(getEncryptionKey(), null);
    assert.deepEqual(encryptPayload({ user_prompt: 'hi' }), { user_prompt: 'hi' });
  });

  it('encrypts strings, objects and JSON columns', () => {
    const out = encryptPayload({
      user_prompt: SAMPLE_TEXT,
      tool_use_result: '{"stdout":"secret output"}',
      commands: ['rm -rf build'],
      input_tokens: 12,
    });
    assert.equal(out.user_prompt, SAMPLE_CIPHERTEXT);
    assert.ok(JSON_COLUMNS.has('tool_use_result'));
    assert.ok(out.tool_use_result.startsWith(`"${ANOSYS_ENCRYPTION_PREFIX}`));
    assert.equal(decrypt(out.tool_use_result, keys), '{"stdout":"secret output"}');
    assert.equal(decrypt(out.commands, keys), '["rm -rf build"]');
    assert.equal(out.input_tokens, 12);
  });

  it('is idempotent and covers all content columns by default', () => {
    const once = encryptPayload({ user_prompt: SAMPLE_TEXT, commands: '[1]' });
    assert.deepEqual(encryptPayload({ ...once }), once);
    for (const c of ['cvs18', 'commands', 'ai_title', 'agent_description', 'error_details', 'cvs199']) {
      assert.ok(DEFAULT_ENCRYPTED_COLUMNS.includes(c));
    }
    process.env.ANOSYS_ENCRYPTED_COLUMNS = 'a, b';
    assert.deepEqual([...getTargetColumns()], ['a', 'b']);
  });
});
