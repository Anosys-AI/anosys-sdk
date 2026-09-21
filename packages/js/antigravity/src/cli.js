#!/usr/bin/env node
/**
 * CLI entry point for anosys-antigravity (JavaScript).
 */

const readline = require('readline');
const {
  HOOK_NAME,
  HOOK_COMMAND,
  DEFAULT_INGESTION_URL,
} = require('./constants');
const {
  getHooksPath,
  getEnvPath,
  loadJson,
  backup,
  hasAnosysHook,
  updateHooksConfig,
  removeHooksConfig,
  updateEnvConfig,
  removeEnvConfig,
  validateApiKey,
} = require('./installer');

function promptUser(query) {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise(resolve => rl.question(query, ans => {
    rl.close();
    resolve(ans.trim());
  }));
}

function parseArgs(argv) {
  const args = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-y' || a === '--yes') {
      args.yes = true;
    } else if (a === '--redaction') {
      args.redaction = true;
    } else if (a === '--no-redaction') {
      args.noRedaction = true;
    } else if (a === '--workspace') {
      args.workspace = true;
    } else if (a === '--api-key') {
      args.apiKey = argv[++i];
    } else if (a === '--endpoint-url') {
      args.endpointUrl = argv[++i];
    } else if (a.startsWith('--api-key=')) {
      args.apiKey = a.split('=')[1];
    } else if (a.startsWith('--endpoint-url=')) {
      args.endpointUrl = a.split('=')[1];
    } else if (!a.startsWith('-')) {
      args._.push(a);
    }
  }
  return args;
}

async function cmdInstall(args) {
  console.log('\nAnoSys Google Antigravity Hook Installer (JavaScript)');
  console.log('='.repeat(48));

  const yes = Boolean(args.yes);
  const workspace = Boolean(args.workspace);
  const hooksPath = getHooksPath(workspace);
  const envPath = getEnvPath(workspace);

  let redaction = Boolean(args.redaction);
  if (!redaction && !args.noRedaction) {
    if (yes) {
      redaction = false;
    } else {
      const choice = (await promptUser('Enable content redaction? (y/N): ')).toLowerCase();
      redaction = choice === 'y';
    }
  }

  let apiKey = args.apiKey || process.env.ANOSYS_HOOK_APIKEY || process.env.ANOSYS_API_KEY || '';
  if (!apiKey && !yes) {
    apiKey = await promptUser('AnoSys API key for logs (leave blank to skip): ');
  }

  if (apiKey) {
    console.log('Validating Logs API key...');
    const isValid = await validateApiKey(apiKey, 'cc');
    if (!isValid) {
      console.log('⚠️  Warning: Logs API key validation failed: key does not belong to a CC (Claude Code / Codex / Antigravity) pixel or is invalid.');
    } else {
      console.log('✅ Logs API key is valid (CC pixel).');
    }
  }

  const endpointUrl = args.endpointUrl || process.env.ANOSYS_HOOK_ENDPOINT_URL || DEFAULT_INGESTION_URL;

  let autoUpdate = true;
  if (!yes) {
    const choice = (await promptUser(`Update ${hooksPath}? (Y/n): `)).toLowerCase();
    autoUpdate = choice !== 'n';
  }

  if (autoUpdate) {
    console.log(`\nUpdating ${hooksPath} ...`);
    const backupPath = backup(hooksPath);
    updateHooksConfig(hooksPath, HOOK_COMMAND);
    updateEnvConfig(envPath, { apiKey, endpointUrl, redaction });

    if (backupPath) {
      console.log(`  Backed up original settings -> ${backupPath}`);
    }
    console.log(`  Hook '${HOOK_NAME}' registered for events: PreInvocation, Stop`);
    console.log(`  Ingestion URL: ${endpointUrl}`);
    if (apiKey) {
      const masked = apiKey.length > 4 ? '*'.repeat(apiKey.length - 4) + apiKey.slice(-4) : '****';
      console.log(`  Logs API key: ${masked}`);
    }
    console.log(`  Redaction: ${redaction ? 'enabled' : 'disabled'}`);
    console.log('\n✅ Antigravity hook installed successfully.\n');
  } else {
    console.log('\n================================================================');
    console.log(`Add the following to your ${hooksPath} file:`);
    const sample = {
      [HOOK_NAME]: {
        PreInvocation: [{ type: 'command', command: `${HOOK_COMMAND} pre_invocation`, timeout: 30 }],
        Stop: [{ type: 'command', command: `${HOOK_COMMAND} stop`, timeout: 30 }],
      },
    };
    console.log(JSON.stringify(sample, null, 2));
    console.log(`\nAnd create ${envPath} with:`);
    const envSample = {
      ANOSYS_HOOK_APIKEY: apiKey,
      ANOSYS_HOOK_ENDPOINT_URL: endpointUrl,
      REDACTION: redaction ? 'true' : 'false',
    };
    console.log(JSON.stringify(envSample, null, 2));
    console.log('================================================================\n');
  }
}

