import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import {
  BASE_KEY_MAPPING,
  CLAUDE_KEY_MAPPING,
  CLAUDE_STARTING_INDICES,
  ANTHROPIC_KEY_MAPPING,
} from '../src/mapping.js';
import { extractGenAiSpanInfo, flattenMessages, spanToJson } from '../src/genai.js';
import { extractSpanInfo, isAnthropicSpan, ANTHROPIC_SOURCE } from '../src/hooks.js';
import { AnosysHttpExporter } from '../src/instrumentor.js';

function span(attributes, { name = 'anthropic.messages.create', status = 'OK' } = {}) {
  return {
    name,
    context: { trace_id: '0xabc', span_id: '0xdef', trace_state: '[]' },
    kind: 'SpanKind.CLIENT',
    parent_id: null,
    start_time: '2026-10-29T10:00:00.000Z',
    end_time: '2026-10-29T10:00:01.500Z',
    status: { status_code: status },
    attributes,
    events: [],
    links: [],
    resource: { attributes: { 'service.name': 'svc' }, schema_url: '' },
  };
}

const CHAT_ATTRS = {
  'gen_ai.provider.name': 'anthropic',
  'gen_ai.operation.name': 'chat',
  'gen_ai.request.model': 'claude-sonnet-4-5',
  'gen_ai.request.max_tokens': 100,
  'gen_ai.response.id': 'msg_1',
  'anthropic.message.stop_reason': 'end_turn',
  'gen_ai.usage.input_tokens': 132,
  'gen_ai.usage.output_tokens': 7,
  'gen_ai.usage.cache_read.input_tokens': 100,
  'gen_ai.usage.cache_write.input_tokens': 20,
  'gen_ai.system_instructions': JSON.stringify([{ type: 'text', content: 'Be terse.' }]),
  'gen_ai.input.messages': JSON.stringify([{ role: 'user', parts: [{ type: 'text', content: 'Hi' }] }]),
  'gen_ai.output.messages': JSON.stringify([{ role: 'assistant', parts: [
    { type: 'reasoning', content: 'hmm' }, { type: 'text', content: 'Hello!' },
  ] }]),
};

describe('mapping', () => {
  it('Claude mapping extends the base mapping without changing it', () => {
    for (const [key, column] of Object.entries(BASE_KEY_MAPPING)) assert.equal(CLAUDE_KEY_MAPPING[key], column);
    assert.equal(CLAUDE_KEY_MAPPING['gen_ai.usage.cache_read.input_tokens'], 'cvn4');
    assert.equal(CLAUDE_KEY_MAPPING['gen_ai.usage.cache_creation.input_tokens'], 'cvn5');
    assert.equal(CLAUDE_KEY_MAPPING['gen_ai.usage.cost'], 'cvn7');
    assert.equal(CLAUDE_KEY_MAPPING.has_thinking, 'cvb3');
    assert.deepEqual(ANTHROPIC_KEY_MAPPING, CLAUDE_KEY_MAPPING);
  });

  it('base mapping matches Python (service.name, attributes, gen_ai.span.kind)', () => {
    assert.equal(BASE_KEY_MAPPING['service.name'], 'cvs17');
    assert.equal(BASE_KEY_MAPPING.attributes, 'cvs18');
    assert.equal(BASE_KEY_MAPPING['gen_ai.span.kind'], 'cvs19');
  });

  it('dynamic slots start above the fixed Claude slots', () => {
    assert.ok(CLAUDE_STARTING_INDICES.number > 7);
    assert.ok(CLAUDE_STARTING_INDICES.bool > 3);
  });
});

