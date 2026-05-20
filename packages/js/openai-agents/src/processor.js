import { trace } from '@opentelemetry/api';
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';
import { BatchSpanProcessor, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { OpenAIInstrumentation } from '@opentelemetry/instrumentation-openai';
import axios from 'axios';

import { DEFAULT_API_URL, resolveApiKey, log } from './config.js';
import { setupApi } from './decorators.js';
import { span2json, extractOtelSpanInfo } from './mapping.js';
import { safeSerialize, cleanNulls } from './utils.js';

let _logApiUrl = DEFAULT_API_URL;
let _tracingInitialized = false;

// ── OTel HTTP exporter ────────────────────────────────────────────────────────

export class AnosysHttpExporter {
  constructor(getUserContext = null) {
    this._getUserContext = getUserContext ?? (() => null);
  }

  async export(spans, resultCallback) {
    for (const span of spans) {
      try {
        const data = extractOtelSpanInfo(span);
        const cleaned = cleanNulls(data) ?? {};

        const spanSource = cleaned.from_source ?? 'unknown_source';
        const spanName   = cleaned.otel_name ?? cleaned.name ?? 'unknown';
        log.debug('Exporting span from: %s | Name: %s', spanSource, spanName);

        await axios.post(_logApiUrl, cleaned, { timeout: 5000 });
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
   */
  constructor({ getUserContext = null } = {}) {
    this.getUserContext = getUserContext ?? (() => null);
    this._logApiUrl = DEFAULT_API_URL;
    this._ready = this._init();
  }

  async _init() {
    if (_tracingInitialized) return;
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
      await axios.post(this._logApiUrl, transformed, { timeout: 5000 });

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
