<p align="center">
  <a href="https://anosys.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="../assets/anosys-new-white-darkmode.svg">
      <img src="../assets/anosys-new-black-lightmode.svg" alt="Anosys.ai" width="240">
    </picture>
  </a>
</p>

# RFC: Unified Data Capture & Privacy Control Architecture

**Document Version:** 1.0.0  
**Date:** 2026-11-09  
**Status:** Implemented (see §9 for what changed from the proposal)  
**Target Packages:** `anosys-sdk-core`, `anosys-sdk-anthropic`, `anosys-sdk-openai`, `anosys-sdk-openai-agents`, `anosys-sdk-claude-agents`, and JavaScript counterparts (`packages/js/*`).

---

## 1. Executive Summary

Today, configuring data capture levels (e.g. **Metadata-Only** vs. **Full Content**) across AnoSys integrations requires developers to understand and configure different environment variables, client constructor flags, and framework-specific parameters depending on whether they use Anthropic, OpenAI, OpenAI Agents, OpenRouter, or Coding Agent hooks (Codex, Claude Code, Antigravity).

This document proposes a **Unified Capture Control Plane** powered by `anosys-sdk-core`. A single environment variable (`ANOSYS_COLLECTION_LEVEL`) or local project file (`.anosys`) will automatically orchestrate all upstream client libraries, runtime loggers, agent processors, and transport layers, while maintaining complete backward compatibility with existing explicit constructor arguments.

---

## 2. Problem Statement: Current State & Fragmentation

Currently, developers must navigate a fragmented configuration matrix across different AI ecosystems:

### Current Configuration Matrix

| Provider / Tool | Environment Variable(s) | Constructor / Setup Parameters | Scope Controlled |
| :--- | :--- | :--- | :--- |
| <picture><source media="(prefers-color-scheme: dark)" srcset="../assets/logos/anthropic-dark.svg"><img src="../assets/logos/anthropic-light.svg" width="16" height="16" alt=""></picture> **Anthropic Claude** | `ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE=metadata_only` | `AnosysAnthropicLogger(capture_content=False)`<br>`anthropic.Anthropic(open_telemetry=get_anthropic_open_telemetry_options())` | Client OpenTelemetry emission & exporter capture |
| <picture><source media="(prefers-color-scheme: dark)" srcset="../assets/logos/openai-dark.svg"><img src="../assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> **OpenAI Agents SDK** | `OPENAI_AGENTS_DONT_LOG_MODEL_DATA=True`<br>`OPENAI_AGENTS_DONT_LOG_TOOL_DATA=True` | `AnosysOpenAIAgentsLogger(capture_inputs=False, capture_outputs=False, capture_parameters=False)` | Agent callback processor & internal agent engine |
| <picture><source media="(prefers-color-scheme: dark)" srcset="../assets/logos/openai-dark.svg"><img src="../assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> **OpenAI (Standard SDK)** | `ANOSYS_COLLECTION_LEVEL=metadata` | `AnosysOpenAILogger()` | OTel span wrapper |
| <picture><source media="(prefers-color-scheme: dark)" srcset="../assets/logos/claude-dark.svg"><img src="../assets/logos/claude-light.svg" width="16" height="16" alt=""></picture> **Claude Agent SDK** | None (SDK-specific) | `AnosysClaudeAgentsLogger(capture_content=False)` | Agent & tool span export |
| <picture><source media="(prefers-color-scheme: dark)" srcset="../assets/logos/openai-dark.svg"><img src="../assets/logos/openai-light.svg" width="16" height="16" alt=""></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="../assets/logos/claude-dark.svg"><img src="../assets/logos/claude-light.svg" width="16" height="16" alt=""></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="../assets/logos/google-dark.svg"><img src="../assets/logos/google-light.svg" width="16" height="16" alt=""></picture> **Coding Hooks (Codex / Claude Code / Antigravity)** | `ANOSYS_COLLECTION_LEVEL=metadata`<br>`ANOSYS_DISABLE=1` | CLI commands: `<tool> privacy metadata`<br>Config file: `~/.anosys/consent.json` | Background transcript / session file processing |

