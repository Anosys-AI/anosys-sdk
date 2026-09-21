/**
 * Schema mapper for Google Antigravity hook turns (JavaScript).
 * Maps Antigravity turns, planner steps, and tool calls into AnoSys CC schema.
 */

const path = require('path');
const os = require('os');
const { INTEGRATION_VERSION } = require('./constants');

const OS_USER = process.env.USERNAME || process.env.USER || 'unknown';
const REDACTION = (process.env.REDACTION || 'false').toLowerCase() === 'true';

function extractToolDetails(toolSteps) {
  const toolsUsed = [];
  const commands = [];
  const writtenPaths = [];
  const viewedPaths = [];
  const searchedQueries = [];
  const subagentsSpawned = [];
  const toolErrors = [];
  const durations = [];

  for (const tool of (toolSteps || [])) {
    const name = String(tool.name || '').trim();
    if (name && !toolsUsed.includes(name)) {
      toolsUsed.push(name);
    }

    let args = tool.args || {};
    if (typeof args === 'string') {
      try {
        args = JSON.parse(args);
      } catch {
        args = { raw: args };
      }
    }
    if (!args || typeof args !== 'object') args = {};

    const output = String(tool.output || '');
    const status = String(tool.status || '');
    const dur = typeof tool.duration_ms === 'number' ? tool.duration_ms : 0;
    if (dur > 0) durations.push(dur);

    if (status.toUpperCase() === 'ERROR' || status.toUpperCase() === 'FAILED' || output.toLowerCase().slice(0, 200).includes('error')) {
      toolErrors.push(`${name}: ${output.slice(0, 300)}`);
    }

    // Commands
    if (['run_command', 'bash', 'shell', 'exec', 'terminal'].includes(name)) {
      const cmd = args.CommandLine || args.command || args.cmd || '';
      if (cmd && typeof cmd === 'string') {
        commands.push(cmd.trim());
      }
    }

    // Written paths
    if (['write_to_file', 'replace_file_content', 'multi_replace_file_content', 'edit', 'save'].includes(name)) {
      const fp = args.TargetFile || args.FilePath || args.file_path || args.path || '';
      if (fp && typeof fp === 'string') {
        writtenPaths.push(fp.trim());
      }
    }

    // Viewed paths
    if (['view_file', 'read_file'].includes(name)) {
      const fp = args.AbsolutePath || args.FilePath || args.file || args.path || '';
      if (fp && typeof fp === 'string') {
        viewedPaths.push(fp.trim());
      }
    }

    // Searches
    if (['search_web', 'grep_search'].includes(name)) {
      const q = args.query || args.Query || '';
      if (q && typeof q === 'string') {
        searchedQueries.push(q.trim());
      }
    }

    // Subagents
    if (name.includes('subagent')) {
      const task = args.TaskName || args.Task || args.task || name;
      if (task && typeof task === 'string') {
        subagentsSpawned.push(task.trim());
      }
    }
  }

  const toolDurationMs = durations.reduce((a, b) => a + b, 0);

  return {
    tools_used: toolsUsed,
    commands,
    written_paths: writtenPaths,
    viewed_paths: viewedPaths,
    searched_queries: searchedQueries,
    subagents_spawned: subagentsSpawned,
    tool_errors: toolErrors,
    tool_duration_ms: toolDurationMs,
    tool_count: (toolSteps || []).length,
  };
}

