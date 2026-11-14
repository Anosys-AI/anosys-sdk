<p align="center">
  <a href="https://anosys.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="assets/anosys-new-white-darkmode.svg">
      <img src="assets/anosys-new-black-lightmode.svg" alt="Anosys.ai" width="240">
    </picture>
  </a>
</p>

# Release notes

## Anosys.ai SDK 2.0 — November 2026

This release changes what the SDKs collect by default and gives users and developers more control over it. The coding-tool hooks now send metadata only until the user opts in. Every package shares one collection-level setting, and encryption covers all content fields. Read the upgrade notes before rolling it out.

### Upgrade notes

- **The coding-tool hooks send metadata only by default.** This applies to Claude Code, Codex and Antigravity. After upgrading, records keep ids, timing, models, tokens and cost, but no prompts, answers, tool input or output, commands or file contents. To keep collecting content, each user runs `<tool> privacy full` and accepts the [data collection policy](PRIVACY.md). Dashboards built on hook content will be empty until they do.
- **Every package needs `anosys-sdk-core` 2.0.0.** Upgrade it together with the other packages; on npm it is a new package that every JavaScript package now depends on.
- **Run `install` again for each coding tool after upgrading.** The hook command now uses absolute paths. The old command forms are still recognised, so uninstall keeps working.
- **`ANOSYS_API_URL` now overrides the key.** When it is set, records go to that URL and the key is not resolved. Leave it unset unless you run your own ingestion endpoint.
- **Encryption covers more columns.** With `ANOSYS_ENCRYPTION_KEY` set, every column outside the metadata allowlist is encrypted, not just a fixed list. Queries that read content columns need the passphrase to decrypt them. `ANOSYS_ENCRYPTED_COLUMNS` still replaces the selection.
- **Claude Code columns changed.** `cvs90` now holds the commands run and `cvs91` the files written, as in Codex and Antigravity.
- **Python reads less from `.env`.** Only `ANOSYS_API_KEY`, `ANOSYS_API_URL` and `ANOSYS_RESOLVER_URL` are read, and they never overwrite variables already set.
- **Old redaction settings now mean `metadata`.** `REDACTION=true` and the installers' `--redaction` flag still work.

### Collection levels

There are three levels: `off`, `metadata` and `full`. Every record says which one applied, in `cvs198`:

| Record | `cvs198` |
| --- | --- |
| Hook record at `full`, policy accepted | `full;2026-11-09` (the policy version) |
| Hook record at `metadata` | `metadata;none` |
| Application SDK record | `full;app` or `metadata;app` |

- **Coding-tool hooks.** Set the level per user with `<tool> privacy off|metadata|full`, for example `anosys-claude-code privacy full`. `full` requires accepting the policy.
- **Application SDKs** (OpenAI, OpenAI Agents, Anthropic, Claude Agent SDK and the decorators). These default to `full`, because the developer chooses what their own application sends. Lower it with `capture_content=False` / `captureContent: false` or `ANOSYS_COLLECTION_LEVEL=metadata`.
- **What can lower the level.** `ANOSYS_DISABLE=1` turns everything off. A project `.anosys` file with `level=off` or `level=metadata` applies to that folder and its subfolders. `ANOSYS_COLLECTION_LEVEL` and `REDACTION=true` can also lower it. None of these can raise the level.
- **Antigravity workspace files** (`.agents/anosys-env.json`). These can lower the level too. They cannot change the endpoint, and they cannot replace the user's own API key.
- **What `metadata` sends.** Only numbers, booleans and an allowlist of descriptive columns. A new field stays out until someone adds it to the list.
- **Secret scrubbing at `full`.** Strings that look like credentials are replaced with `[SECRET]`, for example API keys, GitHub and GitLab tokens, private keys, JWTs and passwords in URLs.
- **User context.** The context passed with `get_user_context` is stored only in `cvs5`. It is dropped at `metadata` and encrypted at `full` when a key is set.
- **Turning collection back on.** Claude Code never sends turns written while collection was off.

### Encryption

- **Format.** `enc2:` values use PBKDF2-HMAC-SHA256 (600,000 iterations) and deterministic AES-256-GCM. The same value always encrypts the same way within a workspace, so `GROUP BY` and joins still work.
- **JSON columns.** Encrypted values are stored as a JSON string, so the column stays valid JSON.
- **Failures.** If encryption fails, the column is dropped rather than sent in clear.

Details and a test vector are in [DATA_CONTROLS.md](docs/DATA_CONTROLS.md).

