'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const readline = require('readline');
const { Writable } = require('stream');

const DEFAULT_MCP_URL = 'https://console.anosys.ai/mcp';
const MCP_SERVER_NAME = 'anosys-intelligence';
const SKILL_NAME = 'anosys-platform-intelligence';
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const PLATFORM_INTELLIGENCE_SKILL_MD = `---
name: anosys-platform-intelligence
description: Use when analyzing a customer's AnoSys software architecture, linked pipelines/tables/evals, active problems, insights, or trace graphs via the AnoSys Public MCP or REST Intelligence Export API.
---

# AnoSys Platform Intelligence Skill

You are connected to **AnoSys Public MCP** (\`anosys_public_mcp\`), a read-only customer intelligence gateway exposing structured architecture graphs, linked component topology, active problems, eval summaries, causal trace trees, and guarded SQL analytics.

## Authentication Rules (Read First)

- Valid credentials for AnoSys MCP & REST tools:
  1. **Scoped MCP API Key** (\`ak_mcp_...\`) passed via HTTP header \`Authorization: Bearer ak_mcp_...\` or \`x-api-key: ak_mcp_...\`. Mint and manage personal keys in AnoSys Console (\`https://console.anosys.ai\`) under **My Profile -> MCP Keys**.
  2. **Customer Auth0 JWT** passed via \`Authorization: Bearer <jwt>\`.
- **Important:** Do **NOT** pass credentials inside tool \`arguments\` (\`apiKey\`) or URL query parameters — credentials are read strictly from HTTP headers. Do **NOT** use an AnoSys telemetry ingestion API key (standard UUID from Integration Options used for \`/generateapikey\` ingestion); ingestion keys are rejected (\`INGESTION_KEY_NOT_SUPPORTED\`).
- **Gateway Auth & Diagnostics:** \`ak_mcp_...\` keys authenticate upstream read-only routes via scoped gateway identity (\`companyId\`, \`keyId\`, personal \`createdBySub\` owner). If a key is paused in Console, tool calls fail with \`PAUSED_MCP_KEY\` until re-enabled in **My Profile -> MCP Keys**. Call \`get_auth_and_health\` anytime to inspect \`authType\`, \`companyId\`, \`scopes\`, and upstream BE health.

## Recommended Investigation Workflow

1. **Start Grounded (Low Token Cost):**
   - Call \`export_context_pack\` first to obtain the customer's architecture summary, Mermaid diagram, active problems, recent eval pass rate, and available telemetry tables in one bounded payload.
   - Call \`load_skill\` (or read MCP resources \`anosys://playbooks/*\`) for detailed playbooks on incident triage, eval regressions, cost/cardinalities, or table \`tid\` schemas.
2. **Trace Architecture & Linked Parts:**
   - Call \`get_architecture\` for full node/edge topology across ReactFlow pipelines (\`nodes\`, \`edges\`), sources, tables, saved queries, evals, and triggers.
   - Call \`get_linked_parts({ target })\` to inspect upstream inputs and downstream dependents around a failing pipeline, table, query, or eval.
3. **Investigate Problems, Insights & Network Context:**
   - Call \`list_problems\` (optionally with \`severity\`, \`telemetryTable\`, \`hours\`, \`limit\`, \`cursor\`) to combine failed eval executions, degraded pipelines, stale jobs, and optional telemetry anomalies.
   - Call \`get_insights\` to combine deterministic health findings and eval regression signals.
   - Call \`resolve_ip({ ip })\` (POC) to validate/classify IPv4/IPv6 addresses (and rate-limited reverse DNS PTR records).
   - Call \`get_eval_summary\` for configured evals and pass/fail ratios (supports pagination with \`cursor\`/\`offset\`).
4. **Deep-Dive Causal Traces, Cardinalities & Ad-Hoc SQL:**
   - Call \`list_tables_and_schemas\` before writing SQL so column names match the customer's actual table \`tid\` type:
     - **\`t\` (OTEL / OtelAI):** \`otel_trace_id\`, \`otel_span_id\`, \`otel_parent_span_id\`, \`otel_name\`, \`otel_status_code\`, \`otel_exception_message\`, \`gen_ai_conversation_id\`.
     - **\`cc\` (Claude Code):** \`session_id\`, \`raw_uuid\`, \`parent_uuid\`, \`logical_parent_uuid\`, \`parent_tool_use_id\`, \`tool_use_id\`, \`error_obj\`, \`error_details\`.
     - **\`n\` / \`g\` / \`a\` / \`i\` / \`c\`:** share the 14 base columns (\`timestamp\`, \`event_id\`, \`event_type\`, \`event_source_name\`, \`risk_score\`, \`is_anomaly\`, \`risk_evidence\`, etc.) and do NOT carry OTel/CC trace columns.
     - **Custom fields (\`cvs*\`, \`cvn*\`, \`cvi*\`, \`cvf*\`, \`cvb*\` / \`cv\` mapping):** inspect \`displayName\` in \`list_tables_and_schemas\` or \`aliasName\` in \`get_cardinalities\`.
   - Call \`get_cardinalities\` before running expensive aggregations to see distinct counts, non-null counts, top values, and human aliases.
   - Call \`get_trace_graph({ table, traceId | sessionId, hours })\` to reconstruct parent-child execution trees. It automatically detects \`t\` (\`otel_*\`) vs \`cc\` (\`session_id\`/\`parent_uuid\`) schemas, applies a 24-hour partition window by default, and enforces dry-run scan budgets.
   - Call \`query_readonly({ sql, maxRows, cursor, offset, maxTokens })\` only when structured tools cannot answer the question. Queries must be single-statement \`SELECT\`/\`WITH\`, reference only authorized workspace tables, include partition filters (\`timestamp >= TIMESTAMP_SUB(...)\`), and pass BigQuery dry-run byte checks.

## Guardrails & Client-Side Encryption (\`enc2\`)

- All tools in \`anosys_public_mcp\` are strictly **read-only**. Do not attempt \`INSERT\`, \`UPDATE\`, \`DELETE\`, \`DROP\`, \`EXTERNAL_QUERY\`, or multi-statement SQL.
- If the customer enabled SDK client-side encryption (\`ANOSYS_ENCRYPTION_KEY\`), prompt/response/command fields stored in BigQuery carry the \`enc2:\` ciphertext prefix. Operational metadata (counts, timestamps, statuses, model names, token/latency metrics, eval pass rates) remains directly queryable without decrypting raw text.
- Always surface \`warnings\` returned in tool outputs (for example, if optional monitor upstreams or sections under shared deadline degraded) so the user knows which data sources were live vs partial.
`;

