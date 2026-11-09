import { trace, SpanStatusCode } from '@opentelemetry/api';
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';
import { BatchSpanProcessor, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { OpenAIInstrumentation } from '@opentelemetry/instrumentation-openai';

import { resolveApiKey, log } from './config.js';
import { setupApi } from './decorators.js';
import { extractSpanInfo } from './hooks.js';
import { OFF, prepareAppRecord, resolveAppLevel, sendAppRecord, spanToJson } from 'anosys-sdk-core';

let _logApiUrl = null; // set by setupTracing; null = nothing is sent
let _tracingInitialized = false;
let _captureLevel = 'full'; // set by AnosysOpenAILogger (see anosys-sdk-core capture.js)

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
        const spanJson = spanToJson(span);
        const data = extractSpanInfo(spanJson);

        // Attach user context if available
        try {
          const userCtx = await this._getUserContext();
          if (userCtx) {
            data.user_context = {
              session_id: (typeof userCtx === 'object' ? (userCtx.session_id ?? 'unknown_session') : 'unknown_session'),
              token:      (typeof userCtx === 'object' ? (userCtx.token ?? null) : null),
            };
          }
        } catch { /* user context errors must not block export */ }

        const spanSource = data.cvs200 ?? 'unknown_source';
        const spanName   = data.otel_name ?? 'unknown';
        log.debug('Exporting span from: %s | Name: %s', spanSource, spanName);

        // Level filtering, cvs198 and encryption in one place
        const payloadToSend = prepareAppRecord(data, this._getLevel());
        if (!payloadToSend) continue;
        // size-limited, in the background: never blocks the instrumented call
        sendAppRecord(this._getUrl(), payloadToSend);

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

export function setupTracing(apiUrl, useBatchProcessor = false, getUserContext = null) {
  _logApiUrl = apiUrl;

  const exporter = new AnosysHttpExporter(getUserContext);
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

  const provider = new NodeTracerProvider({
    spanProcessors: spanProcessors,
  });

  provider.register();

  const instrumentation = new OpenAIInstrumentation({ enrichTokens: true });
  instrumentation.setTracerProvider(provider);
  instrumentation.enable();

  log.info('AnoSys instrumented OpenAI and OpenTelemetry traces');
  return provider;
}

export class AnosysOpenAILogger {
  /**
   * @param {object}   [opts]
   * @param {Function} [opts.getUserContext]
   * @param {boolean}  [opts.captureContent] true: send prompts and completions; false: metadata
   *   only. Omitted: follow ANOSYS_COLLECTION_LEVEL and a project `.anosys` file; full otherwise.
   */
  constructor({ getUserContext = null, captureContent = null } = {}) {
    this.getUserContext = getUserContext;
    const { level, source } = resolveAppLevel(captureContent);
    _captureLevel = level;
    this.captureLevel = level;
    log.info('AnoSys OpenAI collection level: %s (%s)', level, source);
    this._init();
  }

  async _init() {
    if (_tracingInitialized || _captureLevel === OFF) return;
    _tracingInitialized = true;
    this.logApiUrl = await resolveApiKey();
    await setupApi({ path: this.logApiUrl });
    setupTracing(this.logApiUrl, false, this.getUserContext);
  }
}
