// Package × level matrix for the JS application SDKs, on real OpenTelemetry spans:
// off sends nothing, metadata sends no content, full sends content with a truthful
// cvs198 label, everything goes through the core sender, nothing sensitive is logged.
import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';

import { BasicTracerProvider, InMemorySpanExporter, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { setSenderPostForTests, flushAppRecords } from '../src/sender.js';

const SECRET = 'my secret prompt sk-proj-ABCDEFGHIJKLMNOPQRSTUVWX';
const ATTRS = {
  'gen_ai.system': 'openai',
  'gen_ai.request.model': 'gpt-5',
  'gen_ai.usage.input_tokens': 12,
  'gen_ai.usage.output_tokens': 4,
  'gen_ai.input.messages': JSON.stringify([{ role: 'user', content: SECRET }]),
  'gen_ai.output.messages': JSON.stringify([{ role: 'assistant', content: 'the answer' }]),
  'llm.input': SECRET,
};

function makeSpans(scopeName = 'test', name = 'chat gpt-5', attrs = ATTRS) {
  const memory = new InMemorySpanExporter();
  const provider = new BasicTracerProvider({ spanProcessors: [new SimpleSpanProcessor(memory)] });
  const span = provider.getTracer(scopeName).startSpan(name, { attributes: attrs });
  span.end();
  return memory.getFinishedSpans();
}

async function loadPackage(name) {
  try { return await import(name); } catch { return null; }
}

const posted = [];
const logged = [];
const consoleSaved = {};

before(() => {
  setSenderPostForTests(async (url, body) => { posted.push(body); return { status: 200 }; });
  for (const k of ['log', 'info', 'warn', 'error', 'debug']) {
    consoleSaved[k] = console[k];
    console[k] = (...a) => logged.push(a.map(String).join(' '));
  }
  process.env.ANOSYS_LOG_LEVEL = 'debug';
});

after(() => {
  Object.assign(console, consoleSaved);
  setSenderPostForTests(null);
  process.env.ANOSYS_LOG_LEVEL = 'silent';
});

async function exportWith(Exporter, level, spans, extraOpts = {}, ctorStyle = 'positional') {
  posted.length = 0;
  const opts = { getLevel: () => level, getUrl: () => 'https://ingest.example', ...extraOpts };
  const exporter = ctorStyle === 'object' ? new Exporter(opts) : new Exporter(null, opts);
  await new Promise((resolve) => exporter.export(spans, resolve));
  await flushAppRecords(2000);
  return [...posted];
}

const CASES = [
  { pkg: 'anosys-sdk-openai', vendor: 'OpenAI', style: 'positional', spans: () => makeSpans() },
  {
    pkg: 'anosys-sdk-openai', vendor: 'OpenRouter via OpenAI SDK', style: 'positional',
    spans: () => makeSpans('test', 'chat openrouter', { ...ATTRS, 'server.address': 'openrouter.ai', 'gen_ai.request.model': 'anthropic/claude-sonnet-5-5' }),
  },
  { pkg: 'anosys-sdk-openai-agents', vendor: 'OpenAI Agents (OTel path)', style: 'positional', spans: () => makeSpans('openai-agents') },
  {
    pkg: 'anosys-sdk-anthropic', vendor: 'Anthropic', style: 'object',
    spans: () => makeSpans('anthropic', 'chat claude', { ...ATTRS, 'gen_ai.system': 'anthropic', 'gen_ai.provider.name': 'anthropic' }),
    opts: { acceptsSpan: () => true },
  },
];

describe('JS application SDK matrix', () => {
  for (const c of CASES) {
    describe(c.vendor, () => {
      it('off sends nothing', async (t) => {
        const mod = await loadPackage(c.pkg);
        if (!mod?.AnosysHttpExporter) return t.skip(`${c.pkg} not installed`);
        assert.equal((await exportWith(mod.AnosysHttpExporter, 'off', c.spans(), c.opts, c.style)).length, 0);
      });

      it('metadata sends ids, models and numbers but no content', async (t) => {
        const mod = await loadPackage(c.pkg);
        if (!mod?.AnosysHttpExporter) return t.skip(`${c.pkg} not installed`);
        const [rec] = await exportWith(mod.AnosysHttpExporter, 'metadata', c.spans(), c.opts, c.style);
        assert.ok(rec, 'a record was sent');
        assert.equal(rec.cvs198, 'metadata;app');
        const body = JSON.stringify(rec);
        assert.ok(!body.includes('secret prompt') && !body.includes('the answer') && !body.includes('sk-proj'));
        assert.ok(typeof rec.cvn1 === 'number' && rec.otel_trace_id, 'timing and ids kept');
        assert.ok(rec.gen_ai_request_model, 'model kept');
      });

      it('full sends content, labelled as the developer\'s choice', async (t) => {
        const mod = await loadPackage(c.pkg);
        if (!mod?.AnosysHttpExporter) return t.skip(`${c.pkg} not installed`);
        const [rec] = await exportWith(mod.AnosysHttpExporter, 'full', c.spans(), c.opts, c.style);
        assert.equal(rec.cvs198, 'full;app');
        assert.ok(JSON.stringify(rec).includes('secret prompt'));
        assert.equal(Object.keys(rec).filter((k) => k === 'cvs198' || k === 'consent').length, 1);
      });

      it('full with a key encrypts content (enc2)', async (t) => {
        const mod = await loadPackage(c.pkg);
        if (!mod?.AnosysHttpExporter) return t.skip(`${c.pkg} not installed`);
        process.env.ANOSYS_ENCRYPTION_KEY = 'pass';
        process.env.ANOSYS_ENCRYPTION_SALT = 'ws';
        try {
          const [rec] = await exportWith(mod.AnosysHttpExporter, 'full', c.spans(), c.opts, c.style);
          const body = JSON.stringify(rec);
          assert.ok(body.includes('enc2:'));
          assert.ok(!body.includes('secret prompt'));
        } finally {
          delete process.env.ANOSYS_ENCRYPTION_KEY;
          delete process.env.ANOSYS_ENCRYPTION_SALT;
        }
      });
    });
  }

  describe('decorators (anosysLogger / anosysRawLogger)', () => {
    for (const [level, expectContent] of [['metadata', false], ['full', true], ['off', null]]) {
      it(`${level}`, async () => {
        const { createDecorators } = await import('../src/decorators.js');
        process.env.ANOSYS_COLLECTION_LEVEL = level;
        const d = createDecorators();
        await d.setupApi({ path: 'https://ingest.example' });
        posted.length = 0;
        const fn = d.anosysLogger('unit')(async (q) => `answer to ${q}`);
        assert.equal(await fn(SECRET), `answer to ${SECRET}`); // the result is never changed or delayed
        await d.anosysRawLogger({ note: SECRET, count: 3 });
        await flushAppRecords(2000);
        delete process.env.ANOSYS_COLLECTION_LEVEL;
        if (expectContent === null) return assert.equal(posted.length, 0);
        assert.equal(posted.length, 2);
        assert.ok(posted.every((r) => r.cvs198 === `${level};app`));
        assert.equal(JSON.stringify(posted).includes('secret prompt'), expectContent);
      });
    }
  });

  it('no prompt, answer or key appeared in any log line', () => {
    const all = logged.join('\n');
    assert.ok(!all.includes('secret prompt') && !all.includes('the answer') && !all.includes('sk-proj'));
  });
});
