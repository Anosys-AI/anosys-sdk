"""The coding-agent hooks never break the host tool: read-only home, missing transcript, no key."""

import os
import stat
import subprocess
import sys
import time

import pytest

EVENT = '{"type":"agent-turn-complete","thread-id":"t","turn-id":"x"}'
HOOKS = [
    ("anosys_sdk_codex", ["-m", "anosys_sdk_codex.hook_runner", EVENT], ""),
    ("anosys_sdk_claude_code", ["-m", "anosys_sdk_claude_code.cli", "run"],
     '{"session_id":"s","transcript_path":"/nonexistent/t.jsonl"}'),
    ("anosys_sdk_antigravity", ["-m", "anosys_sdk_antigravity.cli", "run", "stop"],
     '{"transcriptPath":"/nonexistent/t.jsonl"}'),
]


@pytest.mark.parametrize("package,args,stdin", HOOKS, ids=[h[0] for h in HOOKS])
def test_hook_survives_read_only_home(package, args, stdin, tmp_path):
    pytest.importorskip(package)
    home = tmp_path / "home"
    home.mkdir()
    home.chmod(stat.S_IRUSR | stat.S_IXUSR)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANOSYS_", "CODEX_"))}
    env.update(HOME=str(home), CODEX_HOME=str(home / ".codex"), ANOSYS_CONSENT_FILE=str(home / "c.json"),
               PYTHONPATH=os.pathsep.join(sys.path))
    try:
        start = time.monotonic()
        result = subprocess.run([sys.executable, *args], input=stdin, env=env, capture_output=True,
                                text=True, timeout=60)
        assert result.returncode == 0, result.stderr[-500:]
        assert result.stdout.strip() in ("", "{}")      # nothing printed into the host tool
        assert time.monotonic() - start < 30
    finally:
        home.chmod(stat.S_IRWXU)
