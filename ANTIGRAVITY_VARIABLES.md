# Google Antigravity Telemetry Variables Map

This document provides the complete, authoritative reference for all telemetry variables used by the **AnoSys Antigravity SDK** (`anosys-antigravity` in Python and JavaScript) when observing **Google Antigravity** (CLI, IDE, and Antigravity 2.0).

It details both **Named Variables** (used in descriptive JSON payloads and API ingestion) and **CV Variables** (**C**ustom **V**ariables — physical database columns `cvs*`, `cvn*`, `cvb*` mapped in BigQuery, ClickHouse, and the AnoSys Dashboard), along with the **Exact Source Extraction Map** detailing precisely where each field is retrieved from Antigravity transcripts and lifecycle hooks.

---

## 1. Architecture: Dual Schema Representation

The Google Antigravity integration operates under the **`CC`** pixel format with source signature **`cvs200: 'AntigravityHook'`** (validated by `CLAUDE_VALID_TYPES` against `schemaClaudeCode.proto`).

Every Antigravity turn processed by the AnoSys SDK hook runner is emitted with two parallel representations:

1. **Named Variables (Descriptive JSON Payload)**: Human-readable, expressive keys (`session_id`, `user_prompt`, `assistant_text`, `primary_model`, `active_document`, `cursor_line`, `tools_used`, `commands`, `written_paths`, `has_thinking`, `duration_ms`, etc.) utilized by generic REST ingestors, audit sinks, and developer integrations.
2. **CV Variables (Physical Database Columns)**: Optimized, indexed columnar database fields (`cvs1`–`cvs94` for strings, `cvn1`–`cvn41` for numbers, `cvb1`–`cvb5` for booleans, `cvs199` for raw audit JSON, and `cvs200` for source signature). These map directly to underlying BigQuery / ClickHouse tables, powering real-time dashboard widgets, anomaly detection, developer velocity tracking, and cost analytics.

---

## 2. Extraction Source Architecture: How Antigravity Works

Google Antigravity uses a **transcript-driven control-plane** architecture:
- **Hook Triggers (`hooks.json`)**: Antigravity fires external hook commands on lifecycle events (`PreInvocation` and `Stop`). The payload sent to standard input (`stdin`) is a lightweight control-plane pointer containing `conversationId`, `workspacePaths`, `transcriptPath`, `artifactDirectoryPath`, and `modelName`.
- **Transcript Source of Truth (`transcript_full.jsonl`)**: The ground truth of the agent's interaction lives in the per-session `transcript_full.jsonl` (or `transcript.jsonl`). Each user turn begins with a `USER_INPUT` record and is followed by one or more `PLANNER_RESPONSE` (LLM steps) and tool execution results.
- **Rich Prompt Context**: Unlike other agents, Antigravity embeds structured XML tags in `USER_INPUT`:
  - `<USER_REQUEST>`: The developer's clean prompt/instruction.
  - `<ADDITIONAL_METADATA>`: Editor state (active file, programming language, cursor line, client local time).
  - `<USER_SETTINGS_CHANGE>`: Active model selection and configuration changes.

---

## 3. Data Source Extraction Map (Where to Check for Infos)

The table below explains exactly where the AnoSys SDK extracts every piece of information:

