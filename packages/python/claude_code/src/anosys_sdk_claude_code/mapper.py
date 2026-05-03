"""
Schema mapper for Claude Code hook turns.
Transforms internal turn dicts into the schema expected by the AnoSys ingestion endpoint.
"""

import datetime
import json
import getpass
import os
import time
from pathlib import Path
from typing import Any, Optional

INTEGRATION_VERSION = '0.2.0'

OS_USER = getpass.getuser()

CLAUDE_PIXEL = os.environ.get('ANOSYS_CLAUDE_PIXEL', 'true').lower() == 'true'

REDACTION = os.environ.get('REDACTION', 'false').lower() == 'true'

UNHANDLED_LOG_PATH = Path('~/.claude/hooks/unhandled_records.jsonl').expanduser()

U = object()


def log_unhandled(record: dict):
    try:
        UNHANDLED_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(UNHANDLED_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, separators=(',', ':')) + '\n')
    except Exception:
        pass


def to_unix_ms(iso_str: str) -> int:
    if not iso_str or not isinstance(iso_str, str):
        return int(time.time() * 1000)
    try:
        cleaned = iso_str.replace('Z', '+00:00')
        dt = datetime.datetime.fromisoformat(cleaned)
        if dt.tzinfo:
            dt = dt.astimezone(datetime.timezone.utc)
        else:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return int(time.time() * 1000)


def redact_raw_record(record: dict) -> dict:
    import copy
    rec = copy.deepcopy(record)
    if 'message' in rec and isinstance(rec['message'], dict):
        if 'content' in rec['message']: rec['message']['content'] = 'REDACTED'
    if 'content' in rec and isinstance(rec['content'], str): rec['content'] = 'REDACTED'
    if 'operation' in rec and 'content' in rec: rec['content'] = 'REDACTED'
    if 'lastPrompt' in rec: rec['lastPrompt'] = 'REDACTED'
    if 'summary' in rec: rec['summary'] = 'REDACTED'
    if 'snapshot' in rec and isinstance(rec['snapshot'], dict):
        if 'trackedFileBackups' in rec['snapshot'] and isinstance(rec['snapshot']['trackedFileBackups'], dict):
            for k in rec['snapshot']['trackedFileBackups']: rec['snapshot']['trackedFileBackups'][k] = 'REDACTED'
    return rec


PRICING_CONFIG = {
    'claude-3-7-sonnet-20250219': {'in': 3.0, 'out': 15.0, 'cacheWrite': 3.75, 'cacheRead': 0.30},
    'claude-3-5-sonnet-20241022': {'in': 3.0, 'out': 15.0, 'cacheWrite': 3.75, 'cacheRead': 0.30},
    'claude-3-opus-20240229': {'in': 15.0, 'out': 75.0, 'cacheWrite': 18.75, 'cacheRead': 1.50},
    'claude-3-5-haiku-20241022': {'in': 1.0, 'out': 5.0, 'cacheWrite': 1.25, 'cacheRead': 0.10},
    'claude-haiku-4-5-20251001': {'in': 1.0, 'out': 5.0, 'cacheWrite': 1.25, 'cacheRead': 0.10},
    'claude-sonnet-4-6': {'in': 3.0, 'out': 15.0, 'cacheWrite': 3.75, 'cacheRead': 0.30},
    '<synthetic>': {'in': 0, 'out': 0, 'cacheWrite': 0, 'cacheRead': 0},
}


def calculate_cost(model: str, usage: dict) -> Optional[float]:
    if not model or not usage: return None
    it, ot, cr = usage.get('input_tokens', 0), usage.get('output_tokens', 0), usage.get('cache_read_input_tokens', 0)
    rc = usage.get('cache_creation')
    if isinstance(rc, dict): cc = rc.get('ephemeral_1h_input_tokens', 0) + rc.get('ephemeral_5m_input_tokens', 0)
    elif isinstance(rc, (int, float)): cc = rc
    else: cc = usage.get('cache_creation_input_tokens', 0)
    rates = PRICING_CONFIG.get(model, PRICING_CONFIG['claude-3-5-sonnet-20241022'])
    in_r, out_r, w_r, r_r = rates['in'], rates['out'], rates['cacheWrite'], rates['cacheRead']
    if (it+cr+cc) > 200000 and ('sonnet' in model or 'opus' in model):
        in_r *= 2; out_r *= 1.5; w_r *= 2; r_r *= 2
    return (it/1000000*in_r) + (ot/1000000*out_r) + (cc/1000000*w_r) + (cr/1000000*r_r)


def to_num(val: Any) -> Any:
    if val is None or val is U: return None
    try:
        f = float(val)
        return int(f) if f.is_integer() else f
    except (ValueError, TypeError): return val


