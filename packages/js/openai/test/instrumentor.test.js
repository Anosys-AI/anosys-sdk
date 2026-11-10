import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { trace } from '@opentelemetry/api';
import { logs } from '@opentelemetry/api-logs';
import { SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { spanToJson, prepareAppRecord, FULL, METADATA, OFF, setSenderPostForTests, flushAppRecords } from 'anosys-sdk-core';

import { AnosysHttpExporter, setupTracing, AnosysOpenAILogger, patchOpenAI } from '../src/instrumentor.js';
import { extractSpanInfo } from '../src/hooks.js';

describe('OpenAI JS Instrumentation & BridgeLogger (S1 & S1b)', () => {
  let OpenAI;
  let postedRecords = [];

  beforeEach(async () => {
    delete process.env.ANOSYS_COLLECTION_LEVEL;
    delete process.env.ANOSYS_DISABLE;
    delete process.env.ANOSYS_ENCRYPTION_KEY;
    postedRecords = [];
    setSenderPostForTests(async (url, payload) => {
      postedRecords.push(payload);
      return { status: 200 };
    });
    const mod = await import('openai');
    OpenAI = mod.default || mod.OpenAI || mod;
  });

  afterEach(async () => {
    await flushAppRecords();
    setSenderPostForTests(null);
  });

  it('captures prompts and answers at full collection level via BridgeLogger (S1)', async () => {
    let captured = [];
    const customExporter = {
      export(spans, done) {
        captured.push(...spans);
        done({ code: 0 });
      },
      shutdown() { return Promise.resolve(); }
    };

    setupTracing('http://localhost:9999/collect', false, null, FULL, [new SimpleSpanProcessor(customExporter)]);
    patchOpenAI(OpenAI);

    const mockResponse = {
      id: 'chatcmpl-unit-1',
      object: 'chat.completion',
      created: Date.now(),
      model: 'gpt-4o',
      choices: [{
        index: 0,
        message: { role: 'assistant', content: 'Paris is the capital of France.' },
        finish_reason: 'stop'
      }],
      usage: { prompt_tokens: 14, completion_tokens: 8, total_tokens: 22 }
    };

    const client = new OpenAI({
      apiKey: 'dummy-test-key',
      fetch: async () => new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })
    });

    const completion = await client.chat.completions.create({
      model: 'gpt-4o',
      messages: [
        { role: 'system', content: 'You are a helpful geography assistant.' },
        { role: 'user', content: 'What is the capital of France?' }
      ]
    });

    assert.equal(completion.choices[0].message.content, 'Paris is the capital of France.');
    assert.ok(captured.length > 0, 'Should have captured at least 1 span');

    const span = captured[captured.length - 1];
    const spanJson = spanToJson(span);
    const data = extractSpanInfo(spanJson);

    // Verify raw input and output captured on span data
    assert.ok(data.llm_input.includes('capital of France'), `llm_input should contain prompt: ${data.llm_input}`);
    assert.ok(data.llm_output.includes('Paris is the capital'), `llm_output should contain answer: ${data.llm_output}`);
    assert.equal(data.gen_ai_request_model, 'gpt-4o');

    // Full record retains prompt and completion
    const fullRec = prepareAppRecord(data, FULL);
    assert.ok(fullRec.llm_input.includes('capital of France'));
    assert.ok(fullRec.llm_output.includes('Paris is the capital'));
    assert.equal(fullRec.cvs198, 'full;app');

    // Also check sender post records
    await flushAppRecords();
    assert.ok(postedRecords.length > 0, 'AnosysHttpExporter should have posted record');
    const posted = postedRecords[postedRecords.length - 1];
    assert.ok(posted.llm_input.includes('capital of France'));
    assert.ok(posted.llm_output.includes('Paris is the capital'));
  });

  it('does NOT capture prompts/answers and does not emit them to log pipelines at metadata level (S1b)', async () => {
    let captured = [];
    const customExporter = {
      export(spans, done) {
        captured.push(...spans);
        done({ code: 0 });
      },
      shutdown() { return Promise.resolve(); }
    };

    // Initialize with METADATA collection level
    setupTracing('http://localhost:9999/collect', false, null, METADATA, [new SimpleSpanProcessor(customExporter)]);
    patchOpenAI(OpenAI);

    // Track any logs emitted through the OpenTelemetry Logs API
    const receivedLogRecords = [];
    const externalLogger = {
      emit(rec) { receivedLogRecords.push(rec); }
    };
    logs.setGlobalLoggerProvider({
      getLogger() { return externalLogger; }
    });

    const mockResponse = {
      id: 'chatcmpl-unit-2',
      object: 'chat.completion',
      created: Date.now(),
      model: 'gpt-4o',
      choices: [{
        index: 0,
        message: { role: 'assistant', content: 'Secret confidential response 12345' },
        finish_reason: 'stop'
      }],
      usage: { prompt_tokens: 10, completion_tokens: 6, total_tokens: 16 }
    };

    const client = new OpenAI({
      apiKey: 'dummy-test-key',
      fetch: async () => new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      })
    });

    await client.chat.completions.create({
      model: 'gpt-4o',
      messages: [{ role: 'user', content: 'Secret password and user data' }]
    });

    assert.ok(captured.length > 0);
    const span = captured[captured.length - 1];
    const spanJson = spanToJson(span);
    const data = extractSpanInfo(spanJson);

    // Metadata record must completely strip content
    const metaRec = prepareAppRecord(data, METADATA);
    assert.equal(metaRec.llm_input, undefined, 'llm_input must be stripped in metadata record');
    assert.equal(metaRec.llm_output, undefined, 'llm_output must be stripped in metadata record');
    assert.equal(metaRec.gen_ai_request_model, 'gpt-4o');
    assert.equal(metaRec.cvs198, 'metadata;app');

    // S1b: external log pipeline must NOT receive any message content
    for (const rec of receivedLogRecords) {
      assert.equal(rec.body?.content, undefined, 'Log record must not contain prompt content at metadata level');
      assert.equal(rec.body?.message?.content, undefined, 'Log record must not contain choice content at metadata level');
    }

    // Also check sender post records
    await flushAppRecords();
    if (postedRecords.length > 0) {
      const posted = postedRecords[postedRecords.length - 1];
      assert.equal(posted.llm_input, undefined);
      assert.equal(posted.llm_output, undefined);
      assert.equal(posted.gen_ai_request_model, 'gpt-4o');
    }
  });

  it('instruments client instances created before or via explicit patchOpenAI', async () => {
    const client = new OpenAI({
      apiKey: 'dummy-test-key',
      fetch: async () => new Response(JSON.stringify({
        id: 'chatcmpl-unit-3',
        object: 'chat.completion',
        created: Date.now(),
        model: 'gpt-4o-mini',
        choices: [{ index: 0, message: { role: 'assistant', content: 'Explicit client patched!' }, finish_reason: 'stop' }],
        usage: { prompt_tokens: 5, completion_tokens: 4, total_tokens: 9 }
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    });

    patchOpenAI(client);

    let captured = [];
    const customExporter = {
      export(spans, done) { captured.push(...spans); done({ code: 0 }); },
      shutdown() { return Promise.resolve(); }
    };
    setupTracing('http://localhost:9999/collect', false, null, FULL, [new SimpleSpanProcessor(customExporter)]);

    const res = await client.chat.completions.create({
      model: 'gpt-4o-mini',
      messages: [{ role: 'user', content: 'Test explicit client' }]
    });

    assert.equal(res.choices[0].message.content, 'Explicit client patched!');
    assert.ok(captured.length > 0);
    const data = extractSpanInfo(spanToJson(captured[captured.length - 1]));
    assert.equal(data.llm_input, 'Test explicit client');
    assert.equal(data.llm_output, 'Explicit client patched!');
  });
});
