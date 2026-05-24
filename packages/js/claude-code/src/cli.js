#!/usr/bin/env node
/**
 * CLI entry point for @anosys/claude-code.
 *
 * Commands:
 *   install    Register the AnoSys Stop hook in ~/.claude/settings.json
 *   uninstall  Remove the AnoSys Stop hook from ~/.claude/settings.json
 *   status     Show current hook registration status
 *   run        Execute the hook (invoked by Claude Code on every Stop event)
 */

'use strict';

const readline = require('readline');
const {
  SETTINGS_PATH,
  loadSettings,
  backup,
  writeAtomic,
  updateEnv,
  removeEnv,
  updateStopHooks,
  removeStopHooks,
  hasAnosysHook,
  getAnosysHookCommand,
  validateApiKey,
} = require('./installer');

const HOOK_COMMAND = 'npx @anosys/claude-code run';
const INGESTION_URL = 'https://api.anosys.ai/ingestion';

function prompt(query, defaultVal = '') {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) => {
    rl.question(query, (answer) => {
      rl.close();
      const val = answer.trim();
      resolve(val ? val : defaultVal);
    });
  });
}

async function cmdInstall(args) {
  console.log('\nAnoSys Claude Code Hook Installer');
  console.log('='.repeat(40));

  let redaction = args.redaction;
  if (!redaction && !args.noRedaction) {
    const choice = await prompt('Enable content redaction? (y/N): ', 'n');
    redaction = choice.toLowerCase() === 'y';
  }

  let apiKey = args.apiKey;
  if (!apiKey) {
    apiKey = await prompt('AnoSys API key for logs (leave blank to skip): ');
  }
  if (apiKey) {
    console.log('Validating Logs API key...');
    const isValid = await validateApiKey(apiKey, 'claudecode');
    if (!isValid) {
      console.warn('⚠️  Warning: Logs API key validation failed (invalid key or incompatible type).');
    } else {
      console.log('✅ Logs API key is valid.');
    }
  }

  // OTEL setup
  let otelApiKey = args.otelKey;
  if (otelApiKey === null) {
    otelApiKey = await prompt('Enter your AnoSys API Key (OTEL type, leave blank to skip OTEL): ');
  }
  if (otelApiKey) {
    console.log('Validating OTEL API key...');
    const isValid = await validateApiKey(otelApiKey, 'otel');
    if (!isValid) {
      console.warn('⚠️  Warning: OTEL API key validation failed (invalid key or incompatible type).');
    } else {
      console.log('✅ OTEL API key is valid.');
    }
  }
  const enableOtel = Boolean(otelApiKey);

  let autoUpdate = args.autoUpdate;
  if (autoUpdate === null) {
    const choice = await prompt('Would you like to automatically update ~/.claude/settings.json? (Y/n): ', 'y');
    autoUpdate = choice.toLowerCase() !== 'n';
  }

  const newEnv = {
    ANOSYS_HOOK_DRY_RUN: 'false',
  };
  if (apiKey) {
    newEnv.ANOSYS_HOOK_APIKEY = apiKey;
  }
  if (redaction) {
    newEnv.REDACTION = 'true';
  }
  if (enableOtel) {
    newEnv.CLAUDE_CODE_ENABLE_TELEMETRY = '1';
    newEnv.OTEL_SERVICE_NAME = 'claude-code';
    newEnv.OTEL_TRACES_EXPORTER = 'otlp';
    newEnv.OTEL_METRICS_EXPORTER = 'otlp';
    newEnv.OTEL_LOGS_EXPORTER = 'otlp';
    newEnv.OTEL_EXPORTER_OTLP_PROTOCOL = 'http/protobuf';
    newEnv.OTEL_EXPORTER_OTLP_ENDPOINT = INGESTION_URL;
    newEnv.OTEL_EXPORTER_OTLP_HEADERS = `anosys-apikey=${otelApiKey}`;
  }

  if (autoUpdate) {
    console.log(`\nUpdating ${SETTINGS_PATH} ...`);
    let settings = loadSettings();
    const backupPath = backup();
    settings = updateEnv(settings, newEnv);
    settings = updateStopHooks(settings, HOOK_COMMAND);
    writeAtomic(SETTINGS_PATH, settings);

    if (backupPath) {
      console.log(`  Backed up original settings -> ${backupPath}`);
    }
    console.log(`  Hook command registered: ${HOOK_COMMAND}`);
    console.log(`  Ingestion URL: ${INGESTION_URL}`);
    if (apiKey) {
      console.log(`  Logs API key: ${'*'.repeat(Math.max(0, apiKey.length - 4))}${apiKey.slice(-4)}`);
    }
    console.log(`  Redaction: ${redaction ? 'enabled' : 'disabled'}`);
    if (enableOtel) {
      console.log(`  OTEL: enabled (API key set, ingestion URL: ${INGESTION_URL})`);
    }
    console.log('\nDone. The hook will fire automatically after each Claude Code session.');
  } else {
    console.log('\n================================================================');
    console.log('Add the following to your ~/.claude/settings.json file options:');
    console.log('');
    
    const manualConfig = {
      env: newEnv,
      hooks: {
        Stop: [
          {
            owner: 'anosys',
            hooks: [
              {
                type: 'command',
                command: HOOK_COMMAND,
              }
            ]
          }
        ]
      }
    };
    
    console.log(JSON.stringify(manualConfig, null, 2));
    console.log('');
    console.log('================================================================');
  }
}

