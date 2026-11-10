'use strict';

/**
 * OpenTelemetry ReadableSpan -> plain JSON in the shape of Python's `span.to_json()`,
 * shared by every JS exporter. Reads fields only (no OTel dependency) and never
 * serialises the span object itself: SDK 2.x spans reference their processors, so
 * JSON.stringify(span) throws on the circular structure.
 */

const STATUS_CODES = { 0: 'UNSET', 1: 'OK', 2: 'ERROR' };
const SPAN_KINDS = { 0: 'INTERNAL', 1: 'SERVER', 2: 'CLIENT', 3: 'PRODUCER', 4: 'CONSUMER' };

function hrTimeToIso(hrTime) {
  if (!Array.isArray(hrTime)) return null;
  const ms = Number(hrTime[0]) * 1e3 + Number(hrTime[1]) / 1e6;
  return new Date(ms).toISOString();
}

const plain = (attrs) => JSON.parse(JSON.stringify(attrs ?? {}, (_, v) => (typeof v === 'bigint' ? Number(v) : v)));

function spanToJson(span) {
  const ctx = typeof span.spanContext === 'function' ? span.spanContext() : (span.context ?? {});
  const parentId = span.parentSpanContext?.spanId ?? span.parentSpanId ?? null;
  const statusCode = span.status?.code ?? 0;
  return {
    name: span.name,
    context: {
      trace_id: ctx.traceId ? `0x${ctx.traceId}` : null,
      span_id: ctx.spanId ? `0x${ctx.spanId}` : null,
      trace_state: ctx.traceState ? ctx.traceState.serialize() : '[]',
    },
    kind: `SpanKind.${SPAN_KINDS[span.kind] ?? 'INTERNAL'}`,
    parent_id: parentId ? `0x${parentId}` : null,
    start_time: hrTimeToIso(span.startTime),
    end_time: hrTimeToIso(span.endTime),
    status: span.status?.message
      ? { status_code: STATUS_CODES[statusCode], description: span.status.message }
      : { status_code: STATUS_CODES[statusCode] },
    attributes: plain(span.attributes),
    events: (span.events ?? []).map((e) => ({ name: e.name, timestamp: hrTimeToIso(e.time), attributes: plain(e.attributes) })),
    links: [],
    resource: { attributes: plain(span.resource?.attributes), schema_url: '' },
  };
}

function scopeName(span) {
  return span.instrumentationScope?.name ?? span.instrumentationLibrary?.name ?? '';
}

/**
 * Set `value` at a dotted OpenTelemetry attribute path, building objects and arrays as
 * needed (`llm.input_messages.0.message.role`: a numeric segment is an array index).
 * JSON-looking strings are parsed. Same as Python util.json.set_nested.
 */
function setNested(obj, path, value) {
  const parts = path.split('.');
  let current = obj;
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];
    const isIndex = /^\d+$/.test(part);
    if (Array.isArray(current) && !isIndex) return; // a name under an array: the path does not fit
    const key = Array.isArray(current) ? Number(part) : part;
    if (i === parts.length - 1) {
      let v = value;
      if (typeof v === 'string' && /^\s*[[{]/.test(v)) { try { v = JSON.parse(v); } catch { /* keep text */ } }
      current[key] = v;
      return;
    }
    const wantArray = /^\d+$/.test(parts[i + 1]);
    const existing = current[key];
    if (wantArray ? !Array.isArray(existing) : (!existing || typeof existing !== 'object' || Array.isArray(existing))) {
      current[key] = wantArray ? [] : {};
    }
    current = current[key];
  }
}

module.exports = { setNested, spanToJson, hrTimeToIso, scopeName, SPAN_KINDS, STATUS_CODES };
