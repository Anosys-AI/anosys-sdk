import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import {
  FULL, METADATA, OFF, POLICY_VERSION, BASE_METADATA_FIELDS,
  effectiveLevel, filterFields, readConsent, writeConsent,
} from '../src/privacy.js';
import { scrubSecrets } from '../src/redaction.js';

let dir;
beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-privacy-'));
  process.env.ANOSYS_CONSENT_FILE = path.join(dir, 'consent.json');
  for (const v of ['ANOSYS_DISABLE', 'ANOSYS_COLLECTION_LEVEL', 'REDACTION']) delete process.env[v];
});

describe('effectiveLevel', () => {
  it('defaults to metadata', () => {
    assert.deepEqual(effectiveLevel(null, dir), { level: METADATA, source: 'default' });
  });

  it('needs consent for full', () => {
    process.env.ANOSYS_COLLECTION_LEVEL = 'full';
    assert.deepEqual(effectiveLevel(null, dir), { level: METADATA, source: 'ANOSYS_COLLECTION_LEVEL (no consent)' });
    assert.throws(() => writeConsent(FULL, 'test'));
    writeConsent(FULL, 'test', POLICY_VERSION);
    assert.equal(effectiveLevel(null, dir).level, FULL);
    assert.equal(fs.statSync(process.env.ANOSYS_CONSENT_FILE).mode & 0o777, 0o600);
    assert.equal(readConsent().policy_version, POLICY_VERSION);
  });

  it('applies the same precedence as Python', () => {
    writeConsent(FULL, 'test', POLICY_VERSION);
    process.env.ANOSYS_COLLECTION_LEVEL = 'metadata';
    assert.deepEqual(effectiveLevel(null, dir), { level: FULL, source: 'consent' });
    assert.deepEqual(effectiveLevel('off', dir), { level: OFF, source: 'flag' });
    fs.writeFileSync(path.join(dir, '.anosys'), 'level=metadata\n');
    assert.deepEqual(effectiveLevel(null, dir), { level: METADATA, source: '.anosys' });
    fs.writeFileSync(path.join(dir, '.anosys'), 'level=full\n');
    writeConsent(METADATA, 'test');
    assert.equal(effectiveLevel(null, dir).level, METADATA);
    process.env.ANOSYS_DISABLE = '1';
    assert.deepEqual(effectiveLevel('full', dir), { level: OFF, source: 'ANOSYS_DISABLE' });
  });

  it('treats REDACTION=true as metadata', () => {
    process.env.REDACTION = 'true';
    assert.deepEqual(effectiveLevel(null, dir), { level: METADATA, source: 'REDACTION' });
  });
});

describe('filterFields', () => {
  it('keeps only allowlisted fields at metadata', () => {
    const record = { session_id: 's', input_tokens: 3, user_prompt: 'secret', brand_new_field: 'x' };
    const allowed = new Set(['session_id', 'input_tokens']);
    assert.deepEqual(filterFields(record, OFF, allowed), {});
    assert.deepEqual(filterFields(record, METADATA, allowed), { session_id: 's', input_tokens: 3, consent: 'metadata;none', cvs198: 'metadata;none' });
    const full = filterFields(record, FULL, allowed);
    assert.equal(full.user_prompt, 'secret');
    assert.equal(full.consent, `full;${POLICY_VERSION}`);
    assert.equal(full.cvs198, `full;${POLICY_VERSION}`);
    assert.ok(!('brand_new_field' in filterFields({ brand_new_field: 1 }, METADATA, BASE_METADATA_FIELDS)));
  });
});

describe('scrubSecrets', () => {
  it('replaces secret-shaped strings like Python does', () => {
    const text = 'key sk-ant-api03-abcdefghijklmnopqrstuvwxyz and AKIAABCDEFGHIJKLMNOP and '
      + 'password=hunter2hunter2hunter2 and ghp_abcdefghijklmnopqrstuvwxyz0123456789';
    const out = scrubSecrets(text);
    for (const s of ['sk-ant-api03', 'AKIAABCDEFGHIJKLMNOP', 'hunter2hunter2', 'ghp_abcdef']) assert.ok(!out.includes(s));
    assert.ok(out.includes('password=[SECRET]'));
    assert.deepEqual(scrubSecrets({ a: ['token: abcdefghijklmnop1234'] }), { a: ['token: [SECRET]'] });
  });
});
