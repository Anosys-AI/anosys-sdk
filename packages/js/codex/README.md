# anosys-sdk-codex (JavaScript / Node.js)

AnoSys observability and analytics hook for OpenAI Codex CLI.

This package automatically captures Codex's telemetry, agent turns, tool calls (`shell`, `apply_patch`, Code Mode custom tools, `web_search`), token usage breakdowns (prompt, completion, cache read/write, reasoning), and API costs, and sends them directly to your AnoSys workspace.

It integrates directly into Codex CLI's native `notify` hook mechanism.

## Installation

```bash
npm install -g anosys-sdk-codex
# or run via npx
npx anosys-sdk-codex install
```

## CLI Commands

### `status`
```bash
anosys-codex status
```

### `install`
Installs the notify hook into `~/.codex/config.toml`:
```bash
anosys-codex install
```

### `uninstall`
Safely removes the AnoSys hook:
```bash
anosys-codex uninstall
```

### `run`
Invoked automatically by Codex CLI notify hook:
```bash
anosys-codex run
```
