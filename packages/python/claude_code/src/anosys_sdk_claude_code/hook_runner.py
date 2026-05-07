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
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from anosys_sdk_claude_code.mapper import transform_record

ENDPOINT_URL = os.environ.get('ANOSYS_HOOK_ENDPOINT_URL', 'https://www.anosys.ai')
API_KEY = os.environ.get('ANOSYS_HOOK_API_KEY', '')
DRY_RUN = os.environ.get('ANOSYS_HOOK_DRY_RUN', 'false').lower() == 'true'
EXPLICIT_TRANSCRIPT = os.environ.get('ANOSYS_HOOK_TRANSCRIPT', '')

STATE_DIR = Path.home() / '.claude' / 'state'
STATE_FILE = STATE_DIR / 'hook_state.json'
PENDING_RECORDS_FILE = STATE_DIR / 'pending_records.jsonl'
LOG_FILE = STATE_DIR / 'hook.log'

STATE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger('anosys_claude_hook')

_stderr = logging.StreamHandler(sys.stderr)
_stderr.setLevel(logging.INFO)
_stderr.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
log.addHandler(_stderr)


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
    projects_dir = Path.home() / '.claude' / 'projects'
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
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding='utf-8')


def load_pending_records() -> List[dict]:
    if not PENDING_RECORDS_FILE.exists():
        return []
    records = []
    try:
        with open(PENDING_RECORDS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
    except Exception as e:
        log.error("Failed to load pending records: %s", e)
    return records


def save_pending_records(records: List[dict], overwrite: bool = False):
    try:
        mode = 'w' if overwrite else 'a'
        with open(PENDING_RECORDS_FILE, mode, encoding='utf-8') as f:
            for r in records:
                f.write(json.dumps(r, separators=(',', ':')) + '\n')
        log.info("Saved %d records to pending storage (%s)", len(records), "overwrite" if overwrite else "append")
    except Exception as e:
        log.error("Failed to save pending records: %s", e)


def clear_pending_records():
    try:
        if PENDING_RECORDS_FILE.exists():
            PENDING_RECORDS_FILE.unlink()
            log.info("Cleared pending records.")
    except Exception as e:
        log.error("Failed to clear pending records: %s", e)


async def post_records_batch(payloads: List[dict]) -> List[dict]:
    import requests
    if not payloads:
        return []

    headers = {'Content-Type': 'application/json'}
    if API_KEY:
        headers['Authorization'] = f"Bearer {API_KEY}"

    failed_records = []
    batch_size = 100

    for i in range(0, len(payloads), batch_size):
        chunk = payloads[i:i + batch_size]
        if DRY_RUN:
            log.info("[DRY RUN] Would POST chunk of %d records", len(chunk))
            continue
        try:
            resp = requests.post(ENDPOINT_URL, json=chunk, headers=headers, timeout=15)
            resp.raise_for_status()
            log.info("Batch POST success — sent %d records", len(chunk))
        except Exception as e:
            log.error("Batch POST failed — trying to send %d records: %s", len(chunk), e)
            failed_records.extend(chunk)
    return failed_records


async def main():
    import asyncio
    await asyncio.sleep(0.5)

    log.info("="*60)
    log.info("anosys-claude-code run invoked at %s", time.strftime('%Y-%m-%d %H:%M:%S'))

    pending = load_pending_records()
    if pending:
        log.info("Found %d pending records. Attempting resend...", len(pending))
        failed_pending = await post_records_batch(pending)
        if not failed_pending:
            clear_pending_records()
        else:
            log.warning("%d records still failed after resend. Updating storage.", len(failed_pending))
            save_pending_records(failed_pending, overwrite=True)

    stdin_ctx = get_stdin_context()
    if stdin_ctx:
        log.info("Received context from stdin: %s", json.dumps(stdin_ctx))

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
    log.info("Targeting transcript: %s (Session: %s)", primary_transcript.path, current_sid)

    state = {} if DRY_RUN else load_state()
    session_state = state.get(current_sid, {})
    full_scan_done = session_state.get('full_scan_done', False)

    if not full_scan_done:
        log.info("First run for session %s. Performing global scan...", current_sid)
        transcripts = find_all_transcripts()
    else:
        all_known = find_all_transcripts()
        transcripts = [primary_transcript] + [t for t in all_known if t.is_agent and t.session_id == current_sid]

    log.info("Processing %d transcript(s) (%d agent(s)).", len(transcripts), sum(1 for t in transcripts if t.is_agent))

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
            log.error("Failed to read transcript %s: %s", transcript.path, e)
            continue

        all_lines = content.strip().split('\n')
        if not all_lines or not all_lines[0]:
            log.debug("Transcript %s is empty.", sid)
            continue

        total_lines = len(all_lines)
        log.info("Processing %s: %d total lines, previously saw %d", state_key, total_lines, last_line)

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
                log.error("Failed to map record in %s at %d: %s", sid, i, e)

        if session_mapped:
            all_mapped_payloads.extend(session_mapped)
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

    pskey = primary_transcript.state_key
    if pskey in state:
        state[pskey]['full_scan_done'] = True
    else:
        state[pskey] = {'full_scan_done': True}

    if not DRY_RUN:
        save_state(state)

    if not all_mapped_payloads:
        log.info("No records to send.")
        return

    failed = await post_records_batch(all_mapped_payloads)
    if failed:
        log.error("%d failed to POST. Saving to pending.", len(failed))
        save_pending_records(failed)
    else:
        log.info("Sent %d records successfully.", len(all_mapped_payloads))
