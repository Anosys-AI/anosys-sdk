import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { finalizeAppRecord, prepareAppRecord, resolveAppLevel, appConsentValue } from '../src/capture.js';

const SPAN = {
  otel_trace_id: 't1', otel_name: 'chat', gen_ai_request_model: 'gpt-5',
  gen_ai_usage_input_tokens: 12, cvb2: false,
  llm_input: 'my secret prompt', llm_output: 'answer',
  gen_ai_input_messages: [{ role: 'user', content: 'hi' }],
  cvs199: '{raw}', cvs105: 'dynamic text', cvs200: 'openAI_Traces', consent: 'stale',
};

describe('unified capture control', () => {
  let dir;
  beforeEach(() => {
    for (const v of ['ANOSYS_DISABLE', 'ANOSYS_COLLECTION_LEVEL', 'ANOSYS_ENCRYPTION_KEY']) delete process.env[v];
    dir = fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-capture-'));
  });

  it('defaults to full and follows the precedence', () => {
    assert.deepEqual(resolveAppLevel(null, dir), { level: 'full', source: 'default' });
    process.env.ANOSYS_COLLECTION_LEVEL = 'metadata';
    assert.deepEqual(resolveAppLevel(null, dir), { level: 'metadata', source: 'ANOSYS_COLLECTION_LEVEL' });
    assert.deepEqual(resolveAppLevel(true, dir), { level: 'full', source: 'argument' });
    fs.writeFileSync(path.join(dir, '.anosys'), 'level=metadata\n');
    assert.deepEqual(resolveAppLevel(true, dir), { level: 'metadata', source: '.anosys' });
    process.env.ANOSYS_DISABLE = '1';
    assert.equal(resolveAppLevel(true, dir).level, 'off');
  });

  it('metadata keeps numbers, flags and allow-listed strings only', () => {
    assert.deepEqual(finalizeAppRecord(SPAN, 'metadata'), {
      otel_trace_id: 't1', otel_name: 'chat', gen_ai_request_model: 'gpt-5',
      gen_ai_usage_input_tokens: 12, cvb2: false, cvs200: 'openAI_Traces', cvs198: 'metadata;app',
    });
    assert.deepEqual(finalizeAppRecord({ cvs78: 'triage', llm_input: 'x' }, 'metadata', ['cvs78']),
      { cvs78: 'triage', cvs198: 'metadata;app' });
  });

  it('full keeps content, off sends nothing, labels never claim policy acceptance', () => {
    const full = finalizeAppRecord(SPAN, 'full');
    assert.equal(full.llm_input, 'my secret prompt');
    assert.equal(full.cvs198, 'full;app');
    assert.equal(full.consent, undefined);
    assert.equal(finalizeAppRecord(SPAN, 'off'), null);
    assert.equal(prepareAppRecord(SPAN, 'off'), null);
    assert.ok(appConsentValue('full').endsWith(';app'));
  });

  it('encrypts after filtering', () => {
    process.env.ANOSYS_ENCRYPTION_KEY = 'pass';
    process.env.ANOSYS_ENCRYPTION_SALT = 'ws';
    const out = prepareAppRecord(SPAN, 'full');
    assert.ok(out.llm_input.startsWith('enc2:'));
    assert.equal(out.cvs198, 'full;app');
    delete process.env.ANOSYS_ENCRYPTION_SALT;
  });
});
