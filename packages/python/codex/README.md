# anosys-codex

AnoSys observability and analytics hook for OpenAI Codex CLI.

This package automatically captures Codex's telemetry, agent turns, tool calls (shell, pply_patch, Code Mode custom tools, web_search), token usage breakdowns (prompt, completion, cache read/write, reasoning), and API costs, and sends them directly to your AnoSys workspace.

It integrates directly into Codex CLI's native 
otify hook mechanism.

## Installation

`ash
pip install anosys-codex
`

After installing the package, run the setup wizard to configure the hook:

`ash
anosys-codex install
`

The installer will prompt you for:
1. **AnoSys API Key for logs**: Your ingestion API key from the AnoSys Console.
2. **Content Redaction**: If enabled, all conversation content (prompts, answers, code) will be redacted and replaced with [REDACTED]. Only metadata and token statistics will be tracked.

### Headless Installation

`ash
anosys-codex install \
  --api-key your_logs_api_key \
  --redaction \
  --auto-update
`

> **Important (Codex Security Trust)**:
> Codex requires explicit user trust for non-managed hooks. After installing, start a Codex CLI session, type /hooks, and approve the nosys-codex entry.

## CLI Commands

### status
Check current installation status:
`ash
anosys-codex status
`

### install
Installs the notify hook in ~/.codex/config.toml (or $CODEX_HOME/config.toml):
`ash
anosys-codex install
`

### uninstall
Safely removes the AnoSys hook and related configuration:
`ash
anosys-codex uninstall
`

### un
Executed automatically by Codex CLI when a turn completes:
`ash
anosys-codex run
`

## How it Works

1. Codex emits an gent-turn-complete notification via 
otify = [anosys-codex run] in ~/.codex/config.toml.
2. The hook runner reads the session thread ID and locates the session's rollout transcript at ~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<session_id>.jsonl.
3. It incrementally extracts user prompts, assistant messages, model details, token counts (including cached inputs and reasoning tokens), and tool calls.
4. It maps the data into the AnoSys schema (cvs200: CodexHook), estimates USD cost using OpenAI pricing, applies optional PII redaction, and batches the payloads to https://api.anosys.ai/ingestion.
5. In case of network errors, failed records are buffered in ~/.codex/state/pending_records.jsonl and retried automatically on subsequent runs.
