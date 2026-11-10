'use strict';
/**
 * Hook leak check (JS): Claude Code, Codex and Antigravity mappers + prepareRecord.
 * Same rules as testcases/python/check_hook_leaks.py: at metadata only METADATA_FIELDS
 * and no content markers; at full with a key every other column is encrypted.
 */
const fs = require('fs');
const path = require('path');
const { check, finish, isolatedHome, isEncrypted, PKG } = require('./common.cjs');

isolatedHome();
const CONTENT = /LEAK_(text|cmd|think|toolres|msg_content|user_prompt|assistant_output|user_input|final_response|command|path|summary|content|description|error_message|message)\b/g;
const ALWAYS = new Set(['cvs198', 'cvs200']);

const keysRead = (file) => new Set([...fs.readFileSync(file, 'utf8').matchAll(/(?:\.|\?\.)([A-Za-z_][A-Za-z0-9_]*)\b/g)]
  .map((m) => m[1]).filter((k) => k.length > 2 && k.length < 40));
const fill = (keys, prefix = '') => Object.fromEntries([...keys].map((k) => [k, `LEAK_${prefix}${k}`]));

function withKey(fn) {
  process.env.ANOSYS_ENCRYPTION_KEY = 'tc-pass';
  process.env.ANOSYS_ENCRYPTION_SALT = 'tc-salt';
  try { return fn(); } finally { delete process.env.ANOSYS_ENCRYPTION_KEY; delete process.env.ANOSYS_ENCRYPTION_SALT; }
}

function verify(tag, meta, full, fields) {
  const allowed = new Set(fields);
  const extra = Object.keys(meta).filter((k) => !allowed.has(k) && !ALWAYS.has(k));
  check(`${tag}: metadata sends only metadata columns`, extra.length === 0, `extra columns ${extra.slice(0, 8)}`);
  const found = [...new Set((JSON.stringify(meta).match(CONTENT) || []))];
  check(`${tag}: metadata carries no content`, found.length === 0, `markers ${found.slice(0, 8)}`);
  const clear = Object.entries(full).filter(([k, v]) => !allowed.has(k) && !ALWAYS.has(k) && typeof v === 'string' && !isEncrypted(v)).map(([k]) => k);
  check(`${tag}: full + key encrypts every content column`, clear.length === 0, `plaintext ${clear.slice(0, 8)}`);
}

// ── Claude Code
{
  const mapperFile = path.join(PKG, 'claude-code/src/mapper.js');
  const keys = keysRead(mapperFile);
  const hr = require(path.join(PKG, 'claude-code/src/hookRunner.js'));
  const { transformRecord, METADATA_FIELDS } = require(mapperFile);
  const types = ['user', 'assistant', 'system', 'summary', 'attachment', 'progress', 'file-history-snapshot',
    'marble-origami-commit', 'task-summary', 'custom-title', 'ai-title', 'last-prompt', 'pr-link',
    'worktree-state', 'queue-operation', 'agent-name', 'tag', 'mode'];
  const record = (t) => {
    const r = fill(keys); r.type = t; r.timestamp = '2026-11-10T00:00:00Z';
    const msg = fill(keys, 'msg_'); msg.model = 'claude-x'; msg.usage = { input_tokens: 1, output_tokens: 1 };
    msg.content = [{ type: 'text', text: 'LEAK_text' }, { type: 'tool_use', id: 't1', name: 'Bash', input: { command: 'LEAK_cmd' } },
      { type: 'thinking', thinking: 'LEAK_think' }, { type: 'tool_result', tool_use_id: 't1', content: 'LEAK_toolres' }];
    r.message = msg;
    for (const k of ['data', 'snapshot', 'worktreeSession', 'agentMap', 'toolUseResult', 'compactMetadata', 'attachment', 'hookSpecificOutput']) r[k] = fill(keys, `${k}_`);
    return r;
  };
  for (const layout of ['true', 'false']) {
    process.env.ANOSYS_CLAUDE_PIXEL = layout;
    for (const t of types) {
      verify(`js claude-code layout=${layout} type=${t}`,
        hr.prepareRecord(transformRecord(record(t), null, { sessionId: 's' }), 'metadata'),
        withKey(() => hr.prepareRecord(transformRecord(record(t), null, { sessionId: 's' }), 'full')), METADATA_FIELDS);
    }
  }
  delete process.env.ANOSYS_CLAUDE_PIXEL;
}

// ── Codex and Antigravity
for (const [pkg, fn] of [['codex', 'transformCodexTurn'], ['antigravity', 'transformAntigravityTurn']]) {
  const mapperFile = path.join(PKG, `${pkg}/src/mapper.js`);
  const keys = keysRead(mapperFile);
  const hr = require(path.join(PKG, `${pkg}/src/hookRunner.js`));
  const m = require(mapperFile);
  const turn = () => {
    const t = fill(keys); Object.assign(t, { start_ms: 1000, end_ms: 2000, tokens: { input_tokens: 1, output_tokens: 1 } });
    const step = fill(keys, 'ts_'); Object.assign(step, { start_ms: 1, end_ms: 2 });
    t.tool_steps = [step]; t.tool_calls = [fill(keys, 'tc_')]; t.commands = ['LEAK_command']; t.written_paths = ['LEAK_path'];
    return t;
  };
  for (const layout of ['cc', 'generic']) {
    process.env.ANOSYS_PIXEL_TYPE = layout;
    verify(`js ${pkg} layout=${layout}`,
      hr.prepareRecord(m[fn](turn(), 's', 't', fill(keys, 'meta_')), 'metadata'),
      withKey(() => hr.prepareRecord(m[fn](turn(), 's', 't', fill(keys, 'meta_')), 'full')), m.METADATA_FIELDS);
  }
  delete process.env.ANOSYS_PIXEL_TYPE;
}
finish();
