# CVS Variable Mappings — Full Reference

> Auto-generated from source code scan on 2026-05-09.
> Covers all Python and JS packages.

---

## 1. Base Key Mapping (shared by all packages)

**Source of truth:**
- Python: `packages/python/core/src/anosys_sdk_core/models.py` → `BASE_KEY_MAPPING`
- JS OpenAI: `packages/js/openai/src/mapping.js` → `BASE_KEY_MAPPING`
- JS Agents: `packages/js/openai-agents/src/mapping.js` → `BASE_KEY_MAPPING`

| Internal Key | CVS Variable | Category | Notes |
|---|---|---|---|
| `custom_mapping` | `otel_schema_url` | Metadata | Schema / custom mapping JSON |
| `otel_observed_timestamp` | `otel_observed_timestamp` | Metadata | ISO timestamp when observed |
| `otel_record_type` | `otel_record_type` | Metadata | e.g. "AnoSys Trace" |
| `cvn1` | `cvn1` | Timing | Start timestamp (numeric ms) |
| `cvn2` | `cvn2` | Timing | End timestamp (numeric ms) |
| `otel_duration_ms` | `otel_duration_ms` | Timing | Duration in milliseconds |
| `name` | `otel_name` | Trace IDs | Span name |
| `trace_id` | `otel_trace_id` | Trace IDs | Trace identifier |
| `span_id` | `otel_span_id` | Trace IDs | Span identifier |
| `trace_state` | `otel_trace_flags` | Trace IDs | W3C trace state |
| `parent_id` | `otel_parent_span_id` | Trace IDs | Parent span ID |
| `start_time` | `otel_start_time` | Trace IDs | ISO start time |
| `end_time` | `otel_end_time` | Trace IDs | ISO end time |
| `kind` | `otel_kind` | Trace IDs | Span kind |
| `status` | `otel_status` | Status | Full status object |
| `status_code` | `otel_status_code` | Status | Status code |
| `resp_id` | `otel_status_message` | Status | Response ID / status message |
| `otel_resource` | `otel_resource` | Resources | Resource attributes JSON |
| `gen_ai.system` | `gen_ai_system` | Gen AI General | e.g. "openai" |
| `gen_ai.provider.name` | `gen_ai_provider_name` | Gen AI General | Provider name |
| `gen_ai.operation.name` | `gen_ai_operation_name` | Gen AI General | Operation name |
| `server.address` | `cvs14` | Gen AI General | Server hostname (reassigned) |
| `server.port` | `cvn3` | Gen AI General | Server port (reassigned) |
| `error.type` | `cvs10` | Gen AI General | Error type string (reassigned) |
| `gen_ai.request.model` | `gen_ai_request_model` | Gen AI Request | Model name |
| `gen_ai.request.temperature` | `gen_ai_request_temperature` | Gen AI Request | Temperature |
| `gen_ai.request.top_p` | `gen_ai_request_top_p` | Gen AI Request | Top-p sampling |
| `gen_ai.request.top_k` | `gen_ai_request_top_k` | Gen AI Request | Top-k sampling |
| `gen_ai.request.max_tokens` | `gen_ai_request_max_tokens` | Gen AI Request | Max output tokens |
| `gen_ai.request.frequency_penalty` | `gen_ai_request_frequency_penalty` | Gen AI Request | Frequency penalty |
| `gen_ai.request.presence_penalty` | `gen_ai_request_presence_penalty` | Gen AI Request | Presence penalty |
| `gen_ai.request.stop_sequences` | `gen_ai_request_stop_sequences` | Gen AI Request | Stop sequences |
| `gen_ai.request.seed` | `gen_ai_request_seed` | Gen AI Request | Deterministic seed |
| `gen_ai.request.choice.count` | `gen_ai_request_choice_count` | Gen AI Request | Number of choices (n) |
| `gen_ai.request.encoding_formats` | `gen_ai_request_encoding_formats` | Gen AI Request | Encoding formats |
| `gen_ai.request.tool_choice` | `cvs15` | Gen AI Request | Tool choice setting (reassigned) |
| `gen_ai.response.model` | `gen_ai_response_model` | Gen AI Response | Response model |
| `gen_ai.response.id` | `gen_ai_response_id` | Gen AI Response | Response ID |
| `gen_ai.response.finish_reasons` | `gen_ai_response_finish_reasons` | Gen AI Response | Finish reasons |
| `gen_ai.usage.input_tokens` | `gen_ai_usage_input_tokens` | Gen AI Usage | Input token count |
| `gen_ai.usage.output_tokens` | `gen_ai_usage_output_tokens` | Gen AI Usage | Output token count |
| `gen_ai.usage.total_tokens` | `gen_ai_usage_total_tokens` | Gen AI Usage | Total token count |
| `gen_ai.output.type` | `gen_ai_output_type` | Gen AI Response | Output type (text/json/image) |
| `gen_ai.input.messages` | `gen_ai_input_messages` | Gen AI Content | Input messages |
| `gen_ai.output.messages` | `gen_ai_output_messages` | Gen AI Content | Output messages |
| `gen_ai.system_instructions` | `gen_ai_system_instructions` | Gen AI Content | System instructions |
| `gen_ai.tool.definitions` | `gen_ai_tool_definitions` | Gen AI Content | Tool definitions |
| `gen_ai.agent.id` | `gen_ai_agent_id` | Gen AI Agents | Agent ID |
| `gen_ai.agent.name` | `gen_ai_agent_name` | Gen AI Agents | Agent name |
| `gen_ai.agent.description` | `gen_ai_agent_description` | Gen AI Agents | Agent description |
| `gen_ai.conversation.id` | `gen_ai_conversation_id` | Gen AI Agents | Conversation ID |
| `gen_ai.data_source.id` | `gen_ai_data_source_id` | Gen AI Agents | Data source ID |
| `gen_ai.embeddings.dimension.count` | `gen_ai_embeddings_dimension_count` | Gen AI Embeddings | Embedding dimensions |
| `llm_tools` | `llm_tools` | Legacy LLM | Tools (legacy) |
| `llm_system` | `llm_system` | Legacy LLM | System prompt (legacy) |
| `llm_input` | `llm_input` | Legacy LLM | Input (legacy) |
| `llm_output` | `llm_output` | Legacy LLM | Output (legacy) |
| `llm_model` | `llm_model` | Legacy LLM | Model name (legacy) |
| `llm_invocation_parameters` | `llm_invocation_parameters` | Legacy LLM | Invocation params (legacy) |
| `llm_token_count` | `llm_token_count` | Legacy LLM | Token count (legacy) |
| `llm_input_messages` | `gen_ai_input_messages` | Legacy LLM | Input messages |
| `llm_output_messages` | `gen_ai_output_messages` | Legacy LLM | Output messages |
| `input` | `llm_input` | Decorator | Decorator input |
| `output` | `llm_output` | Decorator | Decorator output |
| `error` | `cvs3` | Decorator | Error flag |
| `caller` | `cvs4` | Decorator | Caller info |
| `error_type` | `cvs10` | Decorator | Error type |
| `error_message` | `cvs11` | Decorator | Error message |
| `error_stack` | `cvs12` | Decorator | Error stack trace |
| `raw` | `cvs199` | Source | Raw span/record JSON |
| `from_source` | `cvs200` | Source | Source identifier |
| `source` | `cvs200` | Source | Source (alias) |
| `is_streaming` | `cvb2` | Source | Streaming flag |
| `events` | `otel_events` | Source | Span events JSON |
| `user_context` | `cvs5` | Source | User context JSON |
| `llm_model_name` | `cvs16` | Source | LLM model name alias |
| `is_agent` | `cvb1` | Source | Is agent flag |

