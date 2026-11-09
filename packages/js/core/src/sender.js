'use strict';

/**
 * Background sending for the JS application SDKs — the JS side of Python
 * `transport.BackgroundSender`. Instrumented code never awaits AnoSys: records are
 * posted without blocking the caller, at most MAX_IN_FLIGHT at a time; beyond
 * that a record is dropped (warned once) so memory stays bounded when ingestion is
 * slow or down. Nothing is written to disk or retried. Errors are logged by type
 * only, never with the payload.
 */

const { postRecord } = require('./transport.js');
const { createLogger } = require('./config.js');

const log = createLogger('sender');
const MAX_IN_FLIGHT = 64;
const inFlight = new Set();
let warnedFull = false;
let postImpl = null; // injectable for tests

/** Queue one prepared (filtered, encrypted) record; false when dropped. */
function sendAppRecord(url, record, { timeout = 5 } = {}) {
  if (!url || !record) return false;
  if (inFlight.size >= MAX_IN_FLIGHT) {
    if (!warnedFull) { warnedFull = true; log.warn('AnoSys send queue is full; telemetry is being dropped'); }
    return false;
  }
  const p = Promise.resolve()
    .then(() => postRecord(url, record, { timeout, ...(postImpl ? { post: postImpl } : {}) }))
    .then((res) => { if (res && res.status >= 400) log.error(`AnoSys rejected a record (HTTP ${res.status})`); })
    .catch((e) => log.error(`AnoSys send failed (${e?.name || 'Error'})`))
    .finally(() => inFlight.delete(p));
  inFlight.add(p);
  return true;
}

/** Wait (bounded) for records in flight: tests and short-lived scripts. */
async function flushAppRecords(ms = 2000) {
  const all = Promise.allSettled([...inFlight]);
  const timer = new Promise((resolve) => setTimeout(resolve, ms).unref?.());
  await Promise.race([all, timer]);
  return inFlight.size === 0;
}

function setSenderPostForTests(fn) { postImpl = fn; warnedFull = false; }

module.exports = { MAX_IN_FLIGHT, sendAppRecord, flushAppRecords, setSenderPostForTests };
