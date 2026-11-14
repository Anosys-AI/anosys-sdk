<p align="center">
  <a href="https://anosys.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/anosys-ai/anosys-sdk/main/assets/anosys-new-white-darkmode.svg">
      <img src="https://raw.githubusercontent.com/anosys-ai/anosys-sdk/main/assets/anosys-new-black-lightmode.svg" alt="Anosys.ai" width="240">
    </picture>
  </a>
</p>

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
anosys-antigravity install --api-key "your-cc-endpoint-key" --yes
```

Use an AnoSys Claude Code & Codex CLI (CC) endpoint key. Add --workspace for a project-specific configuration. Ensure the Python environment's anosys-antigravity executable is available to the Antigravity process after setup.

## Coverage

The runner reads Antigravity PreInvocation and Stop events and the local transcript. It does not receive token counters; zero token fields mean unavailable. It does not estimate token spend or model cost.

## Privacy

By default the hook sends metadata only: ids, timestamps, models, token and cost numbers, durations, tool names, and the project, branch and OS username. Prompts, answers, tool output, commands and file contents are sent only after you accept the [data-collection policy](../../../PRIVACY.md):

```bash
anosys-antigravity privacy          # show the current level and where it comes from
anosys-antigravity privacy full     # read and accept the policy, then send full content
anosys-antigravity privacy off      # keep the hook installed but send nothing
anosys-antigravity doctor           # installed copies, the active hook and local files
anosys-antigravity purge            # delete the local queue and logs
```

The hook reads only the session that just ended, never earlier history, and its log holds ids and sizes only. The old `--redaction` flag and `REDACTION=true` still work and mean `metadata`. See [content controls](../../../DATA_CONTROLS.md) for the 10 MB request limit, retries and encryption.

See the [complete setup guide](../../../ANTIGRAVITY.md), [variables reference](../../../ANTIGRAVITY_VARIABLES.md), and [content controls](../../../DATA_CONTROLS.md) for configuration paths, environment precedence, diagnostics, and limitations.

## License

[Apache License 2.0](LICENSE).
