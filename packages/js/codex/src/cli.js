#!/usr/bin/env node
'use strict';

const fs = require('fs');
const readline = require('readline');
const {
  HOOK_COMMAND,
  INGESTION_URL,
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
const { run } = require('./hookRunner');

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

  let redaction = args.includes('--redaction');
  if (!redaction && !args.includes('--no-redaction')) {
    if (nonInteractive) {
      redaction = false;
    } else {
      const choice = (await prompt('Enable content redaction? (y/N): ', 'n')).toLowerCase();
      redaction = choice === 'y';
    }
  }

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
    const valid = await validateApiKey(apiKey, 'codex');
    if (!valid) {
      console.log('⚠️  Warning: Logs API key validation failed (invalid key or incompatible type).');
    } else {
      console.log('✅ Logs API key is valid.');
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
    updateCodexConfig(HOOK_COMMAND, configPath);
    updateCodexEnv({ apiKey, redaction, customPath: envPath });

    if (backupPath) console.log(`  Backed up original settings -> ${backupPath}`);
    console.log(`  Hook command registered in notify: ${HOOK_COMMAND}`);
    console.log(`  Ingestion URL: ${INGESTION_URL}`);
    if (apiKey) {
      const masked = apiKey.length > 4 ? '*'.repeat(apiKey.length - 4) + apiKey.slice(-4) : '****';
      console.log(`  Logs API key: ${masked}`);
    }
    console.log(`  Redaction: ${redaction ? 'enabled' : 'disabled'}`);
    console.log('\n✅ Codex hook installed successfully.');
    console.log('\n⚠️  IMPORTANT (Codex Security Trust):');
    console.log('   In your next Codex CLI session, run the \'/hooks\' command');
    console.log(`   and approve the '${HOOK_COMMAND}' entry to allow tracing.\n`);
  } else {
    console.log('\n================================================================');
    console.log('Add the following to your ~/.codex/config.toml file:');
    console.log(`\nnotify = ["${HOOK_COMMAND}"]\n`);
    console.log('And create ~/.codex/anosys-env.sh with:');
    console.log(`export ANOSYS_HOOK_APIKEY="${apiKey}"`);
    console.log(`export ANOSYS_HOOK_ENDPOINT_URL="${INGESTION_URL}"`);
    console.log(`export REDACTION="${redaction ? 'true' : 'false'}"`);
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
    console.log('\nStatus: ✅ Installed and active in config.toml');
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
  } else if (cmd === 'run') {
    await run();
  } else {
    console.log('Usage: anosys-codex <install|uninstall|status|run> [--api-key <key>] [-y|--yes] [--redaction|--no-redaction] [--auto-update|--no-auto-update]');
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