const MCP_KEY_ENV = 'ANOSYS_MCP_API_KEY';

function getCodexHome(homeDir = os.homedir(), env = process.env) {
  const custom = String(env.CODEX_HOME || '').trim();
  if (custom) {
    return path.resolve(custom.replace(/^~(?=$|\/|\\)/, homeDir));
  }
  return path.join(homeDir, '.codex');
}

const HARNESS_SPECS = {
  'claude-code': {
    id: 'claude-code',
    label: 'Claude Code',
    format: 'json-mcpServers',
    urlField: 'url',
    includeTypeHttp: true,
    // Project files are often committed, so they reference the key instead of holding it.
    workspaceKeyRef: '${' + MCP_KEY_ENV + '}',
    resolveMcpPath: ({ workspace, cwd, homeDir }) =>
      workspace ? path.join(cwd, '.mcp.json') : path.join(homeDir, '.claude.json'),
    resolveSkillPath: ({ workspace, cwd, homeDir }) =>
      workspace
        ? path.join(cwd, '.claude', 'skills', SKILL_NAME, 'SKILL.md')
        : path.join(homeDir, '.claude', 'skills', SKILL_NAME, 'SKILL.md'),
  },
  codex: {
    id: 'codex',
    label: 'OpenAI Codex CLI',
    format: 'codex-toml',
    resolveMcpPath: ({ workspace, cwd, homeDir, env }) =>
      workspace ? path.join(cwd, '.codex', 'config.toml') : path.join(getCodexHome(homeDir, env), 'config.toml'),
    resolveSkillPath: ({ workspace, cwd, homeDir, env }) =>
      workspace
        ? path.join(cwd, '.agents', 'skills', SKILL_NAME, 'SKILL.md')
        : path.join(getCodexHome(homeDir, env), 'skills', SKILL_NAME, 'SKILL.md'),
  },
  antigravity: {
    id: 'antigravity',
    label: 'Google Antigravity',
    format: 'json-mcpServers',
    // Antigravity only accepts serverUrl for remote servers.
    urlField: 'serverUrl',
    includeTypeHttp: false,
    // Antigravity does not expand environment variables in mcp_config.json, so the
    // server (and its key) is always registered in the user config, never in the project.
    globalOnlyMcp: true,
    resolveMcpPath: ({ workspace, cwd, homeDir }) =>
      workspace
        ? path.join(cwd, '.agents', 'mcp_config.json')
        : path.join(homeDir, '.gemini', 'config', 'mcp_config.json'),
    resolveSkillPath: ({ workspace, cwd, homeDir }) =>
      workspace
        ? path.join(cwd, '.agents', 'skills', SKILL_NAME, 'SKILL.md')
        : path.join(homeDir, '.gemini', 'config', 'skills', SKILL_NAME, 'SKILL.md'),
  },
  cursor: {
    id: 'cursor',
    label: 'Cursor',
    format: 'json-mcpServers',
    urlField: 'url',
    includeTypeHttp: false,
    workspaceKeyRef: '${env:' + MCP_KEY_ENV + '}',
    resolveMcpPath: ({ workspace, cwd, homeDir }) =>
      workspace ? path.join(cwd, '.cursor', 'mcp.json') : path.join(homeDir, '.cursor', 'mcp.json'),
    resolveSkillPath: ({ workspace, cwd, homeDir }) =>
      workspace
        ? path.join(cwd, '.cursor', 'skills', SKILL_NAME, 'SKILL.md')
        : path.join(homeDir, '.cursor', 'skills', SKILL_NAME, 'SKILL.md'),
  },
};

