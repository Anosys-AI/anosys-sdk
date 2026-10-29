/**
 * Span builder for Claude Agent SDK runs — JS port of Python
 * `anosys_sdk_claude_agents/tracer.py`; both emit the same spans and attributes.
 *
 * The Agent SDK runs the model inside a Claude Code subprocess, so no in-process
 * instrumentor can see the API calls. AgentRunTracer reads the message stream a
 * run yields and turns it into OpenTelemetry GenAI semantic-convention spans:
 *
 * - one `invoke_agent` span per run (root): session id, model, prompt, final
 *   result, total usage and cost;
 * - one `execute_tool` span per tool call, from the assistant's `tool_use` block
 *   to the matching `tool_result`; calls made by a subagent nest under the
 *   `Task`/`Agent` tool span that launched it;
 * - optionally one `chat` span per assistant API response.
 */

import { context, trace, SpanKind, SpanStatusCode } from '@opentelemetry/api';

export const PROVIDER = 'anthropic';
export const DEFAULT_AGENT_NAME = 'claude_agent';
const SUBAGENT_TOOLS = ['Task', 'Agent'];

function contextWith(span) {
  return trace.setSpan(context.active(), span);
}

function setAttributes(span, attributes) {
  for (const [key, value] of Object.entries(attributes)) {
    if (value === null || value === undefined) continue;
    span.setAttribute(key, typeof value === 'object' ? JSON.stringify(value) : value);
  }
}

function messageContent(msg) {
  const content = msg?.message ? msg.message.content : msg?.content;
  if (typeof content === 'string') return [{ type: 'text', text: content }];
  return Array.isArray(content) ? content : [];
}

function systemField(msg, key) {
  return msg?.[key] ?? msg?.data?.[key];
}

function toolResultText(content) {
  if (Array.isArray(content)) {
    const texts = content.map(b => b?.text).filter(Boolean);
    if (texts.length) return texts.join('\n');
  }
  return content;
}

/**
 * GenAI usage attributes from an Anthropic usage object. `gen_ai.usage.input_tokens`
 * is the full prompt (uncached + cache reads + cache writes), like OpenAI prompt tokens.
 */
function usageAttributes(usage) {
  if (!usage) return {};
  const uncached = usage.input_tokens ?? 0;
  const cacheRead = usage.cache_read_input_tokens ?? 0;
  const cacheCreation = usage.cache_creation_input_tokens ?? 0;
  return {
    'gen_ai.usage.input_tokens': uncached + cacheRead + cacheCreation,
    'gen_ai.usage.output_tokens': usage.output_tokens ?? 0,
    'gen_ai.usage.cache_read.input_tokens': cacheRead,
    'gen_ai.usage.cache_creation.input_tokens': cacheCreation,
  };
}

function outputParts(blocks) {
  const parts = [];
  for (const block of blocks) {
    if (block?.type === 'text' && block.text) parts.push({ type: 'text', content: block.text });
    else if (block?.type === 'thinking' && block.thinking) parts.push({ type: 'reasoning', content: block.thinking });
    else if (block?.type === 'tool_use') {
      parts.push({ type: 'tool_call', id: block.id, name: block.name, arguments: block.input });
    }
  }
  return parts;
}

