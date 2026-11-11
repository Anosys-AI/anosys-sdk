import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { hookCliCommand, hookCliCommandString } = require('../src/hookCli.js');

const opts = (cliPath) => ({ cliPath, binName: 'anosys-test-bin', packageName: 'anosys-sdk-test' });

test('an installed CLI is run by absolute path with this Node', () => {
  const cli = path.join(os.tmpdir(), 'lib', 'node_modules', 'x', 'src', 'cli.js');
  assert.deepEqual(hookCliCommand(opts(cli)), [process.execPath, cli, 'run']);
  assert.ok(hookCliCommandString(opts(cli)).startsWith(`"${process.execPath}"`));
});

test('from the npx cache, the installed bin on PATH is used', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'anosys-bin-'));
  const bin = path.join(dir, 'anosys-test-bin');
  fs.writeFileSync(bin, '#!/bin/sh\n', { mode: 0o755 });
  const saved = process.env.PATH;
  process.env.PATH = dir;
  try {
    const cli = path.join(os.homedir(), '.npm', '_npx', 'abc', 'node_modules', 'x', 'src', 'cli.js');
    assert.deepEqual(hookCliCommand(opts(cli)), [bin, 'run']);
  } finally { process.env.PATH = saved; }
});

test('from the npx cache without an installed bin, npx -y runs the package', () => {
  const saved = process.env.PATH;
  process.env.PATH = '';
  const write = process.stderr.write;
  process.stderr.write = () => true;
  try {
    const cli = path.join(os.homedir(), '.npm', '_npx', 'abc', 'node_modules', 'x', 'src', 'cli.js');
    assert.deepEqual(hookCliCommand(opts(cli)), ['npx', '-y', 'anosys-sdk-test', 'run']);
    assert.equal(hookCliCommandString(opts(cli)), 'npx -y anosys-sdk-test run');
  } finally { process.env.PATH = saved; process.stderr.write = write; }
});
