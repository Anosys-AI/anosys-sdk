'use strict';

/**
 * Shared pieces for the coding-agent hook CLIs (Claude Code, Codex,
 * Antigravity) — JS port of Python `anosys_sdk_core/hook_cli.py`.
 */

const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');

const {
  FULL, LEVELS, POLICY_URL, POLICY_VERSION, consentPath, effectiveLevel, readConsent, writeConsent,
} = require('./privacy.js');

const POLICY_SUMMARY = `AnoSys data-collection policy ${POLICY_VERSION} (${POLICY_URL})

At \`full\`, the hook sends the content of your sessions to AnoSys: prompts,
assistant answers, thinking, tool inputs and outputs, shell commands, file
paths and file contents that pass through the tool. Secret-shaped strings
(API keys, tokens, private keys) are scrubbed on a best-effort basis.
At \`metadata\` (the default) only ids, timestamps, models, token and cost
numbers, durations, tool names, project/branch names and your OS username
are sent. Set ANOSYS_ENCRYPTION_KEY to encrypt content so only your browser
can read it. Each record carries the level and policy version you chose.
`;

const LOG_MAX_BYTES = 5000000;

/**
 * Hook log: rotated at 5 MB (2 backups), file mode 0600. Hooks pass ids,
 * sizes and status codes only, never payloads or tool input.
 */
function createHookLog(logFile) {
  try { fs.mkdirSync(path.dirname(logFile), { recursive: true }); } catch { /* ignore */ }
  return (level, message) => {
    try {
      if (fs.existsSync(logFile) && fs.statSync(logFile).size > LOG_MAX_BYTES) {
        const second = `${logFile}.2`;
        const first = `${logFile}.1`;
        if (fs.existsSync(first)) fs.renameSync(first, second);
        fs.renameSync(logFile, first);
      }
      fs.appendFileSync(logFile, `${new Date().toISOString()} [${level}] ${message}\n`, { encoding: 'utf8', mode: 0o600 });
      fs.chmodSync(logFile, 0o600);
    } catch { /* logging must never break the hook */ }
  };
}

function ask(question) {
  return new Promise(resolve => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question(question, answer => { rl.close(); resolve(answer.trim()); });
  });
}

/** `privacy [status|off|metadata|full] [--accept-policy VERSION]` */
async function cmdPrivacy(tool, args) {
  const level = (args.find(a => !a.startsWith('--') && a !== 'privacy') || 'status').toLowerCase();
  const flagIndex = args.indexOf('--accept-policy');
  let accept = flagIndex !== -1 ? args[flagIndex + 1] : null;

  if (level === 'status') {
    const { level: current, source } = effectiveLevel();
    const consent = readConsent();
    console.log(`\n${tool}: collecting at '${current}' (from ${source})`);
    console.log(`Consent file: ${consentPath()}`);
    if (consent.policy_version) console.log(`Policy accepted: ${consent.policy_version} on ${consent.accepted_at}`);
    console.log('Change it with: privacy off | privacy metadata | privacy full\n');
    return 0;
  }
  if (!LEVELS.includes(level)) {
    console.error(`Unknown level '${level}'. Use status, off, metadata or full.`);
    return 1;
  }
  const method = accept ? 'cli-flag' : 'cli';
  if (level === FULL && !accept) {
    console.log(POLICY_SUMMARY);
    const answer = (await ask(`Type 'accept' to accept policy ${POLICY_VERSION}: `)).toLowerCase();
    if (answer !== 'accept') {
      console.log('Policy not accepted; level unchanged.');
      return 1;
    }
    accept = POLICY_VERSION;
  }
  try {
    writeConsent(level, method, accept);
  } catch (e) {
    console.error(`Error: ${e.message}`);
    return 1;
  }
  const { level: now, source } = effectiveLevel();
  console.log(`${tool}: now collecting at '${now}' (from ${source}).`);
  return 0;
}

function formatSize(file) {
  try {
    let n = fs.statSync(file).size;
    for (const unit of ['B', 'KB', 'MB', 'GB']) {
      if (n < 1024) return `${Math.round(n)} ${unit}`;
      n /= 1024;
    }
    return `${n.toFixed(1)} TB`;
  } catch {
    return '?';
  }
}

/** `purge [-y]`: delete local queued records and logs. */
async function cmdPurge(files, args) {
  const existing = files.filter(f => fs.existsSync(f));
  if (!existing.length) {
    console.log('Nothing to purge.');
    return 0;
  }
  for (const f of existing) console.log(`  ${f} (${formatSize(f)})`);
  if (!args.includes('-y') && !args.includes('--yes')) {
    if ((await ask('Delete these files? (y/N): ')).toLowerCase() !== 'y') {
      console.log('Nothing deleted.');
      return 0;
    }
  }
  for (const f of existing) {
    try { fs.unlinkSync(f); console.log(`  deleted ${f}`); } catch (e) { console.log(`  could not delete ${f}: ${e.message}`); }
  }
  return 0;
}

/** `doctor`: installed copies on PATH, the active hook and local files. */
function printDoctor(tool, executables, activeHook, files) {
  const { level, source } = effectiveLevel();
  console.log(`\n${tool} doctor`);
  console.log('='.repeat(45));
  console.log(`Collecting at: ${level} (from ${source})`);
  console.log(`This copy:     ${process.execPath} ${process.argv[1]}`);
  console.log(`Active hook:   ${activeHook || 'not installed'}`);
  console.log('\nInstalled copies on PATH:');
  let found = false;
  for (const name of executables) {
    for (const dir of (process.env.PATH || '').split(path.delimiter)) {
      const candidate = path.join(dir, name);
      try {
        fs.accessSync(candidate, fs.constants.X_OK);
        found = true;
        console.log(`  ${candidate}`);
      } catch { /* not here */ }
    }
  }
  if (!found) console.log('  none');
  console.log('\nLocal files:');
  for (const [label, file] of Object.entries(files)) {
    console.log(`  ${label.padEnd(16)} ${file}  [${fs.existsSync(file) ? formatSize(file) : 'absent'}]`);
  }
  console.log('');
}

/** Run a hook body so it can never break the host tool: errors are swallowed (logged by type). */
async function runHookSafely(fn, writeLog = null) {
  try {
    await fn();
  } catch (e) {
    try { writeLog?.('ERROR', `Hook failed (${e?.code || e?.name || 'Error'})`); } catch { /* ignore */ }
  }
}

module.exports = {
  runHookSafely,
  POLICY_SUMMARY,
  createHookLog,
  cmdPrivacy,
  cmdPurge,
  printDoctor,
};
