/**
 * Pure parser for Google Antigravity transcript JSONL.
 * Parses transcript_full.jsonl (or transcript.jsonl) into structured turn objects.
 */

const fs = require('fs');
const path = require('path');

const USER_REQUEST_RE = /<USER_REQUEST>([\s\S]*?)<\/USER_REQUEST>/;
const ADDITIONAL_METADATA_RE = /<ADDITIONAL_METADATA>([\s\S]*?)<\/ADDITIONAL_METADATA>/;
const USER_SETTINGS_CHANGE_RE = /<USER_SETTINGS_CHANGE>([\s\S]*?)<\/USER_SETTINGS_CHANGE>/;
const MODEL_SELECTION_RE = /changed setting `Model Selection` from .*? to (.+?)\.(?=\s+[A-Z]|\s*$)/s;
const ACTIVE_DOC_RE = /Active Document:\s*([^\r\n(]+?)(?:\s*\((LANGUAGE_\w+)\))?(?:\r?\n|$)/i;
const CURSOR_LINE_RE = /Cursor is on line:\s*(\d+)/i;
const CLIENT_TIME_RE = /The current local time is:\s*([^\r\n.]+)/i;
const CREATED_AT_RE = /^Created At:\s*(\S+)/m;
const COMPLETED_AT_RE = /^Completed At:\s*(\S+)/m;

const NON_TOOL_TYPES = new Set(['USER_INPUT', 'PLANNER_RESPONSE', 'CONVERSATION_HISTORY']);

function isoToMs(value) {
  if (!value) return 0;
  try {
    const ms = Date.parse(value.trim());
    return isNaN(ms) ? 0 : ms;
  } catch {
    return 0;
  }
}

function extractUserRequest(content) {
  if (!content) return '';
  const match = content.match(USER_REQUEST_RE);
  if (match) {
    return match[1].trim();
  }
  let stripped = content.replace(ADDITIONAL_METADATA_RE, '');
  stripped = stripped.replace(USER_SETTINGS_CHANGE_RE, '');
  return stripped.trim();
}

function extractMetadataFields(content) {
  const res = {
    active_document: null,
    active_document_language: null,
    cursor_line: null,
    client_timestamp_iso: null,
  };
  const match = (content || '').match(ADDITIONAL_METADATA_RE);
  if (!match) return res;

  const metaText = match[1];
  const docMatch = metaText.match(ACTIVE_DOC_RE);
  if (docMatch) {
    res.active_document = docMatch[1].trim();
    if (docMatch[2]) {
      res.active_document_language = docMatch[2].trim();
    }
  }

  const lineMatch = metaText.match(CURSOR_LINE_RE);
  if (lineMatch) {
    const lineNum = parseInt(lineMatch[1], 10);
    if (!isNaN(lineNum)) {
      res.cursor_line = lineNum;
    }
  }

  const timeMatch = metaText.match(CLIENT_TIME_RE);
  if (timeMatch) {
    res.client_timestamp_iso = timeMatch[1].trim();
  }

  return res;
}

function extractSettingsChange(content) {
  const res = {
    model_name: null,
    user_settings_change: null,
  };
  const match = (content || '').match(USER_SETTINGS_CHANGE_RE);
  if (!match) return res;

  const settingsText = match[1].trim();
  res.user_settings_change = settingsText;

  const modelMatch = settingsText.match(MODEL_SELECTION_RE);
  if (modelMatch) {
    res.model_name = modelMatch[1].trim();
  }

  return res;
}

function buildTurn(records) {
  const userRecord = records[0] || {};
  const userContent = String(userRecord.content || '');

  const userPrompt = extractUserRequest(userContent);
  const meta = extractMetadataFields(userContent);
  const settings = extractSettingsChange(userContent);

  const stepIndices = records.filter(r => typeof r.step_index === 'number').map(r => r.step_index);
  const maxStepIndex = stepIndices.length > 0 ? Math.max(...stepIndices) : 0;

  const timestamps = records.map(r => isoToMs(r.created_at)).filter(t => t > 0);
  const startMs = timestamps.length > 0 ? timestamps[0] : (isoToMs(meta.client_timestamp_iso) || 0);
  const endMs = timestamps.length > 0 ? timestamps[timestamps.length - 1] : startMs;

  const turn = {
    user_input: userPrompt,
    user_raw_content: userContent,
    final_response: '',
    model_name: settings.model_name || '',
    user_settings_change: settings.user_settings_change,
    active_document: meta.active_document,
    active_document_language: meta.active_document_language,
    cursor_line: meta.cursor_line,
    client_timestamp_iso: meta.client_timestamp_iso,
    user_source: userRecord.source || 'USER_EXPLICIT',
    max_step_index: maxStepIndex,
    step_count: records.length,
    start_ms: startMs,
    end_ms: endMs,
    has_thinking: false,
    thinking_text: '',
    llm_steps: [],
    tool_steps: [],
    raw_records: records,
  };

  const pendingCalls = [];
  let lastPlannerContent = '';
  const thinkingBlocks = [];

  function flushPendingCalls() {
    for (const call of pendingCalls) {
      turn.tool_steps.push({
        name: call.name,
        args: call.args,
        output: '',
        status: 'PENDING',
        step_index: call.step_index,
        start_ms: call.planner_ms,
        end_ms: call.planner_ms,
        duration_ms: 0,
      });
    }
    pendingCalls.length = 0;
  }

  for (let idx = 0; idx < records.length; idx++) {
    const rec = records[idx];
    const recType = rec.type || '';

    if (recType === 'PLANNER_RESPONSE') {
      flushPendingCalls();
      const stepStart = isoToMs(rec.created_at);
      let stepEnd = stepStart;
      if (idx + 1 < records.length) {
        const nextTs = isoToMs(records[idx + 1].created_at);
        if (nextTs > 0) stepEnd = nextTs;
      }

      const content = String(rec.content || '');
      const thinking = String(rec.thinking || '');
      if (thinking) {
        turn.has_thinking = true;
        thinkingBlocks.push(thinking);
      }

      if (content) {
        lastPlannerContent = content;
      }

      turn.llm_steps.push({
        content,
        thinking,
        step_index: typeof rec.step_index === 'number' ? rec.step_index : 0,
        start_ms: stepStart,
        end_ms: stepEnd,
      });

      const calls = Array.isArray(rec.tool_calls) ? rec.tool_calls : [];
      for (const call of calls) {
        if (!call || typeof call !== 'object') continue;
        const name = String(call.name || '');
        const args = (call.args && typeof call.args === 'object') ? call.args : {};
        pendingCalls.push({
          name,
          args,
          step_index: typeof rec.step_index === 'number' ? rec.step_index : 0,
          planner_ms: stepStart,
        });
      }
    } else if (recType === 'USER_INPUT') {
      continue;
    } else if (recType && !NON_TOOL_TYPES.has(recType)) {
      if (pendingCalls.length === 0) continue;
      const call = pendingCalls.shift();
      const resultContent = String(rec.content || '');
      const status = String(rec.status || 'DONE');

      const createdMatch = resultContent.match(CREATED_AT_RE);
      const completedMatch = resultContent.match(COMPLETED_AT_RE);
      const fallbackMs = isoToMs(rec.created_at);

      let toolStart = createdMatch ? isoToMs(createdMatch[1]) : 0;
      let toolEnd = completedMatch ? isoToMs(completedMatch[1]) : 0;
      if (toolStart === 0) toolStart = fallbackMs || call.planner_ms;
      if (toolEnd === 0) toolEnd = fallbackMs || toolStart;

      const toolDuration = Math.max(0, toolEnd - toolStart);

      turn.tool_steps.push({
        name: call.name,
        args: call.args,
        output: resultContent,
        status,
        step_index: typeof rec.step_index === 'number' ? rec.step_index : 0,
        start_ms: toolStart,
        end_ms: toolEnd,
        duration_ms: toolDuration,
      });
    }
  }

  flushPendingCalls();
  turn.final_response = lastPlannerContent;
  turn.thinking_text = thinkingBlocks.join('\n\n');

  return turn;
}

function parseTranscript(targetPath) {
  if (!targetPath) return [];
  const p = path.resolve(targetPath);
  const dir = path.dirname(p);
  const fullPath = path.join(dir, 'transcript_full.jsonl');

  let chosenFile = null;
  if (fs.existsSync(fullPath)) {
    chosenFile = fullPath;
  } else if (fs.existsSync(p)) {
    chosenFile = p;
  } else {
    return [];
  }

  const records = [];
  try {
    const lines = fs.readFileSync(chosenFile, 'utf-8').split('\n');
    for (let line of lines) {
      line = line.trim();
      if (!line) continue;
      try {
        const rec = JSON.parse(line);
        if (rec && typeof rec === 'object' && rec.type !== 'CONVERSATION_HISTORY') {
          records.append ? records.append(rec) : records.push(rec);
        }
      } catch {}
    }
  } catch {
    return [];
  }

  const turns = [];
  let current = [];
  for (const rec of records) {
    if (rec.type === 'USER_INPUT') {
      if (current.length > 0) {
        turns.push(buildTurn(current));
      }
      current = [rec];
    } else {
      if (current.length > 0) {
        current.push(rec);
      }
    }
  }
  if (current.length > 0) {
    turns.push(buildTurn(current));
  }

  return turns;
}

module.exports = {
  isoToMs,
  extractUserRequest,
  extractMetadataFields,
  extractSettingsChange,
  buildTurn,
  parseTranscript,
};
