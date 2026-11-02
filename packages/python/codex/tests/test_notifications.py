"""Exercise the installed CLI contract in fresh processes with isolated state."""

import json
import os
import subprocess
import sys


def _env(tmp_path):
    env = os.environ.copy()
    env.pop("REDACTION", None)
    env.update(CODEX_HOME=str(tmp_path), ANOSYS_HOOK_DRY_RUN="true")
    return env


def test_cli_accepts_codex_notification_argument(tmp_path):
    event = json.dumps({
        "type": "agent-turn-complete",
        "thread-id": "notification-regression",
        "turn-id": "turn-1",
        "input-messages": ["synthetic test"],
        "last-assistant-message": "synthetic result",
    })
    result = subprocess.run(
        [sys.executable, "-m", "anosys_sdk_codex.cli", "run", event],
        env=_env(tmp_path), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    log = (tmp_path / "state" / "anosys_hook.log").read_text()
    assert "anosys-codex run invoked" in log
    assert "[DRY RUN]" in log


def test_saved_redaction_applies_after_mapper_import(tmp_path):
    (tmp_path / "anosys-env.sh").write_text('export REDACTION="true"\n')
    result = subprocess.run(
        [sys.executable, "-c", "import anosys_sdk_codex.hook_runner; "
         "from anosys_sdk_codex.mapper import transform_codex_turn; "
         "assert transform_codex_turn({'user_prompt':'secret'}, 's', 't')['user_prompt'] == '[REDACTED]'"],
        env=_env(tmp_path), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