def transform_record(record: dict, incremental_tokens: Any = None, context_overrides: dict = None) -> dict:
    if REDACTION: record = redact_raw_record(record)
    if context_overrides is None: context_overrides = {}

    msg_type = record.get('type', 'unknown')
    message = record.get('message', {}) if isinstance(record.get('message'), dict) else {}
    usage = message.get('usage', {}) if isinstance(message, dict) else {}
    data = record.get('data', {}) if isinstance(record.get('data'), dict) else {}
    current_ms = int(time.time() * 1000)
    user_ts = to_unix_ms(record.get('timestamp') or "")

    sessionId = record.get('sessionId') or context_overrides.get('sessionId') or U
    rawUuid = record.get('uuid', U)
    rawMessageId = (message.get('messageId') if isinstance(message, dict) else record.get('messageId', U))
    rawId = (message.get('id') if isinstance(message, dict) else record.get('id', U))

    uuid = rawUuid if rawUuid and rawUuid is not U else (rawMessageId if rawMessageId and rawMessageId is not U else (rawId if rawId and rawId is not U else U))

    if uuid is not U: eventId = uuid
    elif context_overrides.get('log_index') is not None: eventId = f"{sessionId}_{context_overrides.get('log_index')}"
    else: eventId = f"{'undefined' if sessionId is U else sessionId}_{current_ms / 1000}"

    cwd = record.get('cwd') or context_overrides.get('cwd') or U
    project = Path(cwd).name if cwd and cwd is not U else None
    gitBranch = record.get('gitBranch') or context_overrides.get('gitBranch') or U
    version = record.get('version') or context_overrides.get('version') or U
    slug = record.get('slug') or context_overrides.get('slug') or U
    parentUuid = record.get('parentUuid') or context_overrides.get('parentUuid') or U

    userType = record.get('userType') or context_overrides.get('userType') or U
    permissionMode = record.get('permissionMode') or context_overrides.get('permissionMode') or U
    isMeta = bool(record.get('isMeta', False))
    isSidechain = bool(record.get('isSidechain', False))
    agentId = record.get('agentId') or context_overrides.get('agent_id') or U
    entrypoint = record.get('entrypoint') if record.get('entrypoint') is not None else U
    logicalParentUuid = record.get('logicalParentUuid') or context_overrides.get('logicalParentUuid') or U

    teamName = record.get('teamName') or context_overrides.get('teamName') or U
    taskStatus = record.get('task_status') or record.get('taskStatus') or context_overrides.get('task_status') or context_overrides.get('taskStatus', None)
    isAgent = bool(record.get('isAgent', context_overrides.get('is_agent', False)))
    agentType = record.get('agentType') or context_overrides.get('agent_type', U)
    agentDescription = record.get('agentDescription') or context_overrides.get('agent_description', U)
    lastPrompt = record.get('lastPrompt') or context_overrides.get('lastPrompt') or U
    logIndex = context_overrides.get('log_index') if context_overrides.get('log_index') is not None else U
    requestId = record.get('requestId', U)
    subtype = record.get('subtype', U)

    hookName = data.get('hookName', U)
    hookCommand = data.get('command', U)
    hookEvent = data.get('hookEvent', U)

    ideDiagnostics = None
    if 'ide_diagnostics' in data: ideDiagnostics = data['ide_diagnostics']
    elif isinstance(record.get('hookInfos'), list):
        for info in record['hookInfos']:
            if isinstance(info, dict) and 'ide_diagnostics' in info:
                ideDiagnostics = info['ide_diagnostics']; break
    ideDiagnosticsStr = json.dumps(ideDiagnostics, separators=(',', ':')) if ideDiagnostics is not None else None

    errorVal = record.get('error')
    errorObjStr = json.dumps(errorVal, separators=(',', ':')) if errorVal is not None else None

    toolUseId = record.get('toolUseID') or record.get('tool_use_id')
    if not toolUseId and msg_type == 'assistant' and isinstance(message, dict):
        for b in message.get('content', []):
            if isinstance(b, dict) and b.get('type') == 'tool_use':
                toolUseId = b.get('id') or b.get('tool_use_id')
                if toolUseId: break

    parentToolUseId = record.get('parentToolUseID') or record.get('parent_tool_use_id') or U
    sourceToolAssistantUuid = record.get('sourceToolAssistantUUID') or U
    sourceToolUseId = record.get('sourceToolUseID') or U

    toolUseResult = record.get('toolUseResult')
    if msg_type == 'user' and isinstance(message, dict):
        for b in message.get('content', []):
            if isinstance(b, dict) and b.get('type') == 'tool_result':
                if not toolUseId: toolUseId = b.get('tool_use_id')
                itemAgentId = b.get('agentId')
                if itemAgentId: agentId = itemAgentId
                if toolUseResult is None: toolUseResult = b.get('content')
    toolUseResultStr = json.dumps(toolUseResult, separators=(',', ':')) if toolUseResult is not None else None

    isSnapshotUpdate = bool(record.get('isSnapshotUpdate', False))
    promptId = record.get('promptId') or U
    level = record.get('level') or U
    hasOutput = record.get('hasOutput') if record.get('hasOutput') is not None else U
    preventedContinuation = record.get('preventedContinuation') if record.get('preventedContinuation') is not None else U

    isSynthetic = bool(record.get('isSynthetic', False))
    isVisibleInTranscriptOnly = record.get('isVisibleInTranscriptOnly') if record.get('isVisibleInTranscriptOnly') is not None else U
    isVirtual = record.get('isVirtual') if record.get('isVirtual') is not None else U
    isCompactSummary = bool(record.get('isCompactSummary', False))
    isP50 = record.get('isP50') if record.get('isP50') is not None else U

    advisorModel = record.get('advisorModel') or U
    upgradeNudge = record.get('upgradeNudge') or U
    url = record.get('url') or U
    priority = record.get('priority') or U
    hookLabel = record.get('hookLabel') or U
    stopReasonTop = record.get('stopReason') or U
    researchStr = json.dumps(record.get('research'), separators=(',', ':')) if record.get('research') is not None else None

    mcpMetaStr = json.dumps(record.get('mcpMeta'), separators=(',', ':')) if isinstance(record.get('mcpMeta'), dict) else None
    summarizeMetadataStr = json.dumps(record.get('summarizeMetadata'), separators=(',', ':')) if isinstance(record.get('summarizeMetadata'), dict) else None
    compactMetadataStr = json.dumps(record.get('compactMetadata'), separators=(',', ':')) if isinstance(record.get('compactMetadata'), dict) else None
    microcompactMetadataStr = json.dumps(record.get('microcompactMetadata'), separators=(',', ':')) if isinstance(record.get('microcompactMetadata'), dict) else None
    causeStr = json.dumps(record.get('cause'), separators=(',', ':')) if record.get('cause') is not None else None
    apiErrorStr = json.dumps(record.get('apiError'), separators=(',', ':')) if isinstance(record.get('apiError'), dict) else None
    errorDetails = record.get('errorDetails', U)
    originStr = json.dumps(record.get('origin'), separators=(',', ':')) if record.get('origin') is not None else None
    imagePasteIdsStr = json.dumps(record.get('imagePasteIds'), separators=(',', ':')) if isinstance(record.get('imagePasteIds'), list) else None
    fileAttachmentsStr = json.dumps(record.get('file_attachments'), separators=(',', ':')) if isinstance(record.get('file_attachments'), list) else None
    writtenPathsStr = json.dumps(record.get('writtenPaths'), separators=(',', ':')) if isinstance(record.get('writtenPaths'), list) else None
    commandsStr = json.dumps(record.get('commands'), separators=(',', ':')) if isinstance(record.get('commands'), list) else None

    service_tier = usage.get('service_tier', U)
    budgetTokens = record.get('budgetTokens', U)
    budgetLimit = record.get('budgetLimit', U)
    budgetNudges = record.get('budgetNudges', U)
    messageCount = record.get('messageCount', U)
    ttftMs = record.get('ttftMs', U)
    otps = record.get('otps', U)

    hookDurationMs = record.get('hookDurationMs', U)
    turnDurationMs = record.get('turnDurationMs', U)
    toolDurationMs = record.get('tool_duration_ms') if 'tool_duration_ms' in record else record.get('toolDurationMs', U)
    classifierDurationMs = record.get('classifier_duration_ms') if 'classifier_duration_ms' in record else record.get('classifierDurationMs', U)
    toolCount = record.get('tool_count') if 'tool_count' in record else record.get('toolCount', U)
    classifierCount = record.get('classifier_count') if 'classifier_count' in record else record.get('classifierCount', U)
    configWriteCount = record.get('config_write_count') if 'config_write_count' in record else record.get('configWriteCount', U)

    promptCount = record.get('promptCount', U)
    promptCountAtLastCommit = record.get('promptCountAtLastCommit', U)
    permissionPromptCount = record.get('permissionPromptCount', U)
    permissionPromptCountAtLastCommit = record.get('permissionPromptCountAtLastCommit', U)
    escapeCount = record.get('escapeCount', U)
    escapeCountAtLastCommit = record.get('escapeCountAtLastCommit', U)
    replacedResultsCount = len(record['replacements']) if isinstance(record.get('replacements'), list) else None
    inferenceGeo = usage.get('inference_geo', U)

    userPrompt = None
    assistantText = None

    if msg_type == 'user':
        c = message.get('content')
        if isinstance(c, str): userPrompt = c
        elif isinstance(c, list):
            parts = []
            for item in c:
                t = item.get('type')
                if t == 'text': parts.append(item.get('text', ''))
                elif t == 'image': parts.append('[Image Content]')
                elif t == 'tool_result':
                    tc = item.get('content')
                    pr = '[Tool Error] ' if item.get('is_error') else '[Tool Result] '
                    if isinstance(tc, str): parts.append(f"{pr}{tc}")
                    elif isinstance(tc, list):
                        sub = []
                        for b in tc:
                            if isinstance(b, dict):
                                if b.get('type') == 'text': sub.append(b.get('text', ''))
                                elif b.get('type') == 'image': sub.append('[Image]')
                            else: sub.append(str(b))
                        parts.append(f"{pr}{' '.join(sub)}")
                    else: parts.append(f"{pr}{json.dumps(tc, separators=(',', ':'))}")
            userPrompt = '\n'.join(parts)
    elif msg_type == 'queue-operation':
        op = record.get('operation')
        cnt = record.get('content', '')
        if isinstance(cnt, list):
            cnt = ' '.join(i.get('text', '') for i in cnt if isinstance(i, dict) and i.get('type') == 'text')
        if op in ['remove', 'popAll', 'dequeue', 'enqueue']:
            op_cap = (op[0].upper() + op[1:]) if op else ""
            userPrompt = f"[Queue {op_cap}]"
            if cnt: userPrompt += f": {cnt}"
    elif msg_type == 'api_error' or (msg_type == 'system' and subtype == 'api_error'):
        ev = record.get('error') or {}
        if isinstance(ev, str): em = ev
        elif isinstance(ev, dict):
            ne = ev.get('error')
            if isinstance(ne, dict): em = ne.get('message') or ev.get('message') or json.dumps(ev, separators=(',', ':'))
            else: em = ev.get('message') or json.dumps(ev, separators=(',', ':'))
        else: em = str(ev)
        assistantText = f"[API Error: {em}]"
        if 'request' in record: assistantText += f"\nRequest Details: {json.dumps(record['request'], separators=(',', ':'))}"
    elif msg_type == 'last-prompt':
        userPrompt = f"[Last Prompt: {record.get('lastPrompt', '')}]"
    elif msg_type == 'file-history-snapshot':
        assistantText = f"[File History Snapshot: {record.get('messageId', 'No ID')}]"
        sn = record.get('snapshot', {})
        if 'trackedFileBackups' in sn:
            assistantText += f"\nTracked files: {', '.join(sn['trackedFileBackups'].keys())}"
    elif msg_type == 'progress':
        assistantText = f"[Progress: {hookName} ({hookEvent})]"
        cmd = hookCommand or data.get('commandName')
        if cmd: assistantText += f"\nCommand: {cmd}"
        if data.get('taskDescription'): assistantText += f"\nTask: {data.get('taskDescription')}"
        if data.get('taskType'): assistantText += f" ({data.get('taskType')})"
        pm = data.get('message')
        if pm and isinstance(pm, dict):
            if requestId is U: requestId = pm.get('requestId', U)
            pc = pm.get('content')
            if pc is not None:
                pt = []
                if isinstance(pc, list):
                    for b in pc:
                        if b.get('type') == 'text': pt.append(b.get('text', ''))
                        elif b.get('type') == 'thinking': pt.append(f"<thinking>\n{b.get('thinking', '')}\n</thinking>")
                elif isinstance(pc, str): pt.append(pc)
                if pt: assistantText += '\n' + '\n'.join(pt)
    elif msg_type == 'assistant':
        c = message.get('content')
        if isinstance(c, str): assistantText = c
        elif isinstance(c, list):
            tx = []
            for b in c:
                bt = b.get('type')
                if bt == 'text': tx.append(b.get('text', ''))
                elif bt == 'thinking': tx.append(f"<thinking>\n{b.get('thinking', '')}\n</thinking>")
                elif bt == 'tool_use': tx.append(f"[Tool Use: {b.get('name', 'unknown')}({json.dumps(b.get('input', {}), separators=(',', ':'))})]")
                elif bt == 'image': tx.append('[Image Content]')
            assistantText = '\n'.join(tx) if tx else None
    elif msg_type == 'summary':
        assistantText = record.get('summary', '')
        userPrompt = '[Session Summary Request]'
    elif msg_type == 'system':
        cnt = record.get('content', '')
        if subtype == 'stop_hook_summary':
            errs = record.get('hookErrors', [])
            infs = record.get('hookInfos', [])
            if not errs and isinstance(infs, list):
                for i in infs:
                    if isinstance(i, dict) and i.get('error'): errs.append(i['error'])
            total_dur = None
            if isinstance(infs, list):
                durs = [i.get('durationMs', 0) for i in infs if isinstance(i, dict) and 'durationMs' in i]
                if durs: total_dur = sum(durs)
            parts = [f"Hook Summary: {cnt}"]
            if errs: parts.append(f"Errors: {json.dumps(errs, separators=(',', ':'))}")
            if infs: parts.append(f"Infos: {json.dumps(infs, separators=(',', ':'))}")
            if total_dur is not None: parts.append(f"Hook Total Duration: {total_dur}ms")
            assistantText = '\n'.join(parts)
        elif subtype == 'local_command':
            import re
            m = re.search(r'<command-name>(.*?)</command-name>', cnt)
            un = m.group(1) if m else 'unknown steering'
            userPrompt = f"[User Steering: {un}]"
        elif subtype == 'turn_duration': assistantText = f"[Turn Duration: {record.get('durationMs', 0)}ms]"
        else: assistantText = cnt
    elif msg_type == 'attachment': userPrompt = f"[Attachment: {json.dumps(record.get('message') or record.get('content') or {}, separators=(',', ':'))}]"
    elif msg_type == 'tombstone': assistantText = '[Tombstone: Orphaned message removed]'
    elif msg_type == 'custom-title': userPrompt = f"[Custom Title: {record.get('customTitle', '')}]"
    elif msg_type == 'ai-title': assistantText = f"[AI Title: {record.get('aiTitle', '')}]"
    elif msg_type == 'task-summary': assistantText = f"[Task Summary: {record.get('summary', '')}]"
    elif msg_type == 'tag': userPrompt = f"[Session Tag: {record.get('tag', '')}]"
    elif msg_type == 'agent-name': userPrompt = f"[Agent Name: {record.get('agentName', '')}]"
    elif msg_type == 'agent-color': userPrompt = f"[Agent Color: {record.get('agentColor', '')}]"
    elif msg_type == 'agent-setting': userPrompt = f"[Agent Setting: {record.get('agentSetting', '')}]"
    elif msg_type == 'pr-link': userPrompt = f"[PR Linked: {record.get('prUrl', '')}]"
    elif msg_type == 'attribution-snapshot': assistantText = f"[Attribution Snapshot: {record.get('surface', 'Unknown Surface')}]"
    elif msg_type == 'speculation-accept': assistantText = f"[Speculation Accept: Saved {record.get('timeSavedMs', 0)}ms]"
    elif msg_type == 'mode': userPrompt = f"[Session Mode: {record.get('mode', '')}]"
    elif msg_type == 'worktree-state': userPrompt = f"[Worktree State Update: {json.dumps(record.get('worktreeSession'), separators=(',', ':'))}]"
    elif msg_type == 'content-replacement': assistantText = f"[Content Replacement: {len(record.get('replacements', []))} tool results replaced]"
    elif msg_type == 'marble-origami-commit': assistantText = f"[Origami Commit: {record.get('summary', '')}]"
    elif msg_type == 'marble-origami-snapshot': assistantText = f"[Origami Snapshot: {len(record.get('staged', []))} staged nodes]"

    if userPrompt is None and assistantText is None:
        log_unhandled(record)
        userPrompt = f"[Unmapped Content for Type: {msg_type}]"
        assistantText = f"Raw Data: {json.dumps(record, separators=(',', ':'))}"

    pModel = (message.get('model') if isinstance(message, dict) else None)
    if not pModel: pModel = record.get('model') or record.get('advisorModel') or U

    it, ot, cr = usage.get('input_tokens', 0), usage.get('output_tokens', 0), usage.get('cache_read_input_tokens', 0)
    arc = usage.get('cache_creation')
    if isinstance(arc, dict): cc = arc.get('ephemeral_1h_input_tokens', 0) + arc.get('ephemeral_5m_input_tokens', 0)
    elif isinstance(arc, (int, float)): cc = arc
    else: cc = usage.get('cache_creation_input_tokens', 0)
    totalTokens = it + ot + cr + cc
    costEstimate = calculate_cost(pModel, usage) if pModel is not U else None

    stu_vals = usage.get('server_tool_use', {}) if isinstance(usage.get('server_tool_use'), dict) else {}
    itrs = json.dumps(usage.get('iterations'), separators=(',', ':')) if 'iterations' in usage else None

    cvs199Obj = {
        'raw': record,
        'user_timestamp': user_ts,
        'event_id': eventId,
        'uuid': uuid,
        'cache_creation': cc,
        'total_tokens': totalTokens,
        'cost_estimate': costEstimate,
        'incremental_tokens': incremental_tokens,
        'is_agent': isAgent,
        'agent_type': agentType,
        'agent_description': agentDescription,
        'log_index': logIndex,
        'integration_version': INTEGRATION_VERSION,
        'os_user': OS_USER,
        'agent_id': agentId,
        'tool_use_id': toolUseId or U,
        'tool_use_result': toolUseResultStr,
        'error_obj': errorObjStr,
        'user_prompt': userPrompt,
        'assistant_text': assistantText,
        'project': project,
        'replaced_results_count': replacedResultsCount,
        'prompt_count': promptCount,
        'prompt_count_at_last_commit': promptCountAtLastCommit,
        'permission_prompt_count': permissionPromptCount,
        'permission_prompt_count_at_last_commit': permissionPromptCountAtLastCommit,
        'escape_count': escapeCount,
        'escape_count_at_last_commit': escapeCountAtLastCommit,
        'pr_number': record.get('prNumber', U),
        'pr_repository': record.get('prRepository', U),
        'service_tier': service_tier,
        'iterations': itrs,
        'web_search_requests': stu_vals.get('web_search_requests', U),
        'web_fetch_requests': stu_vals.get('web_fetch_requests', U),
        'first_archived_uuid': record.get('firstArchivedUuid', U),
        'last_archived_uuid': record.get('lastArchivedUuid', U),
        'worktree_branch': (record.get('worktreeSession', {}).get('worktreeBranch', U) if isinstance(record.get('worktreeSession'), dict) else U),
        'original_branch': (record.get('worktreeSession', {}).get('originalBranch', U) if isinstance(record.get('worktreeSession'), dict) else U),
        'original_head_commit': (record.get('worktreeSession', {}).get('originalHeadCommit', U) if isinstance(record.get('worktreeSession'), dict) else U),
        'tmux_session_name': (record.get('worktreeSession', {}).get('tmuxSessionName', U) if isinstance(record.get('worktreeSession'), dict) else U),
        'task_description': data.get('taskDescription', U),
        'task_type': data.get('taskType', U),
        'hook_based': (record.get('worktreeSession', {}).get('hookBased', U) if isinstance(record.get('worktreeSession'), dict) else U),
        'worktree_original_cwd': (record.get('worktreeSession', {}).get('originalCwd', U) if isinstance(record.get('worktreeSession'), dict) else U),
        'worktree_path': (record.get('worktreeSession', {}).get('worktreePath', U) if isinstance(record.get('worktreeSession'), dict) else U),
        'worktree_name': (record.get('worktreeSession', {}).get('worktreeName', U) if isinstance(record.get('worktreeSession'), dict) else U),
        'is_synthetic': isSynthetic,
        'is_visible_in_transcript_only': isVisibleInTranscriptOnly,
        'is_virtual': isVirtual,
        'is_compact_summary': isCompactSummary,
        'is_p50': isP50,
        'advisor_model': advisorModel,
        'upgrade_nudge': upgradeNudge,
        'url': url,
        'priority': priority,
        'hook_label': hookLabel,
        'stop_reason_top': stopReasonTop,
        'research': researchStr,
        'mcp_meta': mcpMetaStr,
        'summarize_metadata': summarizeMetadataStr,
        'compact_metadata': compactMetadataStr,
        'microcompact_metadata': microcompactMetadataStr,
        'cause': causeStr,
        'api_error': apiErrorStr,
        'error_details': errorDetails,
        'origin': originStr,
        'image_paste_ids': imagePasteIdsStr,
        'file_attachments': fileAttachmentsStr,
        'written_paths': writtenPathsStr,
        'commands': commandsStr,
        'budget_tokens': budgetTokens,
        'budget_limit': budgetLimit,
        'budget_nudges': budgetNudges,
        'message_count': messageCount,
        'ttft_ms': ttftMs,
        'otps': otps,
        'hook_duration_ms': hookDurationMs,
        'turn_duration_ms': turnDurationMs,
        'tool_duration_ms': toolDurationMs,
        'classifier_duration_ms': classifierDurationMs,
        'tool_count': toolCount,
        'classifier_count': classifierCount,
        'config_write_count': configWriteCount,
    }

    def filter_u(p): return {k: v for k, v in p.items() if v is not U}
    cvs199Json = json.dumps(filter_u(cvs199Obj), separators=(',', ':'))

    durMs = record.get('durationMs')
    if durMs is None and (msg_type in ['system', 'progress'] or 'durationMs' in record or record.get('totalDurationMs') is not None):
        durMs = record.get('durationMs') or record.get('totalDurationMs')

    inc = incremental_tokens or {}
    payload = {
        'timestamp': current_ms,
        'user_timestamp': user_ts,
        'event_id': eventId,
        'event_type': f"claude_code_{msg_type}",
        'event_source_name': 'claude_code',
        'debug': False,
        'session_id': sessionId,
        'project': project,
        'git_branch': gitBranch,
        'user_prompt': userPrompt,
        'assistant_text': assistantText,
        'stop_reason': message.get('stop_reason') or U,
        'permission_mode': permissionMode,
        'version': version,
        'primary_model': pModel,
        'slug': slug,
        'parent_uuid': parentUuid,
        'cwd': cwd,
        'raw_uuid': rawUuid,
        'raw_message_id': rawMessageId,
        'assistant_msg_id': (message.get('id') if isinstance(message, dict) and msg_type == 'assistant' else U),
        'user_type': userType,
        'subtype': subtype,
        'hook_name': hookName,
        'hook_command': hookCommand,
        'agent_id': agentId,
        'tool_use_id': toolUseId or U,
        'parent_tool_use_id': parentToolUseId,
        'source_tool_assistant_uuid': sourceToolAssistantUuid,
        'source_tool_use_id': sourceToolUseId,
        'entrypoint': entrypoint,
        'last_prompt': lastPrompt,
        'error_obj': errorObjStr,
        'tool_use_result': toolUseResultStr,
        'hook_event': hookEvent,
        'prompt_id': promptId,
        'level': level,
        'ide_diagnostics': ideDiagnosticsStr,
        'request_id': requestId,
        'integration_version': INTEGRATION_VERSION,
        'os_user': OS_USER,
        'agent_type': agentType,
        'agent_description': agentDescription,
        'log_index': logIndex,
        'input_tokens': to_num(it),
        'output_tokens': to_num(ot),
        'total_tokens': to_num(totalTokens),
        'cache_read': to_num(cr),
        'cache_creation': to_num(cc),
        'duration_ms': to_num(durMs),
        'cost_estimate': costEstimate,
        'incremental_input': to_num(inc.get('input', it)),
        'incremental_output': to_num(inc.get('output', ot)),
        'incremental_total': to_num(inc.get('total', totalTokens)),
        'incremental_cost': to_num(inc.get('cost', costEstimate or 0)),
        'has_thinking': any(b.get('type') == 'thinking' for b in message.get('content', []) if isinstance(b, dict)) if isinstance(message.get('content'), list) else False,
        'is_api_error_message': bool(record.get('isApiErrorMessage', False)),
        'is_meta': isMeta,
        'is_sidechain': isSidechain,
        'is_snapshot_update': isSnapshotUpdate,
        'has_output': hasOutput,
        'prevented_continuation': preventedContinuation,
        'is_agent': isAgent,
        'usage_speed': usage.get('speed', U),
        'inference_geo': inferenceGeo,
        'incremental_cache_read': to_num(inc.get('cache_read', cr)),
        'incremental_cache_creation': to_num(inc.get('cache_creation', cc)),
        'custom_title': record.get('customTitle') or U,
        'ai_title': record.get('aiTitle') or U,
        'session_tag': record.get('tag') or U,
        'agent_map_name': record.get('agentName') or U,
        'agent_map_color': record.get('agentColor') or U,
        'agent_setting': record.get('agentSetting') or U,
        'pr_url': record.get('prUrl') or U,
        'attribution_surface': record.get('surface') or U,
        'session_mode': record.get('mode') or U,
        'task_status': taskStatus,
        'worktree_session': (json.dumps(record.get('worktreeSession'), separators=(',', ':')) if record.get('worktreeSession') else U),
        'staged_nodes': (json.dumps(record.get('staged'), separators=(',', ':')) if record.get('staged') is not None else U),
        'origami_summary': (record.get('summary') if msg_type in ['marble-origami-commit', 'task-summary'] else U),
        'worktree_branch': (record.get('worktreeSession', {}).get('worktreeBranch') if isinstance(record.get('worktreeSession'), dict) else U),
        'pr_repository': record.get('prRepository') or U,
        'service_tier': usage.get('service_tier') or U,
        'iterations': json.dumps(usage.get('iterations'), separators=(',', ':')) if 'iterations' in usage else U,
        'first_archived_uuid': record.get('firstArchivedUuid') or U,
        'last_archived_uuid': record.get('lastArchivedUuid') or U,
        'original_branch': (record.get('worktreeSession', {}).get('originalBranch') if isinstance(record.get('worktreeSession'), dict) else U),
        'original_head_commit': (record.get('worktreeSession', {}).get('originalHeadCommit') if isinstance(record.get('worktreeSession'), dict) else U),
        'tmux_session_name': (record.get('worktreeSession', {}).get('tmuxSessionName') if isinstance(record.get('worktreeSession'), dict) else U),
        'task_description': data.get('taskDescription') or U,
        'task_type': data.get('taskType') or U,
        'time_saved_ms': to_num(record.get('timeSavedMs')),
        'replaced_results_count': to_num(replacedResultsCount),
        'logical_parent_uuid': logicalParentUuid,
        'team_name': teamName,
        'stop_sequence': (message.get('stop_sequence') if isinstance(message, dict) else U),
        'leaf_uuid': record.get('leafUuid') or U,
        'pr_number': to_num(record.get('prNumber') if record.get('prNumber') is not None else U),
        'file_states': (json.dumps(record.get('fileStates'), separators=(',', ':')) if record.get('fileStates') is not None else U),
        'collapse_id': record.get('collapseId') or U,
        'summary_uuid': record.get('summaryUuid') or U,
        'summary_content': record.get('summaryContent') or U,
        'armed': record.get('armed'),
        'last_spawn_tokens': to_num(record.get('lastSpawnTokens')),
        'status_message': data.get('statusMessage') or U,
        'hook_specific_output': (json.dumps(data.get('hookSpecificOutput'), separators=(',', ':')) if 'hookSpecificOutput' in data else U),
        'prompt_count': to_num(promptCount),
        'prompt_count_at_last_commit': to_num(promptCountAtLastCommit),
        'permission_prompt_count': to_num(permissionPromptCount),
        'permission_prompt_count_at_last_commit': to_num(permissionPromptCountAtLastCommit),
        'escape_count': to_num(escapeCount),
        'escape_count_at_last_commit': to_num(escapeCountAtLastCommit),
        'web_search_requests': to_num(stu_vals.get('web_search_requests', U)),
        'web_fetch_requests': to_num(stu_vals.get('web_fetch_requests', U)),
        'hook_based': (record.get('worktreeSession', {}).get('hookBased') if isinstance(record.get('worktreeSession'), dict) else U),
        'is_synthetic': isSynthetic,
        'is_visible_in_transcript_only': isVisibleInTranscriptOnly,
        'is_virtual': isVirtual,
        'is_compact_summary': isCompactSummary,
        'is_p50': isP50,
        'advisor_model': advisorModel,
        'upgrade_nudge': upgradeNudge,
        'url': url,
        'priority': priority,
        'hook_label': hookLabel,
        'stop_reason_top': stopReasonTop,
        'research': researchStr or U,
        'mcp_meta': mcpMetaStr or U,
        'summarize_metadata': summarizeMetadataStr or U,
        'compact_metadata': compactMetadataStr or U,
        'microcompact_metadata': microcompactMetadataStr or U,
        'cause': causeStr or U,
        'api_error': apiErrorStr or U,
        'error_details': errorDetails,
        'origin': originStr or U,
        'image_paste_ids': imagePasteIdsStr or U,
        'file_attachments': fileAttachmentsStr or U,
        'written_paths': writtenPathsStr or U,
        'commands': commandsStr or U,
        'budget_tokens': to_num(budgetTokens),
        'budget_limit': to_num(budgetLimit),
        'budget_nudges': to_num(budgetNudges),
        'message_count': to_num(messageCount),
        'ttft_ms': to_num(ttftMs),
        'otps': to_num(otps),
        'hook_duration_ms': to_num(hookDurationMs),
        'turn_duration_ms': to_num(turnDurationMs),
        'tool_duration_ms': to_num(toolDurationMs),
        'classifier_duration_ms': to_num(classifierDurationMs),
        'tool_count': to_num(toolCount),
        'classifier_count': to_num(classifierCount),
        'config_write_count': to_num(configWriteCount),
        'worktree_original_cwd': (record.get('worktreeSession', {}).get('originalCwd') if isinstance(record.get('worktreeSession'), dict) else U),
        'worktree_path': (record.get('worktreeSession', {}).get('worktreePath') if isinstance(record.get('worktreeSession'), dict) else U),
        'worktree_name': (record.get('worktreeSession', {}).get('worktreeName') if isinstance(record.get('worktreeSession'), dict) else U),
        'cvs199': cvs199Json,
        'cvs200': 'ClaudeCodeHook',
    }

    return {k: v for k, v in payload.items() if v is not None and v is not U}