describe('extractGenAiSpanInfo', () => {
  it('maps base fields', () => {
    const out = extractSpanInfo(span(CHAT_ATTRS));
    assert.equal(out.cvs200, 'AnthropicTelemetry');
    assert.equal(ANTHROPIC_SOURCE, 'AnthropicTelemetry');
    assert.equal(out.otel_duration_ms, 1500);
    assert.equal(out.otel_status_code, 'OK');
    assert.equal(out.gen_ai_system, 'anthropic');
    assert.equal(out.cvs19, 'LLM');
    assert.deepEqual(JSON.parse(out.gen_ai_response_finish_reasons), ['end_turn']);
    assert.equal(out.otel_status_message, 'msg_1');
  });

  it('normalises usage into the cache slots', () => {
    const out = extractSpanInfo(span(CHAT_ATTRS));
    assert.equal(out.gen_ai_usage_input_tokens, 132);
    assert.equal(out.gen_ai_usage_total_tokens, 139);
    assert.equal(out.cvn4, 100);
    assert.equal(out.cvn5, 20);
  });

  it('flattens content and flags thinking', () => {
    const out = extractSpanInfo(span(CHAT_ATTRS));
    assert.equal(out.llm_input, 'System: Be terse.\n\nUser: Hi');
    assert.equal(out.llm_output, 'Assistant: [Thinking] hmm\nHello!');
    assert.equal(out.cvb3, true);
  });

  it('tool spans use arguments and result', () => {
    const out = extractGenAiSpanInfo(span({
      'gen_ai.operation.name': 'execute_tool',
      'gen_ai.tool.call.arguments': JSON.stringify({ command: 'ls' }),
      'gen_ai.tool.call.result': 'a.txt',
    }, { name: 'execute_tool Bash' }), { fromSource: 'ClaudeAgentsTelemetry' });
    assert.equal(out.cvs19, 'TOOL');
    assert.deepEqual(JSON.parse(out.llm_input), { command: 'ls' });
    assert.equal(out.llm_output, 'a.txt');
  });

  it('flattenMessages handles both shapes', () => {
    assert.equal(flattenMessages(null), null);
    assert.equal(flattenMessages([{ role: 'user', content: 'Hello' }]), 'User: Hello');
    assert.equal(
      flattenMessages([{ role: 'assistant', parts: [{ type: 'tool_call', name: 'get_weather', arguments: { city: 'Paris' } }] }]),
      'Assistant: [Tool Call: get_weather] {"city":"Paris"}',
    );
  });
});

describe('spanToJson', () => {
  it('converts a ReadableSpan to the Python to_json shape', () => {
    const json = spanToJson({
      name: 'x',
      spanContext: () => ({ traceId: 'aa', spanId: 'bb' }),
      parentSpanContext: { spanId: 'cc' },
      kind: 2,
      startTime: [1793268000, 0],
      endTime: [1793268001, 500000000],
      status: { code: 2, message: 'boom' },
      attributes: { a: 1 },
      events: [],
      resource: { attributes: { 'service.name': 'svc' } },
    });
    assert.equal(json.context.trace_id, '0xaa');
    assert.equal(json.parent_id, '0xcc');
    assert.equal(json.kind, 'SpanKind.CLIENT');
    assert.deepEqual(json.status, { status_code: 'ERROR', description: 'boom' });
    assert.equal(new Date(json.end_time) - new Date(json.start_time), 1500);
  });
});

describe('isAnthropicSpan', () => {
  it('accepts SDK spans and application GenAI spans only', () => {
    assert.equal(isAnthropicSpan('com.anthropic.sdk.typescript'), true);
    assert.equal(isAnthropicSpan('@opentelemetry/instrumentation-http'), false);
    assert.equal(isAnthropicSpan('my.app', { 'gen_ai.operation.name': 'execute_tool' }), true);
    assert.equal(isAnthropicSpan('anosys.claude_agents', { 'gen_ai.operation.name': 'execute_tool' }), false);
  });
});

describe('AnosysHttpExporter', () => {
  it('skips spans of other instrumentation scopes', async () => {
    let extracted = 0;
    const exporter = new AnosysHttpExporter({ extract: () => { extracted++; return {}; } });
    let result;
    await exporter.export([{ name: 'other', instrumentationScope: { name: 'openai' } }], (r) => { result = r; });
    assert.equal(extracted, 0);
    assert.equal(result.code, 0);
  });
});
