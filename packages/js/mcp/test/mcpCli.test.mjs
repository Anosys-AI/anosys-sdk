import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CLI = path.resolve(__dirname, '../src/cli.js');

test('anosys-sdk-mcp installs, checks status, and uninstalls across harnesses cleanly', () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-sdk-mcp-cli-'));
  try {
    const env = { ...process.env, HOME: home, CODEX_HOME: path.join(home, '.codex') };
    execFileSync(process.execPath, [CLI, 'install', '--target', 'all', '--mcp-key', 'ak_mcp_cli_ok', '-y'], {
      env,
      encoding: 'utf8',
    });

    const stOut = execFileSync(process.execPath, [CLI, 'status', '--target', 'all'], {
      env,
      encoding: 'utf8',
    });
    assert.match(stOut, /Claude Code/);
    assert.match(stOut, /OpenAI Codex CLI/);
    assert.match(stOut, /Google Antigravity/);
    assert.match(stOut, /Cursor/);
    assert.doesNotMatch(stOut, /not configured/);

    // Optional 'mcp' prefix works too (matches Usage: anosys-sdk-mcp [mcp] <install|status|uninstall>)
    const mcpPrefixedOut = execFileSync(process.execPath, [CLI, 'mcp', 'status', '--target', 'claude-code'], {
      env,
      encoding: 'utf8',
    });
    assert.match(mcpPrefixedOut, /Claude Code/);
    assert.doesNotMatch(mcpPrefixedOut, /not configured/);

    execFileSync(process.execPath, [CLI, 'uninstall', '--target', 'all'], { env, encoding: 'utf8' });
    const afterOut = execFileSync(process.execPath, [CLI, 'status', '--target', 'all'], {
      env,
      encoding: 'utf8',
    });
    assert.match(afterOut, /not configured/);
  } finally {
    fs.rmSync(home, { recursive: true, force: true });
  }
});

test('anosys-sdk-mcp rejects ingestion UUIDs with clear message', () => {
  assert.throws(
    () => execFileSync(process.execPath, [CLI, 'install', '--mcp-key', '550e8400-e29b-41d4-a716-446655440000', '-y'], {
      encoding: 'utf8',
      stdio: 'pipe',
    }),
    /INGESTION_KEY_NOT_SUPPORTED|Standard UUID ingestion keys/,
  );
});

test('anosys-sdk-mcp installs using ANOSYS_MCP_KEY or ANOSYS_MCP_API_KEY without --mcp-key', () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-sdk-mcp-env-'));
  try {
    const baseEnv = { ...process.env, HOME: home, CODEX_HOME: path.join(home, '.codex') };
    delete baseEnv.ANOSYS_MCP_API_KEY;
    delete baseEnv.ANOSYS_MCP_KEY;

    execFileSync(process.execPath, [CLI, 'install', '--target', 'claude-code', '-y'], {
      env: { ...baseEnv, ANOSYS_MCP_KEY: 'ak_mcp_env_alias_1' },
      encoding: 'utf8',
    });
    const claudeCfg = JSON.parse(fs.readFileSync(path.join(home, '.claude.json'), 'utf8'));
    assert.equal(
      claudeCfg.mcpServers['anosys-intelligence'].headers.Authorization,
      'Bearer ak_mcp_env_alias_1',
    );

    execFileSync(process.execPath, [CLI, 'install', '--target', 'claude-code', '-y'], {
      env: { ...baseEnv, ANOSYS_MCP_API_KEY: 'ak_mcp_env_primary_2', ANOSYS_MCP_KEY: 'ak_mcp_ignored' },
      encoding: 'utf8',
    });
    const updatedCfg = JSON.parse(fs.readFileSync(path.join(home, '.claude.json'), 'utf8'));
    assert.equal(
      updatedCfg.mcpServers['anosys-intelligence'].headers.Authorization,
      'Bearer ak_mcp_env_primary_2',
    );
  } finally {
    fs.rmSync(home, { recursive: true, force: true });
  }
});
