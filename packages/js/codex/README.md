# anosys-sdk-codex

JavaScript integration for Codex CLI turn-completion telemetry. It reads local rollout transcripts, maps messages and tool calls to AnoSys fields, and reports available token counters and estimated cost.

The package declares Node.js 18 or later. It uses built-in Node.js modules and the Codex notify callback.

## Install and configure

Install the executable persistently so Codex can find it on later turns:

```bash
npm install -g anosys-sdk-codex
anosys-codex install
```

The package name is anosys-sdk-codex; the executable is anosys-codex. A one-time npx invocation of the installer does not guarantee that the executable will be on the PATH when Codex calls it.

The installer asks for a key from an AnoSys Claude Code & Codex CLI (CC) endpoint, a redaction choice, and permission to update the user-level configuration. It backs up config.toml and writes credentials and redaction settings to $CODEX_HOME/anosys-env.sh.

```bash
anosys-codex install --api-key "your-cc-endpoint-key" --redaction --auto-update --yes
```

API-key validation warns on failure; it does not prevent installation. Verify delivery separately.

## Verify execution

The registered command is:

```toml
notify = ["anosys-codex", "run"]
```

Place notify at the top level of $CODEX_HOME/config.toml, before section headers. CODEX_HOME defaults to ~/.codex. If the executable is installed through a Node version manager, replace anosys-codex with its absolute executable path and ensure Node is available to that process.

Restart Codex and complete a CLI turn. Inspect $CODEX_HOME/state/anosys_hook.log for callback execution and delivery errors. The status command checks configuration only.

The notify callback is separate from lifecycle hooks displayed by /hooks. See the [official Codex notification documentation](https://learn.chatgpt.com/docs/config-file/config-advanced#notifications). Preserve any existing notifier separately: the installer can replace the existing notify command.

## Runtime behavior

The runner locates the turn's local rollout transcript under $CODEX_HOME/sessions and posts mapped batches to https://api.anosys.ai/ingestion. Failed records are buffered in $CODEX_HOME/state/pending_records.jsonl and retried later.

Cost is estimated using available token counters and the package's pricing table. This integration targets local Codex CLI transcripts; desktop and cloud sessions should be verified separately.

## Environment variables

| Variable | Purpose |
| --- | --- |
| ANOSYS_HOOK_APIKEY | Runtime ingestion key; also loaded from anosys-env.sh |
| ANOSYS_API_KEY | Installer fallback for the saved ingestion key |
| ANOSYS_HOOK_ENDPOINT_URL | Ingestion URL override |
| REDACTION | true to mask supported content fields |
| ANOSYS_ENCRYPTION_KEY | Enable selected-field encryption |
| ANOSYS_ENCRYPTED_COLUMNS | Override the default encrypted columns |
| ANOSYS_HOOK_DRY_RUN | true to skip network submission |
| CODEX_HOME | Codex configuration, session, and state directory |

See [content controls](../../../DATA_CONTROLS.md) for encryption coverage and redaction limitations.

## Commands

```bash
anosys-codex install
anosys-codex status
anosys-codex uninstall
```

The run handler is invoked by Codex after a turn completes.

## License

Apache License 2.0.
