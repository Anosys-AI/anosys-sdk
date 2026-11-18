'use strict';

// Codex OTel export (--otel-key): never break config.toml, never touch a user's own [otel].

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { parse } = require('smol-toml');

const { OtelConfigError, hasAnosysOtel, updateCodexOtel, removeCodexOtel } = require('../src/installer');

const ORIGINAL = `model = "gpt-5"
notify = ["/usr/local/bin/other-notifier", "turn-ended"]

[projects."/tmp/repo"]
trust_level = "trusted"

[tui.model_availability_nux]
gpt-6 = 4
`;

function tmpConfig(content = ORIGINAL) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-codex-otel-'));
  const file = path.join(dir, 'config.toml');
  fs.writeFileSync(file, content);
  return file;
}

test('writes a valid [otel] block for logs, traces and metrics with prompts off', () => {
  const file = tmpConfig();
  assert.equal(updateCodexOtel('otel-key-1', file), true);
  const data = parse(fs.readFileSync(file, 'utf8'));
  assert.equal(data.otel.log_user_prompt, false);
  for (const [field, signal] of [['exporter', 'logs'], ['trace_exporter', 'traces'], ['metrics_exporter', 'metrics']]) {
    assert.deepEqual(JSON.parse(JSON.stringify(data.otel[field])), { 'otlp-http': {
      endpoint: `https://api.anosys.ai/ingestion/v1/${signal}`, protocol: 'binary', headers: { 'anosys-apikey': 'otel-key-1' },
    } });
  }
  assert.deepEqual(data.notify, ['/usr/local/bin/other-notifier', 'turn-ended']);
  assert.equal(data.projects['/tmp/repo'].trust_level, 'trusted');
  assert.equal(hasAnosysOtel(file), true);
});

test('re-running is idempotent and a new key replaces the old one', () => {
  const file = tmpConfig();
  updateCodexOtel('k1', file);
  assert.equal(updateCodexOtel('k1', file), false);
  assert.equal(updateCodexOtel('k2', file), true);
  const text = fs.readFileSync(file, 'utf8');
  assert.equal((text.match(/^\[otel\]$/gm) || []).length, 1);
  assert.equal(parse(text).otel.exporter['otlp-http'].headers['anosys-apikey'], 'k2');
});

test('uninstall restores the file byte for byte', () => {
  const file = tmpConfig();
  updateCodexOtel('k1', file);
  assert.equal(removeCodexOtel(file), true);
  assert.equal(fs.readFileSync(file, 'utf8'), ORIGINAL);
  assert.equal(removeCodexOtel(file), false);
});

test("a user's own [otel] section is never touched", () => {
  const content = `${ORIGINAL}\n[otel]\nenvironment = "prod"\n`;
  const file = tmpConfig(content);
  assert.throws(() => updateCodexOtel('k1', file), OtelConfigError);
  assert.equal(fs.readFileSync(file, 'utf8'), content);
});

test('an invalid config.toml is left alone', () => {
  const content = 'notify = ["a"\nbroken';
  const file = tmpConfig(content);
  assert.throws(() => updateCodexOtel('k1', file), OtelConfigError);
  assert.equal(fs.readFileSync(file, 'utf8'), content);
});

test('keys with quotes or backslashes are escaped, not injected', () => {
  const file = tmpConfig();
  updateCodexOtel('a"b\\c', file);
  assert.equal(parse(fs.readFileSync(file, 'utf8')).otel.exporter['otlp-http'].headers['anosys-apikey'], 'a"b\\c');
});

test('works on a missing or empty config.toml', () => {
  const file = tmpConfig('');
  assert.equal(updateCodexOtel('k1', file), true);
  assert.equal(parse(fs.readFileSync(file, 'utf8')).otel.log_user_prompt, false);
});
