import { context, trace } from '@opentelemetry/api';
import {
  AnosysHttpExporter,
  addSpanProcessor,
  createSpanProcessor,
  resolveApiKey,
  setLogApiUrl,
  setupApi,
  log,
} from 'anosys-sdk-anthropic';
import { FULL, OFF, currentAppLevel, resolveAppLevel } from 'anosys-sdk-core';

import { extractSpanInfo } from './hooks.js';
import { CLAUDE_AGENTS_SCOPE } from './mapping.js';
import { AgentRunTracer } from './tracer.js';

let _tracer = null;
let _tracingInitialized = false;
const _runSettings = { captureContent: true, emitLlmSpans: false, agentName: null, level: null };

export function setupTracing(apiUrl, useBatchProcessor = false, getUserContext = null) {
  setLogApiUrl(apiUrl);
  const exporter = new AnosysHttpExporter({
    getUserContext,
    acceptsSpan: (name) => name === CLAUDE_AGENTS_SCOPE,
    extract: extractSpanInfo,
    getLevel: () => _runSettings.level ?? currentAppLevel().level,
  });
  const provider = addSpanProcessor(createSpanProcessor(exporter, useBatchProcessor));
  _tracer = provider.getTracer(CLAUDE_AGENTS_SCOPE);
  log.info('AnoSys instrumented the Claude Agent SDK');
  return provider;
}

// ── run tracing ───────────────────────────────────────────────────────────────

/**
 * Trace one agent run from the messages it yields, re-yielding each message.
 * Use it for entry points that `wrapQuery` does not cover.
 *
 * @param {AsyncIterable} messages
 * @param {object} [run]  { prompt, options }
 */
export async function* traceMessages(messages, { prompt = null, options = null } = {}) {
  if (!_tracer) {
    yield* messages;
    return;
  }
  const run = new AgentRunTracer(_tracer, {
    prompt,
    options,
    agentName: _runSettings.agentName,
    captureContent: _runSettings.captureContent,
    emitLlmSpans: _runSettings.emitLlmSpans,
  });
  const iterator = messages[Symbol.asyncIterator]();
  // The run span is active while the SDK works, so work it starts joins the trace
  const runContext = trace.setSpan(context.active(), run.root);
  let error = null;
  let done = false;
  try {
    while (true) {
      const step = await context.with(runContext, () => iterator.next());
      if (step.done) { done = true; break; }
      run.onMessage(step.value);
      yield step.value;
    }
  } catch (e) {
    error = e;
    throw e;
  } finally {
    run.finish(error);
    // Stop the SDK's stream too when the caller stops early
    if (!done && typeof iterator.return === 'function') {
      try { await iterator.return(); } catch { /* already closed */ }
    }
  }
}

/**
 * Wrap the Agent SDK's `query()` so that each call is traced. The returned
 * Query keeps every method of the original (interrupt, setPermissionMode, ...).
 *
 *   import { query } from '@anthropic-ai/claude-agent-sdk';
 *   const tracedQuery = wrapQuery(query);
 */
export function wrapQuery(queryFn) {
  if (queryFn.__anosysWrapped) return queryFn;
  const traced = function tracedQuery(params) {
    const q = queryFn(params);
    const stream = traceMessages(q, { prompt: params?.prompt, options: params?.options });
    return new Proxy(q, {
      get(target, prop) {
        if (prop === Symbol.asyncIterator) return () => stream;
        if (prop === 'next' || prop === 'return' || prop === 'throw') return stream[prop].bind(stream);
        const value = Reflect.get(target, prop, target);
        return typeof value === 'function' ? value.bind(target) : value;
      },
    });
  };
  traced.__anosysWrapped = true;
  return traced;
}

export class AnosysClaudeAgentsLogger {
  /**
   * @param {object}   [opts]
   * @param {Function} [opts.getUserContext]      Returns { session_id, token }
   * @param {string}   [opts.agentName]           gen_ai.agent.name (default "claude_agent")
   * @param {boolean}  [opts.captureContent] true: record prompts, results and tool input/output;
   *   false: metadata only. Omitted: follow ANOSYS_COLLECTION_LEVEL and a project `.anosys`
   *   file; full otherwise.
   * @param {boolean}  [opts.emitLlmSpans=false]  Also emit one chat span per assistant response.
   *   Usage totals stay on the agent span; chat spans carry per-call usage.
   * @param {boolean}  [opts.useBatchProcessor=false]
   */
  constructor({
    getUserContext = null,
    agentName = null,
    captureContent = null,
    emitLlmSpans = false,
    useBatchProcessor = false,
  } = {}) {
    this.getUserContext = getUserContext;
    const { level, source } = resolveAppLevel(captureContent);
    this.captureLevel = level;
    log.info('AnoSys Claude Agents collection level: %s (%s)', level, source);
    Object.assign(_runSettings, { level, captureContent: level === FULL, emitLlmSpans, agentName });
    if (level === OFF) {
      this.ready = Promise.resolve();
    } else if (!_tracingInitialized) {
      _tracingInitialized = true;
      setupTracing(resolveApiKey(), useBatchProcessor, this.getUserContext);
      this.ready = this._init();
    } else {
      this.ready = Promise.resolve();
    }
  }

  async _init() {
    this.logApiUrl = await setLogApiUrl(resolveApiKey());
    await setupApi({ path: this.logApiUrl });
  }

  /** Same as the module-level `wrapQuery`. */
  wrapQuery(queryFn) {
    return wrapQuery(queryFn);
  }

  /** Same as the module-level `traceMessages`. */
  traceMessages(messages, run) {
    return traceMessages(messages, run);
  }
}
