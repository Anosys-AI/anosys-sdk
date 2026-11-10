"""
Claude Code "Stop" hook runner.

Reads the latest JSONL transcript, incrementally processes new messages,
maps them through mapper.transform_record(), and POSTs them as a batch
to the configured endpoint.

Configuration (env vars):
  ANOSYS_HOOK_ENDPOINT_URL  — Target URL to POST records to
  ANOSYS_HOOK_API_KEY       — Optional Bearer token for the endpoint
  ANOSYS_HOOK_DRY_RUN       — Set to "true" to log payloads instead of POSTing
  ANOSYS_HOOK_TRANSCRIPT    — Optional: explicit .jsonl path (skips auto-detection)
"""

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from anosys_sdk_core.encryption import encrypt_payload
from anosys_sdk_core.hook_cli import setup_hook_logging
from anosys_sdk_core.privacy import FULL, OFF, effective_level, filter_fields
from anosys_sdk_core.redaction import scrub_secrets
from anosys_sdk_core.transport import PendingQueue, deliver, is_paused

from anosys_sdk_claude_code.mapper import METADATA_FIELDS, UNHANDLED_COUNTS, transform_record

INGESTION_URL = os.environ.get("ANOSYS_HOOK_ENDPOINT_URL", "https://api.anosys.ai/ingestion")
API_KEY = os.environ.get("ANOSYS_HOOK_APIKEY", "") or os.environ.get("ANOSYS_HOOK_API_KEY", "")
DRY_RUN = os.environ.get('ANOSYS_HOOK_DRY_RUN', 'false').lower() == 'true'
EXPLICIT_TRANSCRIPT = os.environ.get('ANOSYS_HOOK_TRANSCRIPT', '')

STATE_DIR = Path.home() / '.claude' / 'state'
STATE_FILE = STATE_DIR / 'hook_state.json'
PENDING_RECORDS_FILE = STATE_DIR / 'pending_records.jsonl'
PAUSE_FILE = STATE_DIR / 'anosys_paused.json'
LOG_FILE = STATE_DIR / 'hook.log'

# The hook log records ids, sizes and status codes only, never prompts or payloads.
log = setup_hook_logging(LOG_FILE, 'anosys_claude_hook')

# Content fields scrubbed for secrets before sending at `full`
CONTENT_FIELDS = (
    'user_prompt', 'assistant_text', 'last_prompt', 'tool_use_result', 'commands',
    'written_paths', 'file_states', 'summary_content', 'task_description', 'cvs199',
    'cvs4', 'cvs5', 'cvs24', 'cvs26',
)


@dataclass
class TranscriptInfo:
    path: Path
    state_key: str
    session_id: str
    is_agent: bool
    agent_id: Optional[str] = None
    agent_type: Optional[str] = None
    agent_description: Optional[str] = None


def _load_agent_meta(meta_path: Path) -> dict:
    try:
        if meta_path.exists():
            return json.loads(meta_path.read_text(encoding='utf-8'))
    except Exception:
        pass
    return {}


def find_all_transcripts() -> List[TranscriptInfo]:
    """Every transcript on disk; used only to locate the current session's file."""
    try:
        return _scan_transcripts(Path.home() / '.claude' / 'projects')
    except OSError as e:  # unreadable or vanished folder: no transcripts, never a crash
        log.warning("Could not list Claude Code transcripts (%s)", type(e).__name__)
        return []


def _scan_transcripts(projects_dir: Path) -> List[TranscriptInfo]:
    if not projects_dir.exists():
        return []

    results = []
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue

        for f in project_dir.glob('*.jsonl'):
            session_id = f.stem
            results.append(TranscriptInfo(
                path=f,
                state_key=session_id,
                session_id=session_id,
                is_agent=False
            ))

        for session_subdir in project_dir.iterdir():
            if not session_subdir.is_dir():
                continue
            subagents_dir = session_subdir / 'subagents'
            if subagents_dir.exists() and subagents_dir.is_dir():
                session_id = session_subdir.name
                for af in subagents_dir.glob('*.jsonl'):
                    agent_id = af.stem
                    meta_path = af.with_suffix('.meta.json')
                    meta = _load_agent_meta(meta_path)
                    state_key = f"{session_id}:subagent:{agent_id}"
                    results.append(TranscriptInfo(
                        path=af,
                        state_key=state_key,
                        session_id=session_id,
                        is_agent=True,
                        agent_id=agent_id,
                        agent_type=meta.get('agentType'),
                        agent_description=meta.get('description')
                    ))
    return results


