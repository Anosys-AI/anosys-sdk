<p align="center">
  <a href="https://anosys.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="assets/anosys-new-white-darkmode.svg">
      <img src="assets/anosys-new-black-lightmode.svg" alt="Anosys.ai" width="240">
    </picture>
  </a>
</p>

# AnoSys SDK data-collection policy

**Version 2026-11-09** · Draft for legal review

> **For maintainers.** The version above is what a developer accepts with
> `<tool> privacy full`. It must equal `POLICY_VERSION` in
> `packages/python/core/src/anosys_sdk_core/privacy.py` and
> `packages/js/core/src/privacy.js`. Bump both (and add a row to the changelog
> below) whenever this policy changes what is collected, who receives it, how long
> it is kept or what the user is asked to accept. Wording or formatting changes do
> not need a bump. A bump moves every user back to `metadata` until they accept
> again. Items marked **[COUNSEL]** need a lawyer or a business decision before
> release.

This policy explains what the AnoSys SDKs in this repository send to AnoSys, how
to control it, and how it is protected. Each technical statement points to the
code that implements it, so it can be checked.

## 1. Who is responsible for what

- **Customer data.** Telemetry sent by the SDKs belongs to the AnoSys customer
  (the organisation that owns the AnoSys workspace and API key). For that data the
  customer is the controller and AnoSys acts as its processor, under the customer's
  agreement with AnoSys and its data-processing agreement (DPA). **[COUNSEL]: link
  the Terms of Service and DPA; confirm processor role per service.**
- **Account data.** AnoSys is the controller of account and billing data for its
  own users (sign-in identity, workspace membership). That is covered by the AnoSys
  privacy notice, not by this policy. **[COUNSEL]: link it.**
- **Lawful basis.** The customer decides the lawful basis for collecting
  telemetry about its developers and end users (for example legitimate interests or
  contract). **[COUNSEL]: confirm.** The `privacy full` acceptance described in §4
  is an informed opt-in and a record of what a developer agreed to on their
  machine. It is not meant to be the customer's lawful basis under data-protection
  law; in an employment setting consent is usually not considered freely given.

## 2. What is collected, by integration

| | Coding-agent hooks (Claude Code, Codex, Antigravity) | Application SDKs (OpenAI incl. OpenRouter via the OpenAI SDK, OpenAI Agents, Anthropic, Claude Agent SDK, decorators) |
| --- | --- | --- |
| Who decides | The developer, on their machine (`<tool> privacy`) | The developer who adds the SDK to their application |
| Default | `metadata` | `full` |
| `full` requires | Acceptance of this policy version | Nothing more: it is the developer's choice for their own application |
| Label in `cvs198` | `full;2026-11-09`, `metadata;none` | `full;app`, `metadata;app` |
| Code | `anosys_sdk_core/privacy.py`, `privacy.js` | `anosys_sdk_core/capture.py`, `capture.js` |

### Levels

| Level | What is sent |
| --- | --- |
| `off` | Nothing. Hooks stay installed and exit; application SDKs do not set up instrumentation. |
| `metadata` | Identifiers, timestamps, durations, model and provider names, token and cost numbers, tool names and counts, status and error types, plus the workspace identifiers listed below (hooks). No prompts, answers or tool data. |
| `full` | Everything at `metadata` plus content: prompts and system instructions, assistant answers and thinking, tool inputs and outputs, shell commands, file paths and file contents that pass through the tool, task descriptions, titles, error messages, and the raw session record or span. |

At `metadata` only allow-listed fields are sent; a new field stays out until it is
added to the list (`BASE_METADATA_FIELDS` and each hook's list in
`privacy.py`; `APP_METADATA_STRING_COLUMNS` in `capture.py`). The same lists and
rules are used by Python and JavaScript and are checked against shared test
fixtures (`packages/fixtures`).

### Identifiers the hooks send at `metadata`

So that sessions can be grouped and filtered, `metadata` also includes:

- the operating-system username;
- the project (folder) name and working directory;
- git branch, worktree and pull-request identifiers when the tool records them.

If these are sensitive, put a `.anosys` file containing `level=off` (or
`level=metadata`) in the project. A project file can only lower the level, never
raise it, and it also overrides settings in code.

### What the hooks never read

They read only the session that just ended (and its subagents), never earlier
history (`session_transcripts` in the Claude Code hook; the current turn in Codex;
the current conversation in Antigravity).

## 3. Controls

| Control | Effect |
| --- | --- |
| `<tool> privacy off` / `metadata` / `full` | Sets the hook level (`full` asks you to accept this policy) |
| `ANOSYS_DISABLE=1` | Sends nothing from any SDK or hook |
| `.anosys` file in a project | Lowers the level for that folder and below, for hooks and application SDKs |
| `ANOSYS_COLLECTION_LEVEL` | Default level for a process; for hooks, `full` still requires acceptance |
| `capture_content` / `captureContent` (and the OpenAI Agents `capture_*` flags) | Per-integration override in code |
| `ANOSYS_ENCRYPTION_KEY`, `ANOSYS_ENCRYPTION_SALT` | Encrypt content fields before they leave the machine (§6) |

`<tool>` is `anosys-claude-code`, `anosys-codex` or `anosys-antigravity` (Python),
or `anosys-sdk-claude-code`, `anosys-codex`, `anosys-antigravity` (JavaScript).
Full precedence rules are in [DATA_CONTROLS.md](DATA_CONTROLS.md).

