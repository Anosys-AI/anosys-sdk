# anosys-antigravity

AnoSys observability and telemetry hook for **Google Antigravity** (CLI, IDE, and Antigravity 2.0).

Automatically captures agent turns, prompts, model responses, Gemini reasoning/thinking blocks, tool invocations, active IDE document context, settings changes, and execution durations, sending them securely to your AnoSys workspace.

---

## Installation

```bash
pip install anosys-antigravity
```

## Quick Setup

Run the interactive installer to register the hook in Antigravity's global configuration (`~/.gemini/config/hooks.json`):

```bash
anosys-antigravity install
```

### Non-Interactive Install (CI / Automated Scripts)

```bash
anosys-antigravity install --api-key "YOUR_ANOSYS_API_KEY" -y
```

### Options

- `--api-key KEY`: AnoSys API key (validated against CC pixel).
- `-y`, `--yes`: Non-interactive mode with default answers.
- `--redaction`: Enable content masking for user prompts, tool arguments, and responses.
- `--workspace`: Install to workspace `.agents/hooks.json` instead of global `~/.gemini/config/hooks.json`.

---

## Commands

| Command | Description |
|---|---|
| `anosys-antigravity install` | Register the AnoSys hook in Antigravity's `hooks.json` |
| `anosys-antigravity uninstall` | Remove the AnoSys hook from `hooks.json` |
| `anosys-antigravity status` | Display hook registration and configuration status |
| `anosys-antigravity run` | Handler invoked by Antigravity on `PreInvocation` and `Stop` events |

---

## Configuration & Environment Variables

Credentials and configuration are stored in `~/.gemini/config/anosys-env.json`. You can also configure them via environment variables:

| Variable | Default | Description |
|---|---|---|
| `ANOSYS_HOOK_APIKEY` | — | AnoSys API key for log ingestion |
| `ANOSYS_HOOK_ENDPOINT_URL` | `https://api.anosys.ai/ingestion` | Ingestion endpoint URL |
| `REDACTION` | `false` | Set to `true` to mask prompts and outputs |
| `ANOSYS_HOOK_DRY_RUN` | `false` | Log payloads locally instead of sending |

---

## License

Apache 2.0
