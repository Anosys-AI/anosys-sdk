# @anosys/sdk-antigravity

AnoSys observability and telemetry hook for **Google Antigravity** (CLI, IDE, and Antigravity 2.0).

Automatically captures agent turns, prompts, model responses, Gemini reasoning/thinking blocks, tool invocations, active IDE document context, settings changes, and execution durations, sending them securely to your AnoSys workspace.

---

## Installation

```bash
npm install -g anosys-sdk-antigravity
```

or run with npx:

```bash
npx anosys-sdk-antigravity install
```

---

## Commands

| Command | Description |
|---|---|
| `anosys-antigravity install` | Register the AnoSys hook in Antigravity's `hooks.json` |
| `anosys-antigravity uninstall` | Remove the AnoSys hook from `hooks.json` |
| `anosys-antigravity status` | Display hook registration and configuration status |
| `anosys-antigravity run` | Handler invoked by Antigravity on `PreInvocation` and `Stop` events |

---

## License

Apache 2.0