---

## 2. OpenAI Python/JS Mapping

**Python:** `packages/python/openai/src/anosys_sdk_openai/mapping.py`
→ Simply copies `BASE_KEY_MAPPING` with no additions.

**JS:** `packages/js/openai/src/mapping.js`
→ Copies `BASE_KEY_MAPPING` (which includes the JS-only extras above).

### Fields populated by `extract_span_info()` (hooks.py / hooks.js)

| Field | Python hooks.py | JS hooks.js | Notes |
|---|---|---|---|
| `gen_ai.request.tool_choice` | ✅ | ✅ | From invocation params |
| `events` | ✅ | ✅ | Span events JSON |
| `raw` | ✅ | ✅ | Full span JSON |
| `user_context` | ❌ | ✅ | Only in JS |
| `llm_model_name` | ❌ | ✅ | Only in JS |
| `llm_token_count` | ❌ | ✅ | Only in JS (backward compat) |
| `llm_invocation_parameters` | ❌ | ✅ (conditionally) | Only in JS |
| `from_source` | `openAI_Python_Telemetry` | `openAI_Traces` | Different source tags |

---

## 3. OpenAI Agents Mapping (Python + JS)

**Source:**
- Python: `packages/python/openai_agents/src/anosys_sdk_openai_agents/mapping.py` → `AGENTS_KEY_MAPPING`
- JS: `packages/js/openai-agents/src/mapping.js` → `AGENTS_KEY_MAPPING`

