/**
 * anosys_mapper.js — Schema mapper for Claude Code hook turns.
 * Mapper comply with Generic type of AnoSys ingestion path.
 *
 * This module transforms internal turn dicts into the schema expected
 * by the target endpoint. Exact JS clone of anosys_mapper.py.
 */

'use strict';

const os = require('os');
const path = require('path');
const fs = require('fs');

// Version of the Claude Code integration package
const INTEGRATION_VERSION = '0.2.0';

// Current OS Username
const OS_USER = os.userInfo().username;

// Toggle for descriptive schema vs legacy CV schema
const CLAUDE_PIXEL = (process.env.ANOSYS_CLAUDE_PIXEL || 'true').toLowerCase() === 'true';

// Toggle for redacting sensitive content (questions, answers, thinking)
const REDACTION = (process.env.REDACTION || 'false').toLowerCase() === 'true';

// Local log for unhandled record types
const UNHANDLED_LOG_PATH = path.join(os.homedir(), '.claude', 'hooks', 'unhandled_records.jsonl');

/**
 * Log unhandled records to a local JSONL file for future mapping improvements.
 * @param {object} record
 */
function logUnhandled(record) {
  try {
    const dir = path.dirname(UNHANDLED_LOG_PATH);
    fs.mkdirSync(dir, { recursive: true });
    fs.appendFileSync(UNHANDLED_LOG_PATH, JSON.stringify(record) + '\n', 'utf8');
  } catch (_) {
    // Silently fail to avoid crashing the hook
  }
}

/**
 * Validate and format ISO8601 string to a Unix timestamp (milliseconds).
 * @param {string|null|undefined} isoStr
 * @returns {number}
 */
function toUnixMs(isoStr) {
  if (!isoStr || typeof isoStr !== 'string') {
    return Date.now();
  }
  try {
    // Handle 'Z' suffix — Date.parse already handles Z, but mirror Python behaviour
    const cleaned = isoStr.replace('Z', '+00:00');
    const ms = new Date(cleaned).getTime();
    if (isNaN(ms)) return Date.now();
    return ms;
  } catch (_) {
    return Date.now();
  }
}

/**
 * Scrub sensitive content from the raw record, returning a redacted deep copy.
 * @param {object} record
 * @returns {object}
 */
function redactRawRecord(record) {
  const rec = JSON.parse(JSON.stringify(record)); // deep copy

  // Message content (User/Assistant)
  if (rec.message && typeof rec.message === 'object') {
    if ('content' in rec.message) {
      rec.message.content = 'REDACTED';
    }
  }

  // Generic content field (System messages, Queue operations, etc.)
  if ('content' in rec && typeof rec.content === 'string') {
    rec.content = 'REDACTED';
  }

  // Queue operation specific
  if ('operation' in rec && 'content' in rec) {
    rec.content = 'REDACTED';
  }

  // Last prompt context
  if ('lastPrompt' in rec) {
    rec.lastPrompt = 'REDACTED';
  }

  // Session summary
  if ('summary' in rec) {
    rec.summary = 'REDACTED';
  }

  // File history snapshots
  if (rec.snapshot && typeof rec.snapshot === 'object') {
    if (rec.snapshot.trackedFileBackups && typeof rec.snapshot.trackedFileBackups === 'object') {
      for (const k of Object.keys(rec.snapshot.trackedFileBackups)) {
        rec.snapshot.trackedFileBackups[k] = 'REDACTED';
      }
    }
  }

  return rec;
}

// Pricing based on Anthropic rates (USD per 1M tokens)
// Tiered by total prompt size (including cache): <= 200K vs > 200K
const PRICING_CONFIG = {
  'claude-3-7-sonnet-20250219': { in: 3.0, out: 15.0, cacheWrite: 3.75, cacheRead: 0.30 },
  'claude-3-5-sonnet-20241022': { in: 3.0, out: 15.0, cacheWrite: 3.75, cacheRead: 0.30 },
  'claude-3-opus-20240229': { in: 15.0, out: 75.0, cacheWrite: 18.75, cacheRead: 1.50 },
  'claude-3-5-haiku-20241022': { in: 1.0, out: 5.0, cacheWrite: 1.25, cacheRead: 0.10 },
  'claude-haiku-4-5-20251001': { in: 1.0, out: 5.0, cacheWrite: 1.25, cacheRead: 0.10 },
  'claude-sonnet-4-6': { in: 3.0, out: 15.0, cacheWrite: 3.75, cacheRead: 0.30 },
  '<synthetic>': { in: 0, out: 0, cacheWrite: 0, cacheRead: 0 },
};

/**
 * Calculate the total cost of a turn based on model and usage segments.
 * @param {string|null} model
 * @param {object} usage
 * @returns {number|null}
 */
function calculateCost(model, usage) {
  if (!model || !usage) return null;

  const inputTokens = usage.input_tokens || 0;
  const outputTokens = usage.output_tokens || 0;
  const cacheRead = usage.cache_read_input_tokens || 0;

  let cacheCreation = 0;
  const rawCreation = usage.cache_creation;
  if (rawCreation && typeof rawCreation === 'object') {
    cacheCreation =
      (rawCreation.ephemeral_1h_input_tokens || 0) +
      (rawCreation.ephemeral_5m_input_tokens || 0);
  } else if (typeof rawCreation === 'number') {
    cacheCreation = rawCreation;
  } else {
    cacheCreation = usage.cache_creation_input_tokens || 0;
  }

  // Threshold for tiered pricing (200k tokens)
  const isLargeContext = (inputTokens + cacheRead + cacheCreation) > 200000;
  const rates = PRICING_CONFIG[model] || PRICING_CONFIG['claude-3-5-sonnet-20241022'];

  let inRate = rates.in;
  let outRate = rates.out;
  let writeRate = rates.cacheWrite;
  let readRate = rates.cacheRead;

  // 2x/1.5x Premium for large context segments
  if (isLargeContext && (model.includes('sonnet') || model.includes('opus'))) {
    inRate *= 2;
    outRate *= 1.5;
    writeRate *= 2;
    readRate *= 2;
  }

  // Disjoint Sum Logic
  const totalCost =
    (inputTokens / 1000000 * inRate) +
    (outputTokens / 1000000 * outRate) +
    (cacheCreation / 1000000 * writeRate) +
    (cacheRead / 1000000 * readRate);

  return totalCost;
}

