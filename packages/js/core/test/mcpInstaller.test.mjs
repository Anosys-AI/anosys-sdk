import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { PassThrough } from 'node:stream';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const {
  DEFAULT_MCP_URL,
  MCP_SERVER_NAME,
  SKILL_NAME,
  applyInstallMcpOptions,
  getMcpClientStatus,
  installMcpClient,
  isUuidLikeKey,
  promptHidden,
  resolveMcpKeyFromEnv,
  uninstallMcpClient,
  validateMcpKeyFormat,
  validateMcpUrl,
} = require('../src/index.js');

test('validateMcpKeyFormat rejects ingestion UUIDs and accepts ak_mcp_ keys', () => {
  assert.equal(isUuidLikeKey('550e8400-e29b-41d4-a716-446655440000'), true);
  const uuidCheck = validateMcpKeyFormat('550e8400-e29b-41d4-a716-446655440000');
  assert.equal(uuidCheck.ok, false);
  assert.equal(uuidCheck.code, 'INGESTION_KEY_NOT_SUPPORTED');

  const badPrefix = validateMcpKeyFormat('sk_other_123');
  assert.equal(badPrefix.ok, false);
  assert.equal(badPrefix.code, 'INVALID_MCP_KEY_PREFIX');

  const good = validateMcpKeyFormat('ak_mcp_test1234567890');
  assert.equal(good.ok, true);
  assert.equal(good.key, 'ak_mcp_test1234567890');
});

test('validateMcpUrl validates http/https protocols', () => {
  assert.equal(validateMcpUrl(DEFAULT_MCP_URL).ok, true);
  assert.equal(validateMcpUrl('ftp://console.anosys.ai/mcp').ok, false);
  assert.equal(validateMcpUrl('not a url').ok, false);
});