Extends `BASE_KEY_MAPPING` with agents-specific fixed CVS slots:

| CVS Variable | Purpose | Used by span types |
|---|---|---|
| `g1` | Creation timestamp (numeric) | All (span2json base) |
| `llm_input` | Input (consolidated) | function, mcp_tools, generation, speech, speechgroup |
| `llm_output` | Output (consolidated) | function, mcp_tools, generation, transcription |
| `cvs3` | User context | All (span2json base) |
| `cvs60` | Object type (trace/trace.span) | All (span2json base) |
| `cvs61` | Source (span_start/span_end) | All (span2json base) |
| `cvs62` | Handoffs | agent |
| `llm_tools` | Tools list | agent |
| `cvs64` | Output type | agent |
| `cvs67` | MCP data | function, mcp_tools |
| `cvs68` | Triggered flag | guardrail |
| `gen_ai_request_model` | Model | generation, transcription, speech |
| `llm_invocation_parameters` | Model config | generation, transcription, speech |
| `llm_token_count` | Usage JSON | generation |
| `cvs72` | Data / input.data | custom, transcription, speech |
| `cvs73` | Format | transcription, speech |
| `cvs74` | First content at | speech |
| `cvs75` | MCP server | MCPListTools |
| `cvs76` | MCP result | MCPListTools |
| `cvs77` | Response ID / Config ID | response, generation, transcription, speech |
| `cvs78` | From agent | handoff |
| `cvs79` | To agent | handoff |
| `cvs199` | Raw span JSON | All (base) |
| `cvs200` | Source tag | All (`openAI_Agents_Traces`) |

### `extract_otel_span_info()` fields (OTel path)

Both Python and JS populate via `reassign()` through `AGENTS_KEY_MAPPING`:

| Field | Python | JS | Notes |
|---|---|---|---|
| Full gen_ai.* semantic conventions | ✅ (45+ fields) | ❌ (only system + model) | Python is much more complete |
| Legacy llm_* fields | ✅ | ❌ | Only Python extracts these |
| `raw` (cvs199) | ✅ | ✅ | Both capture full span |
| `user_context` | ❌ | ✅ | Only JS |
| `from_source` | `openAI_Agents_Telemetry` | `openAI_Agents_Telemetry` | Aligned |
| Usage extraction in span2json | ❌ | ✅ | JS extracts gen_ai_usage_* from spanData.usage |

---

