'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const https = require('https');
const { hookCliCommand } = require('anosys-sdk-core');

const HOOK_COMMAND = 'anosys-codex run'; // legacy form, still recognized on uninstall
const INGESTION_URL = 'https://api.anosys.ai/ingestion';
// Markers of every hook form this package (Python or JS) has ever written
const HOOK_MARKERS = ['anosys-codex', 'anosys_sdk_codex', 'anosys-sdk-codex'];
// Codex runs a single notify command; another one already configured is kept
// and called after ours (the convention the Codex Computer Use wrapper uses).
const PREVIOUS_NOTIFY_FLAG = '--previous-notify';

/** The notify command: this Node binary and our CLI by absolute path (installed bin when run through npx). */
function hookCommand() {
  return hookCliCommand({ cliPath: path.join(__dirname, 'cli.js'), binName: 'anosys-codex', packageName: 'anosys-sdk-codex' });
}

function getCodexHome() {
  const custom = (process.env.CODEX_HOME || '').trim();
  if (custom) {
    return path.resolve(custom.replace(/^~(?=$|\/|\\)/, os.homedir()));
  }
  return path.join(os.homedir(), '.codex');
}

function getConfigPath() {
  return path.join(getCodexHome(), 'config.toml');
}

function getEnvPath() {
  return path.join(getCodexHome(), 'anosys-env.sh');
}

function backup(customPath) {
  const filePath = customPath || getConfigPath();
  if (fs.existsSync(filePath)) {
    const timestamp = new Date().toISOString().replace(/[-:T.]/g, '').slice(0, 14);
    const backupPath = `${filePath}.${timestamp}.bak`;
    fs.copyFileSync(filePath, backupPath);
    try { fs.chmodSync(backupPath, 0o600); } catch { /* backups can hold the API key */ }
    return backupPath;
  }
  return null;
}

function loadToml(filePath) {
  if (!fs.existsSync(filePath)) return {};
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const result = {};
    const notifyMatch = content.match(/^[ \t]*notify[ \t]*=[ \t]*(\[.*\])/m) || content.match(/^\s*notify\s*=\s*\[(.*?)\]/ms);
    if (notifyMatch) {
      try {
        result.notify = JSON.parse(notifyMatch[1]);
      } catch (_) {
        const items = [];
        const regex = /["']([^"']+)["']/g;
        let match;
        while ((match = regex.exec(notifyMatch[1])) !== null) {
          items.push(match[1]);
        }
        result.notify = items;
      }
    }
    return result;
  } catch (err) {
    console.error(`ERROR: Failed to parse TOML at ${filePath}:`, err.message);
    return {};
  }
}

function writeTomlAtomic(filePath, data) {
  const dir = path.dirname(filePath);
  fs.mkdirSync(dir, { recursive: true });

  let lines = [];
  if (Array.isArray(data.notify)) {
    const serialized = data.notify.map(x => `"${x.replace(/"/g, '\\"')}"`).join(', ');
    lines.push(`notify = [${serialized}]`);
  }

  // Preserve or write other sections if any
  for (const [key, value] of Object.entries(data)) {
    if (key === 'notify') continue;
    if (typeof value === 'object' && !Array.isArray(value) && value !== null) {
      lines.push(`\n[${key}]`);
      for (const [subKey, subVal] of Object.entries(value)) {
        lines.push(`${subKey} = "${String(subVal).replace(/"/g, '\\"')}"`);
      }
    } else {
      lines.push(`${key} = "${String(value).replace(/"/g, '\\"')}"`);
    }
  }

  const tmpPath = path.join(dir, `.tmp_${Date.now()}_config.toml`);
  fs.writeFileSync(tmpPath, lines.join('\n') + '\n', 'utf8');
  fs.renameSync(tmpPath, filePath);
}

// Also this copy's own CLI path, which in a source checkout carries no package name
const isOurs = (value) => HOOK_MARKERS.some(m => String(value).includes(m))
  || String(value).includes(path.join(__dirname, 'cli.js'));

/** True if the AnoSys hook appears anywhere in notify, including chained inside another wrapper. */
function hasAnosysHook(data) {
  return isOurs(JSON.stringify(data.notify ?? []));
}