test('installMcpClient, status, and uninstall preserve existing JSON entries for claude-code, antigravity, and cursor', () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-mcp-home-'));
  const cwd = fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-mcp-cwd-'));
  try {
    // Seed existing server in ~/.claude.json
    const claudePath = path.join(home, '.claude.json');
    fs.writeFileSync(claudePath, JSON.stringify({ mcpServers: { other: { type: 'stdio', command: 'echo' } }, theme: 'dark' }));

    const res = installMcpClient({
      harness: 'claude-code',
      mcpKey: 'ak_mcp_secret_claude',
      homeDir: home,
      cwd,
    });
    assert.equal(res.mcpUpdated, true);
    assert.equal(res.skillUpdated, true);
    assert.ok(res.mcpBackupPath && fs.existsSync(res.mcpBackupPath));

    const claudeJson = JSON.parse(fs.readFileSync(claudePath, 'utf8'));
    assert.equal(claudeJson.theme, 'dark');
    assert.deepEqual(claudeJson.mcpServers.other, { type: 'stdio', command: 'echo' });
    assert.equal(claudeJson.mcpServers[MCP_SERVER_NAME].type, 'http');
    assert.equal(claudeJson.mcpServers[MCP_SERVER_NAME].url, DEFAULT_MCP_URL);
    assert.equal(claudeJson.mcpServers[MCP_SERVER_NAME].headers.Authorization, 'Bearer ak_mcp_secret_claude');

    const skillMd = fs.readFileSync(path.join(home, '.claude', 'skills', SKILL_NAME, 'SKILL.md'), 'utf8');
    assert.match(skillMd, /enc2:/);
    assert.match(skillMd, /ak_mcp_/);
    assert.match(skillMd, /cvn\*/);
    assert.match(skillMd, /get_cardinalities/);
    assert.match(skillMd, /get_auth_and_health/);
    assert.match(skillMd, /My Profile -> MCP Keys/);
    assert.match(skillMd, /load_skill/);
    assert.match(skillMd, /otel_trace_id/);
    assert.match(skillMd, /TIMESTAMP_SUB/);
    assert.doesNotMatch(skillMd, /UPSTREAM_TOKEN_EXPIRED|synced_access_token|Sync My Session|dead-letter/);

    const status = getMcpClientStatus({ harness: 'claude-code', homeDir: home, cwd });
    assert.equal(status.mcpInstalled, true);
    assert.equal(status.skillInstalled, true);

    const removed = uninstallMcpClient({ harness: 'claude-code', homeDir: home, cwd });
    assert.equal(removed.mcpRemoved, true);
    assert.equal(removed.skillRemoved, true);
    const afterJson = JSON.parse(fs.readFileSync(claudePath, 'utf8'));
    assert.equal(afterJson.mcpServers[MCP_SERVER_NAME], undefined);
    assert.ok(afterJson.mcpServers.other);

    // Antigravity global uses ~/.gemini/config/mcp_config.json & ~/.gemini/config/skills/<name>/SKILL.md
    const agRes = installMcpClient({
      harness: 'antigravity',
      mcpKey: 'ak_mcp_ag_123',
      mcpUrl: 'https://custom.anosys.ai/mcp',
      homeDir: home,
      cwd,
    });
    assert.equal(agRes.mcpPath, path.join(home, '.gemini', 'config', 'mcp_config.json'));
    assert.equal(agRes.skillPath, path.join(home, '.gemini', 'config', 'skills', SKILL_NAME, 'SKILL.md'));
    const agJson = JSON.parse(fs.readFileSync(agRes.mcpPath, 'utf8'));
    assert.equal(agJson.mcpServers[MCP_SERVER_NAME].serverUrl, 'https://custom.anosys.ai/mcp');
    assert.equal(agJson.mcpServers[MCP_SERVER_NAME].url, undefined);
    assert.equal(getMcpClientStatus({ harness: 'antigravity', homeDir: home, cwd }).mcpUrl, 'https://custom.anosys.ai/mcp');

    // Antigravity workspace: SKILL.md in .agents/, but the MCP server (with its key) stays in
    // the user config because Antigravity cannot read the key from the environment.
    const agWsRes = installMcpClient({
      harness: 'antigravity',
      mcpKey: 'ak_mcp_ag_ws',
      workspace: true,
      homeDir: home,
      cwd,
    });
    assert.equal(agWsRes.mcpPath, path.join(home, '.gemini', 'config', 'mcp_config.json'));
    assert.equal(agWsRes.mcpGlobalOnly, true);
    assert.equal(fs.existsSync(path.join(cwd, '.agents', 'mcp_config.json')), false);
    assert.equal(agWsRes.skillPath, path.join(cwd, '.agents', 'skills', SKILL_NAME, 'SKILL.md'));

    // Cursor workspace install references the key through the environment
    const curRes = installMcpClient({
      harness: 'cursor',
      mcpKey: 'ak_mcp_cur_123',
      workspace: true,
      homeDir: home,
      cwd,
    });
    assert.equal(curRes.mcpPath, path.join(cwd, '.cursor', 'mcp.json'));
    assert.equal(curRes.skillPath, path.join(cwd, '.cursor', 'skills', SKILL_NAME, 'SKILL.md'));
    const curRaw = fs.readFileSync(curRes.mcpPath, 'utf8');
    assert.doesNotMatch(curRaw, /ak_mcp_cur_123/);
    assert.equal(JSON.parse(curRaw).mcpServers[MCP_SERVER_NAME].headers.Authorization, 'Bearer ${env:ANOSYS_MCP_API_KEY}');

    // Claude Code project .mcp.json references the key through the environment
    const ccWs = installMcpClient({ harness: 'claude-code', mcpKey: 'ak_mcp_cc_ws_9', workspace: true, homeDir: home, cwd });
    const ccRaw = fs.readFileSync(ccWs.mcpPath, 'utf8');
    assert.equal(ccWs.mcpPath, path.join(cwd, '.mcp.json'));
    assert.equal(ccWs.keyFromEnv, true);
    assert.doesNotMatch(ccRaw, /ak_mcp_cc_ws_9/);
    assert.equal(JSON.parse(ccRaw).mcpServers[MCP_SERVER_NAME].headers.Authorization, 'Bearer ${ANOSYS_MCP_API_KEY}');

    // Codex project config uses bearer_token_env_var
    const cxWs = installMcpClient({ harness: 'codex', mcpKey: 'ak_mcp_cx_ws_7', workspace: true, homeDir: home, cwd, env: {} });
    const cxRaw = fs.readFileSync(cxWs.mcpPath, 'utf8');
    assert.equal(cxWs.mcpPath, path.join(cwd, '.codex', 'config.toml'));
    assert.doesNotMatch(cxRaw, /ak_mcp_cx_ws_7/);
    assert.match(cxRaw, /bearer_token_env_var = "ANOSYS_MCP_API_KEY"/);
    assert.doesNotMatch(cxRaw, /http_headers/);
  } finally {
    fs.rmSync(home, { recursive: true, force: true });
    fs.rmSync(cwd, { recursive: true, force: true });
  }
});

