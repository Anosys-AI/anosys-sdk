import { trace } from '@opentelemetry/api';
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';
import { BatchSpanProcessor, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { OpenAIInstrumentation } from '@opentelemetry/instrumentation-openai';

import { resolveApiKey, log } from './config.js';
import { setupApi } from './decorators.js';
import { span2json, extractOtelSpanInfo } from './mapping.js';
import { safeSerialize, cleanNulls } from './utils.js';
import { OFF, prepareAppRecord, resolveAppLevel, sendAppRecord } from 'anosys-sdk-core';

// Agents-specific descriptive columns kept at `metadata` (agent hierarchy, handoffs, model, ids)
export const AGENTS_METADATA_COLUMNS = ['cvs62', 'cvs64', 'cvs68', 'cvs69', 'cvs77', 'cvs78', 'cvs79', 'llm_token_count'];

let _logApiUrl = null; // set by setupTracing; null = nothing is sent
let _tracingInitialized = false;
let _captureLevel = 'full'; // set by AnosysOpenAIAgentsLogger (see anosys-sdk-core capture.js)

// ── OTel HTTP exporter ────────────────────────────────────────────────────────

export class AnosysHttpExporter {
  /**
   * @param {Function} [getUserContext]
   * @param {object}   [opts] `getLevel` / `getUrl` override the module's level and endpoint
   *   (used by tests and by hosts that manage several exporters).
   */
  constructor(getUserContext = null, { getLevel = () => _captureLevel, getUrl = () => _logApiUrl } = {}) {
    this._getUserContext = getUserContext ?? (() => null);
    this._getLevel = getLevel;
    this._getUrl = getUrl;
  }

  async export(spans, resultCallback) {
    for (const span of spans) {
      try {
        const data = extractOtelSpanInfo(span);
        const cleaned = cleanNulls(data) ?? {};

        const spanSource = cleaned.from_source ?? 'unknown_source';
        const spanName   = cleaned.otel_name ?? cleaned.name ?? 'unknown';
        log.debug('Exporting span from: %s | Name: %s', spanSource, spanName);

        // Level filtering, cvs198 and encryption in one place
        const payloadToSend = prepareAppRecord(cleaned, this._getLevel(), AGENTS_METADATA_COLUMNS);
        if (!payloadToSend) continue;
        // size-limited, in the background: never blocks the instrumented call
        sendAppRecord(this._getUrl(), payloadToSend);
        log.debug('Successfully sent: %s | %s', spanSource, spanName);

      } catch (e) {
        if (e.response) {
          log.error('HTTP export failed (%d): %s', e.response.status, e.message);
        } else {
          log.error('Export failed:', e.message);
        }
      }
    }
    resultCallback?.({ code: 0 });
  }

  shutdown() { return Promise.resolve(); }
}

// ── OTel tracing setup ────────────────────────────────────────────────────────

export function setupTracing(apiUrl, useBatchProcessor = false, getUserContext = null) {
  _logApiUrl = apiUrl;

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
  constructor({ getUserContext = null, captureContent = null } = {}) {
    this.getUserContext = getUserContext ?? (() => null);
    const { level, source } = resolveAppLevel(captureContent);
    _captureLevel = level;
    this.captureLevel = level;
    log.info('AnoSys OpenAI Agents collection level: %s (%s)', level, source);
    this._logApiUrl = null;
    this._ready = this._init();
  }

  async _init() {
    if (_tracingInitialized || _captureLevel === OFF) return;
    _tracingInitialized = true;
    this._logApiUrl = await resolveApiKey();
    await setupApi({ path: this._logApiUrl });
    setupTracing(this._logApiUrl, false, this.getUserContext);
  }

  _getUserContextSafe() {
    try { return this.getUserContext(); } catch { return null; }
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

      const userCtx = this._getUserContextSafe();
      if (userCtx) {
        payload.user_context = {
          session_id: (typeof userCtx === 'object' ? (userCtx.session_id ?? 'unknown_session') : 'unknown_session'),
          token:      (typeof userCtx === 'object' ? (userCtx.token ?? null) : null),
          metadata:   null,
        };
      }

      const transformed = span2json(payload);
      // Content dropped at metadata, cvs198 and encryption in one place
      const payloadToSend = prepareAppRecord(transformed, _captureLevel, AGENTS_METADATA_COLUMNS);
      if (!payloadToSend) return;
      await this._ready; // records wait for the endpoint instead of going to a default
      sendAppRecord(this._logApiUrl ?? _logApiUrl, payloadToSend);

    } catch (e) {
      log.error('Error logging trace:', e.message);
    }
  }

  // TracingProcessor interface
  onTraceStart(traceObj)  { this._logSummary({ ...safeSerialize(traceObj), source: 'on_trace_start' }); }
  onTraceEnd(traceObj)    { this._logSummary({ ...safeSerialize(traceObj), source: 'on_trace_end'   }); }
  onSpanStart(span)       { this._logSummary({ ...safeSerialize(span),     source: 'on_span_start'  }); }
  onSpanEnd(span)         { this._logSummary({ ...safeSerialize(span),     source: 'on_span_end'    }); }
  forceFlush()            { return Promise.resolve(); }
  shutdown()              { return Promise.resolve(); }
}
