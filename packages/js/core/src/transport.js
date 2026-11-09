'use strict';

/**
 * Size-limited delivery to AnoSys ingestion — JS port of Python
 * `anosys_sdk_core/transport.py`. Ingestion drops request bodies above 10 MB,
 * so bodies stay under ANOSYS_MAX_BATCH_BYTES (measured after encryption),
 * oversized records are truncated raw-first or dropped, permanent errors are
 * dropped, transient ones go to a bounded 0600 queue, and 401/403 pause
 * collection.
 */

const fs = require('node:fs');

const { writePrivateFile } = require('./privacy.js');

const DEFAULT_MAX_BATCH_BYTES = 10000000;
const TARGET_RATIO = 0.95;
const PERMANENT_STATUS = new Set([400, 401, 403, 404, 413, 422]);
const PAUSE_STATUS = new Set([401, 403]);
const TRUNCATE_FIRST = ['cvs199', 'raw', 'tool_use_result', 'cvs26', 'file_states'];

const log = {
  warn: (...a) => { if ((process.env.ANOSYS_LOG_LEVEL || 'warn') !== 'silent') console.warn('[anosys]', ...a); },
};

/** Request-body limit from ANOSYS_MAX_BATCH_BYTES (default 10,000,000). */
function maxBatchBytes() {
  const v = parseInt(process.env.ANOSYS_MAX_BATCH_BYTES ?? DEFAULT_MAX_BATCH_BYTES, 10);
  return Number.isFinite(v) && v > 1024 ? v : DEFAULT_MAX_BATCH_BYTES;
}

const target = (limit) => Math.floor((limit || maxBatchBytes()) * TARGET_RATIO);

function jsonSize(value) {
  return Buffer.byteLength(JSON.stringify(value), 'utf8');
}

/** The record if it fits, a copy with its largest strings truncated, or null (logged). */
function fitRecord(record, limit = null) {
  const t = target(limit);
  if (jsonSize([record]) <= t) return record;
  const result = { ...record };
  const order = TRUNCATE_FIRST.filter(k => typeof result[k] === 'string');
  order.push(...Object.keys(result)
    .filter(k => typeof result[k] === 'string' && !order.includes(k))
    .sort((a, b) => result[b].length - result[a].length));
  for (const key of order) {
    const excess = jsonSize([result]) - t;
    if (excess <= 0) break;
    const value = result[key];
    const mark = `...[truncated: original ${Buffer.byteLength(value, 'utf8')} bytes]`;
    if (value.startsWith('enc2:') || value.startsWith('"enc2:')) {
      // a cut ciphertext cannot be decrypted: replace the whole value
      result[key] = mark.replace(/^\.+/, '');
      continue;
    }
    const keep = Math.max(0, value.length - excess - mark.length - 64);
    result[key] = value.slice(0, keep) + mark;
  }
  if (jsonSize([result]) <= t) {
    log.warn(`Record over the ${t}-byte limit was truncated`);
    return result;
  }
  log.warn(`Dropped a record that does not fit in ${t} bytes even after truncation`);
  return null;
}

/**
 * POST one already-encrypted record, fitted under the size limit. Resolves to
 * the response, or null when the record had to be dropped. Used by the
 * application SDKs, which send one span or call per request.
 */
async function postRecord(url, record, { timeout = 5, headers = {}, post = defaultPost } = {}) {
  if (!url) return null; // no ingestion endpoint (missing or unresolvable API key)
  const fitted = fitRecord(record);
  if (fitted === null) return null;
  return post(url, fitted, headers, timeout);
}

/** Split records into request bodies under the byte limit. */
function chunkRecords(records, limit = null) {
  const t = target(limit);
  const chunks = [];
  let current = [];
  let size = 2;
  for (const record of records) {
    const fitted = fitRecord(record, limit);
    if (!fitted) continue;
    const s = jsonSize(fitted) + 1;
    if (current.length && size + s > t) {
      chunks.push(current);
      current = [];
      size = 2;
    }
    current.push(fitted);
    size += s;
  }
  if (current.length) chunks.push(current);
  return chunks;
}