test('installMcpClient and uninstallMcpClient manage codex TOML section cleanly alongside notify', () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-codex-mcp-'));
  try {
    const codexDir = path.join(home, '.codex');
    fs.mkdirSync(codexDir, { recursive: true });
    const configToml = path.join(codexDir, 'config.toml');
    fs.writeFileSync(configToml, 'notify = ["node", "hook.js"]\n\n[model_providers.custom]\nname = "demo"\n');

    installMcpClient({
      harness: 'codex',
      mcpKey: 'ak_mcp_codex_123',
      homeDir: home,
      env: {},
    });
    const updated = fs.readFileSync(configToml, 'utf8');
    assert.match(updated, /notify = \["node", "hook\.js"\]/);
    assert.match(updated, /\[model_providers\.custom\]/);
    assert.match(updated, /\[mcp_servers\.anosys-intelligence\]/);
    assert.match(updated, /"Authorization" = "Bearer ak_mcp_codex_123"/);

    // Idempotent second install does not duplicate sections
    installMcpClient({
      harness: 'codex',
      mcpKey: 'ak_mcp_codex_456',
      homeDir: home,
      env: {},
    });
    const reupdated = fs.readFileSync(configToml, 'utf8');
    assert.equal((reupdated.match(/\[mcp_servers\.anosys-intelligence\]/g) || []).length, 1);
    assert.match(reupdated, /ak_mcp_codex_456/);

    const st = getMcpClientStatus({ harness: 'codex', homeDir: home, env: {} });
    assert.equal(st.mcpInstalled, true);
    assert.equal(st.mcpUrl, DEFAULT_MCP_URL);

    uninstallMcpClient({ harness: 'codex', homeDir: home, env: {} });
    const afterRemove = fs.readFileSync(configToml, 'utf8');
    assert.match(afterRemove, /notify = \["node", "hook\.js"\]/);
    assert.match(afterRemove, /\[model_providers\.custom\]/);
    assert.doesNotMatch(afterRemove, /\[mcp_servers\.anosys-intelligence\]/);

    // Status extracts URL even when [mcp_servers.anosys-intelligence] is the last section or contains 'Z'
    fs.writeFileSync(
      configToml,
      '[mcp_servers.anosys-intelligence]\nurl = "https://console.anosys.ai/Z/mcp"\n',
    );
    const stLast = getMcpClientStatus({ harness: 'codex', homeDir: home, env: {} });
    assert.equal(stLast.mcpInstalled, true);
    assert.equal(stLast.mcpUrl, 'https://console.anosys.ai/Z/mcp');
  } finally {
    fs.rmSync(home, { recursive: true, force: true });
  }
});

test('applyInstallMcpOptions rejects missing key without --with-skill in non-interactive mode and falls back to skill-only on blank interactive prompt', async () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-apply-mcp-'));
  try {
    await assert.rejects(
      () => applyInstallMcpOptions({ harness: 'claude-code', withMcp: true, yes: true, homeDir: home }),
      /Missing --mcp-key/,
    );
    const skillRes = await applyInstallMcpOptions({ harness: 'claude-code', withSkill: true, yes: true, homeDir: home });
    assert.equal(skillRes.skillUpdated, true);
    assert.equal(skillRes.mcpUpdated, false);

    const blankPromptRes = await applyInstallMcpOptions({
      harness: 'cursor',
      withMcp: true,
      yes: false,
      homeDir: home,
      promptFn: async () => '',
    });
    assert.equal(blankPromptRes.skillUpdated, true);
    assert.equal(blankPromptRes.mcpUpdated, false);
  } finally {
    fs.rmSync(home, { recursive: true, force: true });
  }
});

test('resolveMcpKeyFromEnv and applyInstallMcpOptions accept ANOSYS_MCP_KEY and ANOSYS_MCP_API_KEY', async () => {
  assert.equal(resolveMcpKeyFromEnv({ ANOSYS_MCP_API_KEY: 'ak_mcp_primary', ANOSYS_MCP_KEY: 'ak_mcp_alias' }), 'ak_mcp_primary');
  assert.equal(resolveMcpKeyFromEnv({ ANOSYS_MCP_KEY: '  ak_mcp_alias  ' }), 'ak_mcp_alias');
  assert.equal(resolveMcpKeyFromEnv({}), '');

  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-env-mcp-'));
  const prevApiKey = process.env.ANOSYS_MCP_API_KEY;
  const prevKey = process.env.ANOSYS_MCP_KEY;
  try {
    delete process.env.ANOSYS_MCP_API_KEY;
    process.env.ANOSYS_MCP_KEY = 'ak_mcp_from_env_alias';
    const res = await applyInstallMcpOptions({
      harness: 'claude-code',
      withMcp: true,
      yes: true,
      homeDir: home,
    });
    assert.equal(res.mcpUpdated, true);
    const cfg = JSON.parse(fs.readFileSync(path.join(home, '.claude.json'), 'utf8'));
    assert.equal(cfg.mcpServers[MCP_SERVER_NAME].headers.Authorization, 'Bearer ak_mcp_from_env_alias');
  } finally {
    if (prevApiKey === undefined) delete process.env.ANOSYS_MCP_API_KEY;
    else process.env.ANOSYS_MCP_API_KEY = prevApiKey;
    if (prevKey === undefined) delete process.env.ANOSYS_MCP_KEY;
    else process.env.ANOSYS_MCP_KEY = prevKey;
    fs.rmSync(home, { recursive: true, force: true });
  }
});

test('promptHidden reads key cleanly and suppresses echo in TTY mode', async () => {
  const input = new PassThrough();
  const outputChunks = [];
  const output = new PassThrough();
  output.on('data', (c) => outputChunks.push(c.toString('utf8')));
  input.isTTY = true;
  output.isTTY = true;

  const p = promptHidden('AnoSys MCP key: ', { input, output });
  input.write('ak_mcp_secret_tty\n');
  const val = await p;
  assert.equal(val, 'ak_mcp_secret_tty');
  const rendered = outputChunks.join('');
  assert.match(rendered, /AnoSys MCP key: /);
  assert.doesNotMatch(rendered, /ak_mcp_secret_tty/);
});
