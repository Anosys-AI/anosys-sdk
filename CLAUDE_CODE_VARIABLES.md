# Claude Code Telemetry Variables Map

This document provides the complete reference for all telemetry variables used by the **AnoSys Claude Code SDK** (`anosys-claude-code` in Python and JavaScript).

It details both **Named Variables** (used in descriptive JSON payloads and API ingestion) and **CV Variables** (**C**ustom **V**ariables — the physical database columns `cvs*`, `cvn*`, `cvb*` mapped in BigQuery, ClickHouse, and the AnoSys Dashboard).

---

## 1. Architecture: Dual Schema Representation

The Claude Code integration operates under the **`CC`** pixel format with source signature **`cvs200: 'ClaudeCodeHook'`**.
Depending on configuration (`CLAUDE_PIXEL=true`), records can be emitted in:

1. **Descriptive Mode (Named Variables)**: Human-readable JSON keys (`session_id`, `input_tokens`, `cost_estimate`, `user_prompt`, `git_branch`, etc.) utilized by generic REST ingestors, logging collectors, and developer tools.
2. **CV Mode (Physical Database Columns)**: High-performance, indexed database columns (`cvs1`–`cvs94` for strings, `cvn1`–`cvn43` for numbers, `cvb1`–`cvb15` for booleans, `cvs199` for raw context, and `cvs200` for source signature). These map directly to BigQuery tables, powering dashboard graphs, prompt audit tools, and real-time triggers.

---

## 2. Named Variables Reference

Below is the complete reference of all named variables emitted for Claude Code session turns:

### 2.1 Identity & Session Context

| Variable Name | Data Type | Mapped CV Column | Description |
| :--- | :--- | :--- | :--- |
| `session_id` | `string` | `cvs1` | Unique identifier of the Claude Code CLI session. Shared across all turns in the same conversation. |
| `event_id` | `string` | System Field | Unique identifier for the individual turn event (derived from turn UUID or message ID). |
| `event_type` | `string` | System Field | Event classification in the format `claude_code_{msgType}` (e.g. `claude_code_user`, `claude_code_assistant`). |
| `event_source_name` | `string` | System Field | Source application identifier, always set to `'claude_code'`. |
| `timestamp` | `number` | System Field | Timestamp when the record was processed by the ingestion pipeline (epoch ms). |
| `user_timestamp` | `number` | System Field | Timestamp when the event actually occurred on the client machine (epoch ms). |
| `debug` | `boolean` | System Field | Indicates whether the CLI was executed in debug mode. Defaults to `false`. |
| `slug` | `string` | `cvs10` | Human-readable workspace or session slug. |
| `parent_uuid` | `string` | `cvs11` | UUID of the parent record in hierarchical or nested execution chains. |
| `logical_parent_uuid` | `string` | `cvs52` | Logical parent UUID connecting sub-agents to the parent task. |
| `leaf_uuid` | `string` | `cvs55` | Terminal/leaf UUID of the execution tree. |
| `raw_uuid` | `string` | `cvs13` | Raw message or turn UUID directly from the client log stream. |
| `raw_message_id` | `string` | `cvs14` | Upstream Anthropic API message identifier. |
| `assistant_msg_id` | `string` | `cvs15` | Unique ID of the assistant response message. |
| `user_type` | `string` | `cvs16` | User classification (e.g. `developer`, `system`, `ci`). |
| `subtype` | `string` | `cvs17` | Sub-classification label (e.g. `stop_hook_summary`, `local_command`). |
| `hook_name` | `string` | `cvs18` | Name of the hook event triggered (e.g. `agent-turn-complete`, `post-tool-exec`). |
| `hook_command` | `string` | `cvs19` | Command string configured for the hook execution. |
| `hook_event` | `string` | `cvs27` | Internal hook lifecycle label. |
| `hook_label` | `string` | `cvs77` | Display label associated with the hook trigger. |
| `request_id` | `string` | `cvs31` | HTTP request ID from the Anthropic LLM API response headers. |
| `integration_version` | `string` | `cvs32` | Version of the installed `anosys-sdk-claude-code` package. |
| `os_user` | `string` | `cvs33` | Operating system username running the CLI. |

