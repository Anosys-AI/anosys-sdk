import { trace } from '@opentelemetry/api';
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';
import { BatchSpanProcessor, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';
import axios from 'axios';

import { DEFAULT_API_URL, resolveApiKey, log } from './config.js';
import { setupApi } from './decorators.js';
import { spanToJson } from './genai.js';
import { extractSpanInfo, isAnthropicSpan } from './hooks.js';
import { encryptPayload } from './encryption.js';

// Read by the Anthropic SDK when a client is constructed
export const CONTENT_MODE_ENV = 'ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE';

let _logApiUrl = DEFAULT_API_URL;
let _logApiUrlReady = Promise.resolve(DEFAULT_API_URL);
let _tracingInitialized = false;
let _provider = null;
let _hub = null;

function scopeName(span) {
  return span.instrumentationScope?.name ?? span.instrumentationLibrary?.name ?? '';
}

// ── OTel HTTP exporter ────────────────────────────────────────────────────────

/**
 * Sends GenAI spans to AnoSys. `acceptsSpan(scopeName, attributes)` picks the
 * spans this exporter owns, so several integrations can share a provider.
 */
export class AnosysHttpExporter {
  constructor({
    getUserContext = null,
    acceptsSpan = isAnthropicSpan,
    extract = extractSpanInfo,
  } = {}) {
    this._getUserContext = getUserContext ?? (() => null);
    this._acceptsSpan = acceptsSpan;
    this._extract = extract;
  }

  async export(spans, resultCallback) {
    for (const span of spans) {
      if (!this._acceptsSpan(scopeName(span), span.attributes ?? {})) continue;
      try {
        const data = this._extract(spanToJson(span));

        // Attach user context if available
        try {
          const userCtx = await this._getUserContext();
          if (userCtx && typeof userCtx === 'object') {
            data.cvs5 = JSON.stringify({
              session_id: userCtx.session_id ?? 'unknown_session',
              token: userCtx.token ?? null,
            });
          }
        } catch { /* user context errors must not block export */ }

        log.debug('Exporting span from: %s | Name: %s', data.cvs200, data.otel_name);

        const payloadToSend = encryptPayload(data);
        await _logApiUrlReady;
        await axios.post(_logApiUrl, payloadToSend, { timeout: 5000 });
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

// ── Shared tracer provider ────────────────────────────────────────────────────

/** Span processor that fans out to processors added after the provider was built. */
class SpanProcessorHub {
  constructor() { this._processors = []; }
  add(processor) { this._processors.push(processor); }
  onStart(span, parentContext) { for (const p of this._processors) p.onStart(span, parentContext); }
  onEnd(span) { for (const p of this._processors) p.onEnd(span); }
  forceFlush() { return Promise.all(this._processors.map(p => p.forceFlush())).then(() => {}); }
  shutdown() { return Promise.all(this._processors.map(p => p.shutdown())).then(() => {}); }
}

/**
 * Add a span processor to the AnoSys tracer provider, creating and registering
 * the provider on first use. Shared by the Anthropic and Claude Agents loggers.
 */
export function addSpanProcessor(processor) {
  if (!_hub) {
    _hub = new SpanProcessorHub();
    _provider = new NodeTracerProvider({ spanProcessors: [_hub] });
    _provider.register();
    const active = trace.getTracerProvider();
    const delegate = typeof active.getDelegate === 'function' ? active.getDelegate() : active;
    if (delegate !== _provider) {
      log.warn('Another global tracer provider is registered. Pass `openTelemetry: { tracerProvider: getTracerProvider() }` to Anthropic clients so their spans reach AnoSys.');
    }
  }
  _hub.add(processor);
  return _provider;
}

/** The AnoSys tracer provider (null until a logger is initialized). */
export function getTracerProvider() {
  return _provider;
}

/** Set the ingestion URL; a promise holds exports until it resolves. */
export function setLogApiUrl(apiUrl) {
  _logApiUrlReady = Promise.resolve(apiUrl).then((url) => { _logApiUrl = url ?? DEFAULT_API_URL; return _logApiUrl; });
  return _logApiUrlReady;
}

export function createSpanProcessor(exporter, useBatchProcessor = false) {
  if (useBatchProcessor) {
    log.info('Using BatchSpanProcessor');
    return new BatchSpanProcessor(exporter, {
      scheduledDelayMillis: 1000,
      maxQueueSize: 2048,
      maxExportBatchSize: 512,
    });
  }
  log.info('Using SimpleSpanProcessor');
  return new SimpleSpanProcessor(exporter);
}

export function setupTracing(apiUrl, useBatchProcessor = false, getUserContext = null) {
  setLogApiUrl(apiUrl);
  const exporter = new AnosysHttpExporter({ getUserContext });
  const provider = addSpanProcessor(createSpanProcessor(exporter, useBatchProcessor));
  log.info('AnoSys attached to Anthropic OpenTelemetry traces');
  return provider;
}

export class AnosysAnthropicLogger {
  /**
   * @param {object}   [opts]
   * @param {Function} [opts.getUserContext]     Returns { session_id, token }
   * @param {boolean}  [opts.captureContent=true] Record prompts and completions. Applies to
   *   clients created afterwards that are given no `openTelemetry` option of their own.
   * @param {boolean}  [opts.useBatchProcessor=false]
   */
  constructor({ getUserContext = null, captureContent = true, useBatchProcessor = false } = {}) {
    this.getUserContext = getUserContext;
    // The SDK records metadata only unless content mode is requested
    if (captureContent && process.env[CONTENT_MODE_ENV] === undefined) {
      process.env[CONTENT_MODE_ENV] = 'content';
    }
    // The provider is registered synchronously so clients created right after see it
    if (!_tracingInitialized) {
      _tracingInitialized = true;
      setupTracing(_logApiUrlReady, useBatchProcessor, this.getUserContext);
      this.ready = this._init();
    } else {
      this.ready = Promise.resolve();
    }
  }

  async _init() {
    this.logApiUrl = await setLogApiUrl(resolveApiKey());
    await setupApi({ path: this.logApiUrl });
  }
}
