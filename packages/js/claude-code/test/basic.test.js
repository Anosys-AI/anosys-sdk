'use strict';

const { describe, it, before, after } = require('node:test');
const assert = require('node:assert/strict');
const os = require('os');
const fs = require('fs');
const path = require('path');

const installer = require('../src/installer');

// ---------------------------------------------------------------------------
// installer — env management
// ---------------------------------------------------------------------------

describe('installer.updateEnv / removeEnv', () => {
  it('writes new env keys and preserves non-anosys keys', () => {
    const result = installer.updateEnv({ env: { EXISTING: 'keep' } }, {
      ANOSYS_HOOK_APIKEY: 'test-key',
      ANOSYS_HOOK_DRY_RUN: 'false',
    });
    assert.equal(result.env.ANOSYS_HOOK_APIKEY, 'test-key');
    assert.equal(result.env.EXISTING, 'keep');
  });

  it('removeEnv strips all managed keys and preserves others', () => {
    const result = installer.removeEnv({
      env: {
        EXISTING: 'keep',
        ANOSYS_HOOK_APIKEY: 'x',
        OTEL_EXPORTER_OTLP_ENDPOINT: 'https://api.anosys.ai/ingestion',
        OTEL_EXPORTER_OTLP_HEADERS: 'anosys-apikey=abc123',
        OTEL_EXPORTER_OTLP_ANOSYS_APIKEY: 'legacy',
        ANOSYS_HOOK_ENDPOINT_URL: 'old',
        ANOSYS_HOOK_API_KEY: 'old-key',
        ANOSYS_CLAUDE_PIXEL: 'false',
        REDACTION: 'true',
      },
    });
    assert.equal(result.env.EXISTING, 'keep');
    assert.equal(result.env.ANOSYS_HOOK_APIKEY, undefined);
    assert.equal(result.env.OTEL_EXPORTER_OTLP_ENDPOINT, undefined);
    assert.equal(result.env.OTEL_EXPORTER_OTLP_HEADERS, undefined);
    assert.equal(result.env.OTEL_EXPORTER_OTLP_ANOSYS_APIKEY, undefined);
    assert.equal(result.env.ANOSYS_HOOK_ENDPOINT_URL, undefined);
    assert.equal(result.env.ANOSYS_HOOK_API_KEY, undefined);
    assert.equal(result.env.ANOSYS_CLAUDE_PIXEL, undefined);
  });

  it('updateEnv sets correct OTEL standard env vars (endpoint + headers)', () => {
    const result = installer.updateEnv({}, {
      OTEL_EXPORTER_OTLP_ENDPOINT: 'https://api.anosys.ai/ingestion',
      OTEL_EXPORTER_OTLP_HEADERS: 'anosys-apikey=mykey',
    });
    assert.equal(result.env.OTEL_EXPORTER_OTLP_ENDPOINT, 'https://api.anosys.ai/ingestion');
    assert.equal(result.env.OTEL_EXPORTER_OTLP_HEADERS, 'anosys-apikey=mykey');
    assert.equal(result.env.OTEL_EXPORTER_OTLP_ANOSYS_APIKEY, undefined,
      'must not set legacy key');
  });

  it('updateEnv replaces old values on reinstall', () => {
    const result = installer.updateEnv({
      env: {
        OTEL_EXPORTER_OTLP_ENDPOINT: 'https://old.example',
        OTEL_EXPORTER_OTLP_HEADERS: 'anosys-apikey=old',
      },
    }, {
      OTEL_EXPORTER_OTLP_ENDPOINT: 'https://api.anosys.ai/ingestion',
      OTEL_EXPORTER_OTLP_HEADERS: 'anosys-apikey=new',
    });
    assert.equal(result.env.OTEL_EXPORTER_OTLP_ENDPOINT, 'https://api.anosys.ai/ingestion');
    assert.equal(result.env.OTEL_EXPORTER_OTLP_HEADERS, 'anosys-apikey=new');
  });

  it('updateEnv cleans up legacy OTEL_EXPORTER_OTLP_ANOSYS_APIKEY on reinstall', () => {
    const result = installer.updateEnv({
      env: { OTEL_EXPORTER_OTLP_ANOSYS_APIKEY: 'old-legacy' },
    }, {
      OTEL_EXPORTER_OTLP_ENDPOINT: 'https://api.anosys.ai/ingestion',
      OTEL_EXPORTER_OTLP_HEADERS: 'anosys-apikey=new',
    });
    assert.equal(result.env.OTEL_EXPORTER_OTLP_ANOSYS_APIKEY, undefined);
  });

  it('updateEnv works with empty initial settings', () => {
    const result = installer.updateEnv({}, { ANOSYS_HOOK_APIKEY: 'k' });
    assert.equal(result.env.ANOSYS_HOOK_APIKEY, 'k');
  });
});

// ---------------------------------------------------------------------------
// installer — hook registration
// ---------------------------------------------------------------------------