def find_latest_transcript() -> Optional[TranscriptInfo]:
    transcripts = find_all_transcripts()
    regular = [t for t in transcripts if not t.is_agent]
    if not regular:
        return None
    return max(regular, key=lambda t: t.path.stat().st_mtime)


def get_stdin_context() -> Optional[dict]:
    import select
    if not select.select([sys.stdin], [], [], 0.1)[0]:
        return None
    try:
        data = sys.stdin.read()
        if not data.strip():
            return None
        return json.loads(data)
    except Exception:
        return None


def load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    except Exception:
        pass
    return {}


def save_state(state: dict):
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding='utf-8')
    except OSError as e:
        log.warning("Could not save hook state (%s)", type(e).__name__)


def session_transcripts(primary: 'TranscriptInfo') -> List['TranscriptInfo']:
    """The current session's transcript and its subagents. Never other sessions."""
    results = [primary]
    subagents_dir = primary.path.with_suffix('') / 'subagents'
    if subagents_dir.is_dir():
        for af in sorted(subagents_dir.glob('*.jsonl')):
            meta = _load_agent_meta(af.with_suffix('.meta.json'))
            results.append(TranscriptInfo(
                path=af,
                state_key=f"{primary.session_id}:subagent:{af.stem}",
                session_id=primary.session_id,
                is_agent=True,
                agent_id=af.stem,
                agent_type=meta.get('agentType'),
                agent_description=meta.get('description'),
            ))
    return results


def prepare_record(mapped: dict, level: str) -> dict:
    """Apply the collection level, scrub secrets at `full`, then encrypt."""
    record = filter_fields(mapped, level, METADATA_FIELDS)
    if level == FULL:
        for field in CONTENT_FIELDS:
            if record.get(field) is not None:
                record[field] = scrub_secrets(record[field])
    return encrypt_payload(record)


def send(records: List[dict]) -> int:
    """Deliver records (and queued retries) within the size limit. Returns the number accepted."""
    if DRY_RUN:
        log.info("[DRY RUN] Would send %d record(s)", len(records))
        return len(records)
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["anosys-apikey"] = API_KEY
    return deliver(INGESTION_URL, records, PendingQueue(PENDING_RECORDS_FILE), PAUSE_FILE, headers=headers)


