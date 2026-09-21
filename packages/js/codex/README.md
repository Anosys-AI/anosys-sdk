# anosys-sdk-codex (JavaScript / Node.js)

AnoSys observability and analytics hook for OpenAI Codex CLI.

This package automatically captures Codex CLI's telemetry, agent turns, tool calls (`shell`, `apply_patch`, Code Mode custom tools, `web_search`), token usage breakdowns (prompt, completion, cache read/write, reasoning tokens), and estimated API costs, sending them directly to your AnoSys workspace.

It integrates seamlessly with Codex CLI's native `notify` hook mechanism with **zero external runtime dependencies**.

---

## Installation

You can run the installer interactively using `npx`:

```bash
npx anosys-sdk-codex install
```

Or install globally:

```bash
npm install -g anosys-sdk-codex
anosys-codex install
```

The installer will prompt you for:
1. **AnoSys API Key for logs**: Your ingestion API key from the [AnoSys Console](https://console.anosys.ai/collect/integrationoptions).
2. **Content Redaction**: If enabled, sensitive conversation content (prompts, answers, code, tool inputs/outputs) will be redacted and replaced with `[REDACTED]`. Only metadata and token statistics will be tracked.
3. **Automatic Config Update**: Confirms whether to automatically write `notify = ["anosys-codex run"]` to `~/.codex/config.toml` (and creates a `.bak` backup first).

---

## Non-Interactive / Headless Installation

For automated pipelines, Dockerfiles, devcontainers, or scripted setups:

### Using the `-y` / `--yes` flag (Recommended):
```bash
npx anosys-sdk-codex install --api-key "your_logs_api_key" -y
```

### Using environment variables:
```bash
export ANOSYS_API_KEY="your_logs_api_key"
npx anosys-sdk-codex install -y
```

### Using explicit granular flags:
```bash
npx anosys-sdk-codex install \
  --api-key "your_logs_api_key" \
  --auto-update \
  --no-redaction
```

> **Important (Codex Security Trust)**:
> Codex requires explicit user approval for unmanaged external notify hooks. After running `install`, start a Codex CLI session, type `/hooks`, and select `approve` / `trust` for the `anosys-codex run` hook entry.

---

## CLI Commands

The package provides a unified CLI to manage your hook installation safely. It modifies `~/.codex/config.toml` and creates automatic timestamped backups (`config.toml.<TIMESTAMP>.bak`) before applying changes.

### `status`
Check the current installation and registration status of the hook:
```bash
npx anosys-sdk-codex status
```

### `install`
Installs or updates the hook in your Codex configuration and writes `~/.codex/anosys-env.sh`:
```bash
npx anosys-sdk-codex install [options]

Options:
  --api-key <key>             AnoSys logs API key
  -y, --yes                   Skip interactive prompts (non-interactive mode)
  --redaction                 Enable content redaction
  --no-redaction              Disable content redaction
  --auto-update               Automatically update ~/.codex/config.toml
  --no-auto-update            Print manual setup instructions instead of modifying config
```

### `uninstall`
Safely removes the AnoSys hook from `~/.codex/config.toml` and deletes `~/.codex/anosys-env.sh`:
```bash
npx anosys-sdk-codex uninstall
```

### `run`
Executed automatically by Codex CLI on turn-complete notify events. You do not need to run this manually:
```bash
npx anosys-sdk-codex run
```

---

## How It Works

1. When a Codex turn completes, Codex CLI triggers `notify = ["anosys-codex run"]` registered in `~/.codex/config.toml`.
2. The hook runner reads the session thread ID and locates the session's rollout transcript at `~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<session_id>.jsonl`.
3. It incrementally extracts user prompts, assistant messages, model details, token counts (including cached inputs and reasoning tokens), and tool calls.
4. It maps the turn into the AnoSys schema (`cvs200: 'CodexHook'`), estimates USD cost using OpenAI's model pricing table, applies optional PII redaction, and batches the payload to `https://api.anosys.ai/ingestion`.
5. If network connectivity is temporarily interrupted, failed records are buffered locally in `~/.codex/state/pending_records.jsonl` and automatically replayed on subsequent runs.

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANOSYS_HOOK_APIKEY` / `ANOSYS_API_KEY` | AnoSys ingestion API key |
| `ANOSYS_HOOK_ENDPOINT_URL` | Override default ingestion URL (`https://api.anosys.ai/ingestion`) |
| `REDACTION` / `ANOSYS_REDACT_CONTENT` | Set to `"true"` to redact prompts, code, and tool outputs |
| `ANOSYS_HOOK_DRY_RUN` | Set to `"true"` to log payloads to stderr without sending to network |
| `CODEX_HOME` | Custom directory for Codex config and sessions (defaults to `~/.codex`) |