### Why This Fragmentation Arose
1. **Upstream Source Architecture**:
   * **Anthropic** built OpenTelemetry natively into their client SDK; privacy must be set before client instantiation via `open_telemetry` options or `ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE`.
   * **OpenAI Agents** uses callback listeners (`TracingProcessor`) with separate flags for model payloads vs. tool data.
   * **Standard OpenAI** relies on bytecode monkey-patching via OpenTelemetry instrumentation.
   * **Coding Agents** run out-of-band as CLI background daemons reading transcript `.jsonl` files from disk.
2. **Granularity Differences**:
   * Standard LLMs have binary content (prompt $\to$ completion).
   * Agent workflows have multi-phase content (user query $\to$ planning $\to$ tool inputs $\to$ tool returns $\to$ handoff routing $\to$ final response).
3. **Independent Evolution**:
   * Each integration originally adopted the native idioms of its underlying framework.

---

## 3. Proposed Specification: The Unified Control Plane

### 3.1 Standard Collection Levels

All integrations will adhere to three canonical levels defined in `anosys-sdk-core`:

| Level | Telemetry Emitted | Prompts / Completions / Tool I/O | BigQuery `cvs198` |
| :--- | :--- | :--- | :--- |
| **`off`** | None (instrumentation disabled; 0 spans sent) | Dropped | *(No records sent)* |
| **`metadata`** | Timestamps, durations, token counts, model names, cost estimates, agent hierarchy, handoff paths, tool execution counts, status codes, errors. | Strictly stripped / omitted (`NULL`) | `metadata;none` |
| **`full`** | All operational metrics + full text prompts, assistant answers, thinking blocks, tool arguments, and tool responses. | Retained (plaintext or encrypted via `enc2:` if key is configured) | `full;2026-11-09` |

### 3.2 Single Precedence Hierarchy

The active capture level is resolved centrally via `effective_level(explicit=...)` in `anosys_sdk_core.privacy`:

```
1. ANOSYS_DISABLE=1                                    ──► Forces "off" (kill switch)
2. Explicit Constructor Argument (in-code override)     ──► e.g., capture_content=False
3. Project file (.anosys in workspace root)            ──► e.g., level=metadata (can only restrict, never elevate)
4. Consent file (~/.anosys/consent.json)               ──► User consent record with policy version
5. Environment Variable (ANOSYS_COLLECTION_LEVEL)       ──► "off" | "metadata" | "full"
6. Legacy REDACTION=true                               ──► Interpreted as "metadata"
7. Default Fallback                                    ──► "metadata" (hooks) or provider default
```

> **Safety Rule**: If `full` is requested without acceptance of the active policy version (`POLICY_VERSION = "2026-11-09"`), the system automatically falls back to `metadata`.

---

## 4. Technical Implementation per Integration

### 4.1 Anthropic Integration (`anosys-sdk-anthropic`)

When `capture_content` is omitted (or set to `None`), `AnosysAnthropicLogger` automatically evaluates `effective_level()`:

```python
class AnosysAnthropicLogger:
    def __init__(
        self,
        get_user_context: Optional[Callable] = None,
        capture_content: Optional[bool] = None,  # Defaults to None (inherits from core)
        use_batch_processor: bool = False,
    ):
        # 1. Resolve effective level
        eff_level, _ = effective_level()
        if capture_content is None:
            capture_content = (eff_level == FULL)
            
        # 2. Automatically propagate to Anthropic SDK environment variable
        if not capture_content:
            os.environ["ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE"] = "metadata_only"
        elif "ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE" not in os.environ:
            os.environ["ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE"] = "content"
            
        # 3. Exporter stamps cvs198 = consent_value(eff_level)
```

**Developer Experience (After):**
```python
# Just set in .env: ANOSYS_COLLECTION_LEVEL=metadata
from anosys_sdk_anthropic import AnosysAnthropicLogger, get_anthropic_open_telemetry_options
import anthropic

AnosysAnthropicLogger() # Zero-config: automatically metadata-only!
client = anthropic.Anthropic(open_telemetry=get_anthropic_open_telemetry_options())
```