| Telemetry Variable | Target CV Slot | Extraction Source in Antigravity | Extraction Method / Pattern |
| :--- | :--- | :--- | :--- |
| `session_id` / `sessionId` | `cvs1` | Hook stdin JSON / State | `input_json.get("conversationId")` or parsed from transcript path |
| `project` | `cvs2` | Workspace folder | `Path(workspace_paths[0]).name` or `Path(cwd).name` |
| `user_prompt` | `cvs4` | `USER_INPUT` record | Content inside `<USER_REQUEST>(.*?)</USER_REQUEST>` |
| `assistant_text` | `cvs5` | `PLANNER_RESPONSE` record | Concatenated / final `content` field from planner responses in the turn |
| `termination_reason` / `stop_reason`| `cvs6` | `Stop` hook stdin JSON | `input_json.get("terminationReason")` (e.g. `model_stop`, `max_steps_exceeded`, `error`) |
| `primary_model` / `model` | `cvs9` | `USER_INPUT` or Hook stdin | Regex `changed setting \`Model Selection\` from .*? to (.+?)\.` in `<USER_SETTINGS_CHANGE>`, or hook `modelName` |
| `cwd` | `cvs12` | Hook stdin JSON | First item in `input_json.get("workspacePaths")` |
| `event_id` / `uuid` | `cvs13` | Generated turn ID | `f"{session_id}_{turn_index}"` or derived from `USER_INPUT` `step_index` |
| `user_type` | `cvs16` | `USER_INPUT` record | `record.get("source")` (e.g. `USER_EXPLICIT`, `MODEL`, `SYSTEM`) |
| `model_provider` | `cvs17` | Constant | Always `'google'` for Antigravity |
| `hook_name` | `cvs18` | Hook event | `'Stop'` or `'PreInvocation'` |
| `hook_command` | `cvs19` | CLI command | `'anosys-antigravity run'` |
| `error_obj` / `error` | `cvs25` | `Stop` hook stdin JSON | `input_json.get("error")` (present if turn failed) |
| `integration_version` | `cvs32` | Package version | Package `INTEGRATION_VERSION` (`'0.1.0'`) |
| `os_user` | `cvs33` | Environment variable | Host OS username (`USERNAME` or `USER`) |
| `active_document` | `cvs70` | `USER_INPUT` `<ADDITIONAL_METADATA>` | Regex: `Active Document:\s*([^\r\n(]+)` |
| `active_document_language`| `cvs71` | `USER_INPUT` `<ADDITIONAL_METADATA>` | Regex: `\((LANGUAGE_\w+)\)` |
| `client_timestamp_iso` | `cvs72` | `USER_INPUT` `<ADDITIONAL_METADATA>` | Regex: `The current local time is:\s*([^\r\n.]+)` |
| `user_settings_change` | `cvs75` | `USER_INPUT` `<USER_SETTINGS_CHANGE>`| Inner text of `<USER_SETTINGS_CHANGE>` block |
| `viewed_paths` | `cvs76` | Tool calls in turn | Array of file paths from `view_file` (`AbsolutePath` arg) |
| `searched_queries` | `cvs77` | Tool calls in turn | Array of query strings from `search_web` (`query`) & `grep_search` (`Query`) |
| `subagents_spawned` | `cvs78` | Tool calls in turn | Array of tasks from `browser_subagent` (`TaskName`) & `invoke_subagent` |
| `tool_errors` | `cvs79` | Tool results in turn | Non-empty errors or failed statuses in tool steps |
| `transcript_path` | `cvs88` | Hook stdin JSON | `input_json.get("transcriptPath")` |
| `artifact_directory` | `cvs89` | Hook stdin JSON | `input_json.get("artifactDirectoryPath")` |
| `commands` | `cvs90` | Tool calls in turn | Array of commands executed via `run_command` (`CommandLine` arg) |
| `written_paths` | `cvs91` | Tool calls in turn | Array of files modified via `write_to_file`, `replace_file_content`, `multi_replace_file_content` |
| `workspace_paths` | `cvs93` | Hook stdin JSON | JSON-serialized array of all `workspacePaths` |
| `input_tokens` | `cvn1` | Transcript / estimation | Reported token count or `0` (Antigravity omits local per-turn tokens) |
| `output_tokens` | `cvn2` | Transcript / estimation | Reported token count or `0` |
| `total_tokens` | `cvn3` | Transcript / estimation | Cumulative token count or `0` |
| `duration_ms` | `cvn6` | Transcript timestamps | `end_ms - start_ms` across records in the turn |
| `cost_estimate` | `cvn7` | Pricing model | Model-specific cost estimate (USD) |
| `execution_num` | `cvn8` | Hook stdin JSON | `input_json.get("executionNum")` |
| `cursor_line` | `cvn25` | `USER_INPUT` `<ADDITIONAL_METADATA>` | Regex: `Cursor is on line:\s*(\d+)` |
| `llm_step_count` | `cvn26` | Transcript turn records | Count of `PLANNER_RESPONSE` records in this turn |
| `max_step_index` | `cvn27` | Transcript turn records | Highest `step_index` recorded in the turn |
| `step_count` | `cvn28` | Transcript turn records | Total count of all records (planner + tools) in the turn |
| `tool_duration_ms` | `cvn39` | Tool result timestamps | Sum of `completed_at - created_at` across all tool steps |
| `tool_count` | `cvn41` | Tool calls in turn | Total count of tool invocations in the turn |
| `debug` | `cvb1` | Operational flag | `true` if debug logging is enabled |
| `has_thinking` | `cvb2` | `PLANNER_RESPONSE` record | `true` if any planner response contains reasoning/thinking blocks |
| `fully_idle` | `cvb3` | `Stop` hook stdin JSON | `input_json.get("fullyIdle")` (background task completion flag) |
| `raw` | `cvs199` | Full turn context | Complete serialized JSON object with turn metadata, planner steps, and tool calls |
| `source_tag` | `cvs200` | Constant | Always `'AntigravityHook'` |

