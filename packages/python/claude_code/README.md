<p align="center">
  <a href="https://anosys.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/anosys-ai/anosys-sdk/main/assets/anosys-new-white-darkmode.svg">
      <img src="https://raw.githubusercontent.com/anosys-ai/anosys-sdk/main/assets/anosys-new-black-lightmode.svg" alt="Anosys.ai" width="240">
    </picture>
  </a>
</p>

# anosys-claude-code

AnoSys observability and analytics hook for Anthropic's Claude Code.

This package automatically captures Claude Code's telemetry, session turns, context sizes, and API costs, and sends them to your AnoSys workspace. It integrates directly into Claude Code's native `Stop` hook mechanism.

## Installation

Requires Python 3.10 or later.

You can install the package via `pip` or your favorite Python package manager:

```bash
pip install anosys-claude-code
```

After installing the package, run the setup wizard to configure the hook:

```bash
anosys-claude-code install
```

The installer will prompt you for:
1. **AnoSys API Key for logs**: Your ingestion API key from the AnoSys Console.
2. **AnoSys API Key for OTEL (optional)**: Your OpenTelemetry ingestion API key from the AnoSys Console.

### Headless Installation

If you prefer to install without interactive prompts, you can pass the configuration via flags:

```bash
anosys-claude-code install \
  --api-key "your_logs_api_key" \
  --otel-key "your_otel_api_key"
```

## CLI Commands

The package provides a unified CLI to manage your hook installation safely. It modifies `~/.claude/settings.json` and creates automatic backups (`~/.claude/settings.json.{TIMESTAMP}.bak`) before any changes.

### `status`
Check the current installation status of the AnoSys hook:
```bash
anosys-claude-code status
```

### `install`
Installs or updates the hook in your Claude Code settings:
```bash
anosys-claude-code install
```

### `uninstall`
Safely removes the AnoSys hook and related environment variables from your settings:
```bash
anosys-claude-code uninstall
```

### `run`
This command is executed automatically by Claude Code when a turn completes. You generally do not need to run this manually:
```bash
anosys-claude-code run
```

## Privacy

By default the hook sends metadata only: ids, timestamps, models, token and cost numbers, durations, tool names, and the project, branch and OS username. Prompts, answers, tool output, commands and file contents are sent only after you accept the [data-collection policy](../../../PRIVACY.md):

```bash
anosys-claude-code privacy          # show the current level and where it comes from
anosys-claude-code privacy full     # read and accept the policy, then send full content
anosys-claude-code privacy off      # keep the hook installed but send nothing
anosys-claude-code doctor           # installed copies, the active hook and local files
anosys-claude-code purge            # delete the local queue and logs
```

The hook reads only the session that just ended, never earlier history, and its log holds ids and sizes only. The old `--redaction` flag and `REDACTION=true` still work and mean `metadata`. See [content controls](../../../docs/DATA_CONTROLS.md) for the 10 MB request limit, retries and encryption.

## How it works

When installed, this package registers a `Stop` hook in `~/.claude/settings.json` using the `{"owner": "anosys"}` tag. When Claude Code finishes a turn, the hook is invoked. It reads the transcript of the session that just ended and its subagents, incrementally maps new messages using the AnoSys schemas, estimates cost using the package's pricing table, applies the collection level, and sends the results in requests under 10 MB to your AnoSys workspace.

## Content controls

See the [content-controls reference](../../../docs/DATA_CONTROLS.md) for encryption coverage, default columns, size limits, and limitations. Encryption is opt-in and applies to selected string fields; it does not encrypt the complete record.
