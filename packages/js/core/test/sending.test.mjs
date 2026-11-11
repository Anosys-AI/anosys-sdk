import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import { resolveApiKey } from '../src/config.js';
import { sendAppRecord, flushAppRecords, setSenderPostForTests, MAX_IN_FLIGHT } from '../src/sender.js';
import { postRecord } from '../src/transport.js';

describe('application sending', () => {
  it('a missing key disables sending instead of posting to a default site', async () => {
    delete process.env.ANOSYS_API_KEY;
    delete process.env.ANOSYS_API_URL;
    process.env.ANOSYS_LOG_LEVEL = 'silent';
    assert.equal(await resolveApiKey(), null);
    assert.equal(await postRecord(null, { a: 1 }, { post: () => assert.fail('posted') }), null);
    assert.equal(sendAppRecord(null, { a: 1 }), false);
  });

  it('an explicit endpoint is used without a key', async () => {
    process.env.ANOSYS_API_URL = 'https://self-hosted.example/ingest';
    assert.equal(await resolveApiKey(), 'https://self-hosted.example/ingest');
    delete process.env.ANOSYS_API_URL;
  });

  it('does not block the caller and stays bounded', async () => {
    const posted = [];
    let release;
    const gate = new Promise((r) => { release = r; });
    setSenderPostForTests(async (url, body) => { await gate; posted.push(body); return { status: 200 }; });
    const start = Date.now();
    const results = Array.from({ length: MAX_IN_FLIGHT + 10 }, (_, i) => sendAppRecord('https://ingest', { i }));
    assert.ok(Date.now() - start < 100);
    assert.equal(results.filter((r) => r === false).length, 10);
    release();
    assert.ok(await flushAppRecords(2000));
    assert.equal(posted.length, MAX_IN_FLIGHT);
  });

  it('never surfaces failures or payloads', async () => {
    const errors = [];
    const orig = console.error;
    console.error = (...a) => errors.push(a.join(' '));
    process.env.ANOSYS_LOG_LEVEL = 'error';
    setSenderPostForTests(async () => { throw new Error('prompt text inside'); });
    assert.ok(sendAppRecord('https://ingest', { a: 1 }));
    await flushAppRecords(1000);
    console.error = orig;
    process.env.ANOSYS_LOG_LEVEL = 'silent';
    assert.ok(errors.length >= 1 && !errors.join(' ').includes('prompt text'));
    setSenderPostForTests(null);
  });
});
