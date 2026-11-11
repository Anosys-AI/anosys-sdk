'use strict';
// Shared helpers for the JS checks: result reporting, isolated homes, fake-ingestion reads.
const fs = require('fs');
const os = require('os');
const path = require('path');

const failures = [];
function check(name, ok, detail = '') {
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${ok || !detail ? '' : `  -> ${detail}`}`);
  if (!ok) failures.push(name);
  return ok;
}
function finish() { process.exitCode = failures.length ? 1 : 0; }

function isolatedHome(prefix = 'anosys-tc-') {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  process.env.HOME = home;
  process.env.USERPROFILE = home;
  process.env.ANOSYS_CONSENT_FILE = path.join(home, '.anosys', 'consent.json');
  for (const v of ['ANOSYS_DISABLE', 'ANOSYS_COLLECTION_LEVEL', 'REDACTION', 'ANOSYS_ENCRYPTION_KEY',
    'ANOSYS_ENCRYPTION_SALT', 'ANOSYS_ENCRYPTED_COLUMNS', 'ANOSYS_CLAUDE_PIXEL', 'ANOSYS_PIXEL_TYPE',
    'ANOSYS_API_KEY', 'ANOSYS_API_URL', 'CODEX_HOME']) delete process.env[v];
  return home;
}

function ingested(outDir, tag) {
  const file = path.join(outDir, `${tag}.jsonl`);
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, 'utf8').split('\n').filter(Boolean)
    .flatMap((line) => { const d = JSON.parse(line); return Array.isArray(d) ? d : [d]; });
}

const isEncrypted = (v) => typeof v === 'string' && (v.startsWith('enc2:') || v.startsWith('"enc2:'));
const PKG = path.resolve(__dirname, '..', '..', 'packages', 'js');

module.exports = { check, finish, isolatedHome, ingested, isEncrypted, PKG };
