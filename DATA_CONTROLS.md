<p align="center">
  <a href="https://anosys.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="assets/anosys-new-white-darkmode.svg">
      <img src="assets/anosys-new-black-lightmode.svg" alt="Anosys.ai" width="240">
    </picture>
  </a>
</p>

# Content controls, size limits and encryption

## Coverage

| Integration | Content control | Encryption |
| --- | --- | --- |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/claude-dark.svg"><img src="assets/logos/claude-light.svg" width="16" height="16" alt=""></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/openai-dark.svg"><img src="assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/google-dark.svg"><img src="assets/logos/google-light.svg" width="16" height="16" alt=""></picture> Claude Code, Codex, Antigravity hooks | Collection levels `off` / `metadata` (default) / `full` after accepting [PRIVACY.md](PRIVACY.md): `<tool> privacy` | Content fields, before sending |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/openai-dark.svg"><img src="assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> OpenAI (including OpenRouter through the OpenAI SDK) and OpenAI Agents | One collection level (below); `capture_content` / `captureContent`, OpenAI Agents `capture_inputs` / `capture_outputs` / `capture_parameters` | Selected fields, before sending |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/anthropic-dark.svg"><img src="assets/logos/anthropic-light.svg" width="16" height="16" alt=""></picture> Anthropic API | Same level; `capture_content=False` / `captureContent: false`; pass the supplied OpenTelemetry options helper to clients | Selected fields, before sending |
| <picture><source media="(prefers-color-scheme: dark)" srcset="assets/logos/claude-dark.svg"><img src="assets/logos/claude-light.svg" width="16" height="16" alt=""></picture> Claude Agent SDK | Same level; `capture_content=False` / `captureContent: false` | Selected fields, before sending |
| Decorators and `AnosysClient` | Same level | Selected fields, before sending |

[PRIVACY.md](PRIVACY.md) is the policy; this page is the technical reference.

The old `REDACTION=true` setting and the installers' `--redaction` flags still
work: they mean `metadata`.

## Collection levels for the coding-agent hooks

```bash
anosys-claude-code privacy            # show the level and where it comes from
anosys-claude-code privacy metadata   # ids, timing, models, tokens and cost only (default)
anosys-claude-code privacy full       # prompts, answers, tool I/O; asks you to accept PRIVACY.md
anosys-claude-code privacy off        # send nothing
```

The same commands exist for `anosys-codex` and `anosys-antigravity`. Other switches:

| Setting | Effect |
| --- | --- |
| `ANOSYS_DISABLE=1` | Sends nothing, whatever else is set |
| `.anosys` file with `level=off` or `level=metadata` | Lowers the level for that project and its subfolders |
| `ANOSYS_COLLECTION_LEVEL=off\|metadata\|full` | Level for environments without the consent file; `full` still needs consent |
| `ANOSYS_CONSENT_FILE` | Location of the consent file (default `~/.anosys/consent.json`) |

Every hook record carries its level in `cvs198` (`full;<policy version>` or `<level>;none`).

At `metadata` only allow-listed fields leave the machine; a new upstream field is
excluded until it is added to the list. At `full`, credential-shaped strings are
replaced with `[SECRET]` on a best-effort basis.

## Collection levels for the application SDKs

The OpenAI, OpenAI Agents, Anthropic and Claude Agent SDK integrations (and the
decorators) use the same three levels, set once for the whole process:

```bash
export ANOSYS_COLLECTION_LEVEL=metadata   # or full / off
```

or `level=metadata` in a project `.anosys` file. Precedence, strongest first:

1. `ANOSYS_DISABLE=1` sends nothing.
2. A project `.anosys` file is a ceiling: it can lower the level, never raise it, even over code.
3. The explicit argument: `capture_content` / `captureContent`, or the OpenAI Agents
   `capture_inputs` / `capture_outputs` / `capture_parameters` (all False means metadata).
4. `ANOSYS_COLLECTION_LEVEL`.
5. Default `full`. The developer instruments their own application, and the per-user
   consent file of the hooks is not read (it does not exist in servers and containers).

At `metadata` only numbers, booleans and a list of descriptive columns (ids, span
names, models, operation, status, agent names and handoffs, source) are sent;
prompts, completions, messages, tool arguments and results, raw spans, attribute
blobs and dynamically mapped attributes are dropped before encryption and sending.
`off` sends nothing and does not set up instrumentation. Records say `full;app` or
`metadata;app` in `cvs198`.

The OpenAI Agents flags `OPENAI_AGENTS_DONT_LOG_MODEL_DATA` / `_TOOL_DATA` only
control that SDK's own debug logging, not traces; the AnoSys level above controls
what AnoSys receives. `pii_redaction=True` redacts e-mail addresses, phone numbers
and similar patterns in captured content.