export class AgentRunTracer {
  constructor(tracer, {
    prompt = null,
    options = null,
    agentName = null,
    captureContent = true,
    emitLlmSpans = false,
  } = {}) {
    this._tracer = tracer;
    this._captureContent = captureContent;
    this._emitLlmSpans = emitLlmSpans;
    this._toolSpans = new Map();
    this._llmMessageIds = new Set();
    this._lastText = null;
    this._model = options?.model ?? null;
    this._sessionId = null;
    this._finished = false;

    this.agentName = agentName || DEFAULT_AGENT_NAME;
    this.root = tracer.startSpan(`invoke_agent ${this.agentName}`, { kind: SpanKind.INTERNAL });
    setAttributes(this.root, {
      'gen_ai.operation.name': 'invoke_agent',
      'gen_ai.provider.name': PROVIDER,
      'gen_ai.agent.name': this.agentName,
      'gen_ai.request.model': this._model,
      'anthropic.agent.permission_mode': options?.permissionMode ?? options?.permission_mode,
      'anthropic.agent.max_turns': options?.maxTurns ?? options?.max_turns,
    });
    if (captureContent) {
      const systemPrompt = options?.systemPrompt ?? options?.system_prompt;
      if (typeof systemPrompt === 'string') {
        setAttributes(this.root, { 'gen_ai.system_instructions': [{ type: 'text', content: systemPrompt }] });
      }
      if (typeof prompt === 'string') {
        setAttributes(this.root, {
          'gen_ai.input.messages': [{ role: 'user', parts: [{ type: 'text', content: prompt }] }],
        });
      }
    }
  }

  // ── message handling ──────────────────────────────────────────────────────

  /** Update spans for one message of the run. Never throws. */
  onMessage(msg) {
    try {
      switch (msg?.type) {
        case 'system': this._onSystem(msg); break;
        case 'assistant': this._onAssistant(msg); break;
        case 'user': this._onUser(msg); break;
        case 'result': this._onResult(msg); break;
        default: break;
      }
    } catch { /* telemetry must never break the agent run */ }
  }

  _onSystem(msg) {
    if (msg.subtype !== 'init') return;
    const sessionId = systemField(msg, 'session_id');
    const model = systemField(msg, 'model');
    const tools = systemField(msg, 'tools');
    if (model && !this._model) this._model = model;
    this._sessionId = sessionId ?? this._sessionId;
    setAttributes(this.root, {
      'gen_ai.conversation.id': sessionId,
      'gen_ai.request.model': this._model,
      'anthropic.agent.claude_code_version': systemField(msg, 'claude_code_version'),
    });
    if (Array.isArray(tools) && tools.length) {
      setAttributes(this.root, {
        'gen_ai.tool.definitions': tools.map(t => ({ type: 'function', name: typeof t === 'string' ? t : t?.name })),
      });
    }
  }

  /** The span a message belongs under: the subagent's tool span, else the root. */
  _parentSpan(parentToolUseId) {
    if (parentToolUseId && this._toolSpans.has(parentToolUseId)) return this._toolSpans.get(parentToolUseId);
    return this.root;
  }

  _onAssistant(msg) {
    const blocks = messageContent(msg);
    const inner = msg.message;
    const parent = this._parentSpan(msg.parent_tool_use_id);
    const model = msg.model ?? inner?.model;
    if (model) setAttributes(this.root, { 'gen_ai.response.model': model });

    const texts = blocks.filter(b => b?.type === 'text' && b.text).map(b => b.text);
    if (texts.length && !msg.parent_tool_use_id) this._lastText = texts.join('\n');

    if (this._emitLlmSpans) this._emitLlmSpan(msg, inner, blocks, parent, model);

    for (const block of blocks) {
      if (block?.type === 'tool_use') this._startToolSpan(block, parent);
    }
  }

  _emitLlmSpan(msg, inner, blocks, parent, model) {
    const messageId = msg.message_id ?? inner?.id;
    // The SDK may split one API response into several messages; record it once
    if (messageId && this._llmMessageIds.has(messageId)) return;
    if (messageId) this._llmMessageIds.add(messageId);
    const span = this._tracer.startSpan(
      `chat ${model ?? ''}`.trim(),
      { kind: SpanKind.CLIENT },
      contextWith(parent),
    );
    const stopReason = msg.stop_reason ?? inner?.stop_reason;
    setAttributes(span, {
      'gen_ai.operation.name': 'chat',
      'gen_ai.provider.name': PROVIDER,
      'gen_ai.request.model': model,
      'gen_ai.response.model': model,
      'gen_ai.response.id': messageId,
      'gen_ai.response.finish_reasons': stopReason ? [stopReason] : null,
      ...usageAttributes(msg.usage ?? inner?.usage),
    });
    if (this._captureContent) {
      setAttributes(span, { 'gen_ai.output.messages': [{ role: 'assistant', parts: outputParts(blocks) }] });
    }
    span.end();
  }

