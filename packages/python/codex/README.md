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

## Notification command for version 0.1.0

The installed CLI's run subcommand does not accept the JSON argument Codex appends to notify commands. After installation, replace its notify entry with a direct module invocation.

Find the Python interpreter containing the package:

```bash
python -c "import sys; print(sys.executable)"
```

Place that absolute path at the beginning of the user-level config.toml, before any section headers:

```toml
notify = [
  "/absolute/path/to/python",
  "-m",
  "anosys_sdk_codex.hook_runner",
]
```

Use the interpreter from the installation environment so Codex can run the callback without activating that environment. Preserve any existing notifier configuration separately: Codex notify specifies a single executable and its arguments, and the installer can replace an existing notify entry.

Restart Codex and complete a CLI turn. Check $CODEX_HOME/state/anosys_hook.log for execution and delivery errors. The status command checks the installer's expected registration; it may report the manual module command as unregistered and does not test network delivery.

This callback is separate from the lifecycle hooks displayed by /hooks. See the [official Codex notification documentation](https://learn.chatgpt.com/docs/config-file/config-advanced#notifications).

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

In version 0.1.0, the mapper reads REDACTION at import time, before the runner loads anosys-env.sh. Set REDACTION in the process environment when relying on redaction, rather than assuming the saved installer choice alone is sufficient.

See [content controls](../../../DATA_CONTROLS.md) for encryption and redaction limitations. Dry-run mode is a network diagnostic; it does not confirm server ingestion.

## Commands

- install: configure the ingestion key and notification entry.
- status: inspect expected registration and the environment file.
- uninstall: remove the installer's recognized notification entry and environment file. Remove a manually configured module entry yourself.
- run: installer-facing entry point; use the module invocation above for version 0.1.0 notifications.

## License

Apache License 2.0.
