<p align="center">
  <a href="https://anosys.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/anosys-ai/anosys-sdk/main/assets/anosys-new-white-darkmode.svg">
      <img src="https://raw.githubusercontent.com/anosys-ai/anosys-sdk/main/assets/anosys-new-black-lightmode.svg" alt="Anosys.ai" width="240">
    </picture>
  </a>
</p>

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

The installer asks for a key from an AnoSys Claude Code & Codex CLI (CC) endpoint and permission to update the user-level configuration. It backs up config.toml and writes credentials to $CODEX_HOME/anosys-env.sh (readable only by you).

```bash
anosys-codex install --api-key "your-cc-endpoint-key" --auto-update --yes
```

API-key validation warns on failure; it does not prevent installation. Verify delivery separately.

## Verify execution

The installer registers this Node and this package by absolute path, so Codex finds them without a PATH lookup:

```toml
notify = ["/path/to/node", "/path/to/anosys-sdk-codex/src/cli.js", "run"]
```

CODEX_HOME defaults to ~/.codex. If another notifier was already configured, it is kept and called after AnoSys (`--previous-notify`); uninstall restores it.

Restart Codex and complete a CLI turn. Inspect $CODEX_HOME/state/anosys_hook.log for callback execution and delivery errors. The status command checks configuration only.

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

The runner locates the turn's local rollout transcript under $CODEX_HOME/sessions and posts it to https://api.anosys.ai/ingestion in requests under 10 MB. Transient failures wait in $CODEX_HOME/state/pending_records.jsonl (at most 24 hours, 5 attempts, 50 MB); rejected requests are not retried.

Cost is estimated using available token counters and the package's pricing table. This integration targets local Codex CLI transcripts; desktop and cloud sessions should be verified separately.

## Environment variables

| Variable | Purpose |
| --- | --- |
| ANOSYS_HOOK_APIKEY | Runtime ingestion key; also loaded from anosys-env.sh |
| ANOSYS_API_KEY | Installer fallback for the saved ingestion key |
| ANOSYS_HOOK_ENDPOINT_URL | Ingestion URL override |
| ANOSYS_DISABLE | 1 to send nothing |
| ANOSYS_COLLECTION_LEVEL | off, metadata or full (full still needs accepted consent) |
| ANOSYS_ENCRYPTION_KEY | Enable selected-field encryption |
| ANOSYS_ENCRYPTION_SALT | Workspace salt shown in the AnoSys console |
| ANOSYS_ENCRYPTED_COLUMNS | Override the default encrypted columns |
| ANOSYS_MAX_BATCH_BYTES | Request size limit (default 10000000) |
| ANOSYS_HOOK_DRY_RUN | true to skip network submission |
| CODEX_HOME | Codex configuration, session, and state directory |

See [content controls](../../../DATA_CONTROLS.md) for encryption details.

## Commands

```bash
anosys-codex install
anosys-codex status
anosys-codex uninstall
```

The run handler is invoked by Codex after a turn completes.

## License

Apache License 2.0.