## 4. Claude Code Mapping

**Source:** `packages/python/claude_code/src/anosys_sdk_claude_code/mapper.py` → `transform_record()`

> [!IMPORTANT]
> Claude Code does **NOT** use `BASE_KEY_MAPPING` or `reassign()`. It builds its own payload dict with hardcoded keys. The output uses some CVS slots directly.

### Fixed CVS slots used:

| Key in payload | CVS equivalent | Purpose |
|---|---|---|
| `cvs199` | `cvs199` | Raw record + metadata JSON |
| `cvs200` | `cvs200` | `'ClaudeCodeHook'` (source tag) |

### All payload fields (159 fields):

<details>
<summary>Click to expand full Claude Code payload fields</summary>

| Key | Type | Description |
|---|---|---|
| `timestamp` | number | Current time (ms) |
| `user_timestamp` | number | User's record timestamp (ms) |
| `event_id` | string | UUID / session-derived ID |
| `event_type` | string | `claude_code_{msg_type}` |
| `event_source_name` | string | Always `'claude_code'` |
| `debug` | bool | Always `false` |
| `session_id` | string | Session identifier |
| `project` | string | Folder name from cwd |
| `git_branch` | string | Current git branch |
| `user_prompt` | string | Extracted user prompt text |
| `assistant_text` | string | Extracted assistant response |
| `stop_reason` | string | LLM stop reason |
| `permission_mode` | string | Permission mode |
| `version` | string | Claude Code version |
| `primary_model` | string | Model name |
| `slug` | string | Session slug |
| `parent_uuid` | string | Parent UUID |
| `cwd` | string | Working directory |
| `raw_uuid` | string | Raw UUID from record |
| `raw_message_id` | string | Raw message ID |
| `assistant_msg_id` | string | Assistant message ID |
| `user_type` | string | User type |
| `subtype` | string | Message subtype |
| `hook_name` | string | Hook name |
| `hook_command` | string | Hook command |
| `agent_id` | string | Agent ID |
| `tool_use_id` | string | Tool use ID |
| `parent_tool_use_id` | string | Parent tool use ID |
| `source_tool_assistant_uuid` | string | Source tool assistant UUID |
| `source_tool_use_id` | string | Source tool use ID |
| `entrypoint` | string | Entrypoint |
| `last_prompt` | string | Last prompt |
| `error_obj` | string | Error object JSON |
| `tool_use_result` | string | Tool use result JSON |
| `hook_event` | string | Hook event type |
| `prompt_id` | string | Prompt ID |
| `level` | string | Log level |
| `ide_diagnostics` | string | IDE diagnostics JSON |
| `request_id` | string | Request ID |
| `integration_version` | string | SDK version (0.2.0) |
| `os_user` | string | OS username |
| `agent_type` | string | Agent type |
| `agent_description` | string | Agent description |
| `log_index` | number | Log sequence index |
| `input_tokens` | number | Input tokens |
| `output_tokens` | number | Output tokens |
| `total_tokens` | number | Total tokens |
| `cache_read` | number | Cache read tokens |
| `cache_creation` | number | Cache creation tokens |
| `duration_ms` | number | Duration in ms |
| `cost_estimate` | number | Estimated cost ($) |
| `incremental_input` | number | Incremental input tokens |
| `incremental_output` | number | Incremental output tokens |
| `incremental_total` | number | Incremental total tokens |
| `incremental_cost` | number | Incremental cost |
| `has_thinking` | bool | Contains thinking blocks |
| `is_api_error_message` | bool | Is API error |
| `is_meta` | bool | Is meta message |
| `is_sidechain` | bool | Is sidechain |
| `is_snapshot_update` | bool | Is snapshot update |
| `has_output` | bool | Has output |
| `prevented_continuation` | bool | Prevented continuation |
| `is_agent` | bool | Is agent mode |
| `usage_speed` | string | Usage speed tier |
| `inference_geo` | string | Inference geography |
| `incremental_cache_read` | number | Incremental cache read |
| `incremental_cache_creation` | number | Incremental cache creation |
| `custom_title` | string | Custom session title |
| `ai_title` | string | AI-generated title |
| `session_tag` | string | Session tag |
| `agent_map_name` | string | Agent name |
| `agent_map_color` | string | Agent color |
| `agent_setting` | string | Agent setting |
| `pr_url` | string | PR URL |
| `attribution_surface` | string | Attribution surface |
| `session_mode` | string | Session mode |
| `task_status` | string | Task status |
| `worktree_session` | string | Worktree session JSON |
| `staged_nodes` | string | Staged nodes JSON |
| `origami_summary` | string | Origami commit summary |
| `worktree_branch` | string | Worktree branch name |
| `pr_repository` | string | PR repository |
| `service_tier` | string | Service tier |
| `iterations` | string | Usage iterations JSON |
| `first_archived_uuid` | string | First archived UUID |
| `last_archived_uuid` | string | Last archived UUID |
| `original_branch` | string | Original branch name |
| `original_head_commit` | string | Original HEAD commit |
| `tmux_session_name` | string | Tmux session name |
| `task_description` | string | Task description |
| `task_type` | string | Task type |
| `time_saved_ms` | number | Time saved (ms) |
| `replaced_results_count` | number | Replaced results count |
| `logical_parent_uuid` | string | Logical parent UUID |
| `team_name` | string | Team name |
| `stop_sequence` | string | Stop sequence used |
| `leaf_uuid` | string | Leaf UUID |
| `pr_number` | number | PR number |
| `file_states` | string | File states JSON |
| `collapse_id` | string | Collapse ID |
| `summary_uuid` | string | Summary UUID |
| `summary_content` | string | Summary content |
| `armed` | bool | Armed flag |
| `last_spawn_tokens` | number | Last spawn tokens |
| `status_message` | string | Status message |
| `hook_specific_output` | string | Hook specific output JSON |
| `prompt_count` | number | Prompt count |
| `prompt_count_at_last_commit` | number | Prompts at last commit |
| `permission_prompt_count` | number | Permission prompt count |
| `permission_prompt_count_at_last_commit` | number | Permission prompts at commit |
| `escape_count` | number | Escape count |
| `escape_count_at_last_commit` | number | Escapes at last commit |
| `web_search_requests` | number | Web search request count |
| `web_fetch_requests` | number | Web fetch request count |
| `hook_based` | bool | Hook-based worktree |
| `is_synthetic` | bool | Synthetic message |
| `is_visible_in_transcript_only` | bool | Visible in transcript only |
| `is_virtual` | bool | Virtual message |
| `is_compact_summary` | bool | Compact summary |
| `is_p50` | bool | P50 flag |
| `advisor_model` | string | Advisor model |
| `upgrade_nudge` | string | Upgrade nudge |
| `url` | string | URL |
| `priority` | string | Priority |
| `hook_label` | string | Hook label |
| `stop_reason_top` | string | Top-level stop reason |
| `research` | string | Research JSON |
| `mcp_meta` | string | MCP metadata JSON |
| `summarize_metadata` | string | Summarize metadata JSON |
| `compact_metadata` | string | Compact metadata JSON |
| `microcompact_metadata` | string | Microcompact metadata JSON |
| `cause` | string | Cause JSON |
| `api_error` | string | API error JSON |
| `error_details` | string | Error details |
| `origin` | string | Origin JSON |
| `image_paste_ids` | string | Image paste IDs JSON |
| `file_attachments` | string | File attachments JSON |
| `written_paths` | string | Written paths JSON |
| `commands` | string | Commands JSON |
| `budget_tokens` | number | Budget tokens |
| `budget_limit` | number | Budget limit |
| `budget_nudges` | number | Budget nudges |
| `message_count` | number | Message count |
| `ttft_ms` | number | Time to first token (ms) |
| `otps` | number | Output tokens per second |
| `hook_duration_ms` | number | Hook duration (ms) |
| `turn_duration_ms` | number | Turn duration (ms) |
| `tool_duration_ms` | number | Tool duration (ms) |
| `classifier_duration_ms` | number | Classifier duration (ms) |
| `tool_count` | number | Tool count |
| `classifier_count` | number | Classifier count |
| `config_write_count` | number | Config write count |
| `worktree_original_cwd` | string | Worktree original CWD |
| `worktree_path` | string | Worktree path |
| `worktree_name` | string | Worktree name |
| `cvs199` | string | Raw record + metadata JSON |
| `cvs200` | string | `'ClaudeCodeHook'` |

