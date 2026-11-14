<p align="center">
  <a href="https://anosys.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="assets/anosys-new-white-darkmode.svg">
      <img src="assets/anosys-new-black-lightmode.svg" alt="Anosys.ai" width="240">
    </picture>
  </a>
</p>

# Antigravity integration

Collect Google Antigravity agent turns, tool calls, commands, changed files, model activity, and duration. The integration uses PreInvocation and Stop hooks and reads the local transcript identified by the hook event.

## Installation

Choose one implementation.

### Python

Requires Python 3.10 or later.

```bash
pip install anosys-antigravity
anosys-antigravity install
anosys-antigravity status
```

### JavaScript

The package declares Node.js 18 or later. Install the executable persistently so Antigravity can invoke it after setup.

```bash
npm install -g anosys-sdk-antigravity
anosys-antigravity install
anosys-antigravity status
```

The npm package is named anosys-sdk-antigravity; its executable is anosys-antigravity. Choose one language implementation per installation.

Use an AnoSys **Claude Code & Codex CLI (CC)** endpoint key from [integration options](https://console.anosys.ai/collect/integrationoptions). The installer validates the key and warns on failure; a successful installation message alone does not confirm delivery.

## Configuration

```bash
anosys-antigravity install --api-key "your-cc-endpoint-key" --yes
```

For project-specific installation, add --workspace. The installer writes hooks and credentials to:

| Scope | Hook configuration | Credentials and settings |
| --- | --- | --- |
| Global | ~/.gemini/config/hooks.json | ~/.gemini/config/anosys-env.json |
| Workspace | .agents/hooks.json | .agents/anosys-env.json |

The runner searches the current working directory and its parents for the nearest workspace configuration, then fills missing values from the global configuration. Explicit ANOSYS_HOOK_APIKEY and ANOSYS_HOOK_ENDPOINT_URL environment variables take precedence over saved values.

The command supports --endpoint-url, --auto-update, and --no-auto-update (--redaction is still accepted and means metadata). For Python virtual environments or Node version managers, ensure the hook executable remains available to Antigravity or use an absolute path in the hook configuration.

## Verify delivery

Restart Antigravity, complete a turn, and inspect ~/.gemini/config/state/anosys_hook.log. Failed submissions are buffered in pending_records.jsonl in the same state directory and retried later. The status command checks configuration, not network delivery.

Use ANOSYS_HOOK_DRY_RUN=true for synthetic-event diagnostics without network submission. The run handler is called by Antigravity; it normally should not be invoked manually.

## Commands

```bash
anosys-antigravity install
anosys-antigravity status
anosys-antigravity uninstall
```

For workspace installations, pass --workspace to status and uninstall as well as install.

## Data coverage and limitations

The integration captures prompts, responses, available reasoning blocks, tool input/output, IDE context when present, settings changes, and execution duration. Token counters are not exposed in the hook inputs and transcripts handled by version 0.1.0. Emitted zero token fields mean **unavailable**, not zero consumption. Token spend and cost cannot be inferred from those fields.

By default only metadata is sent; full content needs `anosys-antigravity privacy full` and acceptance of the [data-collection policy](PRIVACY.md). Content fields are encrypted when ANOSYS_ENCRYPTION_KEY is set. Read [content controls](DATA_CONTROLS.md) and the [Antigravity variables reference](ANTIGRAVITY_VARIABLES.md) before collecting sensitive data.
