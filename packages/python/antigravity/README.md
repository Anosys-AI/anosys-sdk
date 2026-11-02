# anosys-antigravity

Python observability integration for Google Antigravity. Collect agent turns, tool activity, commands, changed paths, available model and IDE context, and duration.

Requires Python 3.10 or later.

## Install

```bash
pip install anosys-antigravity
anosys-antigravity install
anosys-antigravity status
```

For a non-interactive setup:

```bash
anosys-antigravity install --api-key "your-cc-endpoint-key" --redaction --yes
```

Use an AnoSys Claude Code & Codex CLI (CC) endpoint key. Add --workspace for a project-specific configuration. Ensure the Python environment's anosys-antigravity executable is available to the Antigravity process after setup.

## Coverage

The runner reads Antigravity PreInvocation and Stop events and the local transcript. It does not receive token counters; zero token fields mean unavailable. It does not estimate token spend or model cost.

Content redaction is optional. This version does not implement selected-field encryption.

See the [complete setup guide](../../../ANTIGRAVITY.md), [variables reference](../../../ANTIGRAVITY_VARIABLES.md), and [content controls](../../../DATA_CONTROLS.md) for configuration paths, environment precedence, diagnostics, and limitations.

## License

[Apache License 2.0](LICENSE).
