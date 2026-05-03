import { trace, SpanStatusCode } from '@opentelemetry/api';
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';
import { BatchSpanProcessor, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { OpenAIInstrumentation } from '@opentelemetry/instrumentation-openai';
import axios from 'axios';

import { DEFAULT_API_URL, resolveApiKey, log } from './config.js';
import { setupApi } from './decorators.js';
import { extractSpanInfo } from './hooks.js';

let _logApiUrl = DEFAULT_API_URL;
let _tracingInitialized = false;

export class AnosysHttpExporter {
  constructor(getUserContext = null) {
    this._getUserContext = getUserContext ?? (() => null);
  }

  async export(spans, resultCallback) {
    for (const span of spans) {
      try {
        const spanJson = JSON.parse(JSON.stringify(span, (_, v) =>
          typeof v === 'bigint' ? Number(v) : v
        ));
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

        await axios.post(_logApiUrl, data, { timeout: 5000 });

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

  const provider = new NodeTracerProvider();
  const exporter = new AnosysHttpExporter(getUserContext);

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

  provider.register();

  const instrumentation = new OpenAIInstrumentation({ enrichTokens: true });
  instrumentation.setTracerProvider(provider);
  instrumentation.enable();

  log.info('AnoSys instrumented OpenAI and OpenTelemetry traces');
  return provider;
}

export class AnosysOpenAILogger {
  constructor({ getUserContext = null } = {}) {
    this.getUserContext = getUserContext;
    this._init();
  }

  async _init() {
    if (_tracingInitialized) return;
    _tracingInitialized = true;
    this.logApiUrl = await resolveApiKey();
    await setupApi({ path: this.logApiUrl });
    setupTracing(this.logApiUrl, false, this.getUserContext);
  }
}