/** The notify command without the AnoSys hook, or null when nothing is left. */
function notifyWithoutOurs(notify) {
  let items = notify;
  if (typeof items === 'string') items = [items];
  if (!Array.isArray(items) || !items.length) return null;
  items = items.map(String);
  const flag = items.indexOf(PREVIOUS_NOTIFY_FLAG);
  const prevValue = flag !== -1 ? items[flag + 1] : null;
  const head = flag !== -1 ? items.slice(0, flag) : items;

  if (head.some(isOurs)) {
    if (!prevValue) return null;
    try {
      const previous = JSON.parse(prevValue);
      return hasAnosysHook({ notify: previous }) ? notifyWithoutOurs(previous) : previous;
    } catch {
      return null;
    }
  }
  if (prevValue && isOurs(prevValue)) {
    let inner = null;
    try { inner = notifyWithoutOurs(JSON.parse(prevValue)); } catch { inner = null; }
    const rest = [...items.slice(0, flag), ...items.slice(flag + 2)];
    return inner ? [...rest, PREVIOUS_NOTIFY_FLAG, JSON.stringify(inner)] : rest;
  }
  return items;
}

// One top-level `notify = [...]` line (its strings may themselves contain brackets)
/**
 * Start and end of the top-level `notify = ...` entry, including a value spanning several
 * lines and brackets inside strings (same as Python _notify_span). Entries inside a
 * [table] are not the top-level key and are ignored.
 */
function notifySpan(content) {
  const header = /^[ \t]*\[/m.exec(content);
  const limit = header ? header.index : content.length;
  const re = /^[ \t]*notify[ \t]*=[ \t]*/gm;
  const m = re.exec(content);
  if (!m || m.index >= limit) return null;
  let i = m.index + m[0].length;
  if (content[i] === '[') {
    let depth = 0;
    let quote = null;
    for (; i < content.length; i++) {
      const ch = content[i];
      if (quote) {
        if (ch === '\\' && quote === '"') i++;
        else if (ch === quote) quote = null;
      } else if (ch === '"' || ch === "'") quote = ch;
      else if (ch === '[') depth++;
      else if (ch === ']' && --depth === 0) break;
    }
  }
  const end = content.indexOf('\n', i);
  return [m.index, end === -1 ? content.length : end + 1];
}

function writeAtomic(filePath, content) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const tmpPath = path.join(path.dirname(filePath), `.tmp_${Date.now()}_config.toml`);
  fs.writeFileSync(tmpPath, content, { encoding: 'utf8', mode: 0o600 });
  fs.renameSync(tmpPath, filePath);
}

function setNotify(filePath, notify) {
  const content = fs.existsSync(filePath) ? fs.readFileSync(filePath, 'utf8') : '';
  const line = notify ? `notify = [${notify.map(v => JSON.stringify(v)).join(', ')}]\n` : '';
  let next;
  const span = notifySpan(content);
  if (span) next = content.slice(0, span[0]) + line + content.slice(span[1]);
  else next = line ? (content ? `${line}\n${content}` : line) : content;
  writeAtomic(filePath, next);
}

/**
 * Register the hook in notify. A notify command already there is kept and
 * chained after ours; re-running replaces an older AnoSys entry.
 */
function updateCodexConfig(hookArgs = null, customPath = null) {
  const filePath = customPath || getConfigPath();
  const data = loadToml(filePath);
  const current = data.notify;
  let existing;
  if (hasAnosysHook(data)) existing = notifyWithoutOurs(current);
  else if (Array.isArray(current) && current.length) existing = current.map(String);
  else existing = typeof current === 'string' && current ? [current] : null;
  const ours = Array.isArray(hookArgs) ? hookArgs : hookCommand();
  const notify = existing ? [...ours, PREVIOUS_NOTIFY_FLAG, JSON.stringify(existing)] : ours;
  if (JSON.stringify(current) === JSON.stringify(notify)) return false;
  setNotify(filePath, notify);
  return true;
}

/** Remove only the AnoSys part of notify; other tools' notify commands stay. */
function removeCodexConfig(customPath = null) {
  const filePath = customPath || getConfigPath();
  if (!fs.existsSync(filePath)) return false;
  const data = loadToml(filePath);
  if (!hasAnosysHook(data)) return false;
  setNotify(filePath, notifyWithoutOurs(data.notify));
  return true;
}

