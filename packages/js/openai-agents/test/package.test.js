import { it } from 'node:test';
import assert from 'node:assert/strict';

// Regression: the package entry point failed to load (it re-exported a name the
// processor module does not define), so `import 'anosys-sdk-openai-agents'` threw.
it('the package entry point loads and exports the logger', async () => {
  const mod = await import('../src/index.js');
  assert.equal(typeof mod.AnosysOpenAIAgentsLogger, 'function');
  assert.equal(mod.AnosysOpenAILogger, mod.AnosysOpenAIAgentsLogger);
  assert.equal(typeof mod.AnosysHttpExporter, 'function');
});

it('the OTel extractor keeps GenAI usage and content attributes (audit 4.2)', async () => {
  const { BasicTracerProvider, InMemorySpanExporter, SimpleSpanProcessor } = await import('@opentelemetry/sdk-trace-base');
  const { extractOtelSpanInfo } = await import('../src/mapping.js');
  const memory = new InMemorySpanExporter();
  const provider = new BasicTracerProvider({ spanProcessors: [new SimpleSpanProcessor(memory)] });
  provider.getTracer('openai-agents').startSpan('chat', { attributes: {
    'gen_ai.usage.input_tokens': 12, 'gen_ai.response.model': 'gpt-5', 'input.value': 'question', 'output.value': 'answer',
  } }).end();
  const rec = extractOtelSpanInfo(memory.getFinishedSpans()[0]);
  assert.equal(rec.gen_ai_usage_input_tokens, 12);
  assert.equal(rec.gen_ai_response_model, 'gpt-5');
  assert.equal(rec.llm_input, 'question');
  assert.equal(rec.llm_output, 'answer');
});