---

### 2.2 Workspace, Environment & Git Metadata

| Variable Name | Data Type | Mapped CV Column | Description |
| :--- | :--- | :--- | :--- |
| `project` | `string` | `cvs2` | Project / repository name (extracted as the basename of `cwd`). |
| `cwd` | `string` | `cvs12` | Absolute working directory path where the session is running. |
| `git_branch` | `string` | `cvs3` | Active Git branch name at the time the turn executed. |
| `original_branch` | `string` | `cvs67` | Original Git branch before worktree or feature branching was created. |
| `original_head_commit` | `string` | `cvs68` | Git commit SHA at the beginning of the session. |
| `pr_url` | `string` | `cvs46` | URL of the pull request associated with the workspace. |
| `pr_repository` | `string` | `cvs56` | GitHub/GitLab repository identifier for the pull request. |
| `pr_number` | `number` | `cvn21` | Pull request number linked to this session. |
| `worktree_session` | `string` | `cvs49` | Flag / identifier indicating if session is in an isolated Git worktree. |
| `worktree_branch` | `string` | `cvs63` | Dedicated branch created for the Git worktree. |
| `worktree_original_cwd`| `string` | `cvs92` | Working directory before switching to the worktree folder. |
| `worktree_path` | `string` | `cvs93` | Filesystem folder path where the isolated worktree is hosted. |
| `worktree_name` | `string` | `cvs94` | Identifier name assigned to the Git worktree. |
| `tmux_session_name` | `string` | `cvs69` | Name of the active tmux session, if running within a terminal multiplexer. |

---

### 2.3 Conversation & Model Behavior

| Variable Name | Data Type | Mapped CV Column | Description |
| :--- | :--- | :--- | :--- |
| `user_prompt` | `string` | `cvs4` | User input prompt, steering instruction, or queued action text. |
| `assistant_text` | `string` | `cvs5` | Extracted assistant text response, thoughts, progress, or tool explanations. |
| `primary_model` | `string` | `cvs9` | Active Claude model name (e.g. `claude-3-7-sonnet-20250219`, `claude-3-5-haiku`). |
| `advisor_model` | `string` | `cvs73` | Secondary or advisor model used for planning, code review, or classification. |
| `stop_reason` | `string` | `cvs6` | Reason model finished (e.g. `end_turn`, `tool_use`, `max_tokens`, `stop_sequence`). |
| `stop_reason_top` | `string` | `cvs78` | Top-level stop reason classification. |
| `stop_sequence` | `string` | `cvs54` | Exact string sequence that triggered model halt. |
| `permission_mode` | `string` | `cvs7` | CLI permission mode (e.g. `auto`, `ask`, `plan`). |
| `version` | `string` | `cvs8` | Version string of the Claude Code tool itself. |
| `prompt_id` | `string` | `cvs28` | Identifier of the active prompt template. |
| `last_prompt` | `string` | `cvs24` | Text content of the preceding prompt in the multi-turn chain. |
| `has_thinking` | `boolean` | `cvb1` | `true` if Claude 3.7 Sonnet utilized internal reasoning / thinking tokens. |
| `custom_title` | `string` | `cvs40` | Custom user-provided title for the session. |
| `ai_title` | `string` | `cvs41` | AI-generated summary title for the session. |
| `session_tag` | `string` | `cvs42` | User or automated tag categorizing the session. |
| `session_mode` | `string` | `cvs48` | Operational mode (e.g. `interactive`, `batch`, `eval`). |
| `service_tier` | `string` | `cvs64` | Anthropic service tier (e.g. `standard`, `priority`). |
| `upgrade_nudge` | `string` | `cvs74` | Upgrade suggestion banner or nudge text displayed to developer. |

