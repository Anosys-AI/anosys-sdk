#!/usr/bin/env node
'use strict';

const fs = require('fs');
const readline = require('readline');
const { cmdPrivacy, cmdPurge, effectiveLevel, printDoctor } = require('anosys-sdk-core');
const {
  INGESTION_URL,
  hookCommand,
  getConfigPath,
  getEnvPath,
  loadToml,
  hasAnosysHook,
  updateCodexConfig,
  removeCodexConfig,
  updateCodexEnv,
  removeCodexEnv,
  backup,
  validateApiKey
} = require('./installer');
const hookRunner = require('./hookRunner');

const { run } = hookRunner;

function prompt(question, defaultVal = '') {
  return new Promise(resolve => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(question, ans => {
      rl.close();
      resolve(ans.trim() || defaultVal);
    });
  });
}

async function cmdInstall(args) {
  console.log('\nAnoSys OpenAI Codex Hook Installer (JavaScript)');
  console.log('=============================================');

  const nonInteractive = args.includes('-y') || args.includes('--yes') || args.includes('--non-interactive');

  let apiKey = '';
  const keyIdx = args.indexOf('--api-key');
  if (keyIdx !== -1 && args[keyIdx + 1]) {
    apiKey = args[keyIdx + 1].trim();
  } else if (process.env.ANOSYS_API_KEY || process.env.ANOSYS_HOOK_APIKEY) {
    apiKey = (process.env.ANOSYS_API_KEY || process.env.ANOSYS_HOOK_APIKEY).trim();
  } else if (!nonInteractive) {
    apiKey = await prompt('AnoSys API key for logs (leave blank to skip): ');
  }

  if (apiKey) {
    console.log('Validating Logs API key...');
    const valid = await validateApiKey(apiKey, 'cc');
    if (!valid) {
      console.log('⚠️  Warning: Logs API key validation failed: key does not belong to a CC (Claude Code / Codex) pixel or is invalid.');
    } else {
      console.log('✅ Logs API key is valid (CC pixel).');
    }
  }

  let autoUpdate = true;
  if (args.includes('--no-auto-update')) {
    autoUpdate = false;
  } else if (!args.includes('--auto-update')) {
    if (nonInteractive) {
      autoUpdate = true;
    } else {
      const choice = (await prompt('Would you like to automatically update ~/.codex/config.toml? (Y/n): ', 'y')).toLowerCase();
      autoUpdate = choice !== 'n';
    }
  }

  const configPath = getConfigPath();
  const envPath = getEnvPath();

  if (autoUpdate) {
    console.log(`\nUpdating ${configPath} ...`);
    const backupPath = backup(configPath);
    updateCodexConfig(null, configPath);
    updateCodexEnv({ apiKey, customPath: envPath });

    if (backupPath) console.log(`  Backed up original settings -> ${backupPath}`);
    console.log(`  Hook command registered in notify: ${JSON.stringify(hookCommand())}`);
    console.log(`  Ingestion URL: ${INGESTION_URL}`);
    if (apiKey) {
      const masked = apiKey.length > 4 ? '*'.repeat(apiKey.length - 4) + apiKey.slice(-4) : '****';
      console.log(`  Logs API key: ${masked}`);
    }
    const { level, source } = effectiveLevel();
    console.log(`  Collecting: ${level} (from ${source})`);
    console.log('\n✅ Codex hook installed successfully.');
    console.log('\nBy default only metadata is sent (no prompts, answers, commands or files).');
    console.log('To send full content, accept the data-collection policy: anosys-codex privacy full\n');
  } else {
    console.log('\n================================================================');
    console.log('Add the following to your ~/.codex/config.toml file:');
    console.log(`\nnotify = ${JSON.stringify(hookCommand())}\n`);
    console.log('And create ~/.codex/anosys-env.sh with:');
    console.log(`export ANOSYS_HOOK_APIKEY="${apiKey}"`);
    console.log(`export ANOSYS_HOOK_ENDPOINT_URL="${INGESTION_URL}"`);
    console.log('================================================================\n');
  }
}

async function cmdUninstall() {
  console.log('\nAnoSys OpenAI Codex Hook Uninstaller (JavaScript)');
  console.log('=============================================');

  const configPath = getConfigPath();
  const envPath = getEnvPath();

  const backupPath = backup(configPath);
  const removedConfig = removeCodexConfig(configPath);
  const removedEnv = removeCodexEnv(envPath);

  if (backupPath) console.log(`  Backed up settings -> ${backupPath}`);
  if (removedConfig) console.log(`  Removed hook entry from ${configPath}`);
  else console.log(`  No AnoSys hook entry found in ${configPath}`);

  if (removedEnv) console.log(`  Removed ${envPath}`);
  console.log('\n✅ AnoSys Codex hook uninstalled successfully.\n');
}

function cmdStatus() {
  const configPath = getConfigPath();
  const envPath = getEnvPath();

  console.log('\nAnoSys Codex Hook Status (JavaScript)');
  console.log('=============================================');
  console.log(`Codex Config: ${configPath}`);
  console.log(`Env File:     ${envPath}`);

  if (!fs.existsSync(configPath)) {
    console.log('\n⚠️  Codex config.toml does not exist.\n');
    return;
  }

  const data = loadToml(configPath);
  const installed = hasAnosysHook(data);

  if (installed) {
    const { level, source } = effectiveLevel();
    console.log('\nStatus: ✅ Installed and active in config.toml');
    console.log(`Collecting: ${level} (from ${source})`);
    console.log(`Notify hooks: ${JSON.stringify(data.notify || [])}`);
  } else {
    console.log('\nStatus: ❌ Not registered in config.toml');
  }

  console.log(`Env file exists: ${fs.existsSync(envPath) ? '✅ Yes' : '❌ No'}\n`);
}

async function main() {
  const args = process.argv.slice(2);
  const cmd = args[0] || '';

  if (cmd === 'install') {
    await cmdInstall(args);
  } else if (cmd === 'uninstall') {
    await cmdUninstall();
  } else if (cmd === 'status') {
    cmdStatus();
  } else if (cmd === 'privacy') {
    process.exit(await cmdPrivacy('anosys-codex', args.slice(1)));
  } else if (cmd === 'purge') {
    const { LOG_FILE, PENDING_FILE, PAUSE_FILE } = hookRunner;
    process.exit(await cmdPurge([PENDING_FILE, LOG_FILE, `${LOG_FILE}.1`, `${LOG_FILE}.2`, PAUSE_FILE], args));
  } else if (cmd === 'doctor') {
    const data = loadToml(getConfigPath());
    printDoctor('anosys-codex', ['anosys-codex', 'anosys-sdk-codex'],
      hasAnosysHook(data) ? JSON.stringify(data.notify) : null,
      { config: getConfigPath(), 'env file': getEnvPath(), state: hookRunner.STATE_FILE,
        'pending queue': hookRunner.PENDING_FILE, log: hookRunner.LOG_FILE });
  } else if (cmd === 'run') {
    await run(args.slice(1));
    process.exit(0);
  } else {
    console.log('Usage: anosys-codex <install|uninstall|status|privacy|doctor|purge|run> [--api-key <key>] [-y|--yes] [--auto-update|--no-auto-update]');
    process.exit(1);
  }
}

if (require.main === module) {
  main().catch(err => {
    console.error(err);
    process.exit(1);
  });
}

module.exports = { cmdInstall, cmdUninstall, cmdStatus, main };