## Request size and retries

AnoSys ingestion drops request bodies over 10 MB. Every package fits its requests
under `ANOSYS_MAX_BATCH_BYTES` (default `10000000`, measured after encryption):

- records are batched up to the limit;
- a single record that is too large has its biggest content fields truncated
  (raw record first), each marked `...[truncated: original N bytes]`; an
  encrypted value is replaced whole, because cut ciphertext cannot be decrypted;
- a record that still does not fit is dropped with one warning.

The hooks retry only transient failures (timeouts, connection errors, 408, 429,
5xx), from a local queue that keeps records at most 24 hours, 5 attempts and
50 MB. Responses 400, 401, 403, 404, 413 and 422 are not retried; 401 and 403
also pause collection for 6 hours. A hook run spends at most
`ANOSYS_HOOK_TIME_BUDGET` seconds sending (default 20); after a timeout or
connection error the rest is queued at once instead of waiting out the timeout for
each request. Concurrent hook runs take turns on the queue (a lock file next to it,
broken after 120 s if stale); a run that cannot get the queue sends only its own
records. A hook never fails the coding tool: errors are logged by type and the
hook exits normally, also when the home folder is read-only.

The application SDKs never make the instrumented call wait: records are sent in the
background from a bounded in-memory queue (1,000 records in Python, 64 requests in
flight in JavaScript). When it is full, records are dropped with one warning;
nothing is written to disk or retried. Errors are logged by type only.

Without `ANOSYS_API_KEY` (or when the key cannot be resolved) nothing is sent. To
send to a self-hosted endpoint without a key, set `ANOSYS_API_URL`.

## Encryption

Set these in the process that runs the SDK or hook:

```bash
export ANOSYS_ENCRYPTION_KEY="your-secret-passphrase"
export ANOSYS_ENCRYPTION_SALT="your-workspace-salt"   # shown in the AnoSys console
# Optional: replaces the default selection
export ANOSYS_ENCRYPTED_COLUMNS="llm_input,llm_output,cvs199"
```

For coding tools, variables set in a terminal do not reach an already-running GUI
application; set them where the hook is launched. Never commit a passphrase.

### Format (`enc2`)

- Keys: PBKDF2-HMAC-SHA256, 600,000 iterations, salt `anosys-enc2:<workspace salt>`,
  64 bytes split into an encryption key and a nonce key.
- Nonce: the first 12 bytes of HMAC-SHA256(nonce key, plaintext).
- Cipher: AES-256-GCM. Stored as `enc2:` + Base64(nonce + ciphertext + tag).
- Columns stored as JSON in BigQuery hold the JSON string `"enc2:..."`, so the
  column stays valid JSON. Objects and arrays are serialized to JSON first.
- If encryption fails, the column is dropped rather than sent in clear.

The same plaintext always gives the same ciphertext within a workspace. That keeps
`GROUP BY`, `COUNT(DISTINCT ...)` and joins across columns working on encrypted
data, and it reveals which values are equal (never what they are). The salt is
fixed per workspace, so data stored earlier stays decryptable with the same
passphrase and salt. The field name is not part of the key, which is what makes
cross-column joins possible.

Evaluations need plaintext and refuse to run on fields that contain `enc2:` values.

Test vector: passphrase `YOUR_SECRET_KEY_HERE`, salt `workspace-123`, plaintext
`Hello from AnoSys Technologies!` gives
`enc2:QwYbSu12pZL4oSf17Bb5zJUkGjoRc3wL66HwlsbjlJ5sLJWIHWGlgz7f+PXh4yem/EvB20sQjSg+R4A=`.

### Default fields

```text
llm_input, llm_output, llm_system, gen_ai_input_messages, gen_ai_output_messages,
gen_ai_system_instructions, user_prompt, userPrompt, assistant_text, assistantText,
last_prompt, cvs4, cvs5, cvs24, cvs199, cvs18, otel_events, tool_use_result, cvs26,
commands, written_paths, file_states, ide_diagnostics, cvs30, file_attachments,
hook_specific_output, mcp_meta, custom_title, ai_title, cvs40, cvs41,
agent_description, cvs35, summary_content, task_description, cvs65,
origami_summary, status_message, error_details, api_error, error_obj, cvs25,
cause, research
```

These names cover the descriptive and legacy column layouts; see
[column mappings](MAPPINGS.md) before overriding the selection.

For Anthropic clients, use `get_anthropic_open_telemetry_options()` or
`getAnthropicOpenTelemetryOptions()` to pass the intended content setting and tracer
provider explicitly. Setting `capture_content=False` does not remove an existing
content-mode environment variable; the supplied helper carries the logger's choice.
