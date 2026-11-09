# anosys-codex

Python integration for Codex CLI turn-completion telemetry. It reads local rollout transcripts, maps messages and tool calls to AnoSys fields, and reports available token counters and estimated cost.

Requires Python 3.10 or later. This package uses the Codex notify callback; it does not register lifecycle hooks under /hooks.

## Install and configure

```bash
pip install anosys-codex
anosys-codex install
```

The installer asks for an ingestion key from an AnoSys Claude Code & Codex CLI (CC) endpoint and permission to update the user-level Codex configuration. It backs up the configuration and writes the ingestion key to $CODEX_HOME/anosys-env.sh (readable only by you). CODEX_HOME defaults to ~/.codex.

For non-interactive setup:

```bash
anosys-codex install --api-key "your-cc-endpoint-key" --auto-update --yes
```

API-key validation produces a warning on failure; it does not prevent installation. Verify the endpoint key and delivery independently.

## Notification command

The installer registers this Python interpreter by absolute path, so Codex can run the hook without activating a virtual environment:

```toml
notify = ["/path/to/python", "-m", "anosys_sdk_codex.hook_runner"]
```

If another notifier was already configured, it is kept and called after AnoSys (`--previous-notify`); uninstall restores it.

Restart Codex and complete a CLI turn. Check $CODEX_HOME/state/anosys_hook.log for callback execution and delivery errors. The status command checks registration, not network delivery.

The notify callback is separate from lifecycle hooks displayed by /hooks. See the [official Codex notification documentation](https://learn.chatgpt.com/docs/config-file/config-advanced#notifications).

## Privacy

By default the hook sends metadata only: ids, timestamps, models, token and cost numbers, durations, tool names, and the project, branch and OS username. Prompts, answers, tool output, commands and file contents are sent only after you accept the [data-collection policy](../../../PRIVACY.md):

```bash
anosys-codex privacy          # show the current level and where it comes from
anosys-codex privacy full     # read and accept the policy, then send full content
anosys-codex privacy off      # keep the hook installed but send nothing
anosys-codex doctor           # installed copies, the active hook and local files
anosys-codex purge            # delete the local queue and logs
```

The hook reads only the session that just ended, never earlier history, and its log holds ids and sizes only. The old `--redaction` flag and `REDACTION=true` still work and mean `metadata`. See [content controls](../../../DATA_CONTROLS.md) for the 10 MB request limit, retries and encryption.

## Runtime behavior

The runner finds a rollout file under $CODEX_HOME/sessions, maps the completed turn, and posts it to https://api.anosys.ai/ingestion in requests under 10 MB. Transient failures wait in $CODEX_HOME/state/pending_records.jsonl (at most 24 hours, 5 attempts, 50 MB); rejected requests are not retried.

Token usage and cost depend on the transcript fields and the package's embedded pricing table. Treat cost as an estimate. This package targets local Codex CLI transcripts; do not assume that a desktop or cloud session invokes the same callback.

## Environment variables

| Variable | Purpose |
| --- | --- |
| ANOSYS_HOOK_APIKEY | Runtime ingestion key; also loaded from anosys-env.sh |
| ANOSYS_API_KEY | Accepted by the installer as a source for the saved ingestion key |
| ANOSYS_HOOK_ENDPOINT_URL | Ingestion URL override |
| ANOSYS_DISABLE | 1 to send nothing |
| ANOSYS_COLLECTION_LEVEL | off, metadata or full (full still needs accepted consent) |
| ANOSYS_ENCRYPTION_KEY | Enable selected-field encryption |
| ANOSYS_ENCRYPTION_SALT | Workspace salt shown in the AnoSys console |
| ANOSYS_ENCRYPTED_COLUMNS | Override the default encrypted columns |
| ANOSYS_MAX_BATCH_BYTES | Request size limit (default 10000000) |
| ANOSYS_HOOK_DRY_RUN | true to skip network submission |
| CODEX_HOME | Codex configuration, session, and state directory |

See [content controls](../../../DATA_CONTROLS.md) for encryption details. Dry-run mode is a network diagnostic; it does not confirm server ingestion.

## Commands

- install: configure the ingestion key and notification entry.
- status: inspect expected registration and the environment file.
- uninstall: remove the installer's recognized notification entry and environment file. Remove a manually configured module entry yourself.
- run: receives the Codex notification JSON and executes the turn-completion handler.

## License

Apache License 2.0.
