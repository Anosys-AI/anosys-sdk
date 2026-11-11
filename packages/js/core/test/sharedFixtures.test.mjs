// Golden cases shared with the Python core tests (packages/fixtures). The same JSON
// drives both suites, so Python and JS cannot drift on levels, filtering, labels or mapping.
import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { resolveAppLevel, finalizeAppRecord, appConsentValue } from '../src/capture.js';
import { effectiveLevel, filterFields, consentValue, BASE_METADATA_FIELDS, POLICY_VERSION } from '../src/privacy.js';
import * as mapping from '../src/mapping.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = path.resolve(here, '../../../fixtures');
const CASES = JSON.parse(fs.readFileSync(path.join(FIXTURES, 'privacy_cases.json')));
const MAPPINGS = JSON.parse(fs.readFileSync(path.join(FIXTURES, 'mappings.json')));
const ENV_VARS = ['ANOSYS_DISABLE', 'ANOSYS_COLLECTION_LEVEL', 'REDACTION'];

let dir;
function setup(c) {
  for (const k of ENV_VARS) delete process.env[k];
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-fixture-'));
  process.env.ANOSYS_CONSENT_FILE = path.join(dir, 'consent.json');
  Object.assign(process.env, c.env || {});
  if (c.project) fs.writeFileSync(path.join(dir, '.anosys'), `level=${c.project}\n`);
  if (c.consent) {
    const version = c.consent === 'current' ? POLICY_VERSION : '2000-01-01';
    fs.writeFileSync(process.env.ANOSYS_CONSENT_FILE, JSON.stringify({ level: 'full', policy_version: version }));
  }
}

describe('shared fixtures', () => {
  beforeEach(() => { for (const k of ENV_VARS) delete process.env[k]; });

  for (const [i, c] of CASES.app_level.entries()) {
    it(`app level #${i}`, () => {
      setup(c);
      const { level, source } = resolveAppLevel(c.explicit, dir);
      assert.deepEqual([level, source], c.expected);
    });
  }

  for (const [i, c] of CASES.hook_level.entries()) {
    it(`hook level #${i}`, () => {
      setup(c);
      const { level, source } = effectiveLevel(c.explicit, dir);
      assert.deepEqual([level, source], c.expected);
    });
  }

  for (const [i, c] of CASES.app_finalize.entries()) {
    it(`app finalize #${i}`, () => assert.deepEqual(finalizeAppRecord(c.record, c.level, c.extra), c.expected));
  }

  for (const [i, c] of CASES.hook_filter.entries()) {
    it(`hook filter #${i}`, () => assert.deepEqual(filterFields(c.record, c.level, BASE_METADATA_FIELDS), c.expected));
  }

  it('consent values', () => {
    const v = CASES.consent_values;
    assert.equal(consentValue('full'), v.full);
    assert.equal(consentValue('metadata'), v.metadata);
    assert.equal(consentValue('off'), v.off);
    assert.equal(appConsentValue('full'), v.app_full);
    assert.equal(appConsentValue('metadata'), v.app_metadata);
  });

  for (const [i, c] of CASES.assign.entries()) {
    it(`assign #${i}`, () => {
      const out = {};
      mapping.assign(out, 'k', c.value);
      assert.deepEqual(c.json ? JSON.parse(out.k) : out.k, c.expected);
    });
  }

  it('JS tables equal the shared fixture (generated from Python)', () => {
    for (const name of Object.keys(MAPPINGS)) assert.deepEqual({ ...mapping[name] }, MAPPINGS[name], name);
  });
});