function updateCodexEnv({ apiKey = '', endpointUrl = INGESTION_URL, customPath } = {}) {
  const filePath = customPath || getEnvPath();
  const dir = path.dirname(filePath);
  fs.mkdirSync(dir, { recursive: true });

  const lines = [
    '# AnoSys Codex CLI configuration',
    `export ANOSYS_HOOK_ENDPOINT_URL="${endpointUrl}"`,
  ]; // what is collected is set with `anosys-codex privacy`
  if (apiKey) {
    lines.push(`export ANOSYS_HOOK_APIKEY="${apiKey}"`);
  }

  fs.writeFileSync(filePath, lines.join('\n') + '\n', { encoding: 'utf8', mode: 0o600 });
  fs.chmodSync(filePath, 0o600);
}

function removeCodexEnv(customPath) {
  const filePath = customPath || getEnvPath();
  if (fs.existsSync(filePath)) {
    try {
      fs.unlinkSync(filePath);
      return true;
    } catch (_) {
      return false;
    }
  }
  return false;
}

function validateApiKey(apiKey, keyType = 'cc') {
  return new Promise(resolve => {
    if (!apiKey) return resolve(false);
    const encoded = encodeURIComponent(apiKey);
    const url = `https://console.anosys.ai/api/resolveapikeys?apikey=${encoded}`;

    https.get(url, { headers: { 'User-Agent': 'anosys-codex-installer' }, timeout: 10000 }, res => {
      if (res.statusCode < 200 || res.statusCode >= 300) {
        return resolve(false);
      }
      let body = '';
      res.on('data', chunk => { body += chunk; });
      res.on('end', () => {
        try {
          const parsed = JSON.parse(body);
          const apiUrl = parsed && parsed.apiUrl;
          if (!apiUrl) return resolve(false);
          const lower = String(keyType).toLowerCase();
          if (lower === 'cc' || lower === 'claudecode' || lower === 'codex') {
            return resolve(apiUrl.includes('/cc/'));
          }
          if (lower === 't' || lower === 'otel') {
            return resolve(apiUrl.includes('/t/'));
          }
          return resolve(false);
        } catch (_) {
          resolve(false);
        }
      });
    }).on('error', () => resolve(false));
  });
}

// ── Codex's own OpenTelemetry export (opt-in, --otel-key) ─────────────────────
//
// Codex refuses to start when config.toml is invalid, so this block is only ever
// written after the whole new file has been parsed and checked: the [otel] table
// must come out exactly as intended and every other setting must be unchanged.
// An [otel] table the user wrote themselves is never touched.

const OTEL_BEGIN = '# >>> anosys-codex otel (managed by anosys-codex; remove with: anosys-codex uninstall)';
const OTEL_END = '# <<< anosys-codex otel';
const OTEL_SIGNALS = [['exporter', 'logs'], ['trace_exporter', 'traces'], ['metrics_exporter', 'metrics']];

class OtelConfigError extends Error {}