</details>

---

## 5. Source Tag Values (`cvs200`)

| Package | Path | `cvs200` value |
|---|---|---|
| Python OpenAI (hooks) | `extract_span_info()` | `openAI_Python_Telemetry` |
| Python OpenAI (decorators) | via `reassign()` | Uses `source` key from caller |
| Python Agents (span2json) | `span2json()` | `openAI_Agents_Traces` |
| Python Agents (OTel) | `extract_otel_span_info()` | `openAI_Agents_Telemetry` |
| JS OpenAI (hooks) | `extractSpanInfo()` | `openAI_Traces` |
| JS OpenAI (decorators) | via `reassign()` | Uses `source` key from caller |
| JS Agents (span2json) | `span2json()` | `openAI_Agents_Traces` |
| JS Agents (OTel) | `extractOtelSpanInfo()` | `openAI_Agents_Telemetry` |
| Claude Code | `transform_record()` | `ClaudeCodeHook` |

---

## 6. Dynamic CVS Allocation

When a key is **not found** in the mapping, the `reassign()` function allocates a new CVS variable dynamically.

| Type | Prefix | Starting Index |
|---|---|---|
| string / object | `cvs` | 100 |
| number | `cvn` | 3 |
| boolean | `cvb` | 1 |

> The first unmapped string gets `cvs100`, then `cvs101`, etc. Numbers start at `cvn3` (since `cvn1` and `cvn2` are reserved for timestamps).