async def main():
    import asyncio
    await asyncio.sleep(0.5)

    level, source = effective_level()
    if level == OFF:
        log.info("Collection is off (%s); nothing sent", source)
        return
    if is_paused(PAUSE_FILE):
        log.info("Collection paused after an authorization error; nothing sent")
        return

    stdin_ctx = get_stdin_context()

    provided_path = EXPLICIT_TRANSCRIPT
    if not provided_path and stdin_ctx:
        provided_path = stdin_ctx.get('transcriptPath') or stdin_ctx.get('transcript_path') or ''
        if not provided_path:
            sid = stdin_ctx.get('sessionId') or stdin_ctx.get('session_id')
            if sid:
                for t in find_all_transcripts():
                    if t.session_id == sid and not t.is_agent:
                        provided_path = str(t.path)
                        break

    if provided_path:
        p = Path(provided_path)
        sid = p.stem
        primary_transcript = TranscriptInfo(path=p, state_key=sid, session_id=sid, is_agent=False)
    else:
        primary_transcript = find_latest_transcript()

    if not primary_transcript:
        log.warning("No transcript found to process.")
        return

    current_sid = primary_transcript.session_id
    state = {} if DRY_RUN else load_state()

    # Only this session and its subagents: past sessions are never uploaded
    transcripts = session_transcripts(primary_transcript)
    log.info("Session %s at '%s' (%s): %d transcript(s)", current_sid, level, source, len(transcripts))

    all_mapped_payloads = []
    session_updates = []

    for transcript in transcripts:
        state_key = transcript.state_key
        sid = transcript.session_id
        t_state = state.get(state_key, {})
        last_line = t_state.get('last_line', 0)
        last_uuid = t_state.get('last_message_uuid')

        try:
            content = transcript.path.read_text(encoding='utf-8')
        except Exception as e:
            log.error("Failed to read transcript %s: %s", transcript.state_key, type(e).__name__)
            continue

        all_lines = content.strip().split('\n')
        if not all_lines or not all_lines[0]:
            continue

        total_lines = len(all_lines)

        parsed = []
        for line in all_lines:
            line = line.strip()
            if not line:
                parsed.append(None)
                continue
            try:
                msg = json.loads(line)
                uuid = msg.get('uuid') or msg.get('messageId') or msg.get('id')
                parsed.append((msg, uuid))
            except Exception:
                parsed.append(None)

        if last_line > 0 and last_uuid:
            expected_prev = last_line - 1
            matches = False
            if expected_prev < total_lines:
                item = parsed[expected_prev]
                if item and item[1] == last_uuid:
                    matches = True

            if not matches:
                found_idx = -1
                for i in range(total_lines - 1, -1, -1):
                    item = parsed[i]
                    if item and item[1] == last_uuid:
                        found_idx = i
                        break
                last_line = found_idx + 1 if found_idx != -1 else 0

        if last_line >= total_lines:
            continue

        session_mapped = []
        max_tokens_by_id: Dict[str, Dict[str, float]] = {}
        file_mtime = transcript.path.stat().st_mtime * 1000
        current_context: Dict[str, Any] = {
            'sessionId': sid, 'cwd': None, 'gitBranch': None, 'version': None, 'slug': None,
            'permissionMode': None, 'userType': None, 'is_agent': transcript.is_agent,
            'agent_id': transcript.agent_id, 'agent_type': transcript.agent_type,
            'agent_description': transcript.agent_description, 'file_mtime': file_mtime,
            'last_timestamp': None
        }

        for i in range(last_line, total_lines):
            item = parsed[i]
            if not item:
                continue
            msg, uuid = item
            for f in ['cwd', 'sessionId', 'gitBranch', 'version', 'slug', 'permissionMode', 'userType']:
                if msg.get(f):
                    current_context[f] = msg[f]
            if msg.get('timestamp'):
                current_context['last_timestamp'] = msg['timestamp']

            incremental = None
            if msg.get('type') == 'assistant' and isinstance(msg.get('message'), dict):
                msg_id = msg['message'].get('id')
                if msg_id:
                    usage = msg['message'].get('usage', {})
                    c_in = float(usage.get('input_tokens', 0))
                    c_out = float(usage.get('output_tokens', 0))
                    c_read = float(usage.get('cache_read_input_tokens', 0))
                    cc_raw = usage.get('cache_creation')
                    if isinstance(cc_raw, dict):
                        c_create = float(cc_raw.get('ephemeral_1h_input_tokens', 0) + cc_raw.get('ephemeral_5m_input_tokens', 0))
                    elif isinstance(cc_raw, (int, float)):
                        c_create = float(cc_raw)
                    else:
                        c_create = float(usage.get('cache_creation_input_tokens', 0))

                    prev = max_tokens_by_id.get(msg_id, {'input': 0.0, 'output': 0.0, 'cache_read': 0.0, 'cache_creation': 0.0})
                    delta_in = c_in - prev['input']
                    delta_out = c_out - prev['output']
                    delta_read = c_read - prev['cache_read']
                    delta_create = c_create - prev['cache_creation']
                    max_tokens_by_id[msg_id] = {
                        'input': max(prev['input'], c_in),
                        'output': max(prev['output'], c_out),
                        'cache_read': max(prev['cache_read'], c_read),
                        'cache_creation': max(prev['cache_creation'], c_create)
                    }
                    incremental = {
                        'input': delta_in, 'output': delta_out,
                        'cache_read': delta_read, 'cache_creation': delta_create,
                        'total': delta_in + delta_out + delta_read + delta_create
                    }

            try:
                current_context['log_index'] = i
                mapped = transform_record(msg, incremental, current_context)
                session_mapped.append(mapped)
            except Exception as e:
                log.error("Failed to map record in %s at %d: %s", sid, i, type(e).__name__)

        if session_mapped:
            all_mapped_payloads.extend(r for r in (prepare_record(m, level) for m in session_mapped) if r)
            f_uuid = parsed[total_lines-1][1] if parsed[total_lines-1] else None
            session_updates.append((state_key, {
                'last_line': total_lines,
                'last_message_uuid': f_uuid,
                'last_run': time.strftime('%Y-%m-%dT%H:%M:%S'),
                'records_sent_total': t_state.get('records_sent_total', 0) + len(session_mapped),
                'is_agent': transcript.is_agent
            }))

    for skey, up in session_updates:
        s = state.get(skey, {})
        s.update(up)
        state[skey] = s

    if not DRY_RUN:
        save_state(state)
    if UNHANDLED_COUNTS:
        log.info("Unrecognized record types (counted, not stored): %s", UNHANDLED_COUNTS)

    # Also flushes queued retries; failed records go to the bounded queue
    sent = send(all_mapped_payloads)
    log.info("Session %s: %d record(s) mapped, %d accepted", current_sid, len(all_mapped_payloads), sent)
