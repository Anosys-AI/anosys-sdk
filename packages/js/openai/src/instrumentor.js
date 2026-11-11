import { trace, SpanStatusCode } from '@opentelemetry/api';
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';
import { BatchSpanProcessor, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { OpenAIInstrumentation } from '@opentelemetry/instrumentation-openai';
import { createRequire } from 'node:module';

import { resolveApiKey, log } from './config.js';
import { setupApi } from './decorators.js';
import { extractSpanInfo } from './hooks.js';
import { acceptsSpan, currentAppLevel, FULL, METADATA, OFF, prepareAppRecord, resolveAppLevel, sendAppRecord, spanToJson, userContextValue } from 'anosys-sdk-core';

// Spans this exporter owns; everything else on a shared provider is left alone
const OPENAI_SCOPES = ['@opentelemetry/instrumentation-openai', 'openinference.instrumentation.openai'];
const OPENAI_SYSTEMS = ['openai'];

let _logApiUrl = null; // set by setupTracing; null = nothing is sent
let _logApiUrlReady = Promise.resolve(null); // exports wait for the key to resolve
let _tracingInitialized = false;
let _captureLevel = null; // set by AnosysOpenAILogger; until then the shared level applies (anosys-sdk-core capture.js)
let _instrumentation = null;
let _bridgeInstalled = false;
let _activeExporter = null;

// ── Bridge Logger: connects @opentelemetry/instrumentation-openai logs to spans ──
// The instrumentation emits prompts and answers as log records only because AnoSys
// turned on captureMessageContent. They are copied onto the span for AnoSys and go
// nowhere else: never to the app's global logger provider or its log exporters.

class BridgeLogger {

  emit(record) {
    try {
      if (record?.context) {
        const span = trace.getSpan(record.context);
        if (span && typeof span.setAttribute === 'function') {
          const eventName = record.attributes?.['event.name'];
          const body = record.body || {};

          if (eventName === 'gen_ai.user.message' || eventName === 'gen_ai.system.message') {
            if (!body.content) return;
            const raw = span.attributes?.['gen_ai.input.messages'];
            let existing = [];
            if (raw) {
              try { existing = JSON.parse(raw); } catch { existing = []; }
            }
            const role = eventName.includes('system') ? 'system' : 'user';
            const content = body.content || '';
            existing.push({ role, content });
            span.setAttribute('gen_ai.input.messages', JSON.stringify(existing));
            span.setAttribute('llm_input', existing.map((m) => m.content).filter(Boolean).join('\n---\n'));
          } else if (eventName === 'gen_ai.tool.message') {
            if (!body.content && !body.id) return;
            const raw = span.attributes?.['gen_ai.input.messages'];
            let existing = [];
            if (raw) {
              try { existing = JSON.parse(raw); } catch { existing = []; }
            }
            existing.push({ role: 'tool', content: body.content || '', id: body.id });
            span.setAttribute('gen_ai.input.messages', JSON.stringify(existing));
            span.setAttribute('llm_input', existing.map((m) => m.content).filter(Boolean).join('\n---\n'));
          } else if (eventName === 'gen_ai.choice' || eventName === 'gen_ai.assistant.message') {
            const content = body.message?.content || body.content || '';
            const toolCalls = body.message?.tool_calls || body.tool_calls;
            if (!content && !toolCalls) return;
            const raw = span.attributes?.['gen_ai.output.messages'];
            let existing = [];
            if (raw) {
              try { existing = JSON.parse(raw); } catch { existing = []; }
            }
            const item = { role: 'assistant', content };
            if (toolCalls) {
              item.tool_calls = toolCalls;
            }
            existing.push(item);
            span.setAttribute('gen_ai.output.messages', JSON.stringify(existing));
            const outText = existing.map((m) => {
              if (m.content) return m.content;
              if (m.tool_calls) return typeof m.tool_calls === 'string' ? m.tool_calls : JSON.stringify(m.tool_calls);
              return '';
            }).filter(Boolean).join('\n---\n');
            if (outText) span.setAttribute('llm_output', outText);
          }
        }
      }
    } catch {
      // Logger bridge must never crash instrumented execution
    }
  }
}

/** Given only to the OpenAI instrumentation (setLoggerProvider); the global provider is never touched. */
class BridgeLoggerProvider {
  getLogger() {
    return new BridgeLogger();
  }
}

// ── OpenAI patching (works with ESM imports and already-loaded instances) ─────────

let defaultOpenAI = null;
try {
  const mod = await import('openai');
  defaultOpenAI = mod.default || mod.OpenAI || mod;
} catch {
  // CommonJS or openai not in current scope
}
if (!defaultOpenAI) {
  try {
    const req = createRequire(import.meta.url);
    const mod = req('openai');
    defaultOpenAI = mod.OpenAI || mod.default || mod;
  } catch {
    // not present
  }
}

export function patchOpenAI(target = null) {
  if (!_instrumentation) return;
  const targets = [];
  if (target) targets.push(target);
  if (defaultOpenAI) targets.push(defaultOpenAI);
  if (typeof globalThis !== 'undefined' && globalThis.OpenAI) {
    targets.push(globalThis.OpenAI);
  }

  for (const t of targets) {
    if (!t) continue;
    let completionsProto = null;
    let embeddingsProto = null;

    if (t.Chat?.Completions?.prototype) {
      completionsProto = t.Chat.Completions.prototype;
    } else if (t.chat?.completions) {
      completionsProto = Object.getPrototypeOf(t.chat.completions);
    }

    if (t.Embeddings?.prototype) {
      embeddingsProto = t.Embeddings.prototype;
    } else if (t.embeddings) {
      embeddingsProto = Object.getPrototypeOf(t.embeddings);
    }

    if (completionsProto && typeof completionsProto.create === 'function' && !completionsProto.create.__anosys_wrapped) {
      try {
        _instrumentation._wrap(completionsProto, 'create', _instrumentation._getPatchedChatCompletionsCreate());
        completionsProto.create.__anosys_wrapped = true;
      } catch (err) {
        log.warn('Failed to wrap OpenAI completions:', err);
      }
    }

    if (embeddingsProto && typeof embeddingsProto.create === 'function' && !embeddingsProto.create.__anosys_wrapped) {
      try {
        _instrumentation._wrap(embeddingsProto, 'create', _instrumentation._getPatchedEmbeddingsCreate());
        embeddingsProto.create.__anosys_wrapped = true;
      } catch (err) {
        log.warn('Failed to wrap OpenAI embeddings:', err);
      }
    }
  }
}

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
export function setupTracing(apiUrl, useBatchProcessor = false, getUserContext = null, captureLevel = null, extraSpanProcessors = []) {
  _logApiUrlReady = Promise.resolve(apiUrl).then((url) => { _logApiUrl = url ?? null; return _logApiUrl; });

  if (_activeExporter) {
    if (getUserContext) _activeExporter._getUserContext = getUserContext;
  }
  const exporter = _activeExporter ?? new AnosysHttpExporter(getUserContext);
  _activeExporter = exporter;

  let provider;
  const active = trace.getTracerProvider();
  const delegate = active && typeof active.getDelegate === 'function' ? active.getDelegate() : active;
  const hasLegacyAddSpan = active && typeof active.addSpanProcessor === 'function';
  const hasMultiProcessor = delegate && delegate._activeSpanProcessor && Array.isArray(delegate._activeSpanProcessor._spanProcessors);

  const mainProcessor = useBatchProcessor
    ? new BatchSpanProcessor(exporter, { scheduledDelayMillis: 1000, maxQueueSize: 2048, maxExportBatchSize: 512 })
    : new SimpleSpanProcessor(exporter);

  if (hasMultiProcessor) {
    provider = delegate;
    if (!delegate._activeSpanProcessor._spanProcessors.some((p) => p._spanExporter === exporter || p.spanExporter === exporter)) {
      delegate._activeSpanProcessor._spanProcessors.push(mainProcessor);
    }
    for (const esp of extraSpanProcessors) {
      delegate._activeSpanProcessor._spanProcessors.push(esp);
    }
    log.info('Attached span processor to existing TracerProvider');
  } else if (hasLegacyAddSpan) {
    provider = active;
    active.addSpanProcessor(mainProcessor);
    for (const esp of extraSpanProcessors) {
      active.addSpanProcessor(esp);
    }
    log.info('Attached span processor via addSpanProcessor');
  } else {
    const spanProcessors = [mainProcessor, ...extraSpanProcessors];
    provider = new NodeTracerProvider({
      spanProcessors: spanProcessors,
    });
    provider.register();
  }

  const level = captureLevel ?? _captureLevel ?? currentAppLevel().level;
  _captureLevel = level;
  const captureMessageContent = level === FULL;

  if (!_instrumentation) {
    _instrumentation = new OpenAIInstrumentation({ enrichTokens: true, captureMessageContent });
    _instrumentation.setLoggerProvider(new BridgeLoggerProvider());
    _instrumentation.setTracerProvider(provider);
    _instrumentation.enable();
  } else {
    _instrumentation.setConfig({ enrichTokens: true, captureMessageContent });
  }

  // Ensure default and loaded OpenAI classes are patched
  patchOpenAI(defaultOpenAI);

  // Background dynamic import to catch late ESM imports
  try {
    import('openai').then((mod) => {
      const cls = mod.default || mod.OpenAI || mod;
      if (cls) patchOpenAI(cls);
    }).catch(() => {});
  } catch {}

  log.info('AnoSys instrumented OpenAI and OpenTelemetry traces');
  return provider;
}

export class AnosysOpenAILogger {
  /**
   * @param {object}   [opts]
   * @param {Function} [opts.getUserContext]
   * @param {boolean}  [opts.captureContent] true: send prompts and completions; false: metadata
   *   only. Omitted: follow ANOSYS_COLLECTION_LEVEL and a project `.anosys` file; full otherwise.
   * @param {object}   [opts.openai] Explicit OpenAI class or client instance to patch.
   * @param {object}   [opts.client] Explicit OpenAI client instance to patch.
   */
  constructor({ getUserContext = null, captureContent = null, openai = null, client = null } = {}) {
    this.getUserContext = getUserContext;
    const { level, source } = resolveAppLevel(captureContent);
    _captureLevel = level;
    this.captureLevel = level;
    log.info('AnoSys OpenAI collection level: %s (%s)', level, source);

    if (_instrumentation) {
      _instrumentation.setConfig({ enrichTokens: true, captureMessageContent: level === FULL });
    }

    if (openai || client) {
      patchOpenAI(openai || client);
    }

    this.ready = Promise.resolve();
    if (_tracingInitialized || level === OFF) return;
    _tracingInitialized = true;

    // Instrument now (synchronously), so calls made right after the constructor are
    // traced; their spans wait for the key to resolve before they are sent.
    const url = resolveApiKey();
    setupTracing(url, false, this.getUserContext, level);

    if (openai || client) {
      patchOpenAI(openai || client);
    }

    this.ready = url.then(async (resolved) => {
      this.logApiUrl = resolved;
      await setupApi({ path: resolved });
    });
  }
}
