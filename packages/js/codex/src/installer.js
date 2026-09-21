'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');
const https = require('https');

const HOOK_COMMAND = 'anosys-codex run';
const INGESTION_URL = 'https://api.anosys.ai/ingestion';

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
    return backupPath;
  }
  return null;
}

function loadToml(filePath) {
  if (!fs.existsSync(filePath)) return {};
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const result = {};
    const notifyMatch = content.match(/^\s*notify\s*=\s*\[(.*?)\]/ms);
    if (notifyMatch) {
      const items = [];
      const regex = /["']([^"']+)["']/g;
      let match;
      while ((match = regex.exec(notifyMatch[1])) !== null) {
        items.push(match[1]);
      }
      result.notify = items;
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

function hasAnosysHook(data) {
  const notifyList = data.notify;
  if (Array.isArray(notifyList)) {
    return notifyList.some(x => String(x).includes('anosys-codex'));
  }
  return false;
}

function updateCodexConfig(hookCmd, customPath) {
  const cmd = hookCmd || HOOK_COMMAND;
  const filePath = customPath || getConfigPath();
  const data = loadToml(filePath);

  let notifyList = data.notify || [];
  if (notifyList.includes(cmd)) {
    return false; // already present
  }

  notifyList = notifyList.filter(x => !String(x).includes('anosys-codex'));
  notifyList.push(cmd);
  data.notify = notifyList;

  writeTomlAtomic(filePath, data);
  return true;
}

function removeCodexConfig(customPath) {
  const filePath = customPath || getConfigPath();
  if (!fs.existsSync(filePath)) return false;

  const data = loadToml(filePath);
  let notifyList = data.notify || [];
  const prevLen = notifyList.length;

  notifyList = notifyList.filter(x => !String(x).includes('anosys-codex'));
  if (notifyList.length === prevLen) return false;

  data.notify = notifyList;
  writeTomlAtomic(filePath, data);
  return true;
}

function updateCodexEnv({ apiKey = '', redaction = false, endpointUrl = INGESTION_URL, customPath }) {
  const filePath = customPath || getEnvPath();
  const dir = path.dirname(filePath);
  fs.mkdirSync(dir, { recursive: true });

  const lines = [
    '# AnoSys Codex CLI configuration',
    `export ANOSYS_HOOK_ENDPOINT_URL="${endpointUrl}"`,
    `export REDACTION="${redaction ? 'true' : 'false'}"`
  ];
  if (apiKey) {
    lines.push(`export ANOSYS_HOOK_APIKEY="${apiKey}"`);
  }

  fs.writeFileSync(filePath, lines.join('\n') + '\n', { encoding: 'utf8', mode: 0o600 });
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

function validateApiKey(apiKey, keyType = 'codex') {
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
          resolve(Boolean(parsed && parsed.apiUrl));
        } catch (_) {
          resolve(false);
        }
      });
    }).on('error', () => resolve(false));
  });
}

module.exports = {
  HOOK_COMMAND,
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
