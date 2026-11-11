"""
End-to-end hook check: runs the real Claude Code, Codex and Antigravity hooks
(Python and JS) as processes against the local fake ingestion server, in a
throwaway HOME, and checks what arrives.

Needs FAKE_URL (http://127.0.0.1:<port>) and FAKE_OUT (the server's output dir);
run_all.sh starts the server and sets both.
"""

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import check, finish, ingested  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "packages" / "js"
FAKE_URL, FAKE_OUT = os.environ["FAKE_URL"], os.environ["FAKE_OUT"]
POLICY = None


def new_home():
    home = Path(tempfile.mkdtemp(prefix="anosys-e2e-"))
    env = {k: v for k, v in os.environ.items() if not k.startswith("ANOSYS_") and k not in ("CODEX_HOME", "REDACTION")}
    env.update(HOME=str(home), USERPROFILE=str(home), ANOSYS_CONSENT_FILE=str(home / ".anosys" / "consent.json"))
    return home, env


def give_consent(env, level):
    code = ("from anosys_sdk_core.privacy import write_consent, POLICY_VERSION;"
            f"write_consent('{level}', method='testcases', accept_policy=POLICY_VERSION if '{level}'=='full' else None)")
    subprocess.run([sys.executable, "-c", code], env=env, check=True)


def run(cmd, env, stdin=""):
    return subprocess.run(cmd, env=env, input=stdin, capture_output=True, text=True, timeout=120)


def project(level=None):
    d = Path(tempfile.mkdtemp(prefix="anosys-proj-"))
    if level:
        (d / ".anosys").write_text(f"level={level}\n")
    return d


def texts(records):
    return json.dumps(records)


# ── Claude Code: content at full, nothing while off, no backfill, project ceiling ──
def cc_line(kind, text, sid, cwd):
    base = {"type": kind, "uuid": str(uuid.uuid4()), "sessionId": sid, "timestamp": "2026-11-10T10:00:00Z", "cwd": str(cwd)}
    if kind == "user":
        base["message"] = {"role": "user", "content": text}
    else:
        base["message"] = {"id": "m" + base["uuid"][:6], "model": "claude-sonnet-5-5", "role": "assistant",
                           "content": [{"type": "text", "text": text}], "usage": {"input_tokens": 3, "output_tokens": 2}}
    return json.dumps(base)


for impl, cmd in (("py", [sys.executable, "-m", "anosys_sdk_claude_code.cli", "run"]),
                  ("js", ["node", str(JS / "claude-code/src/cli.js"), "run"])):
    home, env = new_home()
    tag = f"cc-{impl}-{uuid.uuid4().hex[:6]}"
    env.update(ANOSYS_HOOK_ENDPOINT_URL=f"{FAKE_URL}/{tag}", ANOSYS_HOOK_APIKEY="user-key")
    give_consent(env, "full")
    cwd = project()
    sid = str(uuid.uuid4())
    tdir = home / ".claude" / "projects" / "app"
    tdir.mkdir(parents=True)
    transcript = tdir / f"{sid}.jsonl"
    stdin = json.dumps({"session_id": sid, "transcript_path": str(transcript), "cwd": str(cwd)})

    def append(*lines):
        with open(transcript, "a") as fh:
            fh.write("\n".join(lines) + "\n")

    append(cc_line("user", "LEAK_CC_FIRST", sid, cwd), cc_line("assistant", "answer one", sid, cwd))
    r = run(cmd, env, stdin)
    first = ingested(FAKE_OUT, tag)
    check(f"{impl} claude-code: full sends the turn with content", "LEAK_CC_FIRST" in texts(first),
          f"{len(first)} records; stderr={r.stderr[-200:]}")
    check(f"{impl} claude-code: records say full;<policy>", all(str(x.get("cvs198", "")).startswith("full;") for x in first) and first)

    append(cc_line("user", "LEAK_CC_WHILE_OFF", sid, cwd))
    env_off = dict(env, ANOSYS_DISABLE="1")
    run(cmd, env_off, stdin)
    append(cc_line("user", "LEAK_CC_AFTER", sid, cwd))
    run(cmd, env, stdin)
    after = ingested(FAKE_OUT, tag)[len(first):]
    check(f"{impl} claude-code: turns written while off are never sent", "LEAK_CC_WHILE_OFF" not in texts(ingested(FAKE_OUT, tag)))
    check(f"{impl} claude-code: collection resumes after off", "LEAK_CC_AFTER" in texts(after))
    check(f"{impl} claude-code: no turn is sent twice", texts(ingested(FAKE_OUT, tag)).count("LEAK_CC_FIRST") == texts(first).count("LEAK_CC_FIRST"))

    off_dir = project("off")
    stdin_off = json.dumps({"session_id": sid, "transcript_path": str(transcript), "cwd": str(off_dir)})
    before = len(ingested(FAKE_OUT, tag))
    append(cc_line("user", "LEAK_CC_PROJECT_OFF", sid, off_dir))
    run(cmd, env, stdin_off)
    check(f"{impl} claude-code: project .anosys=off sends nothing", "LEAK_CC_PROJECT_OFF" not in texts(ingested(FAKE_OUT, tag)[before:]))

    meta_dir = project("metadata")
    stdin_meta = json.dumps({"session_id": sid, "transcript_path": str(transcript), "cwd": str(meta_dir)})
    before = len(ingested(FAKE_OUT, tag))
    append(cc_line("user", "LEAK_CC_PROJECT_META", sid, meta_dir))
    run(cmd, env, stdin_meta)
    new = ingested(FAKE_OUT, tag)[before:]
    check(f"{impl} claude-code: project .anosys=metadata sends metadata only",
          new and "LEAK_CC_PROJECT_META" not in texts(new) and all(str(x.get("cvs198", "")).startswith("metadata") for x in new),
          f"{len(new)} records")


