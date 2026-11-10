'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const https = require('https');

const HOOK_COMMAND = 'anosys-codex run'; // legacy form, still recognized on uninstall
const INGESTION_URL = 'https://api.anosys.ai/ingestion';
// Markers of every hook form this package (Python or JS) has ever written
const HOOK_MARKERS = ['anosys-codex', 'anosys_sdk_codex', 'anosys-sdk-codex'];
// Codex runs a single notify command; another one already configured is kept
// and called after ours (the convention the Codex Computer Use wrapper uses).
const PREVIOUS_NOTIFY_FLAG = '--previous-notify';

/** The notify command: this Node binary and our CLI by absolute path, never a bare PATH lookup. */
function hookCommand() {
  return [process.execPath, path.join(__dirname, 'cli.js'), 'run'];
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
const NOTIFY_LINE = /^[ \t]*notify[ \t]*=[^\n]*(?:\n|$)/m;

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
  if (NOTIFY_LINE.test(content)) next = content.replace(NOTIFY_LINE, line);
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
  validateApiKey
};
