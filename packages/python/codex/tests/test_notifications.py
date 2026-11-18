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
    if os.name != "nt":
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


def test_previous_notify_not_rerun_when_it_wraps_us(tmp_path, monkeypatch):
    """Codex Computer Use can wrap notify after we chained it: don't call it a second time."""
    import json as _json
    from anosys_sdk_codex import hook_runner, installer

    marker = tmp_path / "calls.txt"
    fake = tmp_path / "fake_notifier.sh"
    fake.write_text(f"#!/bin/sh\necho called >> {marker}\n")
    fake.chmod(0o755)
    cu = [str(fake), "turn-ended"]
    ours = installer.hook_command()
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))

    # Wrapped: CU -> ours -> CU. Ours must not call CU again.
    chained = ours + [installer.PREVIOUS_NOTIFY_FLAG, _json.dumps(cu)]
    notify = cu + [installer.PREVIOUS_NOTIFY_FLAG, _json.dumps(chained)]
    (tmp_path / "config.toml").write_text(f"notify = {installer._toml_array(notify)}\n")
    hook_runner.call_previous_notify(cu, "{}")
    assert not marker.exists()

    # Normal: ours -> CU. Ours calls CU once.
    (tmp_path / "config.toml").write_text(f"notify = {installer._toml_array(chained)}\n")
    hook_runner.call_previous_notify(cu, "{}")
    assert marker.read_text().count("called") == 1


def test_reinstall_flattens_self_wrapped_chain(tmp_path):
    import json as _json
    from anosys_sdk_codex import installer
    cu = ["/x/SkyComputerUseClient", "turn-ended"]
    old_ours = ["/old/python", "-m", "anosys_sdk_codex.hook_runner"]
    chained = old_ours + [installer.PREVIOUS_NOTIFY_FLAG, _json.dumps(cu)]
    notify = cu + [installer.PREVIOUS_NOTIFY_FLAG, _json.dumps(chained)]
    assert installer._notify_without_ours(notify) == cu