---

### 2.4 Token Consumption & Costs

| Variable Name | Data Type | Mapped CV Column | Description |
| :--- | :--- | :--- | :--- |
| `input_tokens` | `number` | `cvn1` | Number of input / prompt tokens sent to Claude. |
| `output_tokens` | `number` | `cvn2` | Number of completion / output tokens generated by Claude. |
| `total_tokens` | `number` | `cvn3` | Cumulative token total (`input + output + cache_read`). |
| `cache_read` | `number` | `cvn4` | Number of prompt tokens served from Anthropic's prompt cache. |
| `cache_creation` | `number` | `cvn5` | Number of prompt tokens written to Anthropic's prompt cache (5-min TTL). |
| `cost_estimate` | `number` | `cvn7` | Estimated financial cost in USD using Anthropic model pricing tiers. |
| `incremental_input` | `number` | `cvn9` | Marginal input tokens consumed specifically in this turn. |
| `incremental_output` | `number` | `cvn10` | Marginal output tokens generated specifically in this turn. |
| `incremental_total` | `number` | `cvn11` | Marginal total tokens consumed specifically in this turn. |
| `incremental_cost` | `number` | `cvn12` | Marginal USD cost incurred specifically in this turn. |
| `incremental_cache_read`| `number` | `cvn17` | Marginal cache read tokens specifically in this turn. |
| `incremental_cache_creation`| `number` | `cvn18` | Marginal cache write tokens specifically in this turn. |
| `last_spawn_tokens` | `number` | `cvn22` | Token count consumed when spawning a sub-agent worker. |
| `budget_tokens` | `number` | `cvn31` | Total token budget allocated for this session. |
| `budget_limit` | `number` | `cvn32` | Hard token ceiling limit configured for execution. |
| `budget_nudges` | `number` | `cvn33` | Count of budget warning alerts displayed. |

---

### 2.5 Tool Calls, Commands & File System

| Variable Name | Data Type | Mapped CV Column | Description |
| :--- | :--- | :--- | :--- |
| `tool_use_id` | `string` | `cvs21` | ID of the specific tool invocation. |
| `parent_tool_use_id` | `string` | `cvs22` | ID of the parent tool invocation in nested calls. |
| `source_tool_use_id` | `string` | `cvs37` | Source tool ID initiating the current action. |
| `source_tool_assistant_uuid`| `string`| `cvs23` | UUID of the assistant turn that invoked the tool. |
| `tool_use_result` | `string` | `cvs26` | Stringified output or stdout returned by the executed tool. |
| `tool_count` | `number` | `cvn41` | Total number of tool calls executed during this turn. |
| `tool_duration_ms` | `number` | `cvn39` | Cumulative time in milliseconds spent executing tools. |
| `commands` | `string` | `cvs91` | Stringified list of shell commands executed by the agent. |
| `written_paths` | `string` | `cvs90` | Stringified list of files created, modified, or written. |
| `file_states` | `string` | `cvs57` | Snapshot state summary of tracked files. |
| `web_search_requests` | `number` | `cvn29` | Count of web search queries executed by Claude Code. |
| `web_fetch_requests` | `number` | `cvn30` | Count of web page URL fetch actions executed. |
| `mcp_meta` | `string` | `cvs80` | Metadata regarding Model Context Protocol (MCP) server calls. |

---

### 2.6 Performance, Timing & Developer Productivity

