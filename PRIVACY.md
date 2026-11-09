# AnoSys SDK data-collection policy

**Version 2026-11-09**

> Draft for legal review. The version string above is what users accept with
> `privacy full`; any change that needs fresh consent must bump it together
> with `POLICY_VERSION` in `anosys-sdk-core` (Python and JavaScript).

This policy covers the coding-agent hooks in this repository: the Claude Code,
Codex and Antigravity integrations (Python and JavaScript). These hooks read the
local session files of tools you use every day, so they can see far more than an
application SDK does. They therefore collect **metadata only** unless you
explicitly accept this policy.

The application SDKs (OpenAI, OpenAI Agents, Anthropic, Claude Agent SDK and the
decorators) send what your own code instruments; see
[DATA_CONTROLS.md](DATA_CONTROLS.md) for how to limit and encrypt that.

## Collection levels

| Level | What is sent | How to choose it |
| --- | --- | --- |
| `off` | Nothing. The hook stays installed and exits. | `<tool> privacy off` or `ANOSYS_DISABLE=1` |
| `metadata` (default) | Session and event ids, timestamps, model names, token, cost and duration numbers, tool names and counts, status flags, and the workspace identifiers listed below. | Default; `<tool> privacy metadata` |
| `full` | Everything at `metadata`, plus content: prompts, assistant answers and thinking, tool inputs and outputs, shell commands, file paths and file contents that pass through the tool, task descriptions, titles, error messages and the raw session record. | `<tool> privacy full`, after reading and accepting this policy |

`<tool>` is `anosys-claude-code`, `anosys-codex` or `anosys-antigravity` (Python),
or `anosys-sdk-claude-code`, `anosys-codex`, `anosys-antigravity` (JavaScript).

### Identifiers sent at `metadata`

To make sessions useful to group and filter, `metadata` also sends:

- your operating-system username;
- the project (folder) name and working directory;
- git branch, worktree and pull-request identifiers when the tool records them.

If these are sensitive for a project, put a `.anosys` file containing `level=off`
in that project's root. A project file can only lower the level, never raise it.

### Consent

`full` is used only when `~/.anosys/consent.json` (readable only by you) records
acceptance of this exact policy version. If the version changes, collection falls
back to `metadata` until you accept again. Every record carries a `consent` field (stored in column `cvs198`),
`full;2026-11-09` or `metadata;none`, so the level a record was collected
under is always known.

Precedence, strongest first: `ANOSYS_DISABLE=1`, an explicit flag, a project
`.anosys` file (lower only), the consent file, `ANOSYS_COLLECTION_LEVEL`, the
legacy `REDACTION=true` (means `metadata`), then the default `metadata`.

## What the hooks never do

- Read sessions other than the one that just ended (and its subagents). Earlier
  history is never uploaded.
- Write prompts, answers or payloads to their local log. Logs hold ids, sizes and
  status codes only, rotate at 5 MB and are readable only by you.
- Retry forever. Failed records wait in a local queue (readable only by you) for
  at most 24 hours, 5 attempts and 50 MB. Rejected requests (400, 401, 403, 404,
  413, 422) are dropped, and an authorization error pauses collection for 6 hours.

## Secrets

At `full`, strings shaped like credentials (API keys and tokens for common
providers, private keys, JWTs, `key=value` secrets) are replaced with `[SECRET]`
before sending. This is best effort: it cannot recognize every secret or every
kind of personal data.

## Encryption

Set `ANOSYS_ENCRYPTION_KEY` (and a workspace salt in `ANOSYS_ENCRYPTION_SALT`) to
encrypt content fields on your machine before they are sent. AnoSys stores only
ciphertext for those fields; reading them requires your passphrase in the
browser. Encryption is deterministic so dashboards can still group and join on
encrypted values. That means equal values produce equal ciphertext, which reveals
that two values are equal (not what they are). Details are in
[DATA_CONTROLS.md](DATA_CONTROLS.md).

Evaluations cannot run on encrypted fields and refuse to.

## Where data goes

Records are sent over HTTPS to the AnoSys ingestion endpoint for the API key you
configured and stored in your AnoSys workspace. Retention and deletion follow your
AnoSys workspace agreement.

## Local files and removal

| Command | What it does |
| --- | --- |
| `<tool> privacy` | Shows the current level and where it comes from |
| `<tool> doctor` | Shows installed copies, the active hook and local files |
| `<tool> purge` | Deletes the local queue and logs |
| `<tool> uninstall` | Removes the hook and its saved settings |

## Changes

| Version | Change |
| --- | --- |
| 2026-11-09 | First version: metadata by default, consent for full content, `consent` field on every record. |
