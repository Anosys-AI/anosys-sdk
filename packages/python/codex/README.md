# anosys-codex

Python integration for Codex CLI turn-completion telemetry. It reads local rollout transcripts, maps messages and tool calls to AnoSys fields, and reports available token counters and estimated cost.

Requires Python 3.10 or later. This package uses the Codex notify callback; it does not register lifecycle hooks under /hooks.

## Install and configure

```bash
pip install anosys-codex
anosys-codex install
```

The installer asks for an ingestion key from an AnoSys Claude Code & Codex CLI (CC) endpoint, content redaction, and permission to update the user-level Codex configuration. It backs up the configuration and writes the ingestion key and redaction choice to $CODEX_HOME/anosys-env.sh. CODEX_HOME defaults to ~/.codex.

For non-interactive setup:

```bash
anosys-codex install --api-key "your-cc-endpoint-key" --redaction --auto-update --yes
```

API-key validation produces a warning on failure; it does not prevent installation. Verify the endpoint key and delivery independently.

## Notification command

Version 0.1.1 accepts the JSON argument that Codex appends to the notification command. The registered configuration is:

```toml
notify = ["anosys-codex", "run"]
```

Place notify at the top level of the user-level config.toml, before section headers. If the executable is installed in a virtual environment, use its absolute path so Codex can invoke it without activating that environment.

Restart Codex and complete a CLI turn. Check $CODEX_HOME/state/anosys_hook.log for callback execution and delivery errors. The status command checks registration, not network delivery.

Upgrade from version 0.1.0 with pip install --upgrade anosys-codex. Existing direct module notifications remain supported; the default CLI command no longer needs the old workaround. Saved redaction settings are now applied when mapping each turn.

The notify callback is separate from lifecycle hooks displayed by /hooks. See the [official Codex notification documentation](https://learn.chatgpt.com/docs/config-file/config-advanced#notifications). Preserve existing notification integrations separately: the installer can replace an existing notify command.

## Runtime behavior

The runner finds a rollout file under $CODEX_HOME/sessions, maps the completed turn, and posts batches to https://api.anosys.ai/ingestion. Failed records are buffered in $CODEX_HOME/state/pending_records.jsonl and retried on later invocations.

Token usage and cost depend on the transcript fields and the package's embedded pricing table. Treat cost as an estimate. This package targets local Codex CLI transcripts; do not assume that a desktop or cloud session invokes the same callback.

## Environment variables

| Variable | Purpose |
| --- | --- |
| ANOSYS_HOOK_APIKEY | Runtime ingestion key; also loaded from anosys-env.sh |
| ANOSYS_API_KEY | Accepted by the installer as a source for the saved ingestion key |
| ANOSYS_HOOK_ENDPOINT_URL | Ingestion URL override |
| REDACTION | true to mask supported content fields |
| ANOSYS_ENCRYPTION_KEY | Enable selected-field encryption |
| ANOSYS_ENCRYPTED_COLUMNS | Override the default encrypted columns |
| ANOSYS_HOOK_DRY_RUN | true to skip network submission |
| CODEX_HOME | Codex configuration, session, and state directory |

Version 0.1.1 reads the active REDACTION setting when mapping each turn, including settings loaded from anosys-env.sh.

See [content controls](../../../DATA_CONTROLS.md) for encryption and redaction limitations. Dry-run mode is a network diagnostic; it does not confirm server ingestion.

## Commands

- install: configure the ingestion key and notification entry.
- status: inspect expected registration and the environment file.
- uninstall: remove the installer's recognized notification entry and environment file. Remove a manually configured module entry yourself.
- run: receives the Codex notification JSON and executes the turn-completion handler.

## License

Apache License 2.0.