| Variable Name | Data Type | Mapped CV Column | Description |
| :--- | :--- | :--- | :--- |
| `duration_ms` | `number` | `cvn6` | Total execution duration of the turn in milliseconds. |
| `turn_duration_ms` | `number` | `cvn38` | User-agent response cycle duration in milliseconds. |
| `hook_duration_ms` | `number` | `cvn37` | Execution time consumed by the hook runner script. |
| `classifier_duration_ms`| `number`| `cvn40` | Execution time consumed by safety and intent classifiers. |
| `classifier_count` | `number` | `cvn42` | Number of classifier evaluations performed. |
| `ttft_ms` | `number` | `cvn35` | Time to First Token (TTFT) latency in milliseconds. |
| `otps` | `number` | `cvn36` | Output tokens per second generation speed. |
| `usage_speed` | `string` | `cvs38` | Latency category classification (e.g. `fast`, `normal`). |
| `inference_geo` | `string` | `cvs39` | Geographical region where LLM inference was executed. |
| `time_saved_ms` | `number` | `cvn19` | Estimated developer engineering time saved by automation. |
| `log_index` | `number` | `cvn8` | Sequence index of this turn inside the log stream. |
| `message_count` | `number` | `cvn34` | Cumulative count of messages exchanged in session. |
| `prompt_count` | `number` | `cvn23` | Total number of prompts submitted in session. |
| `prompt_count_at_last_commit`| `number`| `cvn24` | Number of prompts submitted since the last Git commit. |
| `permission_prompt_count`| `number`| `cvn25` | Number of permission prompts presented to the user. |
| `permission_prompt_count_at_last_commit`| `number`| `cvn26` | Permission prompts since the last Git commit. |
| `escape_count` | `number` | `cvn27` | Number of times the user cancelled or escaped an operation. |
| `escape_count_at_last_commit`| `number`| `cvn28` | Escape cancellations since the last Git commit. |
| `config_write_count` | `number` | `cvn43` | Number of configuration file writes performed by the CLI. |

---

### 2.7 Diagnostics, Errors & Status

| Variable Name | Data Type | Mapped CV Column | Description |
| :--- | :--- | :--- | :--- |
| `level` | `string` | `cvs29` | Log severity level (`INFO`, `WARN`, `ERROR`). |
| `error_obj` | `string` | `cvs25` | Serialized error message or exception details. |
| `error_details` | `string` | `cvs86` | In-depth technical error diagnostics or stack trace. |
| `cause` | `string` | `cvs84` | Root cause string for failed operations. |
| `api_error` | `string` | `cvs85` | Direct API error message from Anthropic. |
| `status_message` | `string` | `cvs61` | Status message displayed to the developer. |
| `task_status` | `string` | System Field | Current task state (e.g. `completed`, `in_progress`, `failed`). |
| `ide_diagnostics` | `string` | `cvs30` | Language server / IDE diagnostic errors captured in the session. |

---

### 2.8 Boolean Flags

| Variable Name | Data Type | Mapped CV Column | Description |
| :--- | :--- | :--- | :--- |
| `has_thinking` | `boolean` | `cvb1` | `true` if model generated reasoning / thinking tokens. |
| `is_api_error_message` | `boolean` | `cvb2` | `true` if this turn represents an API error response. |
| `is_meta` | `boolean` | `cvb3` | `true` if the event is a metadata / control record. |
| `is_sidechain` | `boolean` | `cvb4` | `true` if executed in a sidechain or branch execution. |
| `is_snapshot_update` | `boolean` | `cvb5` | `true` if record is a filesystem snapshot state update. |
| `has_output` | `boolean` | `cvb6` | `true` if turn produced visible terminal or assistant output. |
| `prevented_continuation`| `boolean`| `cvb7` | `true` if execution was halted to prevent infinite loops. |
| `is_agent` | `boolean` | `cvb8` | `true` if invoked as an autonomous sub-agent. |
| `armed` | `boolean` | `cvb9` | Operational arming status of the CLI tool. |
| `hook_based` | `boolean` | `cvb10` | `true` if event originated directly from hook lifecycle. |
| `is_synthetic` | `boolean` | `cvb11` | `true` if synthetic turn generated for testing or aggregation. |
| `is_visible_in_transcript_only`| `boolean`| `cvb12` | `true` if turn is only logged to transcript without display. |
| `is_virtual` | `boolean` | `cvb13` | `true` if virtual execution turn. |
| `is_compact_summary` | `boolean` | `cvb14` | `true` if turn represents a compacted context summary. |
| `is_p50` | `boolean` | `cvb15` | Statistical median flag for latency distribution. |