# ── Codex: notify event, content at full, project ceiling ───────────────────
for impl, cmd in (("py", [sys.executable, "-m", "anosys_sdk_codex.cli", "run"]),
                  ("js", ["node", str(JS / "codex/src/cli.js"), "run"])):
    home, env = new_home()
    tag = f"cx-{impl}-{uuid.uuid4().hex[:6]}"
    env.update(ANOSYS_HOOK_ENDPOINT_URL=f"{FAKE_URL}/{tag}", ANOSYS_HOOK_APIKEY="user-key", CODEX_HOME=str(home / ".codex"))
    give_consent(env, "full")

    def event(text, cwd):
        return json.dumps({"type": "agent-turn-complete", "thread-id": "th-" + tag, "turn-id": str(uuid.uuid4()),
                           "cwd": str(cwd), "input-messages": [text], "last-assistant-message": "answer " + text})

    run(cmd + [event("LEAK_CX_FULL", project())], env)
    run(cmd + [event("LEAK_CX_OFF", project("off"))], env)
    run(cmd + [event("LEAK_CX_META", project("metadata"))], env)
    got = ingested(FAKE_OUT, tag)
    check(f"{impl} codex: full sends the turn with content", "LEAK_CX_FULL" in texts(got), f"{len(got)} records")
    check(f"{impl} codex: project .anosys=off sends nothing", "LEAK_CX_OFF" not in texts(got))
    meta = [x for x in got if str(x.get("cvs198", "")).startswith("metadata")]
    check(f"{impl} codex: project .anosys=metadata sends metadata only", meta and "LEAK_CX_META" not in texts(got), f"{len(meta)} metadata records")


# ── Antigravity: runs with a workspace file, ceiling applies, user's key wins ──
AG_TURN = [
    {"step_index": 1, "type": "USER_INPUT", "source": "USER_EXPLICIT", "created_at": "2026-11-10T10:00:00Z",
     "content": "<USER_REQUEST>LEAK_AG_PROMPT</USER_REQUEST>"},
    {"step_index": 2, "type": "PLANNER_RESPONSE", "created_at": "2026-11-10T10:00:02Z", "content": "LEAK_AG_ANSWER"},
]
for impl, cmd in (("py", [sys.executable, "-m", "anosys_sdk_antigravity.hook_runner", "stop"]),
                  ("js", ["node", str(JS / "antigravity/src/hookRunner.js"), "run", "stop"])):
    for case, ws_env, expect in (("no workspace file", None, "full"),
                                  ("workspace lowers to metadata", {"ANOSYS_COLLECTION_LEVEL": "metadata", "ANOSYS_HOOK_APIKEY": "repo-key"}, "metadata"),
                                  ("workspace disables", {"ANOSYS_DISABLE": "1"}, "off")):
        home, env = new_home()
        tag = f"ag-{impl}-{uuid.uuid4().hex[:6]}"
        env.update(ANOSYS_HOOK_ENDPOINT_URL=f"{FAKE_URL}/{tag}")
        give_consent(env, "full")
        gcfg = home / ".gemini" / "config"
        gcfg.mkdir(parents=True)
        (gcfg / "anosys-env.json").write_text(json.dumps({"ANOSYS_HOOK_APIKEY": "user-key"}))
        ws = project()
        if ws_env:
            (ws / ".agents").mkdir()
            (ws / ".agents" / "anosys-env.json").write_text(json.dumps(ws_env))
        tdir = home / ".gemini" / "brain" / "conv1"
        tdir.mkdir(parents=True)
        tfile = tdir / "transcript_full.jsonl"
        tfile.write_text("\n".join(json.dumps(x) for x in AG_TURN) + "\n")
        stdin = json.dumps({"transcriptPath": str(tfile), "conversationId": "conv1", "workspacePaths": [str(ws)]})
        r = run(cmd, env, stdin)
        got = ingested(FAKE_OUT, tag)
        logs = " ".join(p.read_text() for p in home.rglob("*.log")) if home.exists() else ""
        name = f"{impl} antigravity ({case})"
        check(f"{name}: hook runs without errors", "error" not in logs.lower() and "Traceback" not in r.stderr,
              (logs + r.stderr)[-200:])
        if expect == "off":
            check(f"{name}: sends nothing", not got, f"{len(got)} records")
            continue
        check(f"{name}: sends the turn", bool(got), f"{len(got)} records")
        check(f"{name}: level is {expect}", got and all(str(x.get("cvs198", "")).startswith(expect) for x in got),
              str([x.get("cvs198") for x in got]))
        if expect == "metadata":
            check(f"{name}: no content at metadata", "LEAK_AG" not in texts(got))
        else:
            check(f"{name}: content at full", "LEAK_AG_PROMPT" in texts(got))
        hdr = Path(FAKE_OUT) / f"{tag}.headers"
        keys = {json.loads(line).get("anosys-apikey") for line in hdr.read_text().splitlines()} if hdr.exists() else set()
        check(f"{name}: filed under the user's own key", keys == {"user-key"}, str(keys))

finish()
