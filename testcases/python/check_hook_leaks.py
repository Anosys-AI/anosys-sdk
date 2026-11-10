"""
Hook leak check (Python): Claude Code, Codex and Antigravity mappers + prepare_record.

Every field a mapper reads is filled with a marker (LEAK_<field>), for every record
type and both column layouts. Then:

- metadata: every output column must be in the package's METADATA_FIELDS, and no
  content marker (prompt, answer, thinking, tool input/output, commands, paths) may appear
- full + encryption key: every column outside METADATA_FIELDS must be encrypted
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import check, finish, is_encrypted, isolated_home  # noqa: E402

isolated_home()
ROOT = Path(__file__).resolve().parents[2] / "packages" / "python"

from anosys_sdk_core.privacy import FULL, METADATA  # noqa: E402

CONTENT_MARKERS = re.compile(
    r"LEAK_(text|cmd|think|toolres|msg_content|user_prompt|assistant_output|user_input|final_response"
    r"|command|path|summary|content|description|error_message|message)\b")
ALWAYS = {"cvs198", "cvs200"}


def keys_read(source: Path) -> set:
    return set(re.findall(r"\.get\(['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]", source.read_text()))


def fill(keys, prefix=""):
    return {k: f"LEAK_{prefix}{k}" for k in keys}


def verify(tag, out_meta, out_full, metadata_fields):
    extra = set(out_meta) - set(metadata_fields) - ALWAYS
    check(f"{tag}: metadata sends only metadata columns", not extra, f"extra columns {sorted(extra)[:8]}")
    blob = json.dumps(out_meta)
    found = sorted(set(m.group(0) for m in CONTENT_MARKERS.finditer(blob)))
    check(f"{tag}: metadata carries no content", not found, f"markers {found[:8]}")
    clear = sorted(k for k, v in out_full.items()
                   if k not in metadata_fields and k not in ALWAYS and isinstance(v, str) and not is_encrypted(v))
    check(f"{tag}: full + key encrypts every content column", not clear, f"plaintext {clear[:8]}")


def with_key(fn):
    os.environ["ANOSYS_ENCRYPTION_KEY"] = "tc-pass"
    os.environ["ANOSYS_ENCRYPTION_SALT"] = "tc-salt"
    try:
        return fn()
    finally:
        os.environ.pop("ANOSYS_ENCRYPTION_KEY")
        os.environ.pop("ANOSYS_ENCRYPTION_SALT")


# ── Claude Code ──────────────────────────────────────────────────────────────
from anosys_sdk_claude_code import hook_runner as cc  # noqa: E402
from anosys_sdk_claude_code.mapper import METADATA_FIELDS as CC_FIELDS, transform_record  # noqa: E402

cc_keys = keys_read(ROOT / "claude_code/src/anosys_sdk_claude_code/mapper.py")
CC_TYPES = ["user", "assistant", "system", "summary", "attachment", "progress", "file-history-snapshot",
            "marble-origami-commit", "task-summary", "custom-title", "ai-title", "last-prompt", "pr-link",
            "worktree-state", "queue-operation", "agent-name", "tag", "mode"]


def cc_record(kind):
    rec = fill(cc_keys)
    rec.update(type=kind, timestamp="2026-11-10T00:00:00Z")
    msg = fill(cc_keys, "msg_")
    msg.update(model="claude-x", usage={"input_tokens": 1, "output_tokens": 1}, content=[
        {"type": "text", "text": "LEAK_text"},
        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "LEAK_cmd"}},
        {"type": "thinking", "thinking": "LEAK_think"},
        {"type": "tool_result", "tool_use_id": "t1", "content": "LEAK_toolres"}])
    rec["message"] = msg
    for k in ("data", "snapshot", "worktreeSession", "agentMap", "toolUseResult", "compactMetadata",
              "attachment", "hookSpecificOutput"):
        rec[k] = fill(cc_keys, k + "_")
    return rec


for layout in ("true", "false"):
    os.environ["ANOSYS_CLAUDE_PIXEL"] = layout
    for kind in CC_TYPES:
        mapped = transform_record(cc_record(kind), None, {"sessionId": "s"})
        verify(f"py claude-code layout={layout} type={kind}", cc.prepare_record(mapped, METADATA),
               with_key(lambda: cc.prepare_record(transform_record(cc_record(kind), None, {"sessionId": "s"}), FULL)),
               CC_FIELDS)
os.environ.pop("ANOSYS_CLAUDE_PIXEL")


# ── Codex and Antigravity (turn based) ──────────────────────────────────────
def turn(keys):
    t = fill(keys)
    t.update(start_ms=1000, end_ms=2000, duration_ms=1000,
             tokens={"input_tokens": 1, "output_tokens": 1}, commands=["LEAK_command"], written_paths=["LEAK_path"])
    step = fill(keys, "ts_")
    step.update(start_ms=1, end_ms=2, duration_ms=1)
    t["tool_steps"] = [step]
    t["tool_calls"] = [fill(keys, "tc_")]
    t["errors"] = [fill(keys, "err_")]
    return t


from anosys_sdk_codex import hook_runner as cx  # noqa: E402
from anosys_sdk_codex.mapper import METADATA_FIELDS as CX_FIELDS, transform_codex_turn  # noqa: E402
from anosys_sdk_antigravity import hook_runner as ag  # noqa: E402
from anosys_sdk_antigravity.mapper import METADATA_FIELDS as AG_FIELDS, transform_antigravity_turn  # noqa: E402

cx_keys = keys_read(ROOT / "codex/src/anosys_sdk_codex/mapper.py")
ag_keys = keys_read(ROOT / "antigravity/src/anosys_sdk_antigravity/mapper.py")
for layout in ("cc", "generic"):
    os.environ["ANOSYS_PIXEL_TYPE"] = layout
    verify(f"py codex layout={layout}",
           cx.prepare_record(transform_codex_turn(turn(cx_keys), "s", "t"), METADATA),
           with_key(lambda: cx.prepare_record(transform_codex_turn(turn(cx_keys), "s", "t"), FULL)), CX_FIELDS)
    verify(f"py antigravity layout={layout}",
           ag.prepare_record(transform_antigravity_turn(turn(ag_keys), "s", "t", fill(ag_keys, "meta_")), METADATA),
           with_key(lambda: ag.prepare_record(
               transform_antigravity_turn(turn(ag_keys), "s", "t", fill(ag_keys, "meta_")), FULL)), AG_FIELDS)
os.environ.pop("ANOSYS_PIXEL_TYPE")

finish()