const tomlStr = (value) => `"${String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;

function otelExpected(otelKey, baseUrl) {
  const expected = { log_user_prompt: false };
  for (const [field, signal] of OTEL_SIGNALS) {
    expected[field] = { 'otlp-http': {
      endpoint: `${baseUrl.replace(/\/+$/, '')}/v1/${signal}`,
      protocol: 'binary',
      headers: { 'anosys-apikey': otelKey },
    } };
  }
  return expected;
}

function otelBlock(otelKey, baseUrl) {
  const lines = [OTEL_BEGIN, '[otel]', 'log_user_prompt = false'];
  for (const [field, signal] of OTEL_SIGNALS) {
    const endpoint = `${baseUrl.replace(/\/+$/, '')}/v1/${signal}`;
    lines.push(`${field} = { otlp-http = { endpoint = ${tomlStr(endpoint)}, protocol = "binary", `
      + `headers = { "anosys-apikey" = ${tomlStr(otelKey)} } } }`);
  }
  lines.push(OTEL_END);
  return lines.join('\n') + '\n';
}

function stripOtelBlock(content) {
  const out = [];
  let inside = false;
  for (const line of content.split(/(?<=\n)/)) {
    const trimmed = line.trim();
    if (trimmed === OTEL_BEGIN) { inside = true; continue; }
    if (inside) {
      if (trimmed === OTEL_END) inside = false;
      continue;
    }
    out.push(line);
  }
  if (inside) throw new OtelConfigError('the Anosys [otel] block in config.toml has no end marker; fix it by hand');
  const text = out.join('');
  // Drop only the blank line we added before the block; leave the rest of the file as it was
  return text.endsWith('\n\n') ? text.slice(0, -1) : text;
}

function parseStrict(content) {
  const { parse } = require('smol-toml');
  try {
    return parse(content);
  } catch (err) {
    throw new OtelConfigError(`config.toml is not valid TOML (${err.message.split('\n')[0]})`);
  }
}

// Plain-data deep equality (TOML values: objects, arrays, strings, numbers, booleans, dates)
function sameData(a, b) {
  return JSON.stringify(sortKeys(a)) === JSON.stringify(sortKeys(b));
}
function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value && typeof value === 'object' && !(value instanceof Date)) {
    return Object.fromEntries(Object.keys(value).sort().map((k) => [k, sortKeys(value[k])]));
  }
  return value;
}
const withoutOtel = (data) => Object.fromEntries(Object.entries(data).filter(([k]) => k !== 'otel'));

function hasAnosysOtel(customPath = null) {
  const filePath = customPath || getConfigPath();
  return fs.existsSync(filePath) && fs.readFileSync(filePath, 'utf8').includes(OTEL_BEGIN);
}

/**
 * Enable Codex's own OTel export to Anosys.ai (logs, traces, metrics) with prompt
 * logging off. Throws OtelConfigError and writes nothing if the result would not be
 * exactly right. Returns true when the file changed.
 */
function updateCodexOtel(otelKey, customPath = null, baseUrl = INGESTION_URL) {
  const filePath = customPath || getConfigPath();
  const original = fs.existsSync(filePath) ? fs.readFileSync(filePath, 'utf8') : '';
  const before = parseStrict(original);
  const base = stripOtelBlock(original);
  const baseParsed = parseStrict(base);
  if (Object.prototype.hasOwnProperty.call(baseParsed, 'otel')) {
    throw new OtelConfigError('config.toml already has an [otel] section that Anosys did not write; '
      + 'it was left unchanged (remove it first, or point its exporters at Anosys.ai yourself)');
  }
  const next = (base.trim() ? base.replace(/\n+$/, '') + '\n\n' : '') + otelBlock(otelKey, baseUrl);
  const after = parseStrict(next);
  if (!sameData(after.otel, otelExpected(otelKey, baseUrl))) {
    throw new OtelConfigError('the generated [otel] section did not parse as expected; nothing was written');
  }
  if (!sameData(withoutOtel(after), withoutOtel(before))) {
    throw new OtelConfigError('writing [otel] would have changed other settings; nothing was written');
  }
  if (next === original) return false;
  writeAtomic(filePath, next);
  return true;
}

/** Remove the Anosys [otel] block; any other [otel] settings are left alone. */
function removeCodexOtel(customPath = null) {
  const filePath = customPath || getConfigPath();
  if (!hasAnosysOtel(filePath)) return false;
  const original = fs.readFileSync(filePath, 'utf8');
  const before = parseStrict(original);
  const next = stripOtelBlock(original);
  const after = parseStrict(next);
  if (!sameData(after, withoutOtel(before))) {
    throw new OtelConfigError('removing the Anosys [otel] block would have changed other settings; nothing was written');
  }
  writeAtomic(filePath, next);
  return true;
}

module.exports = {
  HOOK_COMMAND,
  HOOK_MARKERS,
  PREVIOUS_NOTIFY_FLAG,
  hookCommand,
  notifyWithoutOurs,
  INGESTION_URL,
  getCodexHome,
  getConfigPath,
  getEnvPath,
  backup,
  loadToml,
  writeTomlAtomic,
  hasAnosysHook,
  updateCodexConfig,
  removeCodexConfig,
  updateCodexEnv,
  removeCodexEnv,
  validateApiKey,
  OtelConfigError,
  hasAnosysOtel,
  updateCodexOtel,
  removeCodexOtel,
};
