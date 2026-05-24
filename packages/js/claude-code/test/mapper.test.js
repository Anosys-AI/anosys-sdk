'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');

const { transformRecord, toUnixMs, calculateCost, INTEGRATION_VERSION } = require('../src/mapper');

// ---------------------------------------------------------------------------
// toUnixMs
// ---------------------------------------------------------------------------

describe('mapper.toUnixMs', () => {
  it('converts a valid ISO Z string to ms', () => {
    const ms = toUnixMs('2024-01-15T12:00:00Z');
    assert.ok(typeof ms === 'number' && ms > 0);
    assert.ok(ms > 1_700_000_000_000); // sanity — after 2023
  });

  it('returns current time for invalid input', () => {
    const before = Date.now();
    const ms = toUnixMs('not-a-date');
    const after = Date.now();
    assert.ok(ms >= before && ms <= after);
  });

  it('returns current time for null/undefined', () => {
    const ms = toUnixMs(null);
    assert.ok(typeof ms === 'number' && ms > 0);
  });
});

// ---------------------------------------------------------------------------
// calculateCost
// ---------------------------------------------------------------------------

describe('mapper.calculateCost', () => {
  it('returns null for missing model', () => {
    assert.equal(calculateCost(null, { input_tokens: 100 }), null);
  });

  it('returns null for missing usage', () => {
    assert.equal(calculateCost('claude-sonnet-4-6', null), null);
  });

  it('calculates basic cost for claude-sonnet-4-6', () => {
    const cost = calculateCost('claude-sonnet-4-6', {
      input_tokens: 1000,
      output_tokens: 500,
    });
    assert.ok(typeof cost === 'number' && cost > 0);
    // 1000 * 3.0/1e6 + 500 * 15.0/1e6 = 0.003 + 0.0075 = 0.0105
    assert.ok(Math.abs(cost - 0.0105) < 0.0001);
  });

  it('falls back to default model pricing for unknown model', () => {
    const cost = calculateCost('unknown-model', { input_tokens: 100, output_tokens: 50 });
    assert.ok(typeof cost === 'number' && cost > 0);
  });

  it('handles nested cache_creation object', () => {
    const cost = calculateCost('claude-sonnet-4-6', {
      input_tokens: 100,
      output_tokens: 50,
      cache_creation: { ephemeral_1h_input_tokens: 200, ephemeral_5m_input_tokens: 100 },
    });
    assert.ok(typeof cost === 'number' && cost > 0);
  });
});

// ---------------------------------------------------------------------------
// transformRecord — user messages
// ---------------------------------------------------------------------------

describe('mapper.transformRecord — user messages', () => {
  it('extracts user_prompt from string content', () => {
    const r = {
      type: 'user',
      uuid: 'uuid-1',
      sessionId: 'sess-1',
      timestamp: '2024-01-15T12:00:00Z',
      message: { content: 'Hello Claude' },
    };
    const p = transformRecord(r);
    assert.equal(p.event_type, 'claude_code_user');
    assert.equal(p.user_prompt, 'Hello Claude');
    assert.equal(p.event_id, 'uuid-1');
    assert.equal(p.session_id, 'sess-1');
    assert.equal(p.cvs200, 'ClaudeCodeHook');
  });

  it('extracts user_prompt from list content', () => {
    const r = {
      type: 'user',
      uuid: 'uuid-2',
      sessionId: 'sess-1',
      timestamp: '2024-01-15T12:00:00Z',
      message: {
        content: [
          { type: 'text', text: 'Hello' },
          { type: 'image' },
        ],
      },
    };
    const p = transformRecord(r);
    assert.ok(p.user_prompt.includes('Hello'));
    assert.ok(p.user_prompt.includes('[Image Content]'));
  });

  it('handles tool_result content', () => {
    const r = {
      type: 'user',
      uuid: 'uuid-3',
      sessionId: 'sess-1',
      timestamp: '2024-01-15T12:00:00Z',
      message: {
        content: [{ type: 'tool_result', tool_use_id: 'tu-1', content: 'file content' }],
      },
    };
    const p = transformRecord(r);
    assert.ok(p.user_prompt.includes('[Tool Result]'));
    assert.equal(p.tool_use_id, 'tu-1');
  });

  it('does not include sentinel U values in output', () => {
    const r = { type: 'user', uuid: 'u1', sessionId: 'sess', timestamp: '2024-01-15T12:00:00Z', message: { content: 'hi' } };
    const p = transformRecord(r);
    for (const v of Object.values(p)) {
      assert.notEqual(String(v), '[object Object]', 'should not have unconverted U sentinel');
    }
  });
});

// ---------------------------------------------------------------------------
// transformRecord — assistant messages
// ---------------------------------------------------------------------------

