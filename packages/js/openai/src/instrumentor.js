import { trace, SpanStatusCode } from '@opentelemetry/api';
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';
import { BatchSpanProcessor, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { OpenAIInstrumentation } from '@opentelemetry/instrumentation-openai';

import { resolveApiKey, log } from './config.js';
import { setupApi } from './decorators.js';
import { extractSpanInfo } from './hooks.js';
import { acceptsSpan, currentAppLevel, OFF, prepareAppRecord, resolveAppLevel, sendAppRecord, spanToJson, userContextValue } from 'anosys-sdk-core';

// Spans this exporter owns; everything else on a shared provider is left alone
const OPENAI_SCOPES = ['@opentelemetry/instrumentation-openai', 'openinference.instrumentation.openai'];
const OPENAI_SYSTEMS = ['openai'];

let _logApiUrl = null; // set by setupTracing; null = nothing is sent
let _logApiUrlReady = Promise.resolve(null); // exports wait for the key to resolve
let _tracingInitialized = false;
let _captureLevel = null; // set by AnosysOpenAILogger; until then the shared level applies (anosys-sdk-core capture.js)

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
      if (!acceptsSpan(span, OPENAI_SCOPES, OPENAI_SYSTEMS)) continue;
      try {
        const spanJson = spanToJson(span);
        const data = extractSpanInfo(spanJson);

        // Attach user context if available
        try {
          const value = userContextValue(await this._getUserContext());
          if (value) data.cvs5 = value;
        } catch { /* user context errors must not block export */ }

        const spanSource = data.cvs200 ?? 'unknown_source';
        const spanName   = data.otel_name ?? 'unknown';
        log.debug('Exporting span from: %s | Name: %s', spanSource, spanName);

        // Level filtering, cvs198 and encryption in one place
        const payloadToSend = prepareAppRecord(data, this._getLevel());
        if (!payloadToSend) continue;
        // size-limited, in the background: never blocks the instrumented call
        await _logApiUrlReady;
        sendAppRecord(this._getUrl(), payloadToSend);

      } catch (e) {
        log.error(`Export failed (${e?.name || 'Error'})`); // no span content in logs
      }
    }
    resultCallback?.({ code: 0 });
  }

  shutdown() { return Promise.resolve(); }
}

/** `apiUrl` may be a promise: spans made before it resolves wait for it instead of being lost. */
export function setupTracing(apiUrl, useBatchProcessor = false, getUserContext = null) {
  _logApiUrlReady = Promise.resolve(apiUrl).then((url) => { _logApiUrl = url ?? null; return _logApiUrl; });

  const exporter = new AnosysHttpExporter(getUserContext);
  let provider;
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
    provider.register();
  }

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
    this.ready = Promise.resolve();
    if (_tracingInitialized || level === OFF) return;
    _tracingInitialized = true;
    // Instrument now (synchronously), so calls made right after the constructor are
    // traced; their spans wait for the key to resolve before they are sent.
    const url = resolveApiKey();
    setupTracing(url, false, this.getUserContext);
    this.ready = url.then(async (resolved) => {
      this.logApiUrl = resolved;
      await setupApi({ path: resolved });
    });
  }
}