---

## 7. Source-Specific Validation

The SDK performs strict type coercion (Double, Boolean, JSON) before sending data, using a validation table that matches the target Protobuf schema.

| Source (`cvs200`) | Validation Table | Target Schema |
|---|---|---|
| `ClaudeCodeHook` | `CLAUDE_VALID_TYPES` | `schemaClaudeCode.proto` |
| (Everything else) | `OTEL_AI_VALID_TYPES` | `schemaOtelAI.proto` |

### Coercion Rules:
- **Double**: Strictly cast to float (defaults to `0.0` on failure).
- **Boolean**: Handles strings like `"true"`, `"1"`, `"yes"`.
- **JSON**: Objects/lists are automatically stringified.
- **CVS Prefixes**: If a key is not in the validation table, it is coerced based on its prefix (`cvn` -> number, `cvb` -> bool, `cvs` -> string).

---

## Findings

### ✅ Aligned across Python & JS

- All `otel_*` fields ✅
- All `gen_ai.*` semantic convention keys ✅
- Agents input/output mappings aligned to `llm_input`/`llm_output` ✅
- Agents usage/tools/config aligned to `llm_*` columns ✅
- Dynamic allocation starting indices (`cvs100`, `cvn3`, `cvb1`) ✅
- `user_context` and `llm_model_name` aligned ✅
- Source-specific validation tables implemented in both languages ✅

### 📝 Duplicate CVS Slots (Multiple keys → same column)

| CVS Variable | Mapped by keys | Risk |
|---|---|---|
| `cvs200` | `from_source`, `source` | Low — intentional alias |
| `otel_name` | `name` (base), also hardcoded in span2json | No risk — same data |

