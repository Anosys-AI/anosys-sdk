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
} = require('./installer');

const HOOK_COMMAND = 'npx @anosys/claude-code run';
const DEFAULT_ENDPOINT = 'https://www.anosys.ai';

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
    apiKey = await prompt('AnoSys API key (leave blank to skip): ');
  }

  let endpoint = args.endpoint;
  let claudePixel = 'false';

  if (apiKey) {
    console.log('Resolving API endpoint...');
    try {
      const resp = await fetch(`https://console.anosys.ai/api/resolveapikeys?apikey=${apiKey}`);
      if (resp.ok) {
        const data = await resp.json();
        endpoint = data.apiUrl || DEFAULT_ENDPOINT;
        console.log(`  Resolved endpoint: ${endpoint}`);
      } else {
        console.log(`  Failed to resolve endpoint (HTTP ${resp.status}). Using default.`);
        endpoint = DEFAULT_ENDPOINT;
      }
    } catch (e) {
      console.log(`  Error resolving endpoint: ${e.message}. Using default.`);
      endpoint = DEFAULT_ENDPOINT;
    }
  } else if (!endpoint) {
    endpoint = await prompt(`AnoSys endpoint URL [${DEFAULT_ENDPOINT}]: `, DEFAULT_ENDPOINT);
  }

  if (endpoint.includes('/cc/')) {
    claudePixel = 'true';
  }

  // OTEL setup
  let otelApiKey = args.otelKey;
  if (otelApiKey === null) {
    otelApiKey = await prompt('Enter your AnoSys API Key (OTEL type, leave blank to skip OTEL): ');
  }
  let enableOtel = false;
  let otelEndpointUrl = 'https://www.anosys.ai';

  if (otelApiKey) {
    console.log('Resolving OTEL endpoint...');
    try {
      const resp = await fetch(`https://console.anosys.ai/api/resolveapikeys?type=otel&apikey=${otelApiKey}`);
      if (resp.ok) {
        const data = await resp.json();
        otelEndpointUrl = data.apiUrl || 'https://www.anosys.ai';
        
        if (otelEndpointUrl.includes('/t/')) {
          enableOtel = true;
          console.log('  OTEL endpoint successfully resolved.');
        } else {
          console.log('  Warning: Resolved OTEL endpoint is invalid (Invalid API Key or incorrect type). Skipping OTEL setup.');
        }
      } else {
        console.log(`  Failed to resolve OTEL endpoint (HTTP ${resp.status}). Skipping OTEL.`);
      }
    } catch (e) {
      console.log(`  Error resolving OTEL endpoint: ${e.message}. Skipping OTEL.`);
    }
  }

  let autoUpdate = args.autoUpdate;
  if (autoUpdate === null) {
    const choice = await prompt('Would you like to automatically update ~/.claude/settings.json? (Y/n): ', 'y');
    autoUpdate = choice.toLowerCase() !== 'n';
  }

  const newEnv = {
    ANOSYS_HOOK_ENDPOINT_URL: endpoint,
    ANOSYS_CLAUDE_PIXEL: claudePixel,
    ANOSYS_HOOK_DRY_RUN: 'false',
  };
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
    newEnv.OTEL_EXPORTER_OTLP_ENDPOINT = otelEndpointUrl;
  }

  if (autoUpdate) {
    console.log(`\nUpdating ${SETTINGS_PATH} ...`);
    let settings = loadSettings();
    backup();
    settings = updateEnv(settings, newEnv);
    settings = updateStopHooks(settings, HOOK_COMMAND);
    writeAtomic(SETTINGS_PATH, settings);

    console.log(`  Backed up original settings -> ${BACKUP_PATH}`);
    console.log(`  Hook command registered: ${HOOK_COMMAND}`);
    console.log(`  Endpoint: ${endpoint}`);
    if (apiKey) {
      console.log(`  API key used for resolution: ${'*'.repeat(Math.max(0, apiKey.length - 4))}${apiKey.slice(-4)}`);
    }
    console.log(`  Redaction: ${redaction ? 'enabled' : 'disabled'}`);
    if (enableOtel) {
      console.log(`  OTEL: enabled (${otelEndpointUrl})`);
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
  backup();
  settings = removeStopHooks(settings);
  settings = removeEnv(settings);
  writeAtomic(SETTINGS_PATH, settings);
  console.log(`  Backed up original settings -> ${BACKUP_PATH}`);
  console.log('  AnoSys hook removed successfully.');
}

function cmdStatus() {
  const settings = loadSettings();
  if (hasAnosysHook(settings)) {
    const cmd = getAnosysHookCommand(settings);
    console.log('AnoSys hook is INSTALLED');
    console.log(`  Command: ${cmd}`);
    const env = settings.env || {};
    const endpoint = env.ANOSYS_HOOK_ENDPOINT_URL || '(not set)';
    const hasKey = 'ANOSYS_HOOK_API_KEY' in env;
    const redaction = env.REDACTION || 'false';
    console.log(`  Endpoint: ${endpoint}`);
    console.log(`  API key: ${hasKey ? 'set' : 'not set'}`);
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
    endpoint: null,
    redaction: false,
    noRedaction: false,
    otelKey: null,
    autoUpdate: null,
  };

  for (let i = 1; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--api-key' && argv[i + 1]) {
      args.apiKey = argv[++i];
    } else if (arg === '--endpoint' && argv[i + 1]) {
      args.endpoint = argv[++i];
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
