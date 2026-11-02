# Content controls and encryption

## Coverage

| Integration | Content control | Encryption |
| --- | --- | --- |
| OpenAI and OpenAI Agents | Review the telemetry captured by each instrumentor | Selected fields through the shared Python core or JavaScript encryption module |
| Anthropic API | `capture_content=False` / `captureContent: false`; pass the supplied OpenTelemetry options helper to clients | Selected fields before export |
| Claude Agent SDK | `capture_content=False` / `captureContent: false` | Selected fields before export |
| Claude Code and Codex CLI | Installer `--redaction` or runtime `REDACTION=true` | Selected fields before sending hook telemetry |
| Antigravity 0.1.0 | Installer `--redaction` or runtime `REDACTION=true` | Not implemented in this version |

Redaction replaces supported content fields. It is not a general-purpose personal-data scanner and is separate from encryption. Review complete payloads before enabling collection for sensitive applications.

## Enable encryption

Set these variables in the process that runs the exporter:

```bash
export ANOSYS_ENCRYPTION_KEY="your-secret-passphrase"
# Optional: replaces the default selection
export ANOSYS_ENCRYPTED_COLUMNS="llm_input,llm_output,cvs199"
```

`ANOSYS_ENCRYPTION_KEY` enables encryption when non-empty. `ANOSYS_ENCRYPTED_COLUMNS` replaces the default selection; `ANOSYS_ENCRYPTES_COLUMNS` is accepted as a compatibility alias.

For coding tools, setting variables in a terminal does not configure an already-running GUI application. Provide them to the process that launches the hook. The Codex installer saves its ingestion key and redaction settings to `$CODEX_HOME/anosys-env.sh`; it does not prompt for or save an encryption passphrase. Do not commit credentials or passphrases to a repository.

## Default fields

The default selection includes these columns when present:

```text
llm_input, llm_output, gen_ai_input_messages, gen_ai_output_messages,
gen_ai_system_instructions, llm_system, user_prompt, userPrompt,
assistant_text, assistantText, cvs4, cvs5, last_prompt, cvs24,
tool_use_result, cvs26, cvs65, task_description, summary_content, cvs199
```

These names cover descriptive and legacy column layouts. Their meaning depends on the integration; consult [column mappings](MAPPINGS.md) before overriding the selection.

Only string values are encrypted. Numbers, booleans, arrays, and objects in selected columns are skipped with a warning and remain unchanged. Values already prefixed with `enc:` are preserved. Untargeted columns remain readable. Selecting one field does not encrypt every copy of its content elsewhere in a record.

## Format and decryption

The passphrase is encoded as UTF-8 and hashed with SHA-256 to derive a 32-byte key. Strings are encrypted using AES-256-CBC with a 16-byte zero IV and PKCS#7 byte padding. The result is Base64 encoded and prefixed with `enc:`.

This compatibility format is deterministic and does not authenticate ciphertext. It is not a guarantee that all payload data is encrypted or that arbitrary personal data is detected. Python packages require `cryptography`; if it is unavailable, the helper logs a warning and skips encryption.

The SDK does not upload the encryption passphrase as a telemetry field or register browser settings. Browser decryption is configured separately in the AnoSys platform. If a setting requests the derived Base64 key, use the Base64 encoding of `SHA256(passphrase UTF-8 bytes)`. Verify the browser setting's storage behavior separately and keep decryption material under your control.

For Anthropic clients, use `get_anthropic_open_telemetry_options()` or `getAnthropicOpenTelemetryOptions()` to pass the intended content setting and tracer provider explicitly. Setting `capture_content=False` does not remove an existing content-mode environment variable; the supplied helper carries the logger's current choice.