/**
 * Map an internal Claude Code transcript record to the target endpoint schema (AnoSys DB).
 *
 * @param {object} record - The raw transcript entry.
 * @param {object|null} incrementalTokens - Optional dict with 'input', 'output', 'total', 'cost' deltas.
 * @param {object|null} contextOverrides - Optional dict with session-level fields.
 * @returns {object}
 */
function transformRecord(record, incrementalTokens = null, contextOverrides = null) {
  if (REDACTION) {
    record = redactRawRecord(record);
  }

  if (contextOverrides === null) {
    contextOverrides = {};
  }

  // Extract common fields from top-level record metadata
  const sessionId = record.sessionId || contextOverrides.sessionId;

  const message = record.message || {};

  // Capture distinct IDs for explicit mapping, favoring nested 'message' object
  const rawUuid = record.uuid;
  const rawMessageId = (message && typeof message === 'object') ? message.messageId : record.messageId;
  const rawId = (message && typeof message === 'object') ? message.id : record.id;

  // Heuristic for the primary event UUID
  const uuid = rawUuid || rawMessageId || rawId;

  // Fallback to session_id + log_index for stable, deterministic event IDs.
  const _logIndex = contextOverrides.log_index;
  let eventId;
  if (uuid) {
    eventId = uuid;
  } else if (_logIndex !== undefined && _logIndex !== null) {
    eventId = `${sessionId}_${_logIndex}`;
  } else {
    eventId = `${sessionId}_${Date.now() / 1000}`;
  }

  // Extract project name from cwd
  const cwd = record.cwd || contextOverrides.cwd;
  const project = cwd ? path.basename(cwd) : null;
  const gitBranch = record.gitBranch || contextOverrides.gitBranch;
  const version = record.version || contextOverrides.version;
  const slug = record.slug || contextOverrides.slug;
  const parentUuid = record.parentUuid || contextOverrides.parentUuid;

  // New Session Context
  const userType = record.userType || contextOverrides.userType;
  const permissionMode = record.permissionMode || contextOverrides.permissionMode;
  const isMeta = Boolean(record.isMeta || false);
  const isSidechain = Boolean(record.isSidechain || false);
  let agentId = record.agentId || contextOverrides.agent_id;
  const entrypoint = record.entrypoint != null ? record.entrypoint : undefined;
  const logicalParentUuid = record.logicalParentUuid || contextOverrides.logicalParentUuid;
  const teamName = record.teamName || contextOverrides.teamName;
  const taskStatus = record.task_status || record.taskStatus || contextOverrides.task_status || contextOverrides.taskStatus || null;

  // Agent execution context
  const isAgent = Boolean(contextOverrides.is_agent || false);
  const agentType = contextOverrides.agent_type;
  const agentDescription = contextOverrides.agent_description;
  const lastPrompt = record.lastPrompt || contextOverrides.lastPrompt;
  const logIndex = contextOverrides.log_index;

  // Extract message type and payload early
  const msgType = record.type || 'unknown';
  let requestId = record.requestId;

  // New System/Hook Metadata
  const subtype = record.subtype;
  const hookData = (record.data && typeof record.data === 'object') ? record.data : {};
  const hookName = hookData.hookName;
  const hookCommand = hookData.command;
  let ideDiagnostics = hookData.ide_diagnostics;
  if (ideDiagnostics == null && Array.isArray(record.hookInfos)) {
    for (const info of record.hookInfos) {
      if (info && typeof info === 'object' && 'ide_diagnostics' in info) {
        ideDiagnostics = info.ide_diagnostics;
        break;
      }
    }
  }
  const ideDiagnosticsStr = ideDiagnostics != null ? JSON.stringify(ideDiagnostics) : null;

  // New Error and Tool Result Objects
  const errorVal = record.error;
  const errorObjStr = errorVal != null ? JSON.stringify(errorVal) : null;

  // Handle variations of tool IDs
  let toolUseId = record.toolUseID || record.tool_use_id;

  // Try extracting tool_use_id from assistant message content blocks if missing
  if (!toolUseId && msgType === 'assistant' && message && typeof message === 'object') {
    const content = message.content;
    if (Array.isArray(content)) {
      for (const block of content) {
        if (block && typeof block === 'object' && block.type === 'tool_use') {
          toolUseId = block.id || block.tool_use_id;
          if (toolUseId) break;
        }
      }
    }
  }

  const parentToolUseId = record.parentToolUseID || record.parent_tool_use_id;
  const sourceToolAssistantUuid = record.sourceToolAssistantUUID;
  const sourceToolUseId = record.sourceToolUseID;

  let toolUseResult = record.toolUseResult;
  // Try extracting tool_use_id from user tool_result blocks if missing
  if (msgType === 'user' && message && typeof message === 'object') {
    const content = message.content;
    if (Array.isArray(content)) {
      for (const block of content) {
        if (block && typeof block === 'object' && block.type === 'tool_result') {
          if (!toolUseId) {
            toolUseId = block.tool_use_id;
          }

          // ALSO: Extract agent_id from tool_result block if available
          const itemAgentId = block.agentId;
          if (itemAgentId) {
            agentId = itemAgentId;
          }

          // Extract tool_use_result content
          if (!toolUseResult) {
            toolUseResult = block.content;
          }
        }
      }
    }
  }

  const toolUseResultStr = toolUseResult != null ? JSON.stringify(toolUseResult) : null;

  const isSnapshotUpdate = Boolean(record.isSnapshotUpdate || false);

  // Extra system/progress fields
  const hookEvent = hookData.hookEvent;
  const promptId = record.promptId;
  const level = record.level;

  const totalDurationMs = record.totalDurationMs;
  const hookCount = record.hookCount != null ? record.hookCount : undefined;
  const hasOutput = record.hasOutput != null ? record.hasOutput : undefined;
  const preventedContinuation = record.preventedContinuation != null ? record.preventedContinuation : undefined;

  const maxRetries = record.maxRetries;
  const retryAttempt = record.retryAttempt;
  const retryInMs = record.retryInMs;

  // ── New schema fields (previously unmapped) ────────────────────────────
  const isSynthetic = Boolean(record.isSynthetic || false);
  const isVisibleInTranscriptOnly = record.isVisibleInTranscriptOnly != null ? record.isVisibleInTranscriptOnly : undefined;
  const isVirtual = record.isVirtual != null ? record.isVirtual : undefined;
  const isCompactSummary = Boolean(record.isCompactSummary || false);
  const isP50 = record.isP50 != null ? record.isP50 : undefined;

  // Model / routing metadata
  const advisorModel = record.advisorModel;
  const upgradeNudge = record.upgradeNudge;
  const url = record.url;
  const priority = record.priority;
  const hookLabel = record.hookLabel;
  const stopReasonTop = record.stopReason; // top-level stopReason

  // Research field
  const _researchRaw = record.research;
  const researchStr = _researchRaw != null ? JSON.stringify(_researchRaw) : null;

  // Structured metadata objects → JSON strings
  const _mcpMeta = record.mcpMeta;
  const mcpMetaStr = (_mcpMeta && typeof _mcpMeta === 'object') ? JSON.stringify(_mcpMeta) : null;

  const _summarizeMeta = record.summarizeMetadata;
  const summarizeMetadataStr = (_summarizeMeta && typeof _summarizeMeta === 'object') ? JSON.stringify(_summarizeMeta) : null;

  const _compactMeta = record.compactMetadata;
  const compactMetadataStr = (_compactMeta && typeof _compactMeta === 'object') ? JSON.stringify(_compactMeta) : null;

  const _microcompactMeta = record.microcompactMetadata;
  const microcompactMetadataStr = (_microcompactMeta && typeof _microcompactMeta === 'object') ? JSON.stringify(_microcompactMeta) : null;

  const _cause = record.cause;
  const causeStr = _cause != null ? JSON.stringify(_cause) : null;

  const _apiError = record.apiError;
  const apiErrorStr = (_apiError && typeof _apiError === 'object') ? JSON.stringify(_apiError) : null;
  const errorDetails = record.errorDetails;

  const _origin = record.origin;
  const originStr = _origin != null ? JSON.stringify(_origin) : null;

  // Array fields → JSON strings
  const _imagePasteIds = record.imagePasteIds;
  const imagePasteIdsStr = Array.isArray(_imagePasteIds) ? JSON.stringify(_imagePasteIds) : null;

  const _fileAttachments = record.file_attachments;
  const fileAttachmentsStr = Array.isArray(_fileAttachments) ? JSON.stringify(_fileAttachments) : null;

  const _writtenPaths = record.writtenPaths;
  const writtenPathsStr = Array.isArray(_writtenPaths) ? JSON.stringify(_writtenPaths) : null;

  const _commands = record.commands;
  const commandsStr = Array.isArray(_commands) ? JSON.stringify(_commands) : null;

  // Budget / context-window pressure metrics
  const budgetTokens = record.budgetTokens;
  const budgetLimit = record.budgetLimit;
  const budgetNudges = record.budgetNudges;

  // Turn / tool / classifier timing breakdown
  const messageCount = record.messageCount;
  const ttftMs = record.ttftMs;
  const otps = record.otps;
  const hookDurationMs = record.hookDurationMs;
  const turnDurationMs = record.turnDurationMs;
  const toolDurationMs = record.toolDurationMs;
  const classifierDurationMs = record.classifierDurationMs;
  const toolCount = record.toolCount;
  const classifierCount = record.classifierCount;
  const configWriteCount = record.configWriteCount;

  // Per-type specific field extractions
  const leafUuid = record.leafUuid;
  const prNumber = record.prNumber;
  const prRepository = record.prRepository;
  const fileStates = record.fileStates != null ? JSON.stringify(record.fileStates) : null;
  const collapseId = record.collapseId;
  const summaryUuid = record.summaryUuid;
  const summaryContent = record.summaryContent;
  const armed = record.armed;
  const lastSpawnTokens = record.lastSpawnTokens;
  const statusMessage = hookData.statusMessage;
  const hookSpecificOutput = hookData.hookSpecificOutput != null ? JSON.stringify(hookData.hookSpecificOutput) : null;
  const stopSequence = (message && typeof message === 'object') ? message.stop_sequence : null;

  // ── Prompt / Text extraction ────────────────────────────────────────────
  let userPrompt = null;
  let assistantText = null;

  if (msgType === 'user') {
    const content = (message && typeof message === 'object') ? message.content : undefined;
    if (typeof content === 'string') {
      userPrompt = content;
    } else if (Array.isArray(content)) {
      const parts = [];
      for (const item of content) {
        const itype = item.type;
        if (itype === 'text') {
          parts.push(item.text || '');
        } else if (itype === 'image') {
          parts.push('[Image Content]');
        } else if (itype === 'tool_result') {
          const toolContent = item.content;
          const isError = item.is_error || false;
          const prefix = isError ? '[Tool Error] ' : '[Tool Result] ';
          const itemAgentId = item.agentId;
          if (itemAgentId) {
            agentId = itemAgentId;
          }

          if (typeof toolContent === 'string') {
            parts.push(`${prefix}${toolContent}`);
          } else if (Array.isArray(toolContent)) {
            const subParts = [];
            for (const block of toolContent) {
              if (block && typeof block === 'object') {
                if (block.type === 'text') {
                  subParts.push(block.text || '');
                } else if (block.type === 'image') {
                  subParts.push('[Image]');
                }
              } else {
                subParts.push(String(block));
              }
            }
            parts.push(`${prefix}${subParts.join(' ')}`);
          } else {
            parts.push(`${prefix}${JSON.stringify(toolContent)}`);
          }
        }
      }
      userPrompt = parts.join('\n');
    }

  } else if (msgType === 'queue-operation') {
    const operation = record.operation;
    let content = record.content || '';
    // content can be a string or a list of ContentItem objects (enqueue operations)
    if (Array.isArray(content)) {
      content = content
        .filter(item => item && typeof item === 'object' && item.type === 'text')
        .map(item => item.text || '')
        .join(' ');
    }
    if (operation && ['remove', 'popAll', 'dequeue', 'enqueue'].includes(operation)) {
      // Capitalize first letter to mirror Python's str.capitalize()
      const opCapitalized = operation.charAt(0).toUpperCase() + operation.slice(1);
      userPrompt = `[Queue ${opCapitalized}]`;
      if (content) {
        userPrompt += `: ${content}`;
      }
    }

  } else if (msgType === 'api_error' || (msgType === 'system' && subtype === 'api_error')) {
    let errorValLocal = record.error || {};
    let errorMsg;
    if (typeof errorValLocal === 'string') {
      errorMsg = errorValLocal;
    } else if (errorValLocal && typeof errorValLocal === 'object') {
      const nestedError = errorValLocal.error;
      if (nestedError && typeof nestedError === 'object') {
        errorMsg = nestedError.message || errorValLocal.message || JSON.stringify(errorValLocal);
      } else {
        errorMsg = errorValLocal.message || JSON.stringify(errorValLocal);
      }
    } else {
      errorMsg = String(errorValLocal);
    }

    assistantText = `[API Error: ${errorMsg}]`;
    if ('request' in record) {
      assistantText += `\nRequest Details: ${JSON.stringify(record.request)}`;
    }

  } else if (msgType === 'last-prompt') {
    userPrompt = `[Last Prompt: ${record.lastPrompt || ''}]`;

  } else if (msgType === 'file-history-snapshot') {
    assistantText = `[File History Snapshot: ${record.messageId || 'No ID'}]`;
    const snapshot = record.snapshot || {};
    if ('trackedFileBackups' in snapshot) {
      const files = Object.keys(snapshot.trackedFileBackups);
      assistantText += `\nTracked files: ${files.join(', ')}`;
    }

  } else if (msgType === 'progress') {
    const data = (record.data && typeof record.data === 'object') ? record.data : {};
    const hName = data.hookName || 'unknown';
    const hEvent = data.hookEvent || 'unknown';
    const command = data.command || data.commandName;
    const taskDescription = data.taskDescription;
    const taskTypeData = data.taskType;
    assistantText = `[Progress: ${hName} (${hEvent})]`;
    if (command) {
      assistantText += `\nCommand: ${command}`;
    }
    if (taskDescription) {
      assistantText += `\nTask: ${taskDescription}`;
    }
    if (taskTypeData) {
      assistantText += ` (${taskTypeData})`;
    }

    // Check for nested message content in progress (common in agent loops)
    const progMsg = data.message;
    if (progMsg && typeof progMsg === 'object') {
      if (!requestId) {
        requestId = progMsg.requestId;
      }
      const pContent = progMsg.content;
      if (pContent != null) {
        const pTexts = [];
        if (Array.isArray(pContent)) {
          for (const b of pContent) {
            if (b.type === 'text') {
              pTexts.push(b.text || '');
            } else if (b.type === 'thinking') {
              pTexts.push(`<thinking>\n${b.thinking || ''}\n</thinking>`);
            }
          }
        } else if (typeof pContent === 'string') {
          pTexts.push(pContent);
        }
        if (pTexts.length) {
          assistantText += '\n' + pTexts.join('\n');
        }
      }
    }

  } else if (msgType === 'assistant') {
    const content = (message && typeof message === 'object') ? message.content : undefined;
    if (typeof content === 'string') {
      assistantText = content;
    } else if (Array.isArray(content)) {
      const texts = [];
      for (const block of content) {
        const btype = block.type;
        if (btype === 'text') {
          texts.push(block.text || '');
        } else if (btype === 'thinking') {
          const thinkingTxt = block.thinking || '';
          texts.push(`<thinking>\n${thinkingTxt}\n</thinking>`);
        } else if (btype === 'tool_use') {
          const toolName = block.name || 'unknown_tool';
          const toolInput = block.input || {};
          texts.push(`[Tool Use: ${toolName}(${JSON.stringify(toolInput)})]`);
        } else if (btype === 'image') {
          texts.push('[Image Content]');
        }
      }
      assistantText = texts.length ? texts.join('\n') : null;
    }

  } else if (msgType === 'summary') {
    assistantText = record.summary || '';
    userPrompt = '[Session Summary Request]';

  } else if (msgType === 'system') {
    const content = record.content || '';
    if (subtype === 'stop_hook_summary') {
      let errors = record.hookErrors || [];
      const infos = record.hookInfos || [];
      // Search for errors in hookInfos if hookErrors is empty
      if (!errors.length && Array.isArray(infos)) {
        for (const info of infos) {
          if (info && typeof info === 'object' && info.error) {
            errors.push(info.error);
          }
        }
      }

      // Aggregate per-hook durations into a single total
      let hookTotalDurationMs = null;
      if (Array.isArray(infos)) {
        const durations = infos
          .filter(info => info && typeof info === 'object' && 'durationMs' in info)
          .map(info => info.durationMs || 0);
        if (durations.length) {
          hookTotalDurationMs = durations.reduce((a, b) => a + b, 0);
        }
      }

      const parts = [`Hook Summary: ${content}`];
      if (errors.length) parts.push(`Errors: ${JSON.stringify(errors)}`);
      if (infos.length) parts.push(`Infos: ${JSON.stringify(infos)}`);
      if (hookTotalDurationMs !== null) {
        parts.push(`Hook Total Duration: ${hookTotalDurationMs}ms`);
      }
      assistantText = parts.join('\n');

    } else if (subtype === 'local_command') {
      const cmdNameMatch = content.match(/<command-name>(.*?)<\/command-name>/);
      const cmdName = cmdNameMatch ? cmdNameMatch[1] : 'unknown steering';
      userPrompt = `[User Steering: ${cmdName}]`;

    } else if (subtype === 'turn_duration') {
      const duration = record.durationMs || 0;
      assistantText = `[Turn Duration: ${duration}ms]`;

    } else {
      assistantText = content;
    }

  } else if (msgType === 'attachment') {
    const attContent = record.message || record.content || {};
    userPrompt = `[Attachment: ${JSON.stringify(attContent)}]`;

  } else if (msgType === 'tombstone') {
    assistantText = '[Tombstone: Orphaned message removed]';

  } else if (msgType === 'custom-title') {
    userPrompt = `[Custom Title: ${record.customTitle || ''}]`;

  } else if (msgType === 'ai-title') {
    assistantText = `[AI Title: ${record.aiTitle || ''}]`;

  } else if (msgType === 'task-summary') {
    assistantText = `[Task Summary: ${record.summary || ''}]`;

  } else if (msgType === 'tag') {
    userPrompt = `[Session Tag: ${record.tag || ''}]`;

  } else if (msgType === 'agent-name') {
    userPrompt = `[Agent Name: ${record.agentName || ''}]`;

  } else if (msgType === 'agent-color') {
    userPrompt = `[Agent Color: ${record.agentColor || ''}]`;

  } else if (msgType === 'agent-setting') {
    userPrompt = `[Agent Setting: ${record.agentSetting || ''}]`;

  } else if (msgType === 'pr-link') {
    userPrompt = `[PR Linked: ${record.prUrl || ''}]`;

  } else if (msgType === 'attribution-snapshot') {
    assistantText = `[Attribution Snapshot: ${record.surface || 'Unknown Surface'}]`;

  } else if (msgType === 'speculation-accept') {
    assistantText = `[Speculation Accept: Saved ${record.timeSavedMs || 0}ms]`;

  } else if (msgType === 'mode') {
    userPrompt = `[Session Mode: ${record.mode || ''}]`;

  } else if (msgType === 'worktree-state') {
    userPrompt = `[Worktree State Update: ${JSON.stringify(record.worktreeSession)}]`;

  } else if (msgType === 'content-replacement') {
    const replacementsLen = Array.isArray(record.replacements) ? record.replacements.length : 0;
    assistantText = `[Content Replacement: ${replacementsLen} tool results replaced]`;

  } else if (msgType === 'marble-origami-commit') {
    assistantText = `[Origami Commit: ${record.summary || ''}]`;

  } else if (msgType === 'marble-origami-snapshot') {
    const stagedLen = Array.isArray(record.staged) ? record.staged.length : 0;
    assistantText = `[Origami Snapshot: ${stagedLen} staged nodes]`;

  } else {
    // Fallback for completely unknown top-level record types
    logUnhandled(record);
    userPrompt = `[Unhandled Record Type: ${msgType}]`;
    assistantText = `Raw Data: ${JSON.stringify(record)}`;
  }

  // Last resort fallback if no content was mapped even for a known type
  if (userPrompt === null && assistantText === null) {
    logUnhandled(record);
    userPrompt = `[Unmapped Content for Type: ${msgType}]`;
    assistantText = `Raw Data: ${JSON.stringify(record)}`;
  }

  // Token usage and cost
  const tokenUsage = (message && typeof message === 'object') ? (message.usage || {}) : {};
  let primaryModel = (message && typeof message === 'object') ? message.model : null;
  if (!primaryModel && record && typeof record === 'object') {
    primaryModel = record.model || record.advisorModel;
  }
  const assistantMsgId = (msgType === 'assistant' && message && typeof message === 'object') ? message.id : null;

  const inputTokens = tokenUsage.input_tokens || 0;
  const outputTokens = tokenUsage.output_tokens || 0;
  const cacheRead = tokenUsage.cache_read_input_tokens || 0;

  let cacheCreation = 0;
  const rawCreation = tokenUsage.cache_creation;
  if (rawCreation && typeof rawCreation === 'object') {
    cacheCreation =
      (rawCreation.ephemeral_1h_input_tokens || 0) +
      (rawCreation.ephemeral_5m_input_tokens || 0);
  } else if (typeof rawCreation === 'number') {
    cacheCreation = rawCreation;
  } else {
    cacheCreation = tokenUsage.cache_creation_input_tokens || 0;
  }

  // Speed tier and inference geo-routing region
  const usageSpeed = (tokenUsage && typeof tokenUsage === 'object') ? tokenUsage.speed : null;
  let inferenceGeo = null;
  if (tokenUsage && typeof tokenUsage === 'object') {
    inferenceGeo = tokenUsage.inference_geo;
    if (inferenceGeo == null && tokenUsage.cache_creation && typeof tokenUsage.cache_creation === 'object') {
      inferenceGeo = tokenUsage.cache_creation.inference_geo;
    }
  }

  // Total tokens is standard input + all cache segments + output
  const totalTokens = inputTokens + outputTokens + cacheRead + cacheCreation;
  const costEstimate = calculateCost(primaryModel, tokenUsage);

  // Accurate incremental metrics (deduplicated across stages of a turn)
  if (incrementalTokens && !incrementalTokens.cost && primaryModel) {
    const rates = PRICING_CONFIG[primaryModel] || PRICING_CONFIG['claude-3-5-sonnet-20241022'];
    const isLargeContext = (inputTokens + cacheRead + cacheCreation) > 200000;
    let inRate = rates.in;
    let outRate = rates.out;
    let writeRate = rates.cacheWrite;
    let readRate = rates.cacheRead;
    if (isLargeContext && (primaryModel.includes('sonnet') || primaryModel.includes('opus'))) {
      inRate *= 2;
      outRate *= 1.5;
      writeRate *= 2;
      readRate *= 2;
    }

    const incInput = incrementalTokens.input || 0;
    const incOutput = incrementalTokens.output || 0;
    const incRead = incrementalTokens.cache_read || 0;
    const incCreation = incrementalTokens.cache_creation || 0;

    // Disjoint Sum Logic
    incrementalTokens.cost =
      (incInput / 1000000 * inRate) +
      (incOutput / 1000000 * outRate) +
      (incCreation / 1000000 * writeRate) +
      (incRead / 1000000 * readRate);
  }

  // Timestamps
  const currentMs = Date.now();

  let tsIso = record.timestamp;
  if (!tsIso && msgType === 'file-history-snapshot') {
    tsIso = (record.snapshot || {}).timestamp;
  }

  let userTs;
  if (tsIso) {
    userTs = toUnixMs(tsIso);
  } else {
    const lastTsIso = contextOverrides.last_timestamp;
    const fileMtime = contextOverrides.file_mtime;

    if (lastTsIso) {
      userTs = toUnixMs(lastTsIso);
    } else if (fileMtime) {
      userTs = Math.floor(fileMtime);
    } else {
      userTs = currentMs;
    }
  }

  // Explicit Mapping Extractions
  const customTitle = record.customTitle;
  const aiTitle = record.aiTitle;
  const sessionTagVal = record.tag;
  const agentMapName = record.agentName;
  const agentMapColor = record.agentColor;
  const agentSetting = record.agentSetting;
  const prUrl = record.prUrl;
  const attributionSurface = record.surface;
  const sessionMode = record.mode;
  const worktreeSession = record.worktreeSession ? JSON.stringify(record.worktreeSession) : null;
  const stagedNodes = record.staged != null ? JSON.stringify(record.staged) : null;
  const origamiSummary = ['marble-origami-commit', 'task-summary'].includes(msgType) ? record.summary : null;
  const timeSavedMs = record.timeSavedMs;
  const replacedResultsCount = Array.isArray(record.replacements) ? record.replacements.length : null;

  // New deep audit variables
  const promptCount = record.promptCount;
  const promptCountAtLastCommit = record.promptCountAtLastCommit;
  const permissionPromptCount = record.permissionPromptCount;
  const permissionPromptCountAtLastCommit = record.permissionPromptCountAtLastCommit;
  const escapeCount = record.escapeCount;
  const escapeCountAtLastCommit = record.escapeCountAtLastCommit;

  const prNumberVal = record.prNumber;
  const prRepositoryVal = record.prRepository;

  const serverToolUseObj = (tokenUsage && typeof tokenUsage === 'object') ? (tokenUsage.server_tool_use || {}) : {};
  const webSearchRequests = (serverToolUseObj && typeof serverToolUseObj === 'object') ? serverToolUseObj.web_search_requests : null;
  const webFetchRequests = (serverToolUseObj && typeof serverToolUseObj === 'object') ? serverToolUseObj.web_fetch_requests : null;
  const serviceTier = (tokenUsage && typeof tokenUsage === 'object') ? tokenUsage.service_tier : null;
  const iterations = (tokenUsage && typeof tokenUsage === 'object' && 'iterations' in tokenUsage)
    ? JSON.stringify(tokenUsage.iterations)
    : null;

  const firstArchivedUuid = record.firstArchivedUuid;
  const lastArchivedUuid = record.lastArchivedUuid;

  const worktreeObj = (record.worktreeSession && typeof record.worktreeSession === 'object') ? record.worktreeSession : {};
  const worktreeBranch = worktreeObj.worktreeBranch;
  const originalBranch = worktreeObj.originalBranch;
  const originalHeadCommit = worktreeObj.originalHeadCommit;
  const tmuxSessionName = worktreeObj.tmuxSessionName;
  const hookBased = worktreeObj.hookBased;
  // Extended worktree sub-fields
  const worktreeOriginalCwd = worktreeObj.originalCwd;
  const worktreePath = worktreeObj.worktreePath;
  const worktreeName = worktreeObj.worktreeName;

  const progressData = (record.data && typeof record.data === 'object') ? record.data : {};
  const taskDescription = progressData.taskDescription;
  const taskType = progressData.taskType;

  // ── has_thinking helper ─────────────────────────────────────────────────
  const messageContentForThinking = (msgType === 'assistant' && message && typeof message === 'object' && Array.isArray(message.content))
    ? message.content
    : [];
  const hasThinking = messageContentForThinking.some(b => b && typeof b === 'object' && b.type === 'thinking');

  // ── duration_ms logic (mirrors Python ternary) ──────────────────────────
  const durationMsFromRecord = record.durationMs;
  let durationMs = null;
  if (['system', 'progress'].includes(msgType) || 'durationMs' in record || totalDurationMs != null) {
    durationMs = durationMsFromRecord || totalDurationMs;
  }

  // ── cvs199 object ───────────────────────────────────────────────────────
  const cvs199Obj = {
    // Raw log record exactly as read from the jsonl file
    raw: record,

    // Computed timestamps / identity
    user_timestamp: userTs,
    event_id: eventId,
    uuid: uuid,

    // True computed aggregates
    cache_creation: cacheCreation,
    total_tokens: totalTokens,
    cost_estimate: costEstimate,
    incremental_tokens: incrementalTokens,

    // Context / environment (from context_overrides)
    is_agent: isAgent,
    agent_type: agentType,
    agent_description: agentDescription,
    log_index: logIndex,
    integration_version: INTEGRATION_VERSION,
    os_user: OS_USER,

    // Derived via content-block scanning
    agent_id: agentId,
    tool_use_id: toolUseId,
    tool_use_result: toolUseResultStr,
    error_obj: errorObjStr,

    // Mapper-synthesised text
    user_prompt: userPrompt,
    assistant_text: assistantText,

    // Trivially computed scalars
    project: project,
    replaced_results_count: replacedResultsCount,
    prompt_count: promptCount,
    prompt_count_at_last_commit: promptCountAtLastCommit,
    permission_prompt_count: permissionPromptCount,
    permission_prompt_count_at_last_commit: permissionPromptCountAtLastCommit,
    escape_count: escapeCount,
    escape_count_at_last_commit: escapeCountAtLastCommit,
    pr_number: prNumberVal,
    pr_repository: prRepositoryVal,
    service_tier: serviceTier,
    iterations: iterations,
    web_search_requests: webSearchRequests,
    web_fetch_requests: webFetchRequests,
    first_archived_uuid: firstArchivedUuid,
    last_archived_uuid: lastArchivedUuid,
    worktree_branch: worktreeBranch,
    original_branch: originalBranch,
    original_head_commit: originalHeadCommit,
    tmux_session_name: tmuxSessionName,
    task_description: taskDescription,
    task_type: taskType,
    hook_based: hookBased,
    worktree_original_cwd: worktreeOriginalCwd,
    worktree_path: worktreePath,
    worktree_name: worktreeName,

    // Newly mapped schema fields
    is_synthetic: isSynthetic,
    is_visible_in_transcript_only: isVisibleInTranscriptOnly,
    is_virtual: isVirtual,
    is_compact_summary: isCompactSummary,
    is_p50: isP50,
    advisor_model: advisorModel,
    upgrade_nudge: upgradeNudge,
    url: url,
    priority: priority,
    hook_label: hookLabel,
    stop_reason_top: stopReasonTop,
    research: researchStr,
    mcp_meta: mcpMetaStr,
    summarize_metadata: summarizeMetadataStr,
    compact_metadata: compactMetadataStr,
    microcompact_metadata: microcompactMetadataStr,
    cause: causeStr,
    api_error: apiErrorStr,
    error_details: errorDetails,
    origin: originStr,
    image_paste_ids: imagePasteIdsStr,
    file_attachments: fileAttachmentsStr,
    written_paths: writtenPathsStr,
    commands: commandsStr,
    budget_tokens: budgetTokens,
    budget_limit: budgetLimit,
    budget_nudges: budgetNudges,
    message_count: messageCount,
    ttft_ms: ttftMs,
    otps: otps,
    hook_duration_ms: hookDurationMs,
    turn_duration_ms: turnDurationMs,
    tool_duration_ms: toolDurationMs,
    classifier_duration_ms: classifierDurationMs,
    tool_count: toolCount,
    classifier_count: classifierCount,
    config_write_count: configWriteCount,
    worktree_original_cwd: worktreeOriginalCwd,
    worktree_path: worktreePath,
    worktree_name: worktreeName,
  };

  // ── Incremental helpers ─────────────────────────────────────────────────
  const incInput = (incrementalTokens ? (incrementalTokens.input != null ? incrementalTokens.input : inputTokens) : inputTokens);
  const incOutput = (incrementalTokens ? (incrementalTokens.output != null ? incrementalTokens.output : outputTokens) : outputTokens);
  const incTotal = (incrementalTokens ? (incrementalTokens.total != null ? incrementalTokens.total : totalTokens) : totalTokens);
  const incCost = (incrementalTokens ? (incrementalTokens.cost != null ? incrementalTokens.cost : (costEstimate || 0.0)) : (costEstimate || 0.0));
  const incCacheRead = (incrementalTokens ? (incrementalTokens.cache_read != null ? incrementalTokens.cache_read : cacheRead) : cacheRead);
  const incCacheCreation = (incrementalTokens ? (incrementalTokens.cache_creation != null ? incrementalTokens.cache_creation : cacheCreation) : cacheCreation);

  // ── Stop reason from message ────────────────────────────────────────────
  const stopReason = (message && typeof message === 'object') ? message.stop_reason : null;

  // ── Build payload ───────────────────────────────────────────────────────
  let payload;

  if (CLAUDE_PIXEL) {
    payload = {
      timestamp: currentMs,
      user_timestamp: userTs,
      event_id: eventId,
      event_type: `claude_code_${msgType}`,
      event_source_name: 'claude_code',
      debug: false,
      session_id: sessionId,
      project: project,
      git_branch: gitBranch,
      user_prompt: userPrompt,
      assistant_text: assistantText,
      stop_reason: stopReason,
      permission_mode: permissionMode,
      version: version,
      primary_model: primaryModel,
      slug: slug,
      parent_uuid: parentUuid,
      cwd: cwd,
      raw_uuid: rawUuid,
      raw_message_id: rawMessageId,
      assistant_msg_id: assistantMsgId,
      user_type: userType,
      subtype: subtype,
      hook_name: hookName,
      hook_command: hookCommand,
      agent_id: agentId,
      tool_use_id: toolUseId,
      parent_tool_use_id: parentToolUseId,
      source_tool_assistant_uuid: sourceToolAssistantUuid,
      source_tool_use_id: sourceToolUseId,
      entrypoint: entrypoint,
      last_prompt: lastPrompt,
      error_obj: errorObjStr,
      tool_use_result: toolUseResultStr,
      hook_event: hookEvent,
      prompt_id: promptId,
      level: level,
      ide_diagnostics: ideDiagnosticsStr,
      request_id: requestId,
      integration_version: INTEGRATION_VERSION,
      os_user: OS_USER,
      agent_type: agentType,
      agent_description: agentDescription,
      log_index: logIndex,
      input_tokens: parseFloat(inputTokens),
      output_tokens: parseFloat(outputTokens),
      total_tokens: parseFloat(totalTokens),
      cache_read: parseFloat(cacheRead),
      cache_creation: parseFloat(cacheCreation),
      duration_ms: durationMs,
      cost_estimate: costEstimate,
      incremental_input: parseFloat(incInput),
      incremental_output: parseFloat(incOutput),
      incremental_total: parseFloat(incTotal),
      incremental_cost: parseFloat(incCost),
      has_thinking: hasThinking,
      is_api_error_message: record.isApiErrorMessage || false,
      is_meta: isMeta,
      is_sidechain: isSidechain,
      is_snapshot_update: isSnapshotUpdate,
      has_output: hasOutput,
      prevented_continuation: preventedContinuation,
      is_agent: isAgent,
      usage_speed: usageSpeed,
      inference_geo: inferenceGeo,
      incremental_cache_read: parseFloat(incCacheRead),
      incremental_cache_creation: parseFloat(incCacheCreation),
      custom_title: customTitle,
      ai_title: aiTitle,
      session_tag: sessionTagVal,
      agent_map_name: agentMapName,
      agent_map_color: agentMapColor,
      agent_setting: agentSetting,
      pr_url: prUrl,
      attribution_surface: attributionSurface,
      session_mode: sessionMode,
      task_status: taskStatus,
      worktree_session: worktreeSession,
      staged_nodes: stagedNodes,
      origami_summary: origamiSummary,
      worktree_branch: worktreeBranch,
      pr_repository: prRepositoryVal,
      service_tier: serviceTier,
      iterations: iterations,
      first_archived_uuid: firstArchivedUuid,
      last_archived_uuid: lastArchivedUuid,
      original_branch: originalBranch,
      original_head_commit: originalHeadCommit,
      tmux_session_name: tmuxSessionName,
      task_description: taskDescription,
      task_type: taskType,
      time_saved_ms: timeSavedMs,
      replaced_results_count: replacedResultsCount,
      logical_parent_uuid: logicalParentUuid,
      team_name: teamName,
      stop_sequence: stopSequence,
      leaf_uuid: leafUuid,
      pr_number: prNumberVal,
      file_states: fileStates,
      collapse_id: collapseId,
      summary_uuid: summaryUuid,
      summary_content: summaryContent,
      armed: armed,
      last_spawn_tokens: lastSpawnTokens,
      status_message: statusMessage,
      hook_specific_output: hookSpecificOutput,
      prompt_count: promptCount,
      prompt_count_at_last_commit: promptCountAtLastCommit,
      permission_prompt_count: permissionPromptCount,
      permission_prompt_count_at_last_commit: permissionPromptCountAtLastCommit,
      escape_count: escapeCount,
      escape_count_at_last_commit: escapeCountAtLastCommit,
      web_search_requests: webSearchRequests,
      web_fetch_requests: webFetchRequests,
      hook_based: hookBased,
      // ── Newly mapped schema fields (descriptive mode) ──────────────
      is_synthetic: isSynthetic,
      is_visible_in_transcript_only: isVisibleInTranscriptOnly,
      is_virtual: isVirtual,
      is_compact_summary: isCompactSummary,
      is_p50: isP50,
      advisor_model: advisorModel,
      upgrade_nudge: upgradeNudge,
      url: url,
      priority: priority,
      hook_label: hookLabel,
      stop_reason_top: stopReasonTop,
      research: researchStr,
      mcp_meta: mcpMetaStr,
      summarize_metadata: summarizeMetadataStr,
      compact_metadata: compactMetadataStr,
      microcompact_metadata: microcompactMetadataStr,
      cause: causeStr,
      api_error: apiErrorStr,
      error_details: errorDetails,
      origin: originStr,
      image_paste_ids: imagePasteIdsStr,
      file_attachments: fileAttachmentsStr,
      written_paths: writtenPathsStr,
      commands: commandsStr,
      budget_tokens: budgetTokens,
      budget_limit: budgetLimit,
      budget_nudges: budgetNudges,
      message_count: messageCount,
      ttft_ms: ttftMs,
      otps: otps,
      hook_duration_ms: hookDurationMs,
      turn_duration_ms: turnDurationMs,
      tool_duration_ms: toolDurationMs,
      classifier_duration_ms: classifierDurationMs,
      tool_count: toolCount,
      classifier_count: classifierCount,
      config_write_count: configWriteCount,
      worktree_original_cwd: worktreeOriginalCwd,
      worktree_path: worktreePath,
      worktree_name: worktreeName,
      cvs199: JSON.stringify(cvs199Obj),
      cvs200: 'ClaudeCodeHook',
    };
  } else {
    // Legacy CV Mapping (cvs, cvn, cvb)
    payload = {
      timestamp: currentMs,
      user_timestamp: userTs,
      event_id: eventId,
      event_type: `claude_code_${msgType}`,
      event_source_name: 'claude_code',
      debug: false,
      cvs1: sessionId,
      cvs2: project,
      cvs3: gitBranch,
      cvs4: userPrompt,
      cvs5: assistantText,
      cvs6: stopReason,
      cvs7: permissionMode,
      cvs8: version,
      cvs9: primaryModel,
      cvs10: slug,
      cvs11: parentUuid,
      cvs12: cwd,
      cvs13: rawUuid,
      cvs14: rawMessageId,
      cvs15: assistantMsgId,
      cvs16: userType,
      cvs17: subtype,
      cvs18: hookName,
      cvs19: hookCommand,
      cvs20: agentId,
      cvs21: toolUseId,
      cvs22: parentToolUseId,
      cvs23: sourceToolAssistantUuid,
      cvs24: lastPrompt,
      cvs25: errorObjStr,
      cvs26: toolUseResultStr,
      cvs27: hookEvent,
      cvs28: promptId,
      cvs29: level,
      cvs30: ideDiagnosticsStr,
      cvs31: requestId,
      cvs32: INTEGRATION_VERSION,
      cvs33: OS_USER,
      cvs34: agentType,
      cvs35: agentDescription,
      cvs36: entrypoint,
      cvs37: sourceToolUseId,
      cvs38: usageSpeed,
      cvs39: inferenceGeo,
      cvs40: customTitle,
      cvs41: aiTitle,
      cvs42: sessionTagVal,
      cvs43: agentMapName,
      cvs44: agentMapColor,
      cvs45: agentSetting,
      cvs46: prUrl,
      cvs47: attributionSurface,
      cvs48: sessionMode,
      cvs49: worktreeSession,
      cvs50: stagedNodes,
      cvs51: origamiSummary,
      cvs52: logicalParentUuid,
      cvs53: teamName,
      cvs54: stopSequence,
      cvs55: leafUuid,
      cvs56: prRepositoryVal,
      cvs57: fileStates,
      cvs58: collapseId,
      cvs59: summaryUuid,
      cvs60: summaryContent,
      cvs61: statusMessage,
      cvs62: hookSpecificOutput,
      cvs63: worktreeBranch,
      cvs64: serviceTier,
      cvs65: firstArchivedUuid,
      cvs66: lastArchivedUuid,
      cvs67: originalBranch,
      cvs68: originalHeadCommit,
      cvs69: tmuxSessionName,
      cvs70: taskDescription,
      cvs71: taskType,
      cvs72: iterations,
      // ── Newly mapped schema fields (CV mode) ──────────────────────
      cvs73: advisorModel,
      cvs74: upgradeNudge,
      cvs75: url,
      cvs76: priority,
      cvs77: hookLabel,
      cvs78: stopReasonTop,
      cvs79: researchStr,
      cvs80: mcpMetaStr,
      cvs81: summarizeMetadataStr,
      cvs82: compactMetadataStr,
      cvs83: microcompactMetadataStr,
      cvs84: causeStr,
      cvs85: apiErrorStr,
      cvs86: errorDetails,
      cvs87: originStr,
      cvs88: imagePasteIdsStr,
      cvs89: fileAttachmentsStr,
      cvs90: writtenPathsStr,
      cvs91: commandsStr,
      cvs92: worktreeOriginalCwd,
      cvs93: worktreePath,
      cvs94: worktreeName,
      cvs199: JSON.stringify(cvs199Obj),
      cvs200: 'ClaudeCodeHook',
      cvn1: inputTokens,
      cvn2: outputTokens,
      cvn3: totalTokens,
      cvn4: cacheRead,
      cvn5: cacheCreation,
      cvn6: durationMs,
      cvn7: costEstimate,
      cvn8: logIndex,
      cvn9: incrementalTokens ? incrementalTokens.input : inputTokens,
      cvn10: incrementalTokens ? incrementalTokens.output : outputTokens,
      cvn11: incrementalTokens ? incrementalTokens.total : totalTokens,
      cvn12: incrementalTokens ? incrementalTokens.cost : costEstimate,
      cvn13: hookCount,
      cvn14: maxRetries,
      cvn15: retryAttempt,
      cvn16: retryInMs,
      cvn17: incrementalTokens ? incrementalTokens.cache_read : cacheRead,
      cvn18: incrementalTokens ? incrementalTokens.cache_creation : cacheCreation,
      cvn19: timeSavedMs,
      cvn20: replacedResultsCount,
      cvn21: prNumberVal,
      cvn22: lastSpawnTokens,
      cvn23: promptCount,
      cvn24: promptCountAtLastCommit,
      cvn25: permissionPromptCount,
      cvn26: permissionPromptCountAtLastCommit,
      cvn27: escapeCount,
      cvn28: escapeCountAtLastCommit,
      cvn29: webSearchRequests,
      cvn30: webFetchRequests,
      cvn31: budgetTokens,
      cvn32: budgetLimit,
      cvn33: budgetNudges,
      cvn34: messageCount,
      cvn35: ttftMs,
      cvn36: otps,
      cvn37: hookDurationMs,
      cvn38: turnDurationMs,
      cvn39: toolDurationMs,
      cvn40: classifierDurationMs,
      cvn41: toolCount,
      cvn42: classifierCount,
      cvn43: configWriteCount,
      cvb1: hasThinking,
      cvb2: record.isApiErrorMessage || false,
      cvb3: isMeta,
      cvb4: isSidechain,
      cvb5: isSnapshotUpdate,
      cvb6: hasOutput,
      cvb7: preventedContinuation,
      cvb8: isAgent,
      cvb9: armed,
      cvb10: hookBased,
      cvb11: isSynthetic,
      cvb12: isVisibleInTranscriptOnly,
      cvb13: isVirtual,
      cvb14: isCompactSummary,
      cvb15: isP50,
    };
  }

  // Remove null/undefined values — mirrors Python's {k:v for k,v in payload.items() if v is not None}
  return Object.fromEntries(
    Object.entries(payload).filter(([, v]) => v !== null && v !== undefined)
  );
}

module.exports = {
  transformRecord,
  calculateCost,
  toUnixMs,
  logUnhandled,
  redactRawRecord,
  INTEGRATION_VERSION,
  OS_USER,
  CLAUDE_PIXEL,
  REDACTION,
  PRICING_CONFIG,
};
