"""Exercise the installed CLI contract in fresh processes with isolated state."""

import json
import os
import subprocess
import sys


def _env(tmp_path):
    env = os.environ.copy()
    for var in ("REDACTION", "ANOSYS_COLLECTION_LEVEL", "ANOSYS_DISABLE", "ANOSYS_ENCRYPTION_KEY"):
        env.pop(var, None)
    env.update(CODEX_HOME=str(tmp_path), ANOSYS_HOOK_DRY_RUN="true",
               ANOSYS_CONSENT_FILE=str(tmp_path / "consent.json"),
               PYTHONPATH=os.pathsep.join(sys.path))
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
    log_file = tmp_path / "state" / "anosys_hook.log"
    log = log_file.read_text()
    assert "[DRY RUN]" in log and "at 'metadata'" in log
    # the log never contains the notification content
    assert "synthetic test" not in log and "synthetic result" not in log
    assert (log_file.stat().st_mode & 0o777) == 0o600


def test_saved_redaction_means_metadata(tmp_path):
    (tmp_path / "anosys-env.sh").write_text('export REDACTION="true"\n')
    result = subprocess.run(
        [sys.executable, "-c", "import anosys_sdk_codex.hook_runner as h; "
         "from anosys_sdk_core.privacy import effective_level; "
         "assert effective_level() == ('metadata', 'REDACTION'), effective_level()"],
        env=_env(tmp_path), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_disable_switch_sends_nothing(tmp_path):
    env = _env(tmp_path)
    env["ANOSYS_DISABLE"] = "1"
    event = json.dumps({"type": "agent-turn-complete", "thread-id": "s", "turn-id": "t"})
    result = subprocess.run([sys.executable, "-m", "anosys_sdk_codex.cli", "run", event],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "Collection is off" in (tmp_path / "state" / "anosys_hook.log").read_text()
