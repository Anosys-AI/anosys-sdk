# AnoSys SDK 2.0 Release Notes

## Privacy-First Observability & Secure Consent Architecture

AnoSys SDK 2.0 introduces a revamped privacy core, unified data controls, non-intrusive OpenTelemetry coexistence, and comprehensive client-side encryption across all Python and JavaScript packages.

---

### Key Highlights

#### 1. Coding Agent Hooks Default to Metadata
- **Claude Code, Codex, and Antigravity hooks default to `metadata` collection.**
- At the default `metadata` level, only identifiers, execution timing, model names, token counts, and operational status are transmitted. No prompts, assistant messages, tool inputs/outputs, file contents, or shell commands are collected.
- Capturing `full` conversation content requires explicit user acceptance of the [AnoSys Data Collection Policy](PRIVACY.md) via CLI (`<tool> privacy full`).
- Every record explicitly carries its consent and policy state in `cvs198` (e.g., `full;2026-11-09` or `metadata;none`).
- Collection can be disabled at any time with `<tool> privacy off` or `ANOSYS_DISABLE=1`.

#### 2. Strict Privacy Ceilings
- Project `.anosys` files and workspace settings files (`.agents/anosys-env.json`) can **only lower** the collection level (e.g. from `full` to `metadata` or `off`), **never raise it**.
- An untrusted repository cannot escalate collection or override the user's consent.
- User global credentials and environment keys take precedence over repository workspace files, preventing credential hijacking.

#### 3. Application SDKs (OpenAI, Anthropic, Agents)
- Application SDKs instrument developer applications and default to `full` capture with consent label `<level>;app`.
- Developers can configure `capture_content=False` (Python) or `captureContent: false` (JS) to restrict collection to `metadata` only.
- Strict allowlisting ensures no prompt, completion, tool arguments, or message content reaches the output when collecting at `metadata`.
- **OpenTelemetry Logger Bridge Coexistence (Fixes N2 & N3)**:
  - In JavaScript OpenAI instrumentation, AnoSys delegates through `_instrumentation.setLoggerProvider(new BridgeLoggerProvider())` on the instrumentation instance instead of registering a process-wide global logger provider (`logs.setGlobalLoggerProvider()`).
  - This guarantees full compatibility with existing host application logging pipelines (e.g. `@opentelemetry/sdk-node` NodeSDK, Datadog, Grafana, Pino, Winston OTel transports), regardless of whether the host application initializes its logging before or after AnoSys.
  - The bridge forwards OpenAI instrumentation log records to the application's active logger provider while enabling AnoSys to capture token and prompt/completion content at `full` collection level without dropping host logs.
- **User Context Plaintext Leak Prevention (Fix N4)**:
  - Discontinued automatic copying/promotion of `user_context.session_id` into `gen_ai_conversation_id` across Anthropic (Python/JS) and OpenAI Agents integrations.
  - Because `gen_ai_conversation_id` is an allowlisted metadata column, previously copying user session IDs (which often contain emails or user identifiers) bypassed metadata filtering.
  - Developer `user_context` is now placed strictly into `cvs5`, ensuring it is dropped at `metadata` level and encrypted with `enc2:` at `full` level when encryption is configured.
- **Core API Surface (Fix N1)**:
  - Explicitly exported `RANK` collection level hierarchy in `@anosys/core` JavaScript package.

#### 4. End-to-End Client-Side Encryption
- When `ANOSYS_ENCRYPTION_KEY` is configured, all content fields (prompts, completions, tool inputs/outputs, code snippets, execution results, errors, raw spans, and dynamic attributes) are encrypted client-side using AES-256-GCM with Argon2id/PBKDF2 key derivation before transmission.
- Encrypted payloads carry the `enc2:<base64>` format, preserving valid JSON strings in structured columns for columnar databases (BigQuery, ClickHouse).
- Only allowlisted metadata columns remain unencrypted for indexing and operational analytics.

#### 5. Safe Ingestion Resolution
- Endpoint resolution automatically connects using customer API keys (`ANOSYS_API_KEY`).
- `ANOSYS_API_URL` is reserved for explicit overrides in self-hosted deployments.
- Default configuration prevents accidental data leakage to marketing or documentation endpoints.

#### 6. Package Distribution Hygiene
- Standardized package manifests across all published npm packages (`@anosys/core`, `@anosys/openai`, `@anosys/anthropic`, `@anosys/openai-agents`, `@anosys/claude-code`, `@anosys/codex`, `@anosys/antigravity`) with explicit `"files": ["src/"]` whitelist.
- Prevents local tests, fixtures, and internal development artifacts from leaking into published production tarballs.

#### 7. Unified Verification & Regression Test Suite
- Consolidated all tests into a single, self-contained `test/` directory.
- Root test runner (`test/run_all_tests.sh`) coordinates 7 comprehensive validation stages:
  1. Python pytest unit tests (350+ tests)
  2. JavaScript package workspaces test runner (335+ tests)
  3. Integration tests across application SDKs and coding hooks
  4. Cross-language schema mapping & fixture compliance
  5. Dedicated release regression suites (`test/core-js/tests/04-release-regressions.test.js`, `test/test_release_regressions.py`) locking in protections against B1–B3, S1–S5, and N1–N4
  6. Release healthcheck & leak detector (`test/healthcheck/run_healthcheck.sh`, `make healthcheck`)
  7. Live LLM end-to-end integration scenarios
