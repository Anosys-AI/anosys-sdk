/**
 * Constants for Google Antigravity AnoSys SDK.
 */

const path = require('path');
const os = require('os');
const { hookCliCommandString } = require('anosys-sdk-core');

const INTEGRATION_VERSION = '0.2.0';
const HARNESS_NAME = 'antigravity';
const HOOK_NAME = 'anosys-tracing';
// The hook command: this Node and this CLI by absolute path (installed bin when run through npx)
const HOOK_COMMAND = hookCliCommandString({ cliPath: path.join(__dirname, 'cli.js'), binName: 'anosys-antigravity', packageName: 'anosys-sdk-antigravity' });

const GLOBAL_CONFIG_DIR = path.join(os.homedir(), '.gemini', 'config');
const GLOBAL_HOOKS_FILE = path.join(GLOBAL_CONFIG_DIR, 'hooks.json');
const GLOBAL_ENV_FILE = path.join(GLOBAL_CONFIG_DIR, 'anosys-env.json');

const DEFAULT_INGESTION_URL = 'https://api.anosys.ai/ingestion';
const HOOK_TIMEOUT_SECONDS = 30;

const EVENTS = ['PreInvocation', 'Stop'];

module.exports = {
  INTEGRATION_VERSION,
  HARNESS_NAME,
  HOOK_NAME,
  HOOK_COMMAND,
  GLOBAL_CONFIG_DIR,
  GLOBAL_HOOKS_FILE,
  GLOBAL_ENV_FILE,
  DEFAULT_INGESTION_URL,
  HOOK_TIMEOUT_SECONDS,
  EVENTS,
};