---

### 4.2 OpenAI Agents Integration (`anosys-sdk-openai-agents`)

When `capture_inputs` and `capture_outputs` are omitted, `AnosysOpenAIAgentsLogger` automatically inherits from `effective_level()`:

```python
class AnosysOpenAIAgentsLogger(TracingProcessor):
    def __init__(
        self,
        get_user_context: Optional[Callable] = None,
        capture_inputs: Optional[bool] = None,
        capture_outputs: Optional[bool] = None,
        capture_parameters: Optional[bool] = None,
        use_batch_processor: bool = False,
    ):
        eff_level, _ = effective_level()
        is_full = (eff_level == FULL)
        
        self.capture_inputs = is_full if capture_inputs is None else capture_inputs
        self.capture_outputs = is_full if capture_outputs is None else capture_outputs
        self.capture_parameters = is_full if capture_parameters is None else capture_parameters
        
        # Automatically sync with OpenAI Agents internal flags
        if not self.capture_inputs and not self.capture_outputs:
            os.environ["OPENAI_AGENTS_DONT_LOG_MODEL_DATA"] = "True"
            os.environ["OPENAI_AGENTS_DONT_LOG_TOOL_DATA"] = "True"
```

**Developer Experience (After):**
```python
# Just set in .env: ANOSYS_COLLECTION_LEVEL=metadata
from agents import add_trace_processor
from anosys_sdk_openai_agents import AnosysOpenAIAgentsLogger

processor = AnosysOpenAIAgentsLogger() # Zero-config: automatically metadata-only!
add_trace_processor(processor)
```

---

### 4.3 Standard OpenAI & OpenRouter (`anosys-sdk-openai`)

When using OpenAI directly or routing through OpenRouter via `base_url="https://openrouter.ai/api/v1"`:
* `AnosysOpenAILogger()` checks `effective_level()`.
* If `metadata`, all `llm_input`, `llm_output`, and `gen_ai.input.messages` fields are scrubbed before payload export.
* `cvs198` is stamped with `metadata;none`.

---

### 4.4 Transport Safety Net (`transport.py` & `transport.js`)

To guarantee zero data leakage even if a third-party framework or new plugin bypasses logger settings:
1. `fit_record` in `transport.py` and `transport.js` inspects all outgoing records before size-checking and encryption.
2. If `cvs198` is missing:
   * It evaluates `effective_level()`.
   * It populates `record["cvs198"] = consent_value(eff_level)` and `record["consent"] = consent_value(eff_level)`.
3. If `eff_level == METADATA`, any accidental content attributes (`llm_input`, `llm_output`) are dropped before HTTP POST.

---

## 5. Developer Experience: Before vs. After

### Before (Provider-Specific Boilerplate)
```python
# Anthropic
os.environ["ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE"] = "metadata_only"
AnosysAnthropicLogger(capture_content=False)
client = anthropic.Anthropic(open_telemetry=get_anthropic_open_telemetry_options())

# OpenAI Agents
os.environ["OPENAI_AGENTS_DONT_LOG_MODEL_DATA"] = "True"
os.environ["OPENAI_AGENTS_DONT_LOG_TOOL_DATA"] = "True"
processor = AnosysOpenAIAgentsLogger(capture_inputs=False, capture_outputs=False, capture_parameters=False)
add_trace_processor(processor)

# Codex CLI
anosys-codex privacy metadata
```

### After (Unified Architecture)
In project `.env` or CI/CD environment:
```bash
export ANOSYS_COLLECTION_LEVEL="metadata"
```
Or in project root `.anosys`:
```ini
level=metadata
```
In application code:
```python
# Anthropic
AnosysAnthropicLogger()
client = anthropic.Anthropic(open_telemetry=get_anthropic_open_telemetry_options())

# OpenAI Agents
processor = AnosysOpenAIAgentsLogger()
add_trace_processor(processor)

# Both automatically emit cvs198="metadata;none" and omit all prompt/completion content!
```