const isPermanent = (status) => PERMANENT_STATUS.has(status);

async function defaultPost(url, body, headers, timeout) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(timeout * 1000),
  });
  return { status: res.status };
}

/**
 * POST records in size-limited batches.
 * Resolves to { sent, retryable, pause } — pause is 401/403 when collection should stop.
 */
async function sendRecords(url, records, { headers = {}, timeout = 15, limit = null, post = defaultPost, deadline = null } = {}) {
  // `deadline` (a Date.now() value) bounds the total time; after a timeout or connection
  // error the remaining chunks are not attempted (they would wait out the same timeout).
  let sent = 0;
  const retryable = [];
  let pause = null;
  let unreachable = false;
  for (const chunk of chunkRecords(records, limit)) {
    if (pause !== null) break;
    const remaining = deadline === null ? null : (deadline - Date.now()) / 1000;
    if (unreachable || (remaining !== null && remaining < 0.5)) { retryable.push(...chunk); continue; }
    let status;
    try {
      ({ status } = await post(url, chunk, headers, remaining === null ? timeout : Math.min(timeout, remaining)));
    } catch (e) {
      log.warn(`Ingestion unreachable (${e.name || 'Error'}); ${chunk.length} record(s) kept for retry`);
      retryable.push(...chunk);
      unreachable = true;
      continue;
    }
    if (status < 300) {
      sent += chunk.length;
    } else if (isPermanent(status)) {
      log.warn(`Ingestion rejected ${chunk.length} record(s) with ${status}; dropped`);
      if (PAUSE_STATUS.has(status)) pause = status;
    } else {
      log.warn(`Ingestion returned ${status}; ${chunk.length} record(s) kept for retry`);
      retryable.push(...chunk);
    }
  }
  return { sent, retryable, pause };
}

/** Stop building payloads for `seconds` after a 401/403. */
function pauseCollection(marker, status, seconds = 6 * 3600) {
  try {
    writePrivateFile(marker, JSON.stringify({ until: Date.now() / 1000 + seconds, status }));
  } catch { /* best effort */ }
}

function isPaused(marker) {
  try {
    const data = JSON.parse(fs.readFileSync(marker, 'utf8'));
    if (Date.now() / 1000 < Number(data.until || 0)) return true;
    fs.unlinkSync(marker);
  } catch { /* no marker */ }
  return false;
}

/** Records waiting for a retry, bounded by total size, age and attempts (0600 JSONL). */
class PendingQueue {
  constructor(file, { maxBytes = 50000000, maxAgeSeconds = 24 * 3600, maxAttempts = 5 } = {}) {
    this.path = file;
    this.maxBytes = maxBytes;
    this.maxAgeSeconds = maxAgeSeconds;
    this.maxAttempts = maxAttempts;
  }

  load() {
    if (!fs.existsSync(this.path)) return [];
    const now = Date.now() / 1000;
    const entries = [];
    for (const line of fs.readFileSync(this.path, 'utf8').split('\n')) {
      if (!line.trim()) continue;
      let entry;
      try { entry = JSON.parse(line); } catch { continue; }
      if (!entry || !('record' in entry)) continue; // pre-v2 bare record
      if (now - Number(entry.first_failed ?? now) > this.maxAgeSeconds) continue;
      if (Number(entry.attempts ?? 0) >= this.maxAttempts) continue;
      entries.push(entry);
    }
    return entries;
  }

  save(entries) {
    const lines = [];
    let total = 0;
    for (const entry of [...entries].reverse()) {
      const line = JSON.stringify(entry);
      if (total + line.length + 1 > this.maxBytes) break;
      lines.push(line);
      total += line.length + 1;
    }
    lines.reverse();
    if (!lines.length) { this.clear(); return; }
    try {
      writePrivateFile(this.path, lines.join('\n') + '\n');
    } catch (e) {
      log.warn(`Could not save pending queue: ${e.message}`);
    }
  }

