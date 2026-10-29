import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';

import { BasicTracerProvider, InMemorySpanExporter, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { spanToJson } from 'anosys-sdk-anthropic';

import { AgentRunTracer } from '../src/tracer.js';
import { extractSpanInfo } from '../src/hooks.js';
import { wrapQuery } from '../src/instrumentor.js';
import { CLAUDE_AGENTS_SCOPE, CLAUDE_AGENTS_SOURCE } from '../src/mapping.js';

const WIRE_RUN = [
  { type: 'system', subtype: 'init', session_id: 'sess-1', model: 'claude-opus-4-5', tools: ['Bash', 'Task'] },
  { type: 'assistant', parent_tool_use_id: null, message: {
    id: 'm1', model: 'claude-opus-4-5', stop_reason: 'tool_use', usage: { input_tokens: 5, output_tokens: 3 },
    content: [
      { type: 'thinking', thinking: 'plan' },
      { type: 'tool_use', id: 'tu1', name: 'Task', input: { subagent_type: 'explorer', description: 'look' } },
    ] } },
  { type: 'assistant', parent_tool_use_id: 'tu1', message: {
    id: 'm2', model: 'claude-haiku-4-5', content: [{ type: 'tool_use', id: 'tu2', name: 'Bash', input: { command: 'ls' } }] } },
  { type: 'user', parent_tool_use_id: 'tu1', message: { content: [
    { type: 'tool_result', tool_use_id: 'tu2', content: 'a.txt', is_error: false }] } },
  { type: 'user', message: { content: [
    { type: 'tool_result', tool_use_id: 'tu1', content: [{ type: 'text', text: 'found a.txt' }] }] } },
  { type: 'result', subtype: 'success', is_error: false, num_turns: 2, session_id: 'sess-1',
    stop_reason: 'end_turn', total_cost_usd: 0.01, result: 'Done',
    usage: { input_tokens: 10, cache_read_input_tokens: 200, cache_creation_input_tokens: 50, output_tokens: 40 } },
];

let exporter;
let tracer;

beforeEach(() => {
  exporter = new InMemorySpanExporter();
  const provider = new BasicTracerProvider({ spanProcessors: [new SimpleSpanProcessor(exporter)] });
  tracer = provider.getTracer(CLAUDE_AGENTS_SCOPE);
});

function run(messages, opts = {}) {
  const t = new AgentRunTracer(tracer, { prompt: 'List files', options: { model: 'claude-opus-4-5' }, ...opts });
  for (const m of messages) t.onMessage(m);
  t.finish();
  return Object.fromEntries(exporter.getFinishedSpans().map(s => [s.name, s]));
}

describe('AgentRunTracer', () => {
  it('builds the agent / tool / subagent tree', () => {
    const spans = run(WIRE_RUN);
    const root = spans['invoke_agent claude_agent'];
    const task = spans['execute_tool Task'];
    const bash = spans['execute_tool Bash'];
    assert.equal(task.parentSpanContext.spanId, root.spanContext().spanId);
    assert.equal(bash.parentSpanContext.spanId, task.spanContext().spanId);
    assert.equal(task.attributes['gen_ai.agent.name'], 'explorer');
    assert.equal(bash.attributes['gen_ai.tool.call.result'], 'a.txt');
    assert.equal(task.attributes['gen_ai.tool.call.result'], 'found a.txt');
  });

  it('puts usage, cost and session on the root', () => {
    const attrs = run(WIRE_RUN)['invoke_agent claude_agent'].attributes;
    assert.equal(attrs['gen_ai.conversation.id'], 'sess-1');
    assert.equal(attrs['gen_ai.usage.input_tokens'], 260);
    assert.equal(attrs['gen_ai.usage.cache_read.input_tokens'], 200);
    assert.equal(attrs['gen_ai.usage.cost'], 0.01);
  });

  it('emits chat spans only when asked', () => {
    assert.ok(!Object.keys(run(WIRE_RUN)).some(n => n.startsWith('chat')));
    exporter.reset();
    const spans = run(WIRE_RUN, { emitLlmSpans: true });
    assert.equal(spans['chat claude-opus-4-5'].attributes['gen_ai.usage.output_tokens'], 3);
  });

  it('records no content when captureContent is off', () => {
    for (const span of Object.values(run(WIRE_RUN, { captureContent: false }))) {
      assert.equal(span.attributes['gen_ai.input.messages'], undefined);
      assert.equal(span.attributes['gen_ai.tool.call.arguments'], undefined);
    }
  });

  it('extracts agent spans with the Claude slots', () => {
    const out = extractSpanInfo(spanToJson(run(WIRE_RUN)['invoke_agent claude_agent']));
    assert.equal(out.cvs200, CLAUDE_AGENTS_SOURCE);
    assert.equal(CLAUDE_AGENTS_SOURCE, 'ClaudeAgentsTelemetry');
    assert.equal(out.cvs19, 'AGENT');
    assert.equal(out.cvn4, 200);
    assert.equal(out.cvn7, 0.01);
  });
});

describe('wrapQuery', () => {
  it('passes messages and Query methods through', async () => {
    const fakeQuery = () => {
      const gen = (async function* () { for (const m of WIRE_RUN) yield m; })();
      gen.interrupt = async () => 'interrupted';
      return gen;
    };
    const q = wrapQuery(fakeQuery)({ prompt: 'hi' });
    assert.equal(await q.interrupt(), 'interrupted');
    const seen = [];
    for await (const m of q) seen.push(m);
    assert.deepEqual(seen, WIRE_RUN);
  });

  it('is idempotent', () => {
    const wrapped = wrapQuery(() => (async function* () {})());
    assert.equal(wrapQuery(wrapped), wrapped);
  });
});
