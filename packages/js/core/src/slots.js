'use strict';

/**
 * Dynamic custom-variable column allocation — JS port of Python
 * `anosys_sdk_core/util/batching.py` (_allocate_slot).
 *
 * A new attribute never shares a column with another attribute (fixed,
 * reserved, or allocated earlier in the same record), never takes the
 * reserved columns, and is dropped (warned once) when its type's columns
 * are used up instead of overflowing into a column that does not exist.
 */

const SLOT_LIMITS = { cvs: 200, cvn: 200, cvb: 100 };
const RESERVED_SLOTS = new Set(['cvs198', 'cvs199', 'cvs200']);
const droppedKeys = new Set();

/** The first free `${prefix}N` from `start`, or null; adds it to `used`. */
function allocateSlot(prefix, start, used) {
  const limit = SLOT_LIMITS[prefix] ?? 200;
  for (let index = Math.max(1, Number(start) || 1); index <= limit; index++) {
    const slot = `${prefix}${index}`;
    if (!used.has(slot) && !RESERVED_SLOTS.has(slot)) {
      used.add(slot);
      return slot;
    }
  }
  return null;
}

/** Log once per attribute that could not get a column. */
function warnDropped(key, prefix) {
  if (droppedKeys.has(key)) return;
  droppedKeys.add(key);
  if ((process.env.ANOSYS_LOG_LEVEL || 'warn') !== 'silent') {
    console.warn(`[anosys] No free ${prefix} column for attribute "${key}"; it is not sent`);
  }
}

module.exports = { SLOT_LIMITS, RESERVED_SLOTS, allocateSlot, warnDropped };
