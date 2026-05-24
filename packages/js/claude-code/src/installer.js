/**
 * Safely patch ~/.claude/settings.json with AnoSys-managed values.
 * Handles idempotent install/uninstall of the AnoSys Stop hook using
 * the {"owner": "anosys"} marker for safe roundtrip updates.
 */

'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');

const ANOSYS_ENV_KEYS = new Set([
  'ANOSYS_HOOK_ENDPOINT_URL',
  'ANOSYS_HOOK_API_KEY',
  'ANOSYS_HOOK_APIKEY',
  'ANOSYS_CLAUDE_PIXEL',
  'ANOSYS_HOOK_DRY_RUN',
  'CLAUDE_CODE_ENABLE_TELEMETRY',
  'OTEL_SERVICE_NAME',
  'OTEL_TRACES_EXPORTER',
  'OTEL_METRICS_EXPORTER',
  'OTEL_LOGS_EXPORTER',
  'OTEL_EXPORTER_OTLP_PROTOCOL',
  'OTEL_EXPORTER_OTLP_ENDPOINT',
  'OTEL_EXPORTER_OTLP_HEADERS',
  'OTEL_EXPORTER_OTLP_ANOSYS_APIKEY', // legacy — kept for clean uninstall
]);

const SETTINGS_PATH = path.join(os.homedir(), '.claude', 'settings.json');
const BACKUP_PATH = SETTINGS_PATH + '.bak';

function loadSettings(filePath = SETTINGS_PATH) {
  if (!fs.existsSync(filePath)) return {};
  const content = fs.readFileSync(filePath, 'utf8').trim();
  if (!content) return {};
  try {
    return JSON.parse(content);
  } catch (err) {
    console.error(`ERROR: ${filePath} contains invalid JSON and cannot be parsed safely.\n  ${err.message}\nPlease fix the file manually and re-run the installer.`);
    process.exit(1);
  }
}

function backup(filePath = SETTINGS_PATH) {
  if (fs.existsSync(filePath)) {
    const timestamp = new Date().toISOString().replace(/[^0-9]/g, '').slice(0, 14);
    const backupPath = `${filePath}.${timestamp}.bak`;
    fs.copyFileSync(filePath, backupPath);
    return backupPath;
  }
  return null;
}

function writeAtomic(filePath, data) {
  const dir = path.dirname(filePath);
  fs.mkdirSync(dir, { recursive: true });
  const tmpPath = filePath + '.tmp.' + process.pid;
  try {
    fs.writeFileSync(tmpPath, JSON.stringify(data, null, 2) + '\n', 'utf8');
    fs.renameSync(tmpPath, filePath);
  } catch (err) {
    try { fs.unlinkSync(tmpPath); } catch (_) { }
    throw err;
  }
}

function updateEnv(settings, newEnv) {
  const env = Object.assign({}, settings.env || {});
  for (const key of ANOSYS_ENV_KEYS) {
    delete env[key];
  }
  Object.assign(env, newEnv);
  settings.env = env;
  return settings;
}

function removeEnv(settings) {
  const env = Object.assign({}, settings.env || {});
  for (const key of ANOSYS_ENV_KEYS) {
    delete env[key];
  }
  settings.env = env;
  return settings;
}

function isAnosysHookEntry(entry) {
  if (!entry || typeof entry !== 'object') return false;
  return String(entry.owner || '').toLowerCase() === 'anosys';
}

function stripAnosysFromGroup(group) {
  if (!group || typeof group !== 'object') return group;
  const inner = group.hooks;
  if (!Array.isArray(inner)) return group;
  const cleaned = inner.filter(h => !isAnosysHookEntry(h));
  if (cleaned.length === 0) return null;
  return Object.assign({}, group, { hooks: cleaned });
}

function updateStopHooks(settings, hookCommand) {
  if (!settings.hooks || typeof settings.hooks !== 'object') {
    settings.hooks = {};
  }
  let stopGroups = settings.hooks.Stop;
  if (!Array.isArray(stopGroups)) stopGroups = [];
  const cleanedGroups = stopGroups
    .map(stripAnosysFromGroup)
    .filter(g => g !== null);
  cleanedGroups.push({
    hooks: [
      {
        owner: 'anosys',
        type: 'command',
        command: hookCommand,
      },
    ],
  });
  settings.hooks.Stop = cleanedGroups;
  return settings;
}

function removeStopHooks(settings) {
  if (!settings.hooks || typeof settings.hooks !== 'object') return settings;
  let stopGroups = settings.hooks.Stop;
  if (!Array.isArray(stopGroups)) return settings;
  const cleanedGroups = stopGroups
    .map(stripAnosysFromGroup)
    .filter(g => g !== null);
  settings.hooks.Stop = cleanedGroups;
  return settings;
}

function hasAnosysHook(settings) {
  const hooksSection = settings.hooks || {};
  const stopGroups = hooksSection.Stop || [];
  if (!Array.isArray(stopGroups)) return false;
  for (const group of stopGroups) {
    if (!group || typeof group !== 'object') continue;
    const inner = group.hooks || [];
    for (const h of inner) {
      if (isAnosysHookEntry(h)) return true;
    }
  }
  return false;
}

function getAnosysHookCommand(settings) {
  const hooksSection = settings.hooks || {};
  const stopGroups = hooksSection.Stop || [];
  if (!Array.isArray(stopGroups)) return null;
  for (const group of stopGroups) {
    if (!group || typeof group !== 'object') continue;
    const inner = group.hooks || [];
    for (const h of inner) {
      if (isAnosysHookEntry(h)) return h.command;
    }
  }
  return null;
}

module.exports = {
  SETTINGS_PATH,
  BACKUP_PATH,
  loadSettings,
  backup,
  writeAtomic,
  updateEnv,
  removeEnv,
  updateStopHooks,
  removeStopHooks,
  hasAnosysHook,
  getAnosysHookCommand,
};