function supportedMcpHarnesses() {
  return Object.keys(HARNESS_SPECS);
}

function isUuidLikeKey(key) {
  return UUID_RE.test(String(key || '').trim());
}

function validateMcpKeyFormat(key) {
  const trimmed = String(key || '').trim();
  if (!trimmed) {
    return {
      ok: false,
      code: 'MCP_KEY_REQUIRED',
      message: 'An AnoSys MCP API key (ak_mcp_...) is required for MCP registration.',
    };
  }
  if (isUuidLikeKey(trimmed)) {
    return {
      ok: false,
      code: 'INGESTION_KEY_NOT_SUPPORTED',
      message:
        'Standard UUID ingestion keys (ANOSYS_HOOK_APIKEY / ANOSYS_API_KEY) cannot authenticate with Public MCP. Mint a scoped ak_mcp_... key in AnoSys Console.',
    };
  }
  if (!trimmed.startsWith('ak_mcp_') && !trimmed.startsWith('eyJ')) {
    return {
      ok: false,
      code: 'INVALID_MCP_KEY_PREFIX',
      message: 'MCP key must start with "ak_mcp_" (scoped MCP API key) or be a customer JWT.',
    };
  }
  return { ok: true, key: trimmed };
}

function validateMcpUrl(url) {
  const raw = String(url || DEFAULT_MCP_URL).trim();
  try {
    const parsed = new URL(raw);
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
      return { ok: false, message: `Unsupported MCP URL protocol: ${parsed.protocol}` };
    }
    return { ok: true, url: parsed.toString() };
  } catch {
    return { ok: false, message: `Invalid MCP URL: ${raw}` };
  }
}

function resolveMcpTargets(harness, { workspace = false, cwd = process.cwd(), homeDir = os.homedir(), env = process.env } = {}) {
  const spec = HARNESS_SPECS[harness];
  if (!spec) {
    throw new Error(`Unsupported MCP harness "${harness}". Supported: ${supportedMcpHarnesses().join(', ')}`);
  }
  const ctx = { workspace: Boolean(workspace), cwd, homeDir, env };
  const mcpGlobalOnly = Boolean(ctx.workspace && spec.globalOnlyMcp);
  return {
    harness: spec.id,
    label: spec.label,
    format: spec.format,
    urlField: spec.urlField || 'url',
    includeTypeHttp: Boolean(spec.includeTypeHttp),
    mcpPath: spec.resolveMcpPath(mcpGlobalOnly ? { ...ctx, workspace: false } : ctx),
    mcpGlobalOnly,
    // In project files the key is referenced through ANOSYS_MCP_API_KEY, never written.
    keyFromEnv: Boolean(ctx.workspace && !mcpGlobalOnly),
    workspaceKeyRef: spec.workspaceKeyRef || null,
    skillPath: spec.resolveSkillPath(ctx),
  };
}