  clear() {
    try { if (fs.existsSync(this.path)) fs.unlinkSync(this.path); } catch { /* ignore */ }
  }

  static entriesFor(records, previous = null) {
    const now = Date.now() / 1000;
    return records.map(record => ({
      record,
      first_failed: previous?.first_failed ?? now,
      attempts: Number(previous?.attempts ?? 0) + 1,
    }));
  }
}

/** Seconds a hook may spend sending (ANOSYS_HOOK_TIME_BUDGET, default 20). */
function hookTimeBudget() {
  const v = Number(process.env.ANOSYS_HOOK_TIME_BUDGET ?? 20);
  return Number.isFinite(v) && v > 0 ? v : 20;
}

const LOCK_STALE_MS = 120000;

/** Exclusive lock file next to the queue (stale locks are broken); false when not acquired. */
async function acquireQueueLock(queuePath, waitMs = 2000) {
  const lock = `${queuePath}.lock`;
  const until = Date.now() + waitMs;
  for (;;) {
    try {
      fs.mkdirSync(require('node:path').dirname(lock), { recursive: true });
      fs.writeFileSync(lock, String(process.pid), { flag: 'wx', mode: 0o600 });
      return () => { try { fs.unlinkSync(lock); } catch { /* ignore */ } };
    } catch (e) {
      if (e.code !== 'EEXIST') return null; // read-only or full disk: run without the queue
      try {
        if (Date.now() - fs.statSync(lock).mtimeMs > LOCK_STALE_MS) { fs.unlinkSync(lock); continue; }
      } catch { /* raced with the owner */ }
      if (Date.now() >= until) return null;
      await new Promise((r) => setTimeout(r, 50));
    }
  }
}

/**
 * Send queued retries plus `records`; requeue only what is retryable. The whole call
 * takes at most `options.budget` seconds (ANOSYS_HOOK_TIME_BUDGET, default 20); what is
 * not sent in time stays queued. Concurrent hook runs are serialised on a lock file; a
 * run that cannot get it sends only its new records. Resolves to the count accepted.
 */
async function deliver(url, records, queue, pauseMarker, options = {}) {
  if (isPaused(pauseMarker)) return 0;
  const { budget = hookTimeBudget(), ...rest } = options;
  const opts = { ...rest, deadline: Date.now() + budget * 1000 };
  const release = await acquireQueueLock(queue.path);
  if (!release) {
    const res = await sendRecords(url, records, opts);
    if (res.pause) pauseCollection(pauseMarker, res.pause);
    if (res.retryable.length) log.warn(`Queue busy (another hook run); ${res.retryable.length} record(s) not kept for retry`);
    return res.sent;
  }
  try {
    return await deliverLocked(url, records, queue, pauseMarker, opts);
  } finally {
    release();
  }
}

async function deliverLocked(url, records, queue, pauseMarker, options) {
  const pending = queue.load();
  let sent = 0;
  const stillPending = [];
  if (pending.length) {
    const byRecord = new Map(pending.map(e => [e.record, e]));
    const res = await sendRecords(url, pending.map(e => e.record), options);
    sent += res.sent;
    if (res.pause) { pauseCollection(pauseMarker, res.pause); queue.clear(); return sent; }
    for (const r of res.retryable) stillPending.push(...PendingQueue.entriesFor([r], byRecord.get(r)));
  }
  if (records.length) {
    const res = await sendRecords(url, records, options);
    sent += res.sent;
    if (res.pause) { pauseCollection(pauseMarker, res.pause); queue.clear(); return sent; }
    stillPending.push(...PendingQueue.entriesFor(res.retryable));
  }
  if (stillPending.length) queue.save(stillPending); else queue.clear();
  return sent;
}

module.exports = {
  postRecord,
  hookTimeBudget,
  DEFAULT_MAX_BATCH_BYTES,
  PERMANENT_STATUS,
  isPermanent,
  maxBatchBytes,
  jsonSize,
  fitRecord,
  chunkRecords,
  pauseCollection,
  isPaused,
  sendRecords,
  deliver,
  PendingQueue,
};