### Reliability

**Application SDKs**
- **Non-blocking sends.** Records go out in the background, so an instrumented call never waits on AnoSys. When the queue is full, records are dropped with a single warning.
- **No key, no traffic.** Without an API key nothing is sent. There is no fallback endpoint.

**Coding-tool hooks**
- **Retries.** Hooks retry only timeouts, connection errors, 408, 429 and 5xx. Retries come from a local queue capped at 24 hours, 5 attempts and 50 MB. A 401 or 403 pauses collection for 6 hours.
- **Bounded run time.** A hook run spends at most `ANOSYS_HOOK_TIME_BUDGET` seconds sending (default 20).
- **Level changes apply to the queue.** Queued records are filtered again to the level in force when they are retried.
- **The coding tool never fails.** Errors are logged by type only and the hook exits normally.

**Both**
- **Request size.** Requests stay under 10 MB (`ANOSYS_MAX_BATCH_BYTES`). Oversized records have their largest content fields cut, with a marker showing the original size.

### Integrations

- **OpenAI (JavaScript).**
  - Prompts and answers are now captured at `full`, including in apps that load `openai` with ESM `import`.
  - AnoSys no longer registers a process-wide OpenTelemetry logger, so the app's own logging is unaffected, and prompts are never copied into the app's logs.
  - `patchOpenAI(client)` covers clients created before the logger.
- **Exporters.** Each exporter now handles only its own spans. Other spans on a shared tracer provider are left alone.
- **Codex installer.** A `notify` setting written over several lines is now handled. An existing notifier is kept and called after AnoSys.
- **Installers.** Hooks now use absolute paths. When the installer runs from the npx cache, the hook falls back to the installed command or `npx -y <package>`. Backups and state files are readable only by the user.
- **Claude Code on Windows.** The JavaScript hook now reads its input correctly on Windows.
- **Decorators (Python).** `@anosys_logger` now supports generator functions as well as sync, async and async-generator functions.

### Examples

New notebooks:
- [Core decorators](examples/anosys_core_decorators_poc.ipynb)
- [LangChain with OpenAI tools](examples/anosys_langchain_agentic_poc.ipynb)
- [OpenRouter through LangChain](examples/anosys_openrouter_agentic_poc.ipynb)

The OpenAI, Anthropic and Claude Agent SDK notebooks were updated for this release.

### Versions

| Package | Python | JavaScript | Previous (Py / JS) |
| --- | --- | --- | --- |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/anosys-dark.svg"><img src="assets/logos/anosys-light.svg" width="16" height="16" alt=""></picture> Core | `anosys-sdk-core` 2.0.0 | `anosys-sdk-core` 2.0.0 (new on npm) | 1.1.0 / — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/openai-dark.svg"><img src="assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> OpenAI | `anosys-sdk-openai` 1.1.0 | `anosys-sdk-openai` 1.1.0 | 1.0.14 / 1.0.12 |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/openai-dark.svg"><img src="assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> OpenAI Agents | `anosys-sdk-openai-agents` 1.1.0 | `anosys-sdk-openai-agents` 1.1.0 | 1.0.13 / 1.0.12 |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/anthropic-dark.svg"><img src="assets/logos/anthropic-light.svg" width="16" height="16" alt=""></picture> Anthropic | `anosys-sdk-anthropic` 1.1.0 | `anosys-sdk-anthropic` 1.1.0 | 1.0.0 / 1.0.0 |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/claude-dark.svg"><img src="assets/logos/claude-light.svg" width="16" height="16" alt=""></picture> Claude Agent SDK | `anosys-sdk-claude-agents` 1.1.0 | `anosys-sdk-claude-agents` 1.1.0 | 1.0.0 / 1.0.0 |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/claude-dark.svg"><img src="assets/logos/claude-light.svg" width="16" height="16" alt=""></picture> Claude Code | `anosys-claude-code` 0.3.0 | `anosys-sdk-claude-code` 0.3.0 | 0.2.9 / 0.2.6 |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/openai-dark.svg"><img src="assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> Codex | `anosys-codex` 0.2.0 | `anosys-sdk-codex` 0.2.0 | 0.1.1 / 0.1.0 |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/google-dark.svg"><img src="assets/logos/google-light.svg" width="16" height="16" alt=""></picture> Antigravity | `anosys-antigravity` 0.2.0 | `anosys-sdk-antigravity` 0.2.0 | 0.1.0 / 0.1.0 |
