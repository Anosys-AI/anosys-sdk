"""Verify workspace installs are usable from a project subdirectory."""

import json
import os
import subprocess
import sys


def test_workspace_credentials_override_global_but_not_environment(tmp_path):
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
    code = ("import json; from anosys_sdk_antigravity.hook_runner import get_config; "
            "print(json.dumps(get_config()))")
    for override, expected in ((None, "workspace-key"), ("environment-key", "environment-key")):
        if override:
            env["ANOSYS_HOOK_APIKEY"] = override
        result = subprocess.run(
            [sys.executable, "-c", code], env=env, cwd=subdirectory,
            capture_output=True, text=True, check=True,
        )
        config = json.loads(result.stdout)
        assert config["api_key"] == expected
        assert config["redaction"] is True