function cmdUninstall(args) {
  console.log('\nAnoSys Google Antigravity Hook Uninstaller (JavaScript)');
  console.log('='.repeat(48));

  const workspace = Boolean(args.workspace);
  const hooksPath = getHooksPath(workspace);
  const envPath = getEnvPath(workspace);

  const backupPath = backup(hooksPath);
  const removedHook = removeHooksConfig(hooksPath);
  const removedEnv = removeEnvConfig(envPath);

  if (backupPath) {
    console.log(`  Backed up settings -> ${backupPath}`);
  }
  if (removedHook) {
    console.log(`  Removed '${HOOK_NAME}' from ${hooksPath}`);
  } else {
    console.log(`  No '${HOOK_NAME}' entry found in ${hooksPath}`);
  }

  if (removedEnv) {
    console.log(`  Removed ${envPath}`);
  }

  console.log('\n✅ AnoSys Antigravity hook uninstalled successfully.\n');
}

function cmdStatus(args) {
  const workspace = Boolean(args.workspace);
  const hooksPath = getHooksPath(workspace);
  const envPath = getEnvPath(workspace);

  console.log('\nAnoSys Antigravity Hook Status (JavaScript)');
  console.log('='.repeat(48));
  console.log(`Hooks File: ${hooksPath}`);
  console.log(`Env File:   ${envPath}`);

  const data = loadJson(hooksPath);
  if (hasAnosysHook(data)) {
    console.log('\nStatus: ✅ Installed and active in hooks.json');
    const block = data[HOOK_NAME] || {};
    console.log(`Events configured: ${Object.keys(block).join(', ')}`);
  } else {
    console.log('\nStatus: ❌ Not registered in hooks.json');
  }

  const envData = loadJson(envPath);
  if (envData.ANOSYS_HOOK_APIKEY !== undefined) {
    console.log('Env file exists: ✅ Yes');
    const key = envData.ANOSYS_HOOK_APIKEY || '';
    if (key) {
      const masked = key.length > 4 ? '*'.repeat(key.length - 4) + key.slice(-4) : '****';
      console.log(`Configured API Key: ${masked}`);
    }
  } else {
    console.log('Env file exists: ❌ No');
  }
  console.log();
}

async function main() {
  const argv = process.argv.slice(2);
  const args = parseArgs(argv);
  const command = args._[0] || 'help';

  switch (command) {
    case 'install':
      await cmdInstall(args);
      break;
    case 'uninstall':
      cmdUninstall(args);
      break;
    case 'status':
      cmdStatus(args);
      break;
    case 'run': {
      const { run } = require('./hookRunner');
      await run();
      break;
    }
    default:
      console.log(`
Usage: anosys-antigravity <command> [options]

Commands:
  install      Install AnoSys hook into hooks.json
  uninstall    Remove AnoSys hook from hooks.json
  status       Check hook installation status
  run [event]  Execute hook handler

Options:
  --api-key <key>       AnoSys API key
  -y, --yes             Automatic yes to prompts
  --redaction           Enable content redaction
  --no-redaction        Disable content redaction
  --workspace           Target workspace .agents/hooks.json
  --endpoint-url <url>  Custom ingestion endpoint URL
`);
      process.exit(1);
  }
}

if (require.main === module) {
  main().catch(err => {
    console.error('Fatal CLI error:', err);
    process.exit(1);
  });
}

module.exports = {
  main,
  parseArgs,
};
