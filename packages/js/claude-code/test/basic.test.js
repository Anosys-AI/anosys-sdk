'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');

// ---------------------------------------------------------------------------
// installer — env management
// ---------------------------------------------------------------------------
const installer = require('../src/installer');

describe('installer.updateEnv / removeEnv', () => {
  it('writes new env keys into settings', () => {
    const settings = { env: { EXISTING: 'keep' } };
    const result = installer.updateEnv(settings, {
      ANOSYS_HOOK_APIKEY: 'test-key',
      ANOSYS_HOOK_DRY_RUN: 'false',
    });
    assert.equal(result.env.ANOSYS_HOOK_APIKEY, 'test-key');
    assert.equal(result.env.ANOSYS_HOOK_DRY_RUN, 'false');
    assert.equal(result.env.EXISTING, 'keep', 'non-anosys keys must be preserved');
  });

  it('removeEnv strips all managed keys and preserves others', () => {
    const settings = {
      env: {
        EXISTING: 'keep',
        ANOSYS_HOOK_APIKEY: 'x',
        ANOSYS_HOOK_DRY_RUN: 'false',
        OTEL_EXPORTER_OTLP_ENDPOINT: 'https://api.anosys.ai/ingestion',
        OTEL_EXPORTER_OTLP_HEADERS: 'anosys-apikey=abc123',
        REDACTION: 'true',
      },
    };
    const result = installer.removeEnv(settings);
    assert.equal(result.env.EXISTING, 'keep');
    assert.equal(result.env.ANOSYS_HOOK_APIKEY, undefined);
    assert.equal(result.env.OTEL_EXPORTER_OTLP_ENDPOINT, undefined);
    assert.equal(result.env.OTEL_EXPORTER_OTLP_HEADERS, undefined);
  });

  it('updateEnv replaces old OTEL endpoint + headers on reinstall', () => {
    const settings = {
      env: {
        OTEL_EXPORTER_OTLP_ENDPOINT: 'https://old.endpoint.example',
        OTEL_EXPORTER_OTLP_HEADERS: 'anosys-apikey=old',
      },
    };
    const result = installer.updateEnv(settings, {
      OTEL_EXPORTER_OTLP_ENDPOINT: 'https://api.anosys.ai/ingestion',
      OTEL_EXPORTER_OTLP_HEADERS: 'anosys-apikey=new-key',
    });
    assert.equal(result.env.OTEL_EXPORTER_OTLP_ENDPOINT, 'https://api.anosys.ai/ingestion');
    assert.equal(result.env.OTEL_EXPORTER_OTLP_HEADERS, 'anosys-apikey=new-key');
  });

  it('updateEnv also cleans up legacy OTEL_EXPORTER_OTLP_ANOSYS_APIKEY on reinstall', () => {
    const settings = {
      env: {
        OTEL_EXPORTER_OTLP_ANOSYS_APIKEY: 'legacy-key',
      },
    };
    const result = installer.updateEnv(settings, {
      OTEL_EXPORTER_OTLP_ENDPOINT: 'https://api.anosys.ai/ingestion',
      OTEL_EXPORTER_OTLP_HEADERS: 'anosys-apikey=new-key',
    });
    assert.equal(result.env.OTEL_EXPORTER_OTLP_ANOSYS_APIKEY, undefined,
      'legacy key should be removed during reinstall');
    assert.equal(result.env.OTEL_EXPORTER_OTLP_HEADERS, 'anosys-apikey=new-key');
  });
});

describe('installer.hasAnosysHook / updateStopHooks / removeStopHooks', () => {
  it('detects no hook in empty settings', () => {
    assert.equal(installer.hasAnosysHook({}), false);
  });

  it('registers and detects the hook', () => {
    let settings = {};
    settings = installer.updateStopHooks(settings, 'npx @anosys/claude-code run');
    assert.equal(installer.hasAnosysHook(settings), true);
    assert.equal(installer.getAnosysHookCommand(settings), 'npx @anosys/claude-code run');
  });

  it('removeStopHooks removes the registered hook', () => {
    let settings = {};
    settings = installer.updateStopHooks(settings, 'npx @anosys/claude-code run');
    settings = installer.removeStopHooks(settings);
    assert.equal(installer.hasAnosysHook(settings), false);
  });

  it('preserves non-anosys hooks when removing', () => {
    const settings = {
      hooks: {
        Stop: [
          {
            hooks: [
              { owner: 'other-tool', type: 'command', command: 'other-cmd' },
              { owner: 'anosys',    type: 'command', command: 'npx @anosys/claude-code run' },
            ],
          },
        ],
      },
    };
    const result = installer.removeStopHooks(settings);
    const stopGroups = result.hooks.Stop;
    const allCommands = stopGroups.flatMap(g => (g.hooks || []).map(h => h.command));
    assert.ok(allCommands.includes('other-cmd'), 'other-tool hook must survive');
    assert.ok(!allCommands.includes('npx @anosys/claude-code run'), 'anosys hook must be gone');
  });
});

// ---------------------------------------------------------------------------
// hookRunner — exported helpers
// ---------------------------------------------------------------------------
const { findAllTranscripts, loadState } = require('../src/hookRunner');

describe('hookRunner exports', () => {
  it('findAllTranscripts returns an array', () => {
    const result = findAllTranscripts();
    assert.ok(Array.isArray(result));
  });

  it('loadState returns an object', () => {
    const state = loadState();
    assert.ok(state !== null && typeof state === 'object');
  });
});
