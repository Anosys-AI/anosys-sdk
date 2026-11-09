import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import {
  PendingQueue, chunkRecords, deliver, fitRecord, isPaused, jsonSize, maxBatchBytes, sendRecords,
} from '../src/transport.js';

function fakePost(...answers) {
  const bodies = [];
  const post = async (url, body) => {
    bodies.push(body);
    const answer = answers.length ? answers.shift() : 200;
    if (answer instanceof Error) throw answer;
    return { status: answer };
  };
  post.bodies = bodies;
  return post;
}
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-transport-'));

describe('size limits', () => {
  it('defaults to 10 MB and can be overridden', () => {
    delete process.env.ANOSYS_MAX_BATCH_BYTES;
    assert.equal(maxBatchBytes(), 10000000);
    process.env.ANOSYS_MAX_BATCH_BYTES = '2000000';
    assert.equal(maxBatchBytes(), 2000000);
    delete process.env.ANOSYS_MAX_BATCH_BYTES;
  });

  it('keeps every chunk under the limit', () => {
    const records = Array.from({ length: 50 }, (_, i) => ({ i, text: 'x'.repeat(900) }));
    const chunks = chunkRecords(records, 10000);
    assert.equal(chunks.flat().length, 50);
    for (const c of chunks) assert.ok(jsonSize(c) <= 10000);
  });

  it('truncates raw first and drops what cannot fit', () => {
    const fitted = fitRecord({ cvs199: 'r'.repeat(50000), user_prompt: 'p'.repeat(3000), session_id: 's' }, 20000);
    assert.ok(jsonSize([fitted]) <= 20000);
    assert.ok(fitted.cvs199.includes('truncated: original 50000 bytes'));
    assert.equal(fitted.user_prompt, 'p'.repeat(3000));
    const huge = Object.fromEntries(Array.from({ length: 5000 }, (_, i) => [`k${i}`, i]));
    assert.equal(fitRecord(huge, 2000), null);
  });
});

describe('failure handling', () => {
  for (const [status, retried] of [[500, true], [503, true], [429, true], [408, true], [400, false], [404, false], [413, false], [422, false]]) {
    it(`status ${status} ${retried ? 'is retried' : 'is dropped'}`, async () => {
      const res = await sendRecords('u', [{ a: 1 }], { post: fakePost(status) });
      assert.equal(res.retryable.length > 0, retried);
      assert.equal(res.pause, null);
    });
  }

  for (const status of [401, 403]) {
    it(`status ${status} pauses collection and queues nothing`, async () => {
      const d = tmp();
      const queue = new PendingQueue(path.join(d, 'q.jsonl'));
      const marker = path.join(d, 'paused.json');
      await deliver('u', [{ turn: 1 }], queue, marker, { post: fakePost(status) });
      assert.ok(isPaused(marker));
      assert.deepEqual(queue.load(), []);
      const post = fakePost();
      assert.equal(await deliver('u', [{ turn: 2 }], queue, marker, { post }), 0);
      assert.deepEqual(post.bodies, []);
    });
  }

  for (const failure of [500, 503, new Error('timeout'), new TypeError('fetch failed')]) {
    it(`queues on ${failure.message || failure} and drains on recovery`, async () => {
      const d = tmp();
      const queue = new PendingQueue(path.join(d, 'q.jsonl'));
      const marker = path.join(d, 'paused.json');
      for (let turn = 0; turn < 3; turn += 1) {
        assert.equal(await deliver('u', [{ turn }], queue, marker, { post: fakePost(failure, failure) }), 0);
      }
      assert.equal(queue.load().length, 3);
      assert.equal(fs.statSync(path.join(d, 'q.jsonl')).mode & 0o777, 0o600);
      assert.equal(await deliver('u', [{ turn: 3 }], queue, marker, { post: fakePost(200, 200) }), 4);
      assert.ok(!fs.existsSync(path.join(d, 'q.jsonl')));
    });
  }

  it('bounds the queue by attempts and ignores pre-v2 lines', async () => {
    const d = tmp();
    const queue = new PendingQueue(path.join(d, 'q.jsonl'), { maxAttempts: 3 });
    for (let turn = 0; turn < 10; turn += 1) {
      await deliver('u', [{ turn }], queue, path.join(d, 'p.json'), { post: fakePost(...Array(20).fill(500)) });
    }
    assert.ok(queue.load().length <= 3);
    fs.writeFileSync(path.join(d, 'old.jsonl'), JSON.stringify({ cvs199: 'bare' }) + '\n');
    assert.deepEqual(new PendingQueue(path.join(d, 'old.jsonl')).load(), []);
  });
});

describe('encrypted values and single-record posts', () => {
  it('replaces an encrypted value whole instead of cutting the ciphertext', async () => {
    const { deriveKeys, encrypt, decrypt } = await import('../src/encryption.js');
    const keys = deriveKeys('pass', 'ws');
    const out = fitRecord({ cvs199: encrypt('x'.repeat(5000), keys), user_prompt: encrypt('keep me', keys) }, 3000);
    assert.ok(out.cvs199.startsWith('[truncated: original'));
    assert.equal(decrypt(out.user_prompt, keys), 'keep me');
  });

  it('postRecord fits the record under the limit before posting', async () => {
    const { postRecord } = await import('../src/transport.js');
    const bodies = [];
    const post = async (url, body) => { bodies.push(body); return { status: 200 }; };
    process.env.ANOSYS_MAX_BATCH_BYTES = '2048';
    try {
      const res = await postRecord('u', { cvs199: 'y'.repeat(5000), a: 1 }, { post });
      assert.equal(res.status, 200);
      assert.ok(bodies[0].cvs199.includes('truncated') && bodies[0].a === 1);
    } finally {
      delete process.env.ANOSYS_MAX_BATCH_BYTES;
    }
  });
});
