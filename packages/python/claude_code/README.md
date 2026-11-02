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
3. **Content redaction**: Replaces supported conversation fields before export. Review the [content-controls reference](../../../DATA_CONTROLS.md) for coverage and limitations.

### Headless Installation

If you prefer to install without interactive prompts, you can pass the configuration via flags:

```bash
anosys-claude-code install \
  --api-key "your_logs_api_key" \
  --otel-key "your_otel_api_key" \
  --redaction
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

## How it works

When installed, this package registers a `Stop` hook in `~/.claude/settings.json` using the `{"owner": "anosys"}` tag. When Claude Code finishes a turn, the hook is invoked. It scans your local Claude transcripts (`~/.claude/projects/`), incrementally maps any new messages or subagent events using the AnoSys schemas, estimates cost using the package's pricing table, applies optional content redaction, and batches the results to your AnoSys workspace.

## Content controls

See the [content-controls reference](../../../DATA_CONTROLS.md) for encryption coverage, default columns, redaction, and limitations. Encryption is opt-in and applies to selected string fields; it does not encrypt the complete record.
