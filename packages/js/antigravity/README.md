# anosys-sdk-antigravity

JavaScript observability integration for Google Antigravity. Collect agent turns, tool activity, commands, changed paths, available model and IDE context, and duration.

The package declares Node.js 18 or later and uses built-in Node.js modules.

## Install

```bash
npm install -g anosys-sdk-antigravity
anosys-antigravity install
anosys-antigravity status
```

The package name is anosys-sdk-antigravity; the executable is anosys-antigravity. A persistent installation keeps the command available when Antigravity invokes it later.

For a non-interactive setup:

```bash
anosys-antigravity install --api-key "your-cc-endpoint-key" --redaction --yes
```

Use an AnoSys Claude Code & Codex CLI (CC) endpoint key. Add --workspace for a project-specific configuration.

## Coverage

The runner reads Antigravity PreInvocation and Stop events and the local transcript. Token counters are unavailable; emitted zero values do not indicate zero consumption. This version does not estimate token spend or cost.

Content redaction is optional. This version does not implement selected-field encryption.

See the [complete setup guide](../../../ANTIGRAVITY.md), [variables reference](../../../ANTIGRAVITY_VARIABLES.md), and [content controls](../../../DATA_CONTROLS.md) for configuration paths, environment precedence, diagnostics, and limitations.

## License

[Apache License 2.0](LICENSE).
