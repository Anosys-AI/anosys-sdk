#!/usr/bin/env node
'use strict';

const { promptHidden, runMcpSubcommand } = require('anosys-sdk-core');

async function main() {
  const argv = process.argv.slice(2);
  const code = await runMcpSubcommand({
    defaultHarness: 'claude-code',
    argv,
    promptFn: promptHidden,
    cliName: 'anosys-sdk-mcp',
  });
  process.exit(code);
}

if (require.main === module) {
  main().catch((err) => {
    console.error('Error:', err.message || err);
    process.exit(1);
  });
}

module.exports = { main };
