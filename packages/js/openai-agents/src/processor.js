import { trace } from '@opentelemetry/api';
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';
import { BatchSpanProcessor, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { OpenAIInstrumentation } from '@opentelemetry/instrumentation-openai';

import { resolveApiKey, log } from './config.js';
import { setupApi } from './decorators.js';
import { span2json, extractOtelSpanInfo } from './mapping.js';
import { safeSerialize, cleanNulls } from './utils.js';
import { acceptsSpan, APP_METADATA_STRING_COLUMNS, currentAppLevel, FULL, OFF, prepareAppRecord, redactPii, resolveAppLevel, sendAppRecord, userContextValue } from 'anosys-sdk-core';

// Spans this exporter owns; everything else on a shared provider is left alone
const AGENTS_SCOPES = ['@opentelemetry/instrumentation-openai', 'openai-agents', '@openai/agents'];
const AGENTS_SYSTEMS = ['openai'];

// Agents-specific descriptive columns kept at `metadata` (agent hierarchy, handoffs, model, ids)
export const AGENTS_METADATA_COLUMNS = ['cvs62', 'cvs64', 'cvs68', 'cvs69', 'cvs77', 'cvs78', 'cvs79', 'llm_token_count'];

const _captureFlags = { inputs: true, outputs: true, parameters: true };
const INPUT_COLUMNS = ['llm_input', 'gen_ai_input_messages', 'gen_ai_system_instructions', 'llm_system', 'cvs65', 'cvs71'];
const OUTPUT_COLUMNS = ['llm_output', 'gen_ai_output_messages', 'cvs66', 'cvs67', 'cvs72', 'cvs76'];
const PARAMETER_COLUMNS = ['llm_invocation_parameters', 'cvs70'];
const RAW_COLUMNS = ['cvs199', 'cvs18', 'otel_events'];

function dropUncaptured(record) {
  if (_captureFlags.inputs && _captureFlags.outputs && _captureFlags.parameters) return record;
  const drop = new Set(RAW_COLUMNS);
  if (!_captureFlags.inputs) for (const c of INPUT_COLUMNS) drop.add(c);
  if (!_captureFlags.outputs) for (const c of OUTPUT_COLUMNS) drop.add(c);
  if (!_captureFlags.parameters) for (const c of PARAMETER_COLUMNS) drop.add(c);
  return Object.fromEntries(Object.entries(record).filter(([k]) => !drop.has(k)));
}

/** pii_redaction: redact PII patterns in content columns, never in ids or metadata. */
function redactContent(record) {
  const keep = new Set([...APP_METADATA_STRING_COLUMNS, ...AGENTS_METADATA_COLUMNS]);
  return Object.fromEntries(Object.entries(record).map(([k, v]) => [k, typeof v === 'string' && !keep.has(k) ? redactPii(v) : v]));
}

let _logApiUrl = null; // set by setupTracing; null = nothing is sent
let _logApiUrlReady = Promise.resolve(null); // exports wait for the key to resolve
let _piiRedaction = false; // set by AnosysOpenAIAgentsLogger
let _tracingInitialized = false;
let _captureLevel = null; // set by AnosysOpenAIAgentsLogger; until then the shared level applies (anosys-sdk-core capture.js)

// ── OTel HTTP exporter ────────────────────────────────────────────────────────

export class AnosysHttpExporter {
  /**
   * @param {Function} [getUserContext]
   * @param {object}   [opts] `getLevel` / `getUrl` override the module's level and endpoint
   *   (used by tests and by hosts that manage several exporters).
   */
  constructor(getUserContext = null, { getLevel = () => _captureLevel ?? currentAppLevel().level, getUrl = () => _logApiUrl } = {}) {
    this._getUserContext = getUserContext ?? (() => null);
    this._getLevel = getLevel;
    this._getUrl = getUrl;
  }

  async export(spans, resultCallback) {
    for (const span of spans) {
      if (!acceptsSpan(span, AGENTS_SCOPES, AGENTS_SYSTEMS)) continue;
      try {
        const data = extractOtelSpanInfo(span);
        let cleaned = dropUncaptured(cleanNulls(data) ?? {});
        if (_piiRedaction) cleaned = redactContent(cleaned);
        try {
          const value = userContextValue(await this._getUserContext());
          if (value) cleaned.cvs5 = value;
        } catch { /* user context errors must not block export */ }

        const spanSource = cleaned.from_source ?? 'unknown_source';
        const spanName   = cleaned.otel_name ?? cleaned.name ?? 'unknown';
        log.debug('Exporting span from: %s | Name: %s', spanSource, spanName);

        // Level filtering, cvs198 and encryption in one place
        const payloadToSend = prepareAppRecord(cleaned, this._getLevel(), AGENTS_METADATA_COLUMNS);
        if (!payloadToSend) continue;
        // size-limited, in the background: never blocks the instrumented call
        await _logApiUrlReady;
        sendAppRecord(this._getUrl(), payloadToSend);
        log.debug('Successfully sent: %s | %s', spanSource, spanName);

      } catch (e) {
        log.error(`Export failed (${e?.name || 'Error'})`); // no span content in logs
      }
    }
    resultCallback?.({ code: 0 });
  }

  shutdown() { return Promise.resolve(); }
}

// ── OTel tracing setup ────────────────────────────────────────────────────────

/** `apiUrl` may be a promise: spans made before it resolves wait for it instead of being lost. */
export function setupTracing(apiUrl, useBatchProcessor = false, getUserContext = null) {
  _logApiUrlReady = Promise.resolve(apiUrl).then((url) => { _logApiUrl = url ?? null; return _logApiUrl; });

  const exporter = new AnosysHttpExporter(getUserContext);
  let provider;

  // Reuse existing global provider if it's a legacy TracerProvider
  const active = trace.getTracerProvider();
  const hasLegacyAddSpan = active && typeof active.addSpanProcessor === 'function';

  if (hasLegacyAddSpan) {
    provider = active;
    log.info('Attaching to existing global TracerProvider');

    if (useBatchProcessor) {
      provider.addSpanProcessor(new BatchSpanProcessor(exporter, {
        scheduledDelayMillis: 1000,
        maxQueueSize: 2048,
        maxExportBatchSize: 512,
      }));
      log.info('Using BatchSpanProcessor');
    } else {
      provider.addSpanProcessor(new SimpleSpanProcessor(exporter));
      log.info('Using SimpleSpanProcessor');
    }
  } else {
    const spanProcessors = [];
    if (useBatchProcessor) {
      spanProcessors.push(new BatchSpanProcessor(exporter, {
        scheduledDelayMillis: 1000,
        maxQueueSize: 2048,
        maxExportBatchSize: 512,
      }));
      log.info('Using BatchSpanProcessor');
    } else {
      spanProcessors.push(new SimpleSpanProcessor(exporter));
      log.info('Using SimpleSpanProcessor');
    }

    provider = new NodeTracerProvider({
      spanProcessors: spanProcessors,
    });
    log.info('Creating new global TracerProvider');
  }

  if (!hasLegacyAddSpan) {
    provider.register();
  }

  const instrumentation = new OpenAIInstrumentation({ enrichTokens: true });
  instrumentation.setTracerProvider(provider);
  instrumentation.enable();

  log.info('AnoSys instrumented OpenAI Agents and OpenTelemetry traces');
  return provider;
}

// ── AnosysOpenAIAgentsLogger — mirrors Python AnosysOpenAIAgentsLogger ────────

export class AnosysOpenAIAgentsLogger {
  /**
   * @param {object}   options
   * @param {function} [options.getUserContext] - Returns user context object { session_id, token }
   * @param {boolean}  [options.captureContent] - true: send inputs and outputs; false: metadata
   *   only. Omitted: follow ANOSYS_COLLECTION_LEVEL and a project `.anosys` file; full otherwise.
   */
  constructor({
    getUserContext = null,
    captureContent = null,
    captureInputs = null,
    captureOutputs = null,
    captureParameters = null,
    piiRedaction = false,
  } = {}) {
    this.getUserContext = getUserContext ?? (() => null);
    _piiRedaction = Boolean(piiRedaction);
    this.piiRedaction = _piiRedaction;
    let explicit = captureContent;
    if (explicit === null || explicit === undefined) {
      const given = [captureInputs, captureOutputs, captureParameters].filter((f) => f !== null && f !== undefined);
      explicit = given.some(Boolean) ? true : (given.length === 3 ? false : null);
    }
    const { level, source } = resolveAppLevel(explicit);
    _captureLevel = level;
    this.captureLevel = level;
    const isFull = level === FULL;
    this.captureInputs = captureInputs === null ? isFull : Boolean(captureInputs && isFull);
    this.captureOutputs = captureOutputs === null ? isFull : Boolean(captureOutputs && isFull);
    this.captureParameters = captureParameters === null ? isFull : Boolean(captureParameters && isFull);
    _captureFlags.inputs = this.captureInputs;
    _captureFlags.outputs = this.captureOutputs;
    _captureFlags.parameters = this.captureParameters;
    log.info('AnoSys OpenAI Agents collection level: %s (%s)', level, source);
    this._logApiUrl = null;
    this._ready = Promise.resolve();
    if (_tracingInitialized || level === OFF) return;
    _tracingInitialized = true;
    // Instrument now (synchronously), so calls made right after the constructor are
    // traced; their spans wait for the key to resolve before they are sent.
    const url = resolveApiKey();
    setupTracing(url, false, this.getUserContext);
    this._ready = url.then(async (resolved) => {
      this._logApiUrl = resolved;
      await setupApi({ path: resolved });
    });
  }

  async _getUserContextSafe() {
    try { return await this.getUserContext(); } catch { return null; }
  }

  async _logSummary(data) {
    try {
      const cleaned = JSON.parse(JSON.stringify(data, (_, v) =>
        v instanceof Map ? Object.fromEntries(v) : v
      ));

      const payload = {
        timestamp: new Date().toISOString(),
        data: cleaned,
      };

      const userCtx = await this._getUserContextSafe();
      if (userCtx) {
        payload.user_context = {
          session_id: (typeof userCtx === 'object' ? (userCtx.session_id ?? 'unknown_session') : 'unknown_session'),
          token:      (typeof userCtx === 'object' ? (userCtx.token ?? null) : null),
          metadata:   null,
        };
      }

      let transformed = dropUncaptured(span2json(payload));
      if (_piiRedaction) transformed = redactContent(transformed);
      // Content dropped at metadata, cvs198 and encryption in one place
      const payloadToSend = prepareAppRecord(transformed, _captureLevel ?? currentAppLevel().level, AGENTS_METADATA_COLUMNS);
      if (!payloadToSend) return;
      await this._ready; // records wait for the endpoint instead of going to a default
      sendAppRecord(this._logApiUrl ?? _logApiUrl, payloadToSend);

    } catch (e) {
      log.error(`Error logging trace (${e?.name || 'Error'})`);
    }
  }

  // TracingProcessor interface
  // Serialising user objects can throw (getters, cycles); it must never break the agent run
  _record(obj, source) {
    try { this._logSummary({ ...safeSerialize(obj), source }); } catch (e) { log.error(`Error logging trace (${e?.name || 'Error'})`); }
  }

  onTraceStart(traceObj)  { this._record(traceObj, 'on_trace_start'); }
  onTraceEnd(traceObj)    { this._record(traceObj, 'on_trace_end'); }
  onSpanStart(span)       { this._record(span, 'on_span_start'); }
  onSpanEnd(span)         { this._record(span, 'on_span_end'); }
  forceFlush()            { return Promise.resolve(); }
  shutdown()              { return Promise.resolve(); }
}
