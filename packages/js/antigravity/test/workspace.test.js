const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { execFileSync } = require('node:child_process');

test('workspace credentials work from a subdirectory and respect environment overrides', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-workspace-test-'));
  const home = path.join(root, 'home');
  const globalConfig = path.join(home, '.gemini', 'config');
  fs.mkdirSync(globalConfig, { recursive: true });
  fs.writeFileSync(path.join(globalConfig, 'anosys-env.json'), JSON.stringify({
    ANOSYS_HOOK_APIKEY: 'global-key', REDACTION: 'false',
  }));
  const workspace = path.join(root, 'workspace');
  fs.mkdirSync(path.join(workspace, '.agents'), { recursive: true });
  fs.writeFileSync(path.join(workspace, '.agents', 'anosys-env.json'), JSON.stringify({
    ANOSYS_HOOK_APIKEY: 'workspace-key', REDACTION: 'true',
  }));
  const cwd = path.join(workspace, 'src');
  fs.mkdirSync(cwd);
  const env = { ...process.env, HOME: home };
  for (const key of ['ANOSYS_HOOK_APIKEY', 'ANOSYS_API_KEY', 'REDACTION']) delete env[key];
  const modulePath = require.resolve('../src/hookRunner');
  const corePath = require.resolve('anosys-sdk-core');
  const code = `const { effectiveLevel } = require(${JSON.stringify(corePath)});
    console.log(JSON.stringify({ ...require(${JSON.stringify(modulePath)}).getConfig(), level: effectiveLevel() }))`;
  env.ANOSYS_CONSENT_FILE = path.join(root, 'consent.json');
  for (const override of [null, 'environment-key']) {
    if (override) env.ANOSYS_HOOK_APIKEY = override;
    const config = JSON.parse(execFileSync(process.execPath, ['-e', code], { env, cwd, encoding: 'utf8' }));
    assert.equal(config.api_key, override || 'workspace-key');
    // a saved REDACTION=true still means metadata only
    assert.deepEqual(config.level, { level: 'metadata', source: 'REDACTION' });
  }
});