describe('mapper.transformRecord — assistant messages', () => {
  it('extracts assistant_text and token counts', () => {
    const r = {
      type: 'assistant',
      uuid: 'asst-1',
      sessionId: 'sess-1',
      timestamp: '2024-01-15T12:01:00Z',
      message: {
        id: 'msg_001',
        model: 'claude-sonnet-4-6',
        content: [{ type: 'text', text: 'Sure, here is the answer.' }],
        usage: { input_tokens: 10, output_tokens: 5 },
      },
    };
    const p = transformRecord(r);
    assert.equal(p.event_type, 'claude_code_assistant');
    assert.equal(p.assistant_text, 'Sure, here is the answer.');
    assert.equal(p.input_tokens, 10);
    assert.equal(p.output_tokens, 5);
    assert.equal(p.primary_model, 'claude-sonnet-4-6');
  });

  it('extracts tool_use from assistant content blocks', () => {
    const r = {
      type: 'assistant',
      uuid: 'asst-2',
      sessionId: 'sess-1',
      timestamp: '2024-01-15T12:01:00Z',
      message: {
        model: 'claude-sonnet-4-6',
        content: [{ type: 'tool_use', id: 'tu-99', name: 'bash', input: { cmd: 'ls' } }],
        usage: { input_tokens: 5, output_tokens: 3 },
      },
    };
    const p = transformRecord(r);
    assert.equal(p.tool_use_id, 'tu-99');
    assert.ok(p.assistant_text.includes('[Tool Use: bash'));
  });

  it('includes thinking blocks in assistant_text', () => {
    const r = {
      type: 'assistant',
      uuid: 'asst-3',
      sessionId: 'sess-1',
      timestamp: '2024-01-15T12:01:00Z',
      message: {
        model: 'claude-sonnet-4-6',
        content: [{ type: 'thinking', thinking: 'Let me consider...' }],
        usage: { input_tokens: 3, output_tokens: 2 },
      },
    };
    const p = transformRecord(r);
    assert.ok(p.has_thinking === true);
    assert.ok(p.assistant_text.includes('thinking'));
  });

  it('uses incremental tokens when provided', () => {
    const r = {
      type: 'assistant', uuid: 'asst-4', sessionId: 'sess-1',
      timestamp: '2024-01-15T12:01:00Z',
      message: { model: 'claude-sonnet-4-6', content: [], usage: { input_tokens: 100, output_tokens: 50 } },
    };
    const inc = { input: 20, output: 10, cache_read: 0, cache_creation: 0, total: 30 };
    const p = transformRecord(r, inc);
    assert.equal(p.incremental_input, 20);
    assert.equal(p.incremental_output, 10);
  });
});

// ---------------------------------------------------------------------------
// transformRecord — system / progress / other types
// ---------------------------------------------------------------------------

describe('mapper.transformRecord — other message types', () => {
  it('handles tombstone type', () => {
    const r = { type: 'tombstone', uuid: 't1', sessionId: 'sess', timestamp: '2024-01-15T12:00:00Z' };
    const p = transformRecord(r);
    assert.ok(p.assistant_text.includes('Tombstone'));
  });

  it('handles summary type', () => {
    const r = { type: 'summary', uuid: 's1', sessionId: 'sess', timestamp: '2024-01-15T12:00:00Z', summary: 'Done.' };
    const p = transformRecord(r);
    assert.equal(p.assistant_text, 'Done.');
    assert.equal(p.user_prompt, '[Session Summary Request]');
  });

  it('handles api_error type', () => {
    const r = { type: 'api_error', uuid: 'e1', sessionId: 'sess', timestamp: '2024-01-15T12:00:00Z', error: { message: 'Rate limit' } };
    const p = transformRecord(r);
    assert.ok(p.assistant_text.includes('[API Error:'));
    assert.ok(p.assistant_text.includes('Rate limit'));
  });

  it('handles progress type', () => {
    const r = {
      type: 'progress', uuid: 'p1', sessionId: 'sess', timestamp: '2024-01-15T12:00:00Z',
      data: { hookName: 'bash', hookEvent: 'start', command: 'ls' },
    };
    const p = transformRecord(r);
    assert.ok(p.assistant_text.includes('[Progress:'));
  });

  it('handles unknown type with fallback', () => {
    const r = { type: 'completely-unknown', uuid: 'u1', sessionId: 'sess', timestamp: '2024-01-15T12:00:00Z' };
    const p = transformRecord(r);
    assert.ok(p.user_prompt.includes('[Unmapped Content for Type:'));
  });
});

// ---------------------------------------------------------------------------
// transformRecord — context_overrides
// ---------------------------------------------------------------------------

describe('mapper.transformRecord — context_overrides', () => {
  it('falls back to context_overrides.sessionId when missing from record', () => {
    const r = { type: 'user', uuid: 'u1', timestamp: '2024-01-15T12:00:00Z', message: { content: 'hi' } };
    const p = transformRecord(r, null, { sessionId: 'ctx-sess' });
    assert.equal(p.session_id, 'ctx-sess');
  });

  it('uses log_index for event_id when no uuid present', () => {
    const r = { type: 'user', sessionId: 'sess', timestamp: '2024-01-15T12:00:00Z', message: { content: 'hi' } };
    const p = transformRecord(r, null, { log_index: 42 });
    assert.ok(p.event_id.includes('42'));
  });

  it('populates is_agent from context_overrides', () => {
    const r = { type: 'user', uuid: 'u1', sessionId: 'sess', timestamp: '2024-01-15T12:00:00Z', message: { content: 'hi' } };
    const p = transformRecord(r, null, { is_agent: true });
    assert.equal(p.is_agent, true);
  });
});

// ---------------------------------------------------------------------------
// INTEGRATION_VERSION
// ---------------------------------------------------------------------------

describe('mapper.INTEGRATION_VERSION', () => {
  it('is a valid semver string', () => {
    assert.match(INTEGRATION_VERSION, /^\d+\.\d+\.\d+$/);
  });
});