  _startToolSpan(block, parent) {
    const toolUseId = block.id;
    const name = block.name || 'unknown_tool';
    const toolInput = block.input;
    const span = this._tracer.startSpan(
      `execute_tool ${name}`,
      { kind: SpanKind.INTERNAL },
      contextWith(parent),
    );
    const attributes = {
      'gen_ai.operation.name': 'execute_tool',
      'gen_ai.provider.name': PROVIDER,
      'gen_ai.tool.name': name,
      'gen_ai.tool.call.id': toolUseId,
      'gen_ai.tool.type': name.startsWith('mcp__') ? 'extension' : 'function',
      'gen_ai.conversation.id': this._sessionId,
    };
    if (SUBAGENT_TOOLS.includes(name) && toolInput && typeof toolInput === 'object') {
      attributes['gen_ai.agent.name'] = toolInput.subagent_type;
      attributes['gen_ai.agent.description'] = toolInput.description;
    }
    if (this._captureContent && toolInput !== undefined && toolInput !== null) {
      attributes['gen_ai.tool.call.arguments'] = toolInput;
    }
    setAttributes(span, attributes);
    if (toolUseId) this._toolSpans.set(toolUseId, span);
    else span.end();
  }

  _onUser(msg) {
    for (const block of messageContent(msg)) {
      if (block?.type !== 'tool_result') continue;
      const span = this._toolSpans.get(block.tool_use_id);
      if (!span) continue;
      this._toolSpans.delete(block.tool_use_id);
      const content = toolResultText(block.content);
      if (this._captureContent && content !== undefined && content !== null) {
        setAttributes(span, { 'gen_ai.tool.call.result': content });
      }
      if (block.is_error) {
        setAttributes(span, { 'error.type': 'tool_error' });
        span.setStatus({ code: SpanStatusCode.ERROR, message: content ? String(content).slice(0, 500) : undefined });
      }
      span.end();
    }
  }

  _onResult(msg) {
    const stopReason = msg.stop_reason;
    setAttributes(this.root, {
      'gen_ai.conversation.id': msg.session_id,
      'gen_ai.response.finish_reasons': stopReason ? [stopReason] : null,
      'gen_ai.usage.cost': msg.total_cost_usd,
      'anthropic.agent.num_turns': msg.num_turns,
      'anthropic.agent.duration_api_ms': msg.duration_api_ms,
      'anthropic.agent.result_subtype': msg.subtype,
      ...usageAttributes(msg.usage),
    });
    const result = msg.result;
    if (this._captureContent && (result || this._lastText)) {
      setAttributes(this.root, {
        'gen_ai.output.messages': [{ role: 'assistant', parts: [{ type: 'text', content: result || this._lastText }] }],
      });
    }
    if (msg.is_error) {
      const errors = msg.errors;
      setAttributes(this.root, { 'error.type': msg.subtype || 'agent_error' });
      this.root.setStatus({ code: SpanStatusCode.ERROR, message: errors?.length ? errors.join('; ') : undefined });
    }
  }

  // ── lifecycle ─────────────────────────────────────────────────────────────

  /** Close any open tool spans and the root span. Idempotent. */
  finish(error = null) {
    if (this._finished) return;
    this._finished = true;
    for (const span of this._toolSpans.values()) span.end();
    this._toolSpans.clear();
    if (error) {
      this.root.recordException(error);
      setAttributes(this.root, { 'error.type': error.name || 'Error' });
      this.root.setStatus({ code: SpanStatusCode.ERROR, message: String(error.message ?? error) });
    }
    this.root.end();
  }
}
