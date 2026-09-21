# @anosys/sdk-antigravity

AnoSys observability and telemetry hook for **Google Antigravity** (CLI, IDE, and Antigravity 2.0).

Automatically captures agent turns, prompts, model responses, Gemini reasoning/thinking blocks, tool invocations, active IDE document context, settings changes, and execution durations, sending them securely to your AnoSys workspace.

---

## Installation

```bash
npm install -g anosys-sdk-antigravity
```

or run directly with npx without installing:

```bash
npx anosys-sdk-antigravity install
```

---

## Quick Setup

Run the installer to register the hook in Antigravity's configuration (`~/.gemini/config/hooks.json`):

```bash
npx anosys-sdk-antigravity install
```

The installer will prompt you for your **AnoSys Logs API Key** (CC pixel).

### Passing API Key on Install

You can provide the API key using any of the following methods:

#### 1. CLI Flag (`--api-key`)
```bash
npx anosys-sdk-antigravity install --api-key "YOUR_ANOSYS_API_KEY" -y
```

#### 2. Positional Argument
```bash
npx anosys-sdk-antigravity install "YOUR_ANOSYS_API_KEY" -y
```

#### 3. Environment Variable
```bash
export ANOSYS_HOOK_APIKEY="YOUR_ANOSYS_API_KEY"
# or: export ANOSYS_API_KEY="YOUR_ANOSYS_API_KEY"
npx anosys-sdk-antigravity install -y
```

#### 4. Interactive Prompt
```bash
npx anosys-sdk-antigravity install
# Prompts: "AnoSys API key for logs (leave blank to skip): "
```

### Options

- `api_key`: AnoSys API key passed as an optional positional argument.
- `--api-key <key>`: AnoSys API key passed as a flag.
- `-y`, `--yes`: Non-interactive mode (uses defaults for prompts).
- `--redaction`: Enable content masking for user prompts, tool arguments, and responses.
- `--no-redaction`: Disable content masking (default).
- `--endpoint-url <url>`: Custom ingestion endpoint URL.
- `--workspace`: Install to workspace `.agents/hooks.json` instead of global `~/.gemini/config/hooks.json`.
- `-h`, `--help`: Show help and command options.

---

## Commands

| Command | Description |
|---|---|
| `npx anosys-sdk-antigravity install [key]` | Register the AnoSys hook in Antigravity's `hooks.json` |
| `npx anosys-sdk-antigravity uninstall` | Remove the AnoSys hook from `hooks.json` |
| `npx anosys-sdk-antigravity status` | Display hook registration and configuration status |
| `npx anosys-sdk-antigravity run` | Handler invoked by Antigravity on `PreInvocation` and `Stop` events |

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

## Telemetry Coverage & Limitations

### AI Token Usage (`input_tokens`, `output_tokens`, `total_tokens`)

Unlike Claude Code or OpenAI Codex (which record token counters in local session logs), **Google Antigravity does not report token counts** in either its hook stdin payloads (`PreInvocation`, `Stop`) or in its local transcript files (`transcript_full.jsonl`).

Consequently:
- **`input_tokens` (`cvn1`)**, **`output_tokens` (`cvn2`)**, and **`total_tokens` (`cvn3`)** are emitted as **`0`**.
- Model and agent activity is observed and tracked through:
  - **`llm_step_count` (`cvn26`)**: Total number of LLM planner round-trips in the turn.
  - **`has_thinking` (`cvb2`) & `thinking`**: Full Gemini reasoning and thinking blocks captured in `llm_steps` and `cvs199`.
  - **`duration_ms` (`cvn6`) & `tool_duration_ms` (`cvn39`)**: Turn wall-clock duration and cumulative tool execution time.
  - **`tool_count` (`cvn41`)**: Total number of tool invocations performed in the turn.
  - **`commands` (`cvs90`) & `written_paths` (`cvs91`)**: Full audit trail of executed terminal commands and modified files.

---

## License

Apache 2.0
