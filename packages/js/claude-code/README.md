# @anosys/claude-code

AnoSys observability and analytics hook for Anthropic's Claude Code.

This package automatically captures Claude Code's telemetry, session turns, context sizes, and API costs, and sends them to your AnoSys workspace. It integrates directly into Claude Code's native `Stop` hook mechanism.

## Installation

You can run the installer interactively using `npx`:

```bash
npx @anosys/claude-code install
```

The installer will prompt you for:
1. **AnoSys API Key**: Your ingestion API key from the AnoSys Console.
2. **Endpoint URL**: Defaults to `https://www.anosys.ai`.
3. **Content Redaction**: If enabled, all conversation content (prompts, answers, thinking) will be redacted and replaced with `REDACTED` before being sent. Only metadata and tokens will be tracked.

### Headless Installation

If you prefer to install without interactive prompts, you can pass the configuration via flags:

```bash
npx @anosys/claude-code install \
  --api-key "your_api_key" \
  --endpoint "https://api.anosys.ai" \
  --redaction
```

## CLI Commands

The package provides a unified CLI to manage your hook installation safely. It modifies `~/.claude/settings.json` and creates automatic backups (`~/.claude/settings.json.bak`) before any changes.

### `status`
Check the current installation status of the AnoSys hook:
```bash
npx @anosys/claude-code status
```

### `install`
Installs or updates the hook in your Claude Code settings:
```bash
npx @anosys/claude-code install
```

### `uninstall`
Safely removes the AnoSys hook and related environment variables from your settings:
```bash
npx @anosys/claude-code uninstall
```

### `run`
This command is executed automatically by Claude Code when a session ends. You generally do not need to run this manually:
```bash
npx @anosys/claude-code run
```

## How it works

When installed, this package registers a `Stop` hook in `~/.claude/settings.json` using the `{"owner": "anosys"}` tag. When a Claude Code session concludes, the hook is invoked. It scans your local Claude transcripts (`~/.claude/projects/`), incrementally maps any new messages or subagent events using the AnoSys schemas, calculates accurate pricing, applies optional PII redaction, and batches the results to your AnoSys workspace.
