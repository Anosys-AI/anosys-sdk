// The JS coding-agent hooks never break the host tool: read-only home, missing transcript, no key.
import { it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const js = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const HOOKS = [
  ['codex', [path.join(js, 'codex/src/cli.js'), 'run', '{"type":"agent-turn-complete","thread-id":"t","turn-id":"x"}'], ''],
  ['claude-code', [path.join(js, 'claude-code/src/cli.js'), 'run'], '{"session_id":"s","transcript_path":"/nonexistent/t.jsonl"}'],
  ['antigravity', [path.join(js, 'antigravity/src/cli.js'), 'run', 'stop'], '{"transcriptPath":"/nonexistent/t.jsonl"}'],
];

for (const [name, args, input] of HOOKS) {
  it(`${name} survives a read-only home`, (t) => {
    if (!fs.existsSync(args[0])) return t.skip('not in this checkout');
    const home = fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-ro-'));
    fs.chmodSync(home, 0o500);
    const env = Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith('ANOSYS_') && !k.startsWith('CODEX_')));
    Object.assign(env, { HOME: home, CODEX_HOME: path.join(home, '.codex'), ANOSYS_CONSENT_FILE: path.join(home, 'c.json') });
    try {
      const start = Date.now();
      const res = spawnSync(process.execPath, args, { input, env, encoding: 'utf8', timeout: 60000 });
      assert.equal(res.status, 0, res.stderr.slice(-500));
      assert.ok(['', '{}'].includes(res.stdout.trim()), `printed: ${res.stdout.slice(0, 200)}`);
      assert.ok(Date.now() - start < 30000);
    } finally {
      fs.chmodSync(home, 0o700);
    }
  });
}