describe('installer.hasAnosysHook / updateStopHooks / removeStopHooks', () => {
  it('detects no hook in empty settings', () => {
    assert.equal(installer.hasAnosysHook({}), false);
    assert.equal(installer.hasAnosysHook({ hooks: {} }), false);
    assert.equal(installer.hasAnosysHook({ hooks: { Stop: [] } }), false);
  });

  it('registers and detects the hook', () => {
    let s = installer.updateStopHooks({}, 'npx @anosys/claude-code run');
    assert.equal(installer.hasAnosysHook(s), true);
    assert.equal(installer.getAnosysHookCommand(s), 'npx @anosys/claude-code run');
  });

  it('removeStopHooks removes the registered hook', () => {
    let s = installer.updateStopHooks({}, 'npx @anosys/claude-code run');
    s = installer.removeStopHooks(s);
    assert.equal(installer.hasAnosysHook(s), false);
    assert.equal(installer.getAnosysHookCommand(s), null);
  });

  it('double-install is idempotent — only one anosys entry', () => {
    let s = installer.updateStopHooks({}, 'npx @anosys/claude-code run');
    s = installer.updateStopHooks(s, 'npx @anosys/claude-code run');
    const all = (s.hooks?.Stop ?? []).flatMap(g => g.hooks ?? []);
    const anosys = all.filter(h => h.owner === 'anosys');
    assert.equal(anosys.length, 1);
  });

  it('preserves non-anosys hooks when removing', () => {
    const s0 = {
      hooks: {
        Stop: [{
          hooks: [
            { owner: 'other-tool', type: 'command', command: 'other-cmd' },
            { owner: 'anosys',    type: 'command', command: 'npx @anosys/claude-code run' },
          ],
        }],
      },
    };
    const result = installer.removeStopHooks(s0);
    const cmds = (result.hooks?.Stop ?? []).flatMap(g => (g.hooks ?? []).map(h => h.command));
    assert.ok(cmds.includes('other-cmd'), 'other-tool hook must survive');
    assert.ok(!cmds.includes('npx @anosys/claude-code run'), 'anosys hook must be removed');
  });

  it('getAnosysHookCommand returns null when not installed', () => {
    assert.equal(installer.getAnosysHookCommand({}), null);
  });
});

// ---------------------------------------------------------------------------
// installer — backup (timestamped, returns path)
// ---------------------------------------------------------------------------

describe('installer.backup', () => {
  let tmpFile;
  before(() => {
    tmpFile = path.join(os.tmpdir(), `anosys_test_settings_${Date.now()}.json`);
    fs.writeFileSync(tmpFile, '{"env":{}}', 'utf8');
  });
  after(() => {
    // Clean up tmp file and any backups
    const dir = path.dirname(tmpFile);
    const base = path.basename(tmpFile);
    for (const f of fs.readdirSync(dir)) {
      if (f.startsWith(base) || (f.includes('anosys_test_settings') && f.endsWith('.bak'))) {
        try { fs.unlinkSync(path.join(dir, f)); } catch (_) {}
      }
    }
  });

  it('backup returns a timestamped path and creates the file', () => {
    const backupPath = installer.backup(tmpFile);
    assert.ok(backupPath, 'backup path should be returned');
    assert.ok(backupPath.endsWith('.bak'), 'backup must have .bak extension');
    assert.ok(fs.existsSync(backupPath), 'backup file must exist');
  });

  it('backup returns null for non-existent file', () => {
    const result = installer.backup('/tmp/does_not_exist_anosys.json');
    assert.equal(result, null);
  });
});

// ---------------------------------------------------------------------------
// installer — writeAtomic / loadSettings
// ---------------------------------------------------------------------------

describe('installer.writeAtomic / loadSettings', () => {
  let tmpFile;
  before(() => {
    tmpFile = path.join(os.tmpdir(), `anosys_test_write_${Date.now()}.json`);
  });
  after(() => { try { fs.unlinkSync(tmpFile); } catch (_) {} });

  it('round-trips a settings object through writeAtomic + loadSettings', () => {
    const data = { env: { ANOSYS_HOOK_APIKEY: 'abc' }, hooks: { Stop: [] } };
    installer.writeAtomic(tmpFile, data);
    const loaded = installer.loadSettings(tmpFile);
    assert.deepEqual(loaded, data);
  });

  it('loadSettings returns {} for non-existent file', () => {
    const result = installer.loadSettings('/tmp/does_not_exist_anosys_xyz.json');
    assert.deepEqual(result, {});
  });
});

// ---------------------------------------------------------------------------
// hookRunner — exported helpers (smoke tests, no filesystem writes)
// ---------------------------------------------------------------------------

const { findAllTranscripts, findLatestTranscript, loadState } = require('../src/hookRunner');

describe('hookRunner exports', () => {
  it('findAllTranscripts returns an array', () => {
    assert.ok(Array.isArray(findAllTranscripts()));
  });

  it('findLatestTranscript returns null or a transcript object', () => {
    const result = findLatestTranscript();
    assert.ok(result === null || (typeof result === 'object' && result.path));
  });

  it('loadState returns a plain object', () => {
    const state = loadState();
    assert.ok(state !== null && typeof state === 'object' && !Array.isArray(state));
  });
});
