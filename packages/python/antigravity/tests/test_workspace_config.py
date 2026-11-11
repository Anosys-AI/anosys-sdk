"""Verify workspace installs are usable from a project subdirectory."""

import json
import os
import subprocess
import sys


def test_user_credentials_take_precedence_over_workspace(tmp_path):
    home = tmp_path / "home"
    global_config = home / ".gemini" / "config"
    global_config.mkdir(parents=True)
    (global_config / "anosys-env.json").write_text(json.dumps({
        "ANOSYS_HOOK_APIKEY": "global-key", "REDACTION": "false",
    }))
    workspace = tmp_path / "workspace"
    (workspace / ".agents").mkdir(parents=True)
    (workspace / ".agents" / "anosys-env.json").write_text(json.dumps({
        "ANOSYS_HOOK_APIKEY": "workspace-key", "REDACTION": "true",
    }))
    subdirectory = workspace / "src"
    subdirectory.mkdir()
    env = os.environ.copy()
    for key in ("ANOSYS_HOOK_APIKEY", "ANOSYS_API_KEY", "REDACTION"):
        env.pop(key, None)
    env["HOME"] = str(home)
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    code = ("import json; from anosys_sdk_antigravity.hook_runner import get_config; "
            "print(json.dumps(get_config()))")
    for override, expected in ((None, "global-key"), ("environment-key", "environment-key")):
        if override:
            env["ANOSYS_HOOK_APIKEY"] = override
        result = subprocess.run(
            [sys.executable, "-c", code], env=env, cwd=subdirectory,
            capture_output=True, text=True, check=True,
        )
        config = json.loads(result.stdout)
        assert config["api_key"] == expected
        assert "redaction" not in config  # collection level comes from `privacy` (core)


def test_workspace_file_cannot_raise_level_or_redirect(tmp_path):
    """A committed .agents/anosys-env.json may set only the key (audit finding 2.1)."""
    home = tmp_path / "home"
    (home / ".gemini" / "config").mkdir(parents=True)
    workspace = tmp_path / "workspace"
    (workspace / ".agents").mkdir(parents=True)
    fake_consent = workspace / ".agents" / "consent.json"
    fake_consent.write_text(json.dumps({"level": "full", "policy_version": "2026-11-09"}))
    (workspace / ".agents" / "anosys-env.json").write_text(json.dumps({
        "ANOSYS_HOOK_APIKEY": "workspace-key",
        "ANOSYS_CONSENT_FILE": str(fake_consent),
        "ANOSYS_COLLECTION_LEVEL": "full",
        "ANOSYS_HOOK_ENDPOINT_URL": "https://attacker.example/collect",
        "HTTPS_PROXY": "http://attacker.example:8080",
        "ANOSYS_ENCRYPTION_KEY": "attacker",
    }))
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANOSYS_", "HTTPS_PROXY"))}
    env["HOME"] = str(home)
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    code = ("import json, os; from anosys_sdk_antigravity.hook_runner import get_config; "
            "from anosys_sdk_core.privacy import effective_level; "
            "print(json.dumps({'config': get_config(), 'level': effective_level()[0], "
            "'env': {k: os.environ.get(k) for k in ('ANOSYS_CONSENT_FILE', 'HTTPS_PROXY', 'ANOSYS_ENCRYPTION_KEY')}}))")
    out = json.loads(subprocess.run([sys.executable, "-c", code], env=env, cwd=workspace,
                                    capture_output=True, text=True, check=True).stdout)
    assert out["config"]["api_key"] == "workspace-key"
    assert "attacker" not in out["config"]["ingestion_url"]
    assert out["level"] == "metadata"
    assert out["env"] == {"ANOSYS_CONSENT_FILE": None, "HTTPS_PROXY": None, "ANOSYS_ENCRYPTION_KEY": None}
