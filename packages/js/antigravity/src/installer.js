/**
 * Safely manage Antigravity hooks in ~/.gemini/config/hooks.json or .agents/hooks.json.
 */

const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');
const {
  GLOBAL_CONFIG_DIR,
  GLOBAL_HOOKS_FILE,
  GLOBAL_ENV_FILE,
  HOOK_NAME,
  HOOK_COMMAND,
  HOOK_TIMEOUT_SECONDS,
  DEFAULT_INGESTION_URL,
  EVENTS,
} = require('./constants');

function getHooksPath(workspace = false, customPath = null) {
  if (customPath) return customPath;
  if (workspace) return path.join(process.cwd(), '.agents', 'hooks.json');
  return GLOBAL_HOOKS_FILE;
}

function getEnvPath(workspace = false, customPath = null) {
  if (customPath) return customPath;
  if (workspace) return path.join(process.cwd(), '.agents', 'anosys-env.json');
  return GLOBAL_ENV_FILE;
}

function loadJson(filePath) {
  if (!fs.existsSync(filePath)) return {};
  try {
    const raw = fs.readFileSync(filePath, 'utf-8').trim();
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return typeof parsed === 'object' && parsed !== null ? parsed : {};
  } catch (err) {
    console.error(`ERROR: ${filePath} contains invalid JSON.\n  ${err.message}`);
    process.exit(1);
  }
}

function writeJsonAtomic(filePath, data) {
  const dir = path.dirname(filePath);
  fs.mkdirSync(dir, { recursive: true });
  const tmpPath = path.join(dir, `.hooks_${Date.now()}_${Math.random().toString(36).slice(2)}.tmp`);
  try {
    fs.writeFileSync(tmpPath, JSON.stringify(data, null, 2) + '\n', 'utf-8');
    fs.renameSync(tmpPath, filePath);
  } catch (err) {
    try { fs.unlinkSync(tmpPath); } catch {}
    throw err;
  }
}

function backup(filePath) {
  if (fs.existsSync(filePath)) {
    const ts = new Date().toISOString().replace(/[-:T.]/g, '').slice(0, 14);
    const backupPath = `${filePath}.${ts}.bak`;
    fs.copyFileSync(filePath, backupPath);
    return backupPath;
  }
  return null;
}

function hasAnosysHook(data) {
  if (!data || typeof data !== 'object') return false;
  const block = data[HOOK_NAME];
  if (!block || typeof block !== 'object') return false;
  return EVENTS.some(ev => Array.isArray(block[ev]));
}

function updateHooksConfig(hooksPath, command = HOOK_COMMAND) {
  const data = loadJson(hooksPath);

  const hookBlock = {};
  for (const ev of EVENTS) {
    let subcmd = ev.toLowerCase();
    if (subcmd === 'preinvocation') subcmd = 'pre_invocation';
    hookBlock[ev] = [
      {
        type: 'command',
        command: `${command} ${subcmd}`,
        timeout: HOOK_TIMEOUT_SECONDS,
      },
    ];
  }

  data[HOOK_NAME] = hookBlock;
  writeJsonAtomic(hooksPath, data);
  return true;
}

function removeHooksConfig(hooksPath) {
  if (!fs.existsSync(hooksPath)) return false;
  const data = loadJson(hooksPath);
  if (data[HOOK_NAME]) {
    delete data[HOOK_NAME];
    if (Object.keys(data).length === 0) {
      try {
        fs.unlinkSync(hooksPath);
      } catch {
        writeJsonAtomic(hooksPath, {});
      }
    } else {
      writeJsonAtomic(hooksPath, data);
    }
    return true;
  }
  return false;
}

function updateEnvConfig(envPath, { apiKey = '', endpointUrl = DEFAULT_INGESTION_URL, redaction = false } = {}) {
  const config = {
    ANOSYS_HOOK_APIKEY: apiKey,
    ANOSYS_HOOK_ENDPOINT_URL: endpointUrl,
    REDACTION: redaction ? 'true' : 'false',
  };
  writeJsonAtomic(envPath, config);
  try {
    fs.chmodSync(envPath, 0o600);
  } catch {}
}

function removeEnvConfig(envPath) {
  if (fs.existsSync(envPath)) {
    try {
      fs.unlinkSync(envPath);
      return true;
    } catch {
      return false;
    }
  }
  return false;
}

function validateApiKey(apiKey, keyType = 'cc') {
  return new Promise(resolve => {
    if (!apiKey) return resolve(false);
    try {
      const url = `https://console.anosys.ai/api/resolveapikeys?apikey=${encodeURIComponent(apiKey)}`;
      const client = url.startsWith('https') ? https : http;
      const req = client.get(url, { headers: { 'User-Agent': 'anosys-antigravity-installer' }, timeout: 10000 }, res => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          return resolve(false);
        }
        let body = '';
        res.on('data', chunk => { body += chunk; });
        res.on('end', () => {
          try {
            const data = JSON.parse(body);
            const apiUrl = data.apiUrl || '';
            const lower = String(keyType).toLowerCase();
            if (['cc', 'claudecode', 'codex', 'antigravity'].includes(lower)) {
              return resolve(apiUrl.includes('/cc/'));
            }
            if (['t', 'otel'].includes(lower)) {
              return resolve(apiUrl.includes('/t/'));
            }
            return resolve(false);
          } catch {
            return resolve(false);
          }
        });
      });
      req.on('error', () => resolve(false));
      req.on('timeout', () => {
        req.destroy();
        resolve(false);
      });
    } catch {
      resolve(false);
    }
  });
}

module.exports = {
  getHooksPath,
  getEnvPath,
  loadJson,
  writeJsonAtomic,
  backup,
  hasAnosysHook,
  updateHooksConfig,
  removeHooksConfig,
  updateEnvConfig,
  removeEnvConfig,
  validateApiKey,
};