function backupFile(filePath) {
  if (!fs.existsSync(filePath)) return null;
  const ts = new Date().toISOString().replace(/[-:T.]/g, '').slice(0, 14);
  const backupPath = `${filePath}.${ts}.bak`;
  fs.copyFileSync(filePath, backupPath);
  try { fs.chmodSync(backupPath, 0o600); } catch { /* best-effort */ }
  return backupPath;
}

function writePrivateAtomic(filePath, content) {
  const dir = path.dirname(filePath);
  fs.mkdirSync(dir, { recursive: true });
  const tmpPath = path.join(dir, `.tmp_${Date.now()}_${Math.random().toString(36).slice(2)}`);
  try {
    fs.writeFileSync(tmpPath, content, { encoding: 'utf8', mode: 0o600 });
    fs.renameSync(tmpPath, filePath);
  } catch (err) {
    try { fs.unlinkSync(tmpPath); } catch { /* ignore */ }
    throw err;
  }
}

function readJsonStrict(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const raw = fs.readFileSync(filePath, 'utf8').trim();
  if (!raw) return {};
  const parsed = JSON.parse(raw);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${filePath} must contain a JSON object`);
  }
  return parsed;
}

function escapeTomlString(value) {
  return String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function stripCodexMcpTomlSection(content, serverName = MCP_SERVER_NAME) {
  if (!content) return '';
  const lines = content.split(/\r?\n/);
  const kept = [];
  const exactHeaders = new Set([
    `[mcp_servers.${serverName}]`,
    `[mcp_servers."${serverName}"]`,
    `[mcp_servers.${serverName}.http_headers]`,
    `[mcp_servers."${serverName}".http_headers]`,
  ]);
  let skipping = false;
  for (const line of lines) {
    const trimmed = line.trim();
    if (/^\[[^\]]+\]$/.test(trimmed)) {
      skipping = exactHeaders.has(trimmed);
      if (skipping) continue;
    }
    if (!skipping) kept.push(line);
  }
  return kept.join('\n').replace(/\n{3,}/g, '\n\n').trimEnd();
}

function buildCodexMcpTomlBlock(url, mcpKey, serverName = MCP_SERVER_NAME, { keyFromEnv = false } = {}) {
  if (keyFromEnv) {
    return [
      `[mcp_servers.${serverName}]`,
      `url = "${escapeTomlString(url)}"`,
      `bearer_token_env_var = "${MCP_KEY_ENV}"`,
    ].join('\n');
  }
  return [
    `[mcp_servers.${serverName}]`,
    `url = "${escapeTomlString(url)}"`,
    '',
    `[mcp_servers.${serverName}.http_headers]`,
    `"Authorization" = "Bearer ${escapeTomlString(mcpKey)}"`,
  ].join('\n');
}

function hasCodexMcpTomlSection(content, serverName = MCP_SERVER_NAME) {
  if (!content) return false;
  const escaped = serverName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`^\\[mcp_servers\\."?${escaped}"?\\]\\s*$`, 'm').test(content);
}

function installMcpClient({
  harness,
  mcpKey = '',
  mcpUrl = DEFAULT_MCP_URL,
  workspace = false,
  cwd = process.cwd(),
  homeDir = os.homedir(),
  env = process.env,
  installMcp = true,
  installSkill = true,
  serverName = MCP_SERVER_NAME,
} = {}) {
  const target = resolveMcpTargets(harness, { workspace, cwd, homeDir, env });
  const result = {
    harness: target.harness,
    label: target.label,
    mcpPath: target.mcpPath,
    skillPath: target.skillPath,
    mcpUpdated: false,
    skillUpdated: false,
    mcpBackupPath: null,
    mcpUrl: null,
    keyFromEnv: target.keyFromEnv,
    mcpGlobalOnly: target.mcpGlobalOnly,
  };

  if (installMcp) {
    const keyCheck = validateMcpKeyFormat(mcpKey);
    if (!keyCheck.ok) {
      const err = new Error(keyCheck.message);
      err.code = keyCheck.code;
      throw err;
    }
    const urlCheck = validateMcpUrl(mcpUrl);
    if (!urlCheck.ok) {
      throw new Error(urlCheck.message);
    }
    result.mcpUrl = urlCheck.url;

    result.mcpBackupPath = backupFile(target.mcpPath);

    if (target.format === 'codex-toml') {
      const existing = fs.existsSync(target.mcpPath) ? fs.readFileSync(target.mcpPath, 'utf8') : '';
      const stripped = stripCodexMcpTomlSection(existing, serverName);
      const block = buildCodexMcpTomlBlock(urlCheck.url, keyCheck.key, serverName, { keyFromEnv: target.keyFromEnv });
      const next = (stripped ? `${stripped}\n\n${block}` : block) + '\n';
      writePrivateAtomic(target.mcpPath, next);
      result.mcpUpdated = true;
    } else {
      const data = readJsonStrict(target.mcpPath);
      if (!data.mcpServers || typeof data.mcpServers !== 'object' || Array.isArray(data.mcpServers)) {
        data.mcpServers = {};
      }
      const entry = {};
      if (target.includeTypeHttp) entry.type = 'http';
      entry[target.urlField] = urlCheck.url;
      const keyValue = target.keyFromEnv ? target.workspaceKeyRef : keyCheck.key;
      entry.headers = { Authorization: `Bearer ${keyValue}` };
      data.mcpServers[serverName] = entry;
      writePrivateAtomic(target.mcpPath, JSON.stringify(data, null, 2) + '\n');
      result.mcpUpdated = true;
    }
  }

  if (installSkill) {
    writePrivateAtomic(target.skillPath, PLATFORM_INTELLIGENCE_SKILL_MD);
    result.skillUpdated = true;
  }

  return result;
}

function uninstallMcpClient({
  harness,
  workspace = false,
  cwd = process.cwd(),
  homeDir = os.homedir(),
  env = process.env,
  removeMcp = true,
  removeSkill = true,
  serverName = MCP_SERVER_NAME,
} = {}) {
  const target = resolveMcpTargets(harness, { workspace, cwd, homeDir, env });
  const result = {
    harness: target.harness,
    mcpPath: target.mcpPath,
    skillPath: target.skillPath,
    mcpRemoved: false,
    skillRemoved: false,
    mcpBackupPath: null,
  };

  if (removeMcp && fs.existsSync(target.mcpPath)) {
    if (target.format === 'codex-toml') {
      const existing = fs.readFileSync(target.mcpPath, 'utf8');
      if (hasCodexMcpTomlSection(existing, serverName)) {
        result.mcpBackupPath = backupFile(target.mcpPath);
        const next = stripCodexMcpTomlSection(existing, serverName);
        writePrivateAtomic(target.mcpPath, next ? `${next}\n` : '');
        result.mcpRemoved = true;
      }
    } else {
      const data = readJsonStrict(target.mcpPath);
      if (data.mcpServers && typeof data.mcpServers === 'object' && Object.prototype.hasOwnProperty.call(data.mcpServers, serverName)) {
        result.mcpBackupPath = backupFile(target.mcpPath);
        delete data.mcpServers[serverName];
        if (Object.keys(data.mcpServers).length === 0) delete data.mcpServers;
        writePrivateAtomic(target.mcpPath, JSON.stringify(data, null, 2) + '\n');
        result.mcpRemoved = true;
      }
    }
  }

  if (removeSkill && fs.existsSync(target.skillPath)) {
    fs.rmSync(target.skillPath, { force: true });
    const skillDir = path.dirname(target.skillPath);
    try {
      if (fs.readdirSync(skillDir).length === 0) fs.rmdirSync(skillDir);
    } catch { /* ignore */ }
    result.skillRemoved = true;
  }

  return result;
}

function getMcpClientStatus({
  harness,
  workspace = false,
  cwd = process.cwd(),
  homeDir = os.homedir(),
  env = process.env,
  serverName = MCP_SERVER_NAME,
} = {}) {
  const target = resolveMcpTargets(harness, { workspace, cwd, homeDir, env });
  let mcpInstalled = false;
  let mcpUrl = null;

  if (fs.existsSync(target.mcpPath)) {
    if (target.format === 'codex-toml') {
      const raw = fs.readFileSync(target.mcpPath, 'utf8');
      mcpInstalled = hasCodexMcpTomlSection(raw, serverName);
      if (mcpInstalled) {
        const escaped = serverName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const sectionMatch = raw.match(new RegExp(`^\\[mcp_servers\\."?${escaped}"?\\]\\s*$([\\s\\S]*?)(?:^\\[|(?![\\s\\S]))`, 'm'));
        const urlMatch = sectionMatch && sectionMatch[1].match(/^\s*url\s*=\s*"([^"]+)"/m);
        mcpUrl = urlMatch ? urlMatch[1] : null;
      }
    } else {
      try {
        const data = readJsonStrict(target.mcpPath);
        const entry = data.mcpServers && data.mcpServers[serverName];
        if (entry && typeof entry === 'object') {
          mcpInstalled = true;
          mcpUrl = entry[target.urlField] || entry.url || entry.serverUrl || null;
        }
      } catch {
        mcpInstalled = false;
      }
    }
  }

  return {
    harness: target.harness,
    label: target.label,
    mcpPath: target.mcpPath,
    skillPath: target.skillPath,
    mcpInstalled,
    mcpUrl,
    skillInstalled: fs.existsSync(target.skillPath),
  };
}

function parseMcpCliArgs(argv) {
  const parsed = {
    action: null,
    targets: [],
    mcpKey: '',
    mcpUrl: DEFAULT_MCP_URL,
    workspace: false,
    withMcp: false,
    withSkill: false,
    skillOnly: false,
    noSkill: false,
    yes: false,
    help: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if ((a === '--target' || a === '-t') && argv[i + 1]) {
      parsed.targets.push(
        ...argv[++i]
          .split(',')
          .map((x) => x.trim())
          .filter(Boolean)
      );
    } else if (a.startsWith('--target=')) {
      parsed.targets.push(
        ...a
          .slice('--target='.length)
          .split(',')
          .map((x) => x.trim())
          .filter(Boolean)
      );
    } else if (a === '--mcp-key' && argv[i + 1]) {
      parsed.mcpKey = argv[++i].trim();
    } else if (a.startsWith('--mcp-key=')) {
      parsed.mcpKey = a.slice('--mcp-key='.length).trim();
    } else if (a === '--mcp-url' && argv[i + 1]) {
      parsed.mcpUrl = argv[++i].trim();
    } else if (a.startsWith('--mcp-url=')) {
      parsed.mcpUrl = a.slice('--mcp-url='.length).trim();
    } else if (a === '--workspace') {
      parsed.workspace = true;
    } else if (a === '--with-mcp') {
      parsed.withMcp = true;
    } else if (a === '--with-skill') {
      parsed.withSkill = true;
    } else if (a === '--skill-only') {
      parsed.skillOnly = true;
      parsed.withSkill = true;
    } else if (a === '--no-skill') {
      parsed.noSkill = true;
    } else if (a === '-y' || a === '--yes' || a === '--non-interactive') {
      parsed.yes = true;
    } else if (a === '-h' || a === '--help' || a === 'help') {
      parsed.help = true;
    } else if (!a.startsWith('-') && !parsed.action) {
      if (a === 'mcp') continue;
      parsed.action = a;
    }
  }
  return parsed;
}

function expandTargets(rawTargets, defaultHarness) {
  const list = rawTargets && rawTargets.length ? rawTargets : [defaultHarness];
  const expanded = [];
  for (const t of list) {
    if (t === 'all') {
      for (const h of supportedMcpHarnesses()) {
        if (!expanded.includes(h)) expanded.push(h);
      }
    } else if (!expanded.includes(t)) {
      expanded.push(t);
    }
  }
  return expanded;
}

function resolveMcpKeyFromEnv(env = process.env) {
  if (!env) return '';
  return String(env.ANOSYS_MCP_API_KEY || env.ANOSYS_MCP_KEY || '').trim();
}

function promptHidden(query, { input = process.stdin, output = process.stdout } = {}) {
  if (!input || !output || !input.isTTY || !output.isTTY) {
    const rl = readline.createInterface({ input, output });
    return new Promise((resolve) => {
      rl.question(query, (ans) => {
        rl.close();
        resolve(String(ans || '').trim());
      });
    });
  }

  let muted = false;
  const mutedOutput = new Writable({
    write(chunk, encoding, callback) {
      if (!muted) {
        output.write(chunk, encoding, callback);
      } else {
        callback();
      }
    },
  });

  const rl = readline.createInterface({
    input,
    output: mutedOutput,
    terminal: true,
  });

  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      muted = false;
      output.write('\n');
      rl.close();
      resolve(String(value || '').trim());
    };
    rl.on('SIGINT', () => finish(''));
    // Show the prompt first, then mute everything readline echoes (the key itself).
    output.write(query);
    muted = true;
    rl.question('', finish);
  });
}

function mcpInstallNotes(res) {
  const notes = [];
  if (res.keyFromEnv) {
    notes.push(`  The project config reads the key from $${MCP_KEY_ENV}; the key itself is not written to the project.`);
    notes.push(`  Export ${MCP_KEY_ENV} in the shell that starts ${res.label}.`);
  }
  if (res.mcpGlobalOnly) {
    notes.push(`  ${res.label} cannot read the key from the environment, so the MCP server was registered in your user config (${res.mcpPath}), not in the project.`);
  }
  return notes;
}

async function applyInstallMcpOptions({
  harness,
  withMcp = false,
  withSkill = false,
  skillOnly = false,
  mcpKey = '',
  mcpUrl = DEFAULT_MCP_URL,
  workspace = false,
  noSkill = false,
  yes = false,
  nonInteractive = false,
  homeDir = os.homedir(),
  cwd = process.cwd(),
  promptFn = null,
} = {}) {
  const isNonInteractive = Boolean(nonInteractive || yes);
  const resolvedKey = (mcpKey || resolveMcpKeyFromEnv()).trim();
  const wantMcp = Boolean(!skillOnly && (withMcp || resolvedKey));
  const explicitSkillOnly = Boolean(withSkill || skillOnly);
  const wantSkill = Boolean(explicitSkillOnly || (wantMcp && !noSkill));
  if (!wantMcp && !explicitSkillOnly) return null;

  let keyToUse = resolvedKey;
  let promptedBlankForSkillOnly = false;
  if (wantMcp && !keyToUse && !isNonInteractive && typeof promptFn === 'function') {
    keyToUse = (await promptFn('AnoSys MCP API key (ak_mcp_..., leave blank for skill only): ')).trim();
    if (!keyToUse && !noSkill) {
      promptedBlankForSkillOnly = true;
    }
  }

  const shouldInstallMcp = Boolean(wantMcp && keyToUse);
  if (wantMcp && !keyToUse && !explicitSkillOnly && !promptedBlankForSkillOnly) {
    throw new Error('Missing --mcp-key (ak_mcp_...). Mint one at https://console.anosys.ai or pass --with-skill.');
  }
  if (wantMcp && !keyToUse && (explicitSkillOnly || promptedBlankForSkillOnly)) {
    console.log('⚠️  No MCP key provided; installing SKILL.md only. Re-run with --mcp-key ak_mcp_... when ready.');
  }

  const res = installMcpClient({
    harness,
    mcpKey: keyToUse,
    mcpUrl,
    workspace,
    cwd,
    homeDir,
    installMcp: shouldInstallMcp,
    installSkill: wantSkill,
  });
  if (res.mcpUpdated) {
    console.log(`  MCP server '${MCP_SERVER_NAME}' -> ${res.mcpPath} (${res.mcpUrl})`);
    for (const line of mcpInstallNotes(res)) console.log(line);
  }
  if (res.skillUpdated) {
    console.log(`  AI Skill '${SKILL_NAME}' -> ${res.skillPath}`);
  }
  return res;
}

async function runMcpSubcommand({ defaultHarness = 'claude-code', argv = [], promptFn = null, cliName = 'anosys-sdk-mcp' } = {}) {
  const opts = parseMcpCliArgs(argv);
  if (opts.help || !opts.action) {
    console.log(`
Usage: ${cliName} [mcp] <install|status|uninstall> [options]

Options:
  --mcp-key <ak_mcp_...>   Scoped AnoSys MCP API key (or set ANOSYS_MCP_API_KEY / ANOSYS_MCP_KEY)
  --mcp-url <url>          MCP endpoint URL (default: ${DEFAULT_MCP_URL})
  --target <harness>       ${supportedMcpHarnesses().join(', ')}, or all (default: ${defaultHarness})
  --workspace              Write project-local config instead of user-global config
  --skill-only             Install only SKILL.md (no MCP key required)
  --no-skill               Skip writing SKILL.md
  -y, --yes                Non-interactive mode
`);
    return 0;
  }

  const targets = expandTargets(opts.targets, defaultHarness);
  if (opts.action === 'install') {
    let keyToUse = (opts.mcpKey || resolveMcpKeyFromEnv()).trim();
    let fallbackSkillOnly = Boolean(opts.skillOnly);
    if (!fallbackSkillOnly && !keyToUse && !opts.yes && typeof promptFn === 'function') {
      keyToUse = (await promptFn('AnoSys MCP API key (ak_mcp_..., leave blank for --skill-only): ')).trim();
      if (!keyToUse && !opts.noSkill) {
        fallbackSkillOnly = true;
        console.log('⚠️  No MCP key provided; installing SKILL.md only. Re-run with --mcp-key ak_mcp_... when ready.');
      }
    }
    const installMcp = !fallbackSkillOnly && Boolean(keyToUse || opts.mcpKey);
    if (!fallbackSkillOnly && !keyToUse) {
      throw new Error('Missing --mcp-key (ak_mcp_...). Mint an MCP key in AnoSys Console, or pass --skill-only.');
    }
    for (const h of targets) {
      const res = installMcpClient({
        harness: h,
        mcpKey: keyToUse,
        mcpUrl: opts.mcpUrl,
        workspace: opts.workspace,
        installMcp,
        installSkill: !opts.noSkill,
      });
      console.log(`✅ [${res.label}]`);
      if (res.mcpUpdated) {
        console.log(`   MCP config: ${res.mcpPath} -> ${res.mcpUrl}`);
        for (const line of mcpInstallNotes(res)) console.log(` ${line}`);
      }
      if (res.skillUpdated) console.log(`   SKILL.md:   ${res.skillPath}`);
    }
    return 0;
  }

  if (opts.action === 'uninstall') {
    for (const h of targets) {
      const res = uninstallMcpClient({ harness: h, workspace: opts.workspace });
      console.log(`[${h}] mcpRemoved=${res.mcpRemoved} skillRemoved=${res.skillRemoved}`);
    }
    return 0;
  }

  if (opts.action === 'status') {
    for (const h of targets) {
      const st = getMcpClientStatus({ harness: h, workspace: opts.workspace });
      console.log(`[${st.label}]`);
      console.log(`  MCP server: ${st.mcpInstalled ? `✅ ${st.mcpUrl}` : '❌ not configured'} (${st.mcpPath})`);
      console.log(`  SKILL.md:   ${st.skillInstalled ? '✅ installed' : '❌ not installed'} (${st.skillPath})`);
    }
    return 0;
  }

  console.error(`Unknown mcp command: ${opts.action}`);
  return 1;
}

module.exports = {
  DEFAULT_MCP_URL,
  MCP_KEY_ENV,
  MCP_SERVER_NAME,
  SKILL_NAME,
  PLATFORM_INTELLIGENCE_SKILL_MD,
  supportedMcpHarnesses,
  isUuidLikeKey,
  validateMcpKeyFormat,
  validateMcpUrl,
  resolveMcpTargets,
  installMcpClient,
  uninstallMcpClient,
  getMcpClientStatus,
  parseMcpCliArgs,
  resolveMcpKeyFromEnv,
  promptHidden,
  applyInstallMcpOptions,
  runMcpSubcommand,
};