---

## 4. Complete Named Variables Reference

This table describes all named variables emitted in the descriptive JSON payload for each Antigravity turn:

| Variable Name | Data Type | Mapped CV Column | Category | Description |
| :--- | :--- | :--- | :--- | :--- |
| `session_id` / `sessionId` | `string` | `cvs1` | Session Identity | Unique conversation identifier (`conversationId` UUID). Shared across all turns. |
| `uuid` / `event_id` / `eventId` | `string` | `cvs13` | Event Identity | Unique turn event identifier (`{sessionId}_{turnIndex}`). |
| `event_type` | `string` | System Field | Event Lifecycle | Lifecycle classification, always `'antigravity_turn'`. |
| `event_source_name` | `string` | System Field | Source Identity | Source harness name, always `'antigravity'`. |
| `timestamp` | `number` | System Field | Timing | Ingestion timestamp in epoch milliseconds. |
| `user_timestamp` | `number` | System Field | Timing | Client-side timestamp when the turn started (epoch ms). |
| `debug` | `boolean` | `cvb1` | Operational | Boolean flag indicating if debug mode was active. |
| `user_prompt` / `userPrompt` | `string` | `cvs4` | Content | Text of user prompt from `<USER_REQUEST>` (redacted if enabled). |
| `assistant_text` / `assistantText` | `string` | `cvs5` | Content | Final model output or thoughts generated for the user (redacted if enabled). |
| `model` / `primary_model` | `string` | `cvs9` | Model | Name of the primary AI model used (e.g. `gemini-2.5-pro`, `gemini-2.5-flash`). |
| `model_provider` | `string` | `cvs17` | Model | Provider name, always `'google'`. |
| `cwd` | `string` | `cvs12` | Environment | Active workspace folder directory path. |
| `project` | `string` | `cvs2` | Environment | Basename of active workspace folder. |
| `active_document` | `string` | `cvs70` | IDE Context | File path of the currently focused document in the editor. |
| `active_document_language` | `string` | `cvs71` | IDE Context | Language ID of active document (e.g. `LANGUAGE_PYTHON`, `LANGUAGE_TYPESCRIPT`). |
| `cursor_line` | `number` | `cvn25` | IDE Context | 1-indexed line number of user cursor position in active document. |
| `user_settings_change` | `string` | `cvs75` | Settings | Text of any settings change made by developer during session. |
| `termination_reason` | `string` | `cvs6` | Lifecycle | Reason turn terminated (`model_stop`, `max_steps_exceeded`, `error`). |
| `duration_ms` | `number` | `cvn6` | Performance | Total elapsed turn time in milliseconds. |
| `tool_count` | `number` | `cvn41` | Tool Execution | Total number of tool invocations in the turn. |
| `tool_duration_ms` | `number` | `cvn39` | Tool Execution | Cumulative execution time spent inside tools in milliseconds. |
| `tools_used` | `array` | System Field | Tool Execution | Array of unique tool names invoked (`run_command`, `view_file`, etc.). |
| `commands` | `array` / `string` | `cvs90` | Tool Execution | Shell / terminal commands executed via `run_command`. |
| `written_paths` | `array` / `string` | `cvs91` | File System | Files modified or written via `write_to_file` or `replace_file_content`. |
| `viewed_paths` | `array` / `string` | `cvs76` | File System | Files inspected via `view_file`. |
| `searched_queries` | `array` / `string` | `cvs77` | Research | Search terms queried via `search_web` or `grep_search`. |
| `subagents_spawned` | `array` / `string` | `cvs78` | Subagents | Subagent tasks launched (e.g. `browser_subagent`). |
| `has_thinking` | `boolean` | `cvb2` | Model Reasoning | `true` if Gemini reasoning / thinking blocks were present in planner output. |
| `llm_step_count` | `number` | `cvn26` | Model Reasoning | Number of model invocations within this single user turn. |
| `fully_idle` | `boolean` | `cvb3` | Operational | `true` if all background tasks completed. |
| `execution_num` | `number` | `cvn8` | Lifecycle | Execution sequence number from Stop hook. |
| `error_obj` | `string` | `cvs25` | Diagnostics | Error description if execution failed. |
| `transcript_path` | `string` | `cvs88` | Metadata | Path to Antigravity transcript JSONL file. |
| `artifact_directory` | `string` | `cvs89` | Metadata | Path to session artifacts folder. |
| `workspace_paths` | `array` / `string` | `cvs93` | Metadata | All workspace directories attached to session. |
| `integration_version` | `string` | `cvs32` | Metadata | Version string of the AnoSys Antigravity SDK (`0.1.0`). |
| `os_user` | `string` | `cvs33` | Environment | OS username of developer running Antigravity. |
| `raw` / `cvs199` | `string` | `cvs199` | Audit Context | Serialized JSON array of all raw planner steps, tool calls, and results. |
| `source_tag` / `cvs200` | `string` | `cvs200` | Source Tag | Hook signature tag, always `'AntigravityHook'`. |