---

## 3. Physical Custom Variables (CV) Schema Map

This section provides the exhaustive physical database mapping for Claude Code in BigQuery / ClickHouse:

### 3.1 String Columns (`cvs1` – `cvs94`, `cvs199`, `cvs200`)

| CV Column | Canonical Field | Description |
| :--- | :--- | :--- |
| `cvs1` | `sessionId` | CLI session identifier |
| `cvs2` | `project` | Repository name from working directory |
| `cvs3` | `gitBranch` | Active Git branch |
| `cvs4` | `userPrompt` | User prompt text |
| `cvs5` | `assistantText` | Model response text |
| `cvs6` | `stopReason` | Stop reason (`end_turn`, `tool_use`, etc.) |
| `cvs7` | `permissionMode`| Approval mode (`auto`, `ask`) |
| `cvs8` | `version` | Tool version |
| `cvs9` | `primaryModel` | Model name |
| `cvs10` | `slug` | Session slug |
| `cvs11` | `parentUuid` | Parent trace UUID |
| `cvs12` | `cwd` | Working directory path |
| `cvs13` | `rawUuid` | Raw event UUID |
| `cvs14` | `rawMessageId` | Raw API message ID |
| `cvs15` | `assistantMsgId`| Assistant message ID |
| `cvs16` | `userType` | User category |
| `cvs17` | `subtype` | Subtype label |
| `cvs18` | `hookName` | Hook name |
| `cvs19` | `hookCommand` | Hook command string |
| `cvs20` | `agentId` | Agent identifier |
| `cvs21` | `toolUseId` | Tool invocation ID |
| `cvs22` | `parentToolUseId`| Parent tool invocation ID |
| `cvs23` | `sourceToolAssistantUuid`| Assistant UUID invoking tool |
| `cvs24` | `lastPrompt` | Preceding prompt text |
| `cvs25` | `errorObj` | Error message string |
| `cvs26` | `toolUseResult`| Tool execution output |
| `cvs27` | `hookEvent` | Hook lifecycle label |
| `cvs28` | `promptId` | Prompt template ID |
| `cvs29` | `level` | Severity level |
| `cvs30` | `ideDiagnostics`| IDE diagnostics string |
| `cvs31` | `requestId` | Upstream HTTP request ID |
| `cvs32` | `integrationVersion`| SDK package version |
| `cvs33` | `osUser` | OS username |
| `cvs34` | `agentType` | Sub-agent type |
| `cvs35` | `agentDescription`| Sub-agent description |
| `cvs36` | `entrypoint` | Binary entrypoint |
| `cvs37` | `sourceToolUseId`| Initiating tool use ID |
| `cvs38` | `usageSpeed` | Latency category |
| `cvs39` | `inferenceGeo` | Inference region |
| `cvs40` | `customTitle` | User session title |
| `cvs41` | `aiTitle` | AI session title |
| `cvs42` | `sessionTag` | Session category tag |
| `cvs43` | `agentMapName` | Agent mapping name |
| `cvs44` | `agentMapColor`| Agent color code |
| `cvs45` | `agentSetting` | Agent configuration |
| `cvs46` | `prUrl` | Pull request URL |
| `cvs47` | `attributionSurface`| Attribution source |
| `cvs48` | `sessionMode` | Interactive/batch mode |
| `cvs49` | `worktreeSession`| Worktree flag |
| `cvs50` | `stagedNodes` | Staged tree nodes |
| `cvs51` | `origamiSummary`| Structural summary |
| `cvs52` | `logicalParentUuid`| Logical task parent UUID |
| `cvs53` | `teamName` | Team/workspace name |
| `cvs54` | `stopSequence` | Halting string sequence |
| `cvs55` | `leafUuid` | Leaf trace UUID |
| `cvs56` | `prRepository` | PR repository |
| `cvs57` | `fileStates` | File state snapshot |
| `cvs58` | `collapseId` | UI collapse identifier |
| `cvs59` | `summaryUuid` | Summary record UUID |
| `cvs60` | `summaryContent`| Summary text |
| `cvs61` | `statusMessage`| Status notification |
| `cvs62` | `hookSpecificOutput`| Hook output |
| `cvs63` | `worktreeBranch`| Worktree Git branch |
| `cvs64` | `serviceTier` | Anthropic service tier |
| `cvs65` | `firstArchivedUuid`| First archived turn UUID |
| `cvs66` | `lastArchivedUuid`| Last archived turn UUID |
| `cvs67` | `originalBranch`| Pre-worktree branch |
| `cvs68` | `originalHeadCommit`| Pre-worktree commit SHA |
| `cvs69` | `tmuxSessionName`| tmux session |
| `cvs70` | `taskDescription`| Task objective |
| `cvs71` | `taskType` | Task classification |
| `cvs72` | `iterations` | Turn loop count |
| `cvs73` | `advisorModel` | Secondary advisor model |
| `cvs74` | `upgradeNudge` | Tool upgrade notice |
| `cvs75` | `url` | Relevant documentation URL |
| `cvs76` | `priority` | Priority label |
| `cvs77` | `hookLabel` | Hook display label |
| `cvs78` | `stopReasonTop`| Top-level stop reason |
| `cvs79` | `research` | Deep research metadata |
| `cvs80` | `mcpMeta` | MCP tool call details |
| `cvs81` | `summarizeMetadata`| Context summarization info |
| `cvs82` | `compactMetadata`| Compact mode info |
| `cvs83` | `microcompactMetadata`| Microcompact mode info |
| `cvs84` | `cause` | Failure root cause |
| `cvs85` | `apiError` | Provider error message |
| `cvs86` | `errorDetails` | Error diagnostics |
| `cvs87` | `origin` | Originating host |
| `cvs88` | `imagePasteIds`| Image paste references |
| `cvs89` | `fileAttachments`| Attached file names |
| `cvs90` | `writtenPaths` | Modified file paths |
| `cvs91` | `commands` | Shell commands run |
| `cvs92` | `worktreeOriginalCwd`| Original worktree directory |
| `cvs93` | `worktreePath` | Worktree folder |
| `cvs94` | `worktreeName` | Worktree identifier |
| `cvs199`| `raw` | Full JSON dump of raw turn |
| `cvs200`| `sourceTag` | `'ClaudeCodeHook'` |

