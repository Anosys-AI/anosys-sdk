# Antigravity integration

## Availability

The Python and JavaScript integrations are implemented on the [moisisv/antigravity branch](https://github.com/Anosys-AI/anosys-sdk/tree/moisisv/antigravity). They are not merged into main, and `anosys-antigravity` and `anosys-sdk-antigravity` are not currently published to PyPI or npm.

Use a separate checkout to evaluate the integration. Registry installation commands will not work until packages are published.

## Install from source

```bash
git clone --branch moisisv/antigravity --single-branch \
  https://github.com/Anosys-AI/anosys-sdk.git anosys-antigravity-dev
cd anosys-antigravity-dev
```

Choose one implementation.

### Python

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e packages/python/antigravity
anosys-antigravity install
anosys-antigravity status
```

### JavaScript

```bash
npm install -g ./packages/js/antigravity
anosys-antigravity install
anosys-antigravity status
```

Use an AnoSys **Claude Code & Codex CLI (CC)** endpoint key from [integration options](https://console.anosys.ai/collect/integrationoptions). The installer supports `--api-key`, `--redaction`, and `--workspace`. Keep the installed executable available to the Antigravity process. A Python virtual environment may require an absolute executable path in the hook configuration when the environment is inactive.

## Collection and limitations

The branch registers `PreInvocation` and `Stop` handlers in `~/.gemini/config/hooks.json`, or `.agents/hooks.json` with `--workspace`. It records agent turns, prompts, responses, reasoning when available, tool activity, commands, changed paths, and duration. Test the hook configuration against the Antigravity version being used.

Antigravity does not expose token counters through the hook inputs and transcripts handled by this implementation. Token fields are emitted as zero; treat them as unavailable, not as zero consumption. Do not use them to report token spend or cost. Content redaction is available; the branch does not include the encryption modules present in the released SDK packages.

Read the branch's [Python guide](https://github.com/Anosys-AI/anosys-sdk/blob/moisisv/antigravity/packages/python/antigravity/README.md) and [JavaScript guide](https://github.com/Anosys-AI/anosys-sdk/blob/moisisv/antigravity/packages/js/antigravity/README.md) for implementation-specific options.