---

## 5. Physical CV Columns Map (`schemaClaudeCode.proto`)

### 5.1 String Columns (`cvs1` – `cvs200`)

| CV Column | Variable Name | Purpose |
| :--- | :--- | :--- |
| **`cvs1`** | `session_id` | Antigravity `conversationId` |
| **`cvs2`** | `project` | Repository / workspace folder name |
| **`cvs4`** | `user_prompt` | Developer prompt text (from `<USER_REQUEST>`) |
| **`cvs5`** | `assistant_text` | Final assistant response / thought summary |
| **`cvs6`** | `stop_reason` | Turn termination reason (`model_stop`, `error`, etc.) |
| **`cvs9`** | `primary_model` | Model name (e.g. `gemini-2.5-pro`, `gemini-2.5-flash`) |
| **`cvs12`** | `cwd` | Absolute workspace root directory |
| **`cvs13`** | `raw_uuid` | Turn event UUID (`{sessionId}_{turnIndex}`) |
| **`cvs16`** | `user_type` | User event source (e.g. `USER_EXPLICIT`) |
| **`cvs17`** | `model_provider` | AI provider (`'google'`) |
| **`cvs18`** | `hook_name` | Hook event (`'Stop'` or `'PreInvocation'`) |
| **`cvs19`** | `hook_command` | Hook command (`'anosys-antigravity run'`) |
| **`cvs25`** | `error_obj` | Error details / message |
| **`cvs32`** | `integration_version` | SDK version (`'0.1.0'`) |
| **`cvs33`** | `os_user` | Operating system username |
| **`cvs70`** | `active_document` | Active file opened in IDE |
| **`cvs71`** | `active_document_language` | Language of active document |
| **`cvs72`** | `client_timestamp_iso` | Client local ISO timestamp string |
| **`cvs75`** | `user_settings_change` | User settings change block text |
| **`cvs76`** | `viewed_paths` | JSON string array of viewed file paths |
| **`cvs77`** | `searched_queries` | JSON string array of web/grep queries |
| **`cvs78`** | `subagents_spawned` | JSON string array of subagents launched |
| **`cvs79`** | `tool_errors` | JSON string array of tool execution errors |
| **`cvs88`** | `transcript_path` | Absolute path to session transcript JSONL |
| **`cvs89`** | `artifact_directory` | Absolute path to session artifact directory |
| **`cvs90`** | `commands` | JSON string array of shell commands run |
| **`cvs91`** | `written_paths` | JSON string array of files created / edited |
| **`cvs93`** | `workspace_paths` | JSON string array of all workspace directories |
| **`cvs199`**| `raw` | Full JSON-serialized turn context and steps |
| **`cvs200`**| `source_tag` | Fixed signature `'AntigravityHook'` |