---

### 3.2 Numeric Columns (`cvn1` – `cvn43`)

| CV Column | Canonical Field | Unit / Type | Description |
| :--- | :--- | :--- | :--- |
| `cvn1` | `inputTokens` | Tokens (int) | Prompt / input token count |
| `cvn2` | `outputTokens` | Tokens (int) | Completion / output token count |
| `cvn3` | `totalTokens` | Tokens (int) | Cumulative token count (`input + output + cache_read`) |
| `cvn4` | `cacheRead` | Tokens (int) | Prompt tokens read from cache |
| `cvn5` | `cacheCreation`| Tokens (int) | Tokens written to prompt cache |
| `cvn6` | `durationMs` | Milliseconds | Turn execution time |
| `cvn7` | `costEstimate` | USD ($ float) | Estimated cost of turn |
| `cvn8` | `logIndex` | Sequence (int) | Index of turn in stream |
| `cvn9` | `incrementalInput`| Tokens (int) | Turn delta input tokens |
| `cvn10` | `incrementalOutput`| Tokens (int)| Turn delta output tokens |
| `cvn11` | `incrementalTotal`| Tokens (int) | Turn delta total tokens |
| `cvn12` | `incrementalCost`| USD ($ float)| Turn delta cost |
| `cvn13` | `hookCount` | Count (int) | Hook executions count |
| `cvn14` | `maxRetries` | Count (int) | Ingestion retry ceiling |
| `cvn15` | `retryAttempt` | Count (int) | Retry attempt number |
| `cvn16` | `retryInMs` | Milliseconds | Backoff duration |
| `cvn17` | `incrementalCacheRead`| Tokens (int)| Turn delta cache read |
| `cvn18` | `incrementalCacheCreation`| Tokens (int)| Turn delta cache write |
| `cvn19` | `timeSavedMs` | Milliseconds | Developer time saved |
| `cvn20` | `replacedResultsCount`| Count (int)| Overwritten tool results |
| `cvn21` | `prNumber` | Number (int) | Linked pull request number |
| `cvn22` | `lastSpawnTokens`| Tokens (int) | Tokens to spawn subagent |
| `cvn23` | `promptCount` | Count (int) | Cumulative prompts count |
| `cvn24` | `promptCountAtLastCommit`| Count (int)| Prompts since last commit |
| `cvn25` | `permissionPromptCount`| Count (int)| Permission requests count |
| `cvn26` | `permissionPromptCountAtLastCommit`| Count (int)| Permission prompts since last commit |
| `cvn27` | `escapeCount` | Count (int) | Operation cancellations |
| `cvn28` | `escapeCountAtLastCommit`| Count (int)| Cancellations since last commit |
| `cvn29` | `webSearchRequests`| Count (int) | Web searches executed |
| `cvn30` | `webFetchRequests`| Count (int) | Web pages fetched |
| `cvn31` | `budgetTokens`| Tokens (int) | Allocated token budget |
| `cvn32` | `budgetLimit` | Tokens (int) | Hard token ceiling |
| `cvn33` | `budgetNudges`| Count (int) | Budget warning alerts |
| `cvn34` | `messageCount`| Count (int) | Messages exchanged |
| `cvn35` | `ttftMs` | Milliseconds | Time to first token |
| `cvn36` | `otps` | Tokens/sec | Output generation rate |
| `cvn37` | `hookDurationMs`| Milliseconds | Hook execution duration |
| `cvn38` | `turnDurationMs`| Milliseconds | Turn cycle duration |
| `cvn39` | `toolDurationMs`| Milliseconds | Tool execution time |
| `cvn40` | `classifierDurationMs`| Milliseconds| Classifier execution time |
| `cvn41` | `toolCount` | Count (int) | Tools executed in turn |
| `cvn42` | `classifierCount`| Count (int) | Classifiers executed |
| `cvn43` | `configWriteCount`| Count (int) | Config file modifications |

