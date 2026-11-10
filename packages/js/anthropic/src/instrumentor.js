import { trace } from '@opentelemetry/api';
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';
import { BatchSpanProcessor, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';

import { resolveApiKey, log } from './config.js';
import { setupApi } from './decorators.js';
import { spanToJson } from './genai.js';
import { extractSpanInfo, isAnthropicSpan } from './hooks.js';
import { currentAppLevel, FULL, OFF, prepareAppRecord, resolveAppLevel, scopeName, sendAppRecord, userContextValue } from 'anosys-sdk-core';

// Read by the Anthropic SDK when a client is constructed
export const CONTENT_MODE_ENV = 'ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE';

let _logApiUrl = null; // null = nothing is sent
let _logApiUrlReady = Promise.resolve(null);
let _tracingInitialized = false;
let _provider = null;
let _captureContent = true;
let _captureLevel = null; // set by AnosysAnthropicLogger; until then the shared level applies (anosys-sdk-core capture.js)
let _hub = null;


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
    getLevel = () => _captureLevel ?? currentAppLevel().level,
    getUrl = () => _logApiUrl,
  } = {}) {
    this._getUserContext = getUserContext ?? (() => null);
    this._getLevel = getLevel;
    this._getUrl = getUrl;
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
          const value = userContextValue(await this._getUserContext());
          if (value) data.cvs5 = value;
        } catch { /* user context errors must not block export */ }

        log.debug(
          'Exporting span from: %s | Name: %s | input_len: %d | output_len: %d',
          data.cvs200,
          data.otel_name,
          data.llm_input ? String(data.llm_input).length : 0,
          data.llm_output ? String(data.llm_output).length : 0,
        );

        // Level filtering, cvs198 and encryption in one place
        const payloadToSend = prepareAppRecord(data, this._getLevel());
        if (!payloadToSend) continue;
        await _logApiUrlReady;
        // size-limited, in the background: never blocks the instrumented call
        sendAppRecord(this._getUrl(), payloadToSend);
      } catch (e) {
        log.error(`Export failed (${e?.name || 'Error'})`); // no span content in logs
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
      log.warn('Another global tracer provider is registered. Pass `openTelemetry: getAnthropicOpenTelemetryOptions()` to Anthropic clients so their spans reach AnoSys.');
    }
  }
  _hub.add(processor);
  return _provider;
}

/** The AnoSys tracer provider (null until a logger is initialized). */
export function getTracerProvider() {
  return _provider;
}

/**
 * Returns the recommended OpenTelemetry options to pass to `new Anthropic({ openTelemetry })`.
 * The SDK treats a given option as complete and ignores the environment, so this
 * carries both the AnoSys tracer provider and the logger's `captureContent` choice.
 * Call it after creating the logger.
 */
export function getAnthropicOpenTelemetryOptions() {
  const options = {
    traces: {
      contentMode: _captureContent ? 'content' : 'metadata_only',
    },
  };
  if (_provider) {
    options.tracerProvider = _provider;
  } else {
    log.warn('getAnthropicOpenTelemetryOptions() was called before AnosysAnthropicLogger; the client will use the global tracer provider.');
  }
  return options;
}

/** Set the ingestion URL; a promise holds exports until it resolves. */
export function setLogApiUrl(apiUrl) {
  _logApiUrlReady = Promise.resolve(apiUrl).then((url) => { _logApiUrl = url ?? null; return _logApiUrl; });
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
   * @param {boolean}  [opts.captureContent] true: record prompts and completions; false: metadata
   *   only. Omitted: follow ANOSYS_COLLECTION_LEVEL and a project `.anosys` file; full otherwise. Applies to
   *   clients created afterwards that are given no `openTelemetry` option of their own.
   * @param {boolean}  [opts.useBatchProcessor=false]
   */
  constructor({ getUserContext = null, captureContent = null, useBatchProcessor = false } = {}) {
    this.getUserContext = getUserContext;
    const { level, source } = resolveAppLevel(captureContent);
    _captureLevel = level;
    _captureContent = level === FULL;
    this.captureLevel = level;
    log.info('AnoSys Anthropic collection level: %s (%s)', level, source);
    // The SDK records metadata only unless content mode is requested
    if (_captureContent && process.env[CONTENT_MODE_ENV] === undefined) {
      process.env[CONTENT_MODE_ENV] = 'content';
    }
    // The provider is registered synchronously so clients created right after see it
    if (level === OFF) {
      this.ready = Promise.resolve();
    } else if (!_tracingInitialized) {
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
