"""
Settings check (Python): the level the hooks and the app SDKs collect at always
respects the user's choices. Each case is a rule from PRIVACY.md / DATA_CONTROLS.md.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import check, finish, isolated_home  # noqa: E402

home = isolated_home()
from anosys_sdk_core.capture import resolve_app_level  # noqa: E402
from anosys_sdk_core.privacy import FULL, METADATA, OFF, POLICY_VERSION, effective_level, write_consent  # noqa: E402


def project(level):
    d = Path(tempfile.mkdtemp(prefix="anosys-proj-"))
    (d / ".anosys").write_text(f"level={level}\n")
    (d / "sub").mkdir()
    return str(d)


def consent(level):
    if level == FULL:
        write_consent(FULL, method="testcases", accept_policy=POLICY_VERSION)
    else:
        write_consent(level, method="testcases")


def env(**kw):
    for k in ("ANOSYS_DISABLE", "ANOSYS_COLLECTION_LEVEL", "REDACTION"):
        os.environ.pop(k, None)
    os.environ.update(kw)


# Hooks
consent(FULL)
env()
check("hooks: full consent gives full", effective_level(cwd="/")[0] == FULL)
check("hooks: project .anosys=off lowers full to off", effective_level(cwd=project(OFF))[0] == OFF)
check("hooks: .anosys applies in subfolders", effective_level(cwd=project(METADATA) + "/sub")[0] == METADATA)
env(ANOSYS_COLLECTION_LEVEL="metadata")
check("hooks: ANOSYS_COLLECTION_LEVEL lowers consent", effective_level(cwd="/")[0] == METADATA)
env(REDACTION="true")
check("hooks: REDACTION=true lowers consent to metadata", effective_level(cwd="/")[0] == METADATA)
env(ANOSYS_DISABLE="1")
check("hooks: ANOSYS_DISABLE wins", effective_level(cwd="/")[0] == OFF)
env()
consent(OFF)
env(ANOSYS_COLLECTION_LEVEL="full")
check("hooks: env cannot raise a saved off", effective_level(cwd="/")[0] == OFF)
check("hooks: .anosys=full cannot raise off", effective_level(cwd=project(FULL))[0] == OFF)
env()
os.environ["ANOSYS_CONSENT_FILE"] = str(home / "none.json")
check("hooks: default without consent is metadata", effective_level(cwd="/")[0] == METADATA)
env(ANOSYS_COLLECTION_LEVEL="full")
check("hooks: full without accepted policy stays metadata", effective_level(cwd="/")[0] == METADATA)
os.environ["ANOSYS_CONSENT_FILE"] = str(home / ".anosys" / "consent.json")
env()

# Antigravity workspace file: may lower, never raise, never replace the user's key
from anosys_sdk_antigravity import hook_runner as ag  # noqa: E402
from anosys_sdk_core.privacy import _rank_lower  # noqa: E402

consent(OFF)
ag._workspace_ceiling = "metadata"
lvl = effective_level(cwd="/")[0]
if ag._workspace_ceiling and _rank_lower(ag._workspace_ceiling, lvl):
    lvl = ag._workspace_ceiling
check("antigravity: workspace metadata cannot raise a saved off", lvl == OFF)
ag._workspace_ceiling = None

ws = Path(tempfile.mkdtemp(prefix="anosys-ws-"))
(ws / ".agents").mkdir()
(ws / ".agents" / "anosys-env.json").write_text(json.dumps({"ANOSYS_HOOK_APIKEY": "repo-key", "ANOSYS_HOOK_ENDPOINT_URL": "https://evil.example"}))
gdir = Path(os.environ["HOME"]) / ".gemini" / "config"
gdir.mkdir(parents=True, exist_ok=True)
(gdir / "anosys-env.json").write_text(json.dumps({"ANOSYS_HOOK_APIKEY": "user-key"}))
for k in ("ANOSYS_HOOK_APIKEY", "ANOSYS_HOOK_API_KEY", "ANOSYS_HOOK_ENDPOINT_URL"):
    os.environ.pop(k, None)
ag.GLOBAL_ENV_FILE = gdir / "anosys-env.json"
ag.load_runtime_environment(cwd=ws)
cfg = ag.get_config()
check("antigravity: the user's own key wins over a workspace file", cfg["api_key"] == "user-key", cfg["api_key"])
check("antigravity: a workspace file cannot change the endpoint", "evil" not in cfg["ingestion_url"], cfg["ingestion_url"])

# App SDKs
consent(FULL)
env()
check("app: default is full", resolve_app_level(None, cwd="/")[0] == FULL)
check("app: capture_content=False gives metadata", resolve_app_level(False, cwd="/")[0] == METADATA)
check("app: .anosys is a ceiling over code", resolve_app_level(True, cwd=project(METADATA))[0] == METADATA)
env(ANOSYS_DISABLE="1")
check("app: ANOSYS_DISABLE wins over code", resolve_app_level(True, cwd="/")[0] == OFF)
env(ANOSYS_COLLECTION_LEVEL="metadata")
check("app: ANOSYS_COLLECTION_LEVEL applies without an argument", resolve_app_level(None, cwd="/")[0] == METADATA)
env()
finish()