## 4. Acceptance record and withdrawal

- `privacy full` shows a summary of this policy and records the accepted version in
  `~/.anosys/consent.json`, readable only by the user (mode 0600).
- `full` is used only while that file holds the current version. When the version
  changes, collection falls back to `metadata` until the user accepts again.
- Every record carries the level it was collected under in `cvs198`, so it can be
  shown later which records were sent with content and under which version.
- **Withdrawal.** `<tool> privacy metadata` or `privacy off` takes effect from the
  next record. It does not delete records already sent; deletion of stored data is
  done in the AnoSys workspace (§8). **[COUNSEL]: confirm the process and response
  time for deletion requests.**

## 5. The customer's responsibilities

The customer is responsible for:

- informing its developers and the end users of its applications that telemetry is
  collected, and on what basis;
- choosing the level for each integration, and not sending special-category data
  (health, biometrics, beliefs and similar), payment card data, or children's data
  unless that is permitted and the relevant fields are encrypted (§6);
- keeping API keys and encryption passphrases secret, and rotating them if exposed;
- configuring retention and responding to data-subject requests in its workspace.

**[COUNSEL]: align with the Acceptable Use Policy and the DPA.**

## 6. Security measures

| Measure | Where |
| --- | --- |
| HTTPS to the ingestion endpoint returned for the API key. A missing or unrecognised key disables sending; data is never sent to a default site. | `config.py` / `config.js` (`resolve_api_key`) |
| Field encryption on the user's machine (`enc2`: PBKDF2-SHA256 600,000 iterations with a workspace salt, AES-256-GCM) | `encryption.py`, `encryption.js` |
| Decryption happens only in the browser; the passphrase is never stored or sent to AnoSys, and AnoSys servers have no key to decrypt with | console `src/utils/dataDecryption.js`, `decryptionKeyStore.js` |
| Evaluations refuse encrypted fields (no ciphertext is sent to a judge model) | `eval_core/execution/judge.js` (console, queue runner, backend) |
| Best-effort scrubbing of credential-shaped strings at `full` (hooks) | `redaction.py` / `redaction.js` (`scrub_secrets`) |
| Local queue, logs, consent and state files readable only by the user (0600) | `transport.py`, `hook_cli.py`, `privacy.py` and JS equivalents |
| Logs hold ids, sizes, status codes and error types, never prompts, payloads or keys | hook runners, exporters, `transport` |
| Bounded resources: requests under 10 MB, hooks finish within a time budget (20 s by default), at most 24 h / 5 attempts / 50 MB of queued retries, application telemetry sent in the background with a bounded queue | `transport.py`, `transport.js`, `sender.js` |

**Known limitation of encryption.** Encryption is deterministic so dashboards can
group and join on encrypted values. Equal values therefore produce equal
ciphertext, which reveals that two values are equal (not what they are). Only the
selected fields are encrypted; identifiers and metadata stay readable.

## 7. Where data goes

- Records go to the AnoSys ingestion service and are stored in the customer's
  workspace. **[COUNSEL]: hosting provider and regions (the platform runs on Google
  Cloud with BigQuery storage), international transfer mechanism.**
- Optional AnoSys AI features (the assistant, insights and evaluations) send the
  data a user selects to large-language-model providers to produce results.
  Encrypted fields stay encrypted. **[COUNSEL]: list subprocessors (for example
  OpenAI and Fireworks AI as used by these features) and the notice process for
  changes.**

## 8. Retention and deletion

| Data | Retention |
| --- | --- |
| Local queue of unsent records | At most 24 hours, 5 attempts, 50 MB; `<tool> purge` deletes it |
| Local hook logs | Rotated at 5 MB, two backups; `<tool> purge` deletes them |
| Consent file (`~/.anosys/consent.json`) and hook state files | Kept after uninstall so a reinstall keeps the user's choice; delete them manually to remove them |
| Workspace data at AnoSys | **[COUNSEL]: default retention period, deletion on request and at contract end, backups** |

Data-subject requests (access, deletion, correction) about workspace data are
handled through the customer as controller. **[COUNSEL]: process and timelines.**

## 9. Incidents

**[COUNSEL]: commitment to notify customers of a personal-data breach without undue
delay (and the contractual time limit), and the contact point.** Technically,
customers can limit the impact of a breach at AnoSys by keeping hooks at
`metadata` and encrypting content fields, which AnoSys cannot decrypt.

## 10. Limits and disclaimer

Secret scrubbing and PII redaction (`pii_redaction` in the OpenAI Agents
integration) are best effort. They cannot recognise every secret or every kind of
personal data, and they do not replace choosing the right level and encrypting
sensitive fields. The SDKs are provided under the Apache 2.0 licence, without
warranty. **[COUNSEL]: align the disclaimer and liability with the commercial
terms.**

## 11. Local commands

| Command | What it does |
| --- | --- |
| `<tool> privacy` | Shows the current level and where it comes from |
| `<tool> doctor` | Shows installed copies, the active hook and local files |
| `<tool> purge` | Deletes the local queue and logs |
| `<tool> uninstall` | Removes the hook and its saved settings |

## 12. Changes

| Version | Change |
| --- | --- |
| 2026-11-09 | First version: hooks collect metadata by default and need acceptance for full content; application SDKs follow one collection level; collection level recorded in `cvs198` on every record; roles, controls, security measures, retention and open legal items. |