---

### 3.3 Boolean Columns (`cvb1` – `cvb15`)

| CV Column | Canonical Field | Description |
| :--- | :--- | :--- |
| `cvb1` | `hasThinking` | `true` if model utilized reasoning / thinking tokens |
| `cvb2` | `isApiErrorMessage` | `true` if turn encountered an API error |
| `cvb3` | `isMeta` | `true` if record is metadata / control event |
| `cvb4` | `isSidechain` | `true` if turn executed in sidechain |
| `cvb5` | `isSnapshotUpdate`| `true` if record is a filesystem snapshot update |
| `cvb6` | `hasOutput` | `true` if turn produced output |
| `cvb7` | `preventedContinuation`| `true` if loop prevention halted execution |
| `cvb8` | `isAgent` | `true` if executed as subagent |
| `cvb9` | `armed` | Operational arming status |
| `cvb10` | `hookBased` | `true` if event originated from hook |
| `cvb11` | `isSynthetic` | `true` if synthetic test event |
| `cvb12` | `isVisibleInTranscriptOnly`| `true` if transcript-only log |
| `cvb13` | `isVirtual` | `true` if virtual execution turn |
| `cvb14` | `isCompactSummary`| `true` if turn is a compacted summary |
| `cvb15` | `isP50` | Median latency flag |