function cmdUninstall() {
  console.log(`\nRemoving AnoSys hook from ${SETTINGS_PATH} ...`);
  let settings = loadSettings();
  if (!hasAnosysHook(settings)) {
    console.log('  No AnoSys hook found — nothing to remove.');
    return;
  }
  const backupPath = backup();
  settings = removeStopHooks(settings);
  settings = removeEnv(settings);
  writeAtomic(SETTINGS_PATH, settings);
  if (backupPath) {
    console.log(`  Backed up original settings -> ${backupPath}`);
  }
  console.log('  AnoSys hook removed successfully.');
}

function cmdStatus() {
  const settings = loadSettings();
  if (hasAnosysHook(settings)) {
    const cmd = getAnosysHookCommand(settings);
    console.log('AnoSys hook is INSTALLED');
    console.log(`  Command: ${cmd}`);
    const env = settings.env || {};
    const hasLogsKey = 'ANOSYS_HOOK_APIKEY' in env;
    const hasOtelKey = 'OTEL_EXPORTER_OTLP_HEADERS' in env;
    const redaction = env.REDACTION || 'false';
    console.log(`  Ingestion URL: ${INGESTION_URL}`);
    console.log(`  Logs API key: ${hasLogsKey ? 'set' : 'not set'}`);
    console.log(`  OTEL API key: ${hasOtelKey ? 'set' : 'not set'}`);
    console.log(`  Redaction: ${redaction}`);
  } else {
    console.log('AnoSys hook is NOT installed.');
    console.log("  Run 'npx @anosys/claude-code install' to set it up.");
  }
}

async function cmdRun() {
  const { main } = require('./hookRunner');
  await main();
}

async function main() {
  const argv = process.argv.slice(2);
  const command = argv[0];

  if (!command) {
    console.log('Usage: anosys-claude-code <command> [options]');
    console.log('\nCommands:');
    console.log('  install    Register the AnoSys Stop hook');
    console.log('  uninstall  Remove the AnoSys Stop hook');
    console.log('  status     Show hook registration status');
    console.log('  run        Execute the hook (called by Claude Code)');
    process.exit(1);
  }

  const args = {
    apiKey: null,
    redaction: false,
    noRedaction: false,
    otelKey: null,
    autoUpdate: null,
  };

  for (let i = 1; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--api-key' && argv[i + 1]) {
      args.apiKey = argv[++i];
    } else if (arg === '--redaction') {
      args.redaction = true;
    } else if (arg === '--no-redaction') {
      args.noRedaction = true;
    } else if (arg === '--otel-key' && argv[i + 1]) {
      args.otelKey = argv[++i];
    } else if (arg === '--auto-update') {
      args.autoUpdate = true;
    } else if (arg === '--no-auto-update') {
      args.autoUpdate = false;
    }
  }

  try {
    switch (command) {
      case 'install':
        await cmdInstall(args);
        break;
      case 'uninstall':
        cmdUninstall();
        break;
      case 'status':
        cmdStatus();
        break;
      case 'run':
        await cmdRun();
        break;
      default:
        console.error(`Unknown command: ${command}`);
        process.exit(1);
    }
  } catch (error) {
    console.error('Error executing command:', error);
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}
