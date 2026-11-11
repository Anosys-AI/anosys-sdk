'use strict';
/** Settings check (JS): same rules as testcases/python/check_levels.py, plus both call forms. */
const fs = require('fs');
const os = require('os');
const path = require('path');
const { check, finish, isolatedHome, PKG } = require('./common.cjs');

const home = isolatedHome();
const core = require(path.join(PKG, 'core/src/index.js'));
const { FULL, METADATA, OFF, POLICY_VERSION, effectiveLevel, writeConsent, resolveAppLevel } = core;

const project = (level) => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-proj-'));
  fs.writeFileSync(path.join(d, '.anosys'), `level=${level}\n`);
  fs.mkdirSync(path.join(d, 'sub'));
  return d;
};
const consent = (level) => (level === FULL ? writeConsent(FULL, 'testcases', POLICY_VERSION) : writeConsent(level, 'testcases'));
const env = (kv = {}) => { for (const k of ['ANOSYS_DISABLE', 'ANOSYS_COLLECTION_LEVEL', 'REDACTION']) delete process.env[k]; Object.assign(process.env, kv); };
const lvl = (...a) => effectiveLevel(...a).level;

process.chdir(os.tmpdir());
consent(FULL); env();
check('hooks: full consent gives full', lvl(null, '/') === FULL);
check('hooks: project .anosys=off lowers full (positional call)', lvl(null, project(OFF)) === OFF);
check('hooks: project .anosys=off lowers full (object call)', lvl({ cwd: project(OFF) }) === OFF);
check('hooks: .anosys applies in subfolders', lvl(null, path.join(project(METADATA), 'sub')) === METADATA);
env({ ANOSYS_COLLECTION_LEVEL: 'metadata' });
check('hooks: ANOSYS_COLLECTION_LEVEL lowers consent', lvl(null, '/') === METADATA);
env({ REDACTION: 'true' });
check('hooks: REDACTION=true lowers consent to metadata', lvl(null, '/') === METADATA);
env({ ANOSYS_DISABLE: '1' });
check('hooks: ANOSYS_DISABLE wins', lvl(null, '/') === OFF);
env(); consent(OFF);
env({ ANOSYS_COLLECTION_LEVEL: 'full' });
check('hooks: env cannot raise a saved off', lvl(null, '/') === OFF);
check('hooks: .anosys=full cannot raise off', lvl(null, project(FULL)) === OFF);
env();
process.env.ANOSYS_CONSENT_FILE = path.join(home, 'none.json');
check('hooks: default without consent is metadata', lvl(null, '/') === METADATA);
env({ ANOSYS_COLLECTION_LEVEL: 'full' });
check('hooks: full without accepted policy stays metadata', lvl(null, '/') === METADATA);
process.env.ANOSYS_CONSENT_FILE = path.join(home, '.anosys', 'consent.json');
env();

consent(FULL);
check('app: default is full', resolveAppLevel(null, '/').level === FULL);
check('app: captureContent=false gives metadata', resolveAppLevel(false, '/').level === METADATA);
check('app: .anosys is a ceiling over code', resolveAppLevel(true, project(METADATA)).level === METADATA);
env({ ANOSYS_DISABLE: '1' });
check('app: ANOSYS_DISABLE wins over code', resolveAppLevel(true, '/').level === OFF);
env({ ANOSYS_COLLECTION_LEVEL: 'metadata' });
check('app: ANOSYS_COLLECTION_LEVEL applies without an argument', resolveAppLevel(null, '/').level === METADATA);
env();
finish();