### 5.2 Numeric Columns (`cvn1` – `cvn41`)

| CV Column | Variable Name | Purpose |
| :--- | :--- | :--- |
| **`cvn1`** | `input_tokens` | Input token count (or 0) |
| **`cvn2`** | `output_tokens` | Output token count (or 0) |
| **`cvn3`** | `total_tokens` | Total token count (or 0) |
| **`cvn6`** | `duration_ms` | Elapsed turn duration in milliseconds |
| **`cvn7`** | `cost_estimate` | Estimated turn cost in USD |
| **`cvn8`** | `execution_num` | Execution attempt sequence number |
| **`cvn25`** | `cursor_line` | Active document cursor line number |
| **`cvn26`** | `llm_step_count` | Number of LLM planner steps in the turn |
| **`cvn27`** | `max_step_index` | Maximum step index in the turn |
| **`cvn28`** | `step_count` | Total steps / events in the turn |
| **`cvn39`** | `tool_duration_ms` | Cumulative tool execution time (ms) |
| **`cvn41`** | `tool_count` | Number of tool calls executed |

### 5.3 Boolean Columns (`cvb1` – `cvb5`)

| CV Column | Variable Name | Purpose |
| :--- | :--- | :--- |
| **`cvb1`** | `debug` | Debug logging enabled |
| **`cvb2`** | `has_thinking` | Gemini reasoning / thinking present |
| **`cvb3`** | `fully_idle` | Background tasks completed |

---

## 6. Comparison: Arize AX vs. AnoSys SDK on Antigravity

| Feature / Metric | Arize AX Coding Harness Tracing | AnoSys SDK (`anosys-antigravity`) |
| :--- | :--- | :--- |
| **Ingestion Protocol** | OpenTelemetry OTLP / OpenInference | AnoSys Dual-Schema (Named JSON + CC Physical Columns) |
| **Pixel Validation** | None (generic OTLP endpoint) | Strict CC Pixel validation (`validate_api_key`) |
| **Hooks Registered** | `PreInvocation`, `Stop` | `PreInvocation`, `Stop` |
| **Transcript Parsing** | `transcript_full.jsonl` / `transcript.jsonl` | `transcript_full.jsonl` / `transcript.jsonl` |
| **User Prompt Extraction** | Strips metadata & settings changes | Strips metadata & settings changes |
| **Active Document & Cursor** | ❌ Ignored | ✅ Extracted (`cvs70`, `cvs71`, `cvn25`) |
| **Settings Changes** | ❌ Partial (model name only) | ✅ Full text captured (`cvs75`) + model name (`cvs9`) |
| **Thinking / Reasoning** | ✅ Captured in `llm.reasoning` | ✅ Captured in `has_thinking` (`cvb2`) + raw (`cvs199`) |
| **Commands Executed** | ❌ Truncated in tool description | ✅ Structured array in `commands` (`cvs90`) |
| **Files Written / Edited** | ❌ Truncated in tool description | ✅ Structured array in `written_paths` (`cvs91`) |
| **Files Viewed & Searched**| ❌ Truncated in tool description | ✅ Structured arrays in `cvs76` and `cvs77` |
| **Subagents Tracked** | ❌ Generic tool span | ✅ Structured subagent extraction in `cvs78` |
| **Tool Execution Durations**| ✅ Captured per tool span | ✅ Captured per tool + cumulative `tool_duration_ms` (`cvn39`) |
| **Offline Delivery Queue** | ❌ Spans dropped on network failure | ✅ Persistent `pending_records.jsonl` with automatic retry |
| **Dual Language Support** | Python only | Python & JavaScript / Node.js |
| **Global & Workspace Hooks**| `~/.gemini/config/hooks.json` only | `~/.gemini/config/hooks.json` + `.agents/hooks.json` |