---

## 6. Audit & Database Verification (`cvs198`)

Every record received by BigQuery contains column `cvs198`:

```sql
SELECT 
  timestamp,
  cvs200 AS integration_source,
  cvs17  AS model_name,
  cvs198 AS consent_level,
  llm_input,
  llm_output,
  gen_ai_usage_total_tokens
FROM `your_project.anosys_dataset.traces`
WHERE DATE(timestamp) = CURRENT_DATE();
```

* **When `cvs198 = 'metadata;none'`**: `llm_input` and `llm_output` are guaranteed `NULL`. Token counts and durations remain intact for observability.
* **When `cvs198 = 'full;2026-11-09'`**: Content is present, and encrypted if `ANOSYS_ENCRYPTION_KEY` was provided (`enc2:...`).

---

## 7. Backward Compatibility

* **Existing code remains 100% compatible**: Passing explicit parameters (`capture_content=False`, `capture_inputs=True`, etc.) still takes precedence over the environment level.
* **Deprecation Notice**: No existing flags will be deprecated; they are treated as explicit, localized overrides.

---

## 8. Questions for Engineering Team Discussion

1. **Default for Application SDKs vs. Coding Hooks**:
   * Coding hooks default to `metadata` because they observe arbitrary developer file systems and shell history.
   * Should application SDKs (`AnosysAnthropicLogger`, `AnosysOpenAILogger`) also default to `metadata` if no setting is provided, or retain `full` for explicit app-level instrumentation?
2. **Granular Agent Overrides in Unified Mode**:
   * If `ANOSYS_COLLECTION_LEVEL="metadata"`, should an explicit in-code `capture_inputs=True` in `AnosysOpenAIAgentsLogger` be allowed to override it, or should `.anosys` / `ANOSYS_COLLECTION_LEVEL` strictly enforce the ceiling?
   * *Recommendation*: A project `.anosys` file should act as an unbreakable ceiling (cannot be overridden by code); process env variables can be overridden by explicit constructor args.
3. **OpenRouter Broadcast Integration**:
   * OpenRouter server-to-server broadcast bypasses client SDKs. Should the gateway server (`anosys-public-server`) enforce an account-level default in `cvs198` when OpenRouter does not specify consent?


---

## 9. Implementation notes (2026-11-09)

Implemented in `anosys_sdk_core.capture` (Python) and `capture.js` (JS), used by every
application SDK. Where the implementation differs from the text above:

1. **Precedence.** The project `.anosys` file is a ceiling over everything, including
   explicit constructor arguments (the §8.2 recommendation), so the list in §3.2 reads:
   `ANOSYS_DISABLE` → `.anosys` (lower only) → explicit argument → `ANOSYS_COLLECTION_LEVEL`
   → default. The per-user consent file is used by the coding-agent hooks only.
2. **Default (§8.1).** Application SDKs default to `full`; the hooks stay `metadata`.
3. **Labels.** `cvs198` is the single consent column. Hooks write `full;<policy>` only
   when that policy was accepted, otherwise `metadata;none`. Application SDKs write
   `full;app` / `metadata;app`, so a record never claims a policy acceptance that did
   not happen, and the label always matches what was sent.
4. **No environment writes (§4.1, §4.2).** The loggers do not set provider environment
   variables to lower content. `OPENAI_AGENTS_DONT_LOG_MODEL_DATA` / `_TOOL_DATA` only
   control the Agents SDK's debug logging and are read once at import, so they are not
   used. Anthropic's content mode is still set to `content` at `full`, as before, since
   that SDK records metadata only by default.
5. **Filtering (§4.3, §4.4).** Each exporter applies the level itself, just before
   encryption, with an allowlist: numbers, booleans and listed descriptive columns are
   kept; every other string, list or object is dropped (raw span, attribute blobs,
   messages, tool arguments and results, dynamic attributes). The transport layer does
   not decide or stamp levels.
6. **`off`** sends nothing and skips instrumentation setup.