function transformAntigravityTurn(turn, sessionId, turnId, hookMetadata, redact) {
  const doRedact = typeof redact === 'boolean' ? redact : REDACTION;
  const meta = hookMetadata || {};

  let userPrompt = String(turn.user_input || '');
  let assistantText = String(turn.final_response || '');

  if (doRedact) {
    userPrompt = '[REDACTED]';
    assistantText = '[REDACTED]';
  }

  const model = turn.model_name || meta.modelName || meta.model || 'gemini-2.5-pro';

  const workspacePaths = Array.isArray(meta.workspacePaths) ? meta.workspacePaths : [];
  let cwd = '';
  if (workspacePaths.length > 0) {
    cwd = String(workspacePaths[0]);
  } else if (meta.cwd) {
    cwd = String(meta.cwd);
  }
  const project = cwd ? path.basename(cwd) : null;

  const startMs = turn.start_ms || Date.now();
  const endMs = turn.end_ms || startMs;
  const durationMs = Math.max(0, endMs - startMs);

  const toolSteps = turn.tool_steps || [];
  const toolDetails = extractToolDetails(toolSteps);

  const toolStepsClean = toolSteps.map(tc => {
    const entry = { ...tc };
    if (doRedact) {
      entry.args = '[REDACTED]';
      entry.output = '[REDACTED]';
    }
    return entry;
  });

  const rawData = {
    turn: {
      start_ms: startMs,
      end_ms: endMs,
      duration_ms: durationMs,
      model_name: model,
      has_thinking: Boolean(turn.has_thinking),
      step_count: turn.step_count || 0,
      max_step_index: turn.max_step_index || 0,
      llm_steps: turn.llm_steps || [],
      tool_steps: toolStepsClean,
      hook_metadata: meta,
    },
  };

  let rawToSerialize = rawData;
  if (doRedact) {
    try {
      let rawStr = JSON.stringify(rawData);
      const origPrompt = String(turn.user_input || '');
      const origResp = String(turn.final_response || '');
      if (origPrompt) rawStr = rawStr.split(origPrompt).join('[REDACTED]');
      if (origResp) rawStr = rawStr.split(origResp).join('[REDACTED]');
      rawToSerialize = JSON.parse(rawStr);
    } catch {
      rawToSerialize = rawData;
    }
  }

  const terminationReason = meta.terminationReason || null;
  const errorObj = meta.error || null;
  const fullyIdle = typeof meta.fullyIdle === 'boolean' ? meta.fullyIdle : true;
  const executionNum = typeof meta.executionNum === 'number' ? meta.executionNum : null;
  const transcriptPath = meta.transcriptPath || null;
  const artifactDir = meta.artifactDirectoryPath || null;

  const commandsStr = toolDetails.commands.length > 0 ? JSON.stringify(toolDetails.commands) : null;
  const writtenPathsStr = toolDetails.written_paths.length > 0 ? JSON.stringify(toolDetails.written_paths) : null;
  const viewedPathsStr = toolDetails.viewed_paths.length > 0 ? JSON.stringify(toolDetails.viewed_paths) : null;
  const queriesStr = toolDetails.searched_queries.length > 0 ? JSON.stringify(toolDetails.searched_queries) : null;
  const subagentsStr = toolDetails.subagents_spawned.length > 0 ? JSON.stringify(toolDetails.subagents_spawned) : null;
  const toolErrorsStr = toolDetails.tool_errors.length > 0 ? JSON.stringify(toolDetails.tool_errors) : null;
  const workspacePathsStr = workspacePaths.length > 0 ? JSON.stringify(workspacePaths) : null;

  const payload = {
    // Identity
    session_id: sessionId,
    sessionId: sessionId,
    uuid: turnId,
    event_id: turnId,
    eventId: turnId,
    event_type: 'antigravity_turn',
    event_source_name: 'antigravity',
    timestamp: startMs,
    user_timestamp: startMs,
    debug: false,
    // Content
    user_prompt: userPrompt,
    userPrompt: userPrompt,
    assistant_text: assistantText,
    assistantText: assistantText,
    // Model
    model: model,
    primary_model: model,
    model_provider: 'google',
    // Environment
    cwd: cwd || null,
    project: project,
    // IDE Metadata
    active_document: turn.active_document || null,
    active_document_language: turn.active_document_language || null,
    cursor_line: turn.cursor_line || null,
    client_timestamp_iso: turn.client_timestamp_iso || null,
    user_settings_change: turn.user_settings_change || null,
    termination_reason: terminationReason,
    // Metrics
    duration_ms: durationMs,
    tool_count: toolDetails.tool_count,
    tool_duration_ms: toolDetails.tool_duration_ms,
    tools_used: toolDetails.tools_used,
    commands: commandsStr,
    written_paths: writtenPathsStr,
    viewed_paths: viewedPathsStr,
    searched_queries: queriesStr,
    subagents_spawned: subagentsStr,
    has_thinking: Boolean(turn.has_thinking),
    llm_step_count: (turn.llm_steps || []).length,
    fully_idle: fullyIdle,
    execution_num: executionNum,
    error_obj: errorObj,
    transcript_path: transcriptPath,
    artifact_directory: artifactDir,
    workspace_paths: workspacePathsStr,
    integration_version: INTEGRATION_VERSION,
    os_user: OS_USER,
    // CV Columns (CC Pixel)
    cvs1: sessionId,
    cvs2: project,
    cvs4: userPrompt,
    cvs5: assistantText,
    cvs6: terminationReason ? String(terminationReason) : null,
    cvs9: model,
    cvs12: cwd || null,
    cvs13: turnId,
    cvs16: String(turn.user_source || 'USER_EXPLICIT'),
    cvs17: 'google',
    cvs18: meta.hook_name || 'Stop',
    cvs19: 'anosys-antigravity run',
    cvs25: errorObj ? String(errorObj) : null,
    cvs32: INTEGRATION_VERSION,
    cvs33: OS_USER,
    cvs70: turn.active_document || null,
    cvs71: turn.active_document_language || null,
    cvs72: turn.client_timestamp_iso || null,
    cvs75: turn.user_settings_change || null,
    cvs76: viewedPathsStr,
    cvs77: queriesStr,
    cvs78: subagentsStr,
    cvs79: toolErrorsStr,
    cvs88: transcriptPath,
    cvs89: artifactDir,
    cvs90: commandsStr,
    cvs91: writtenPathsStr,
    cvs93: workspacePathsStr,
    cvn1: 0,
    cvn2: 0,
    cvn3: 0,
    cvn6: durationMs,
    cvn7: 0.0,
    cvn8: typeof executionNum === 'number' ? executionNum : null,
    cvn25: turn.cursor_line || null,
    cvn26: (turn.llm_steps || []).length,
    cvn27: turn.max_step_index || null,
    cvn28: turn.step_count || null,
    cvn39: toolDetails.tool_duration_ms,
    cvn41: toolDetails.tool_count,
    cvb1: false,
    cvb2: Boolean(turn.has_thinking),
    cvb3: typeof fullyIdle === 'boolean' ? fullyIdle : null,
    cvs199: JSON.stringify(rawToSerialize),
    cvs200: 'AntigravityHook',
  };

  const clean = {};
  for (const [k, v] of Object.entries(payload)) {
    if (v !== null && v !== undefined) {
      clean[k] = v;
    }
  }
  return clean;
}

module.exports = {
  extractToolDetails,
  transformAntigravityTurn,
};
