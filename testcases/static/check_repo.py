"""
Static release checks: things that broke before and that no unit test catches.

- every name a JS package takes from 'anosys-sdk-core' is exported by core
  (an unexported name is `undefined` at runtime, e.g. RANK in 80f1c49)
- every name a Python package imports from anosys_sdk_core exists
- packages require a core version that the core in this repo satisfies
- integration versions in code match the package version
- no local machine paths in tracked files; README links resolve;
  .env.example does not point telemetry at the website
- npm packages ship src/ and nothing private
"""

import ast
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import check, finish  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
JS, PY = ROOT / "packages" / "js", ROOT / "packages" / "python"
tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()

# ── JS: names imported from anosys-sdk-core exist ─────────────────────────────
core_js = subprocess.run(["node", "-e", f"console.log(JSON.stringify(Object.keys(require('{JS / 'core/src/index.js'}'))))"],
                         capture_output=True, text=True)
exported = set(json.loads(core_js.stdout or "[]"))
check("js core: index.js loads", bool(exported), core_js.stderr[-200:])
pattern = re.compile(r"(?:const|let|var)\s*\{([^}]*)\}\s*=\s*require\(['\"]anosys-sdk-core['\"]\)|import\s*\{([^}]*)\}\s*from\s*['\"]anosys-sdk-core['\"]", re.S)
missing = []
for f in sorted(JS.glob("*/src/**/*.js")):
    if "node_modules" in f.parts:
        continue
    for m in pattern.finditer(f.read_text()):
        for item in (m.group(1) or m.group(2)).split(","):
            name = item.strip().split(":")[0].split(" as ")[0].split("=")[0].strip()
            if name and name not in exported:
                missing.append(f"{f.relative_to(ROOT)}: {name}")
check("js: every name taken from anosys-sdk-core is exported", not missing, "; ".join(missing[:6]))

# ── Python: names imported from anosys_sdk_core exist ─────────────────────────
missing = []
for f in sorted(PY.glob("*/src/**/*.py")):
    try:
        tree = ast.parse(f.read_text())
    except SyntaxError as e:
        missing.append(f"{f}: syntax error {e}")
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("anosys_sdk_core"):
            try:
                mod = importlib.import_module(node.module)
            except Exception as e:  # noqa: BLE001
                missing.append(f"{f.relative_to(ROOT)}: {node.module} ({type(e).__name__})")
                continue
            for alias in node.names:
                if alias.name != "*" and not hasattr(mod, alias.name):
                    try:
                        importlib.import_module(f"{node.module}.{alias.name}")
                    except Exception:  # noqa: BLE001
                        missing.append(f"{f.relative_to(ROOT)}: {node.module}.{alias.name}")
check("py: every name imported from anosys_sdk_core exists", not missing, "; ".join(missing[:6]))

# ── Versions ───────────────────────────────────────────────────────────────────
def py_version(pkg):
    return re.search(r'^version\s*=\s*"([^"]+)"', (PY / pkg / "pyproject.toml").read_text(), re.M).group(1)


def major_minor(v):
    return tuple(int(x) for x in v.split("-")[0].split(".")[:2])


core_py, core_js_v = py_version("core"), json.loads((JS / "core/package.json").read_text())["version"]
bad = []
for d in sorted(PY.iterdir()):
    pp = d / "pyproject.toml"
    if d.name == "core" or not pp.exists():
        continue
    m = re.search(r'"anosys-sdk-core\s*>=\s*([0-9.]+)', pp.read_text())
    if m and major_minor(m.group(1)) > major_minor(core_py):
        bad.append(f"{d.name} needs core>={m.group(1)}, repo has {core_py}")
for d in sorted(JS.iterdir()):
    pj = d / "package.json"
    if d.name in ("core", "node_modules") or not pj.exists():
        continue
    dep = json.loads(pj.read_text()).get("dependencies", {}).get("anosys-sdk-core")
    if dep and major_minor(re.sub(r"^[\^~>=]+", "", dep)) > major_minor(core_js_v):
        bad.append(f"js {d.name} needs core {dep}, repo has {core_js_v}")
check("packages require a core version this repo provides", not bad, "; ".join(bad))

mismatch = []
for pkg_py, pkg_js in (("claude_code", "claude-code"), ("codex", "codex"), ("antigravity", "antigravity")):
    pv = py_version(pkg_py)
    jv = json.loads((JS / pkg_js / "package.json").read_text())["version"]
    for f in list((PY / pkg_py / "src").rglob("*.py")) + list((JS / pkg_js / "src").rglob("*.js")):
        m = re.search(r"INTEGRATION_VERSION\s*=\s*['\"]([^'\"]+)['\"]", f.read_text())
        want = pv if f.suffix == ".py" else jv
        if m and m.group(1) != want:
            mismatch.append(f"{f.relative_to(ROOT)} says {m.group(1)}, package is {want}")
check("integration versions match package versions", not mismatch, "; ".join(mismatch))

# ── Repository hygiene ─────────────────────────────────────────────────────────
local = [f for f in tracked if not f.startswith("testcases/") and (ROOT / f).is_file()
         and (ROOT / f).stat().st_size < 2_000_000 and not f.endswith((".png", ".jpg", ".ipynb"))
         and re.search(r"file:///Users/|/Users/[a-z]+/(Projects|Dropbox|Documents)", (ROOT / f).read_text(errors="ignore"))]
check("no local machine paths in tracked files", not local, ", ".join(local[:5]))

env_example = ROOT / ".env.example"
if env_example.exists():
    check(".env.example does not point ANOSYS_API_URL at the website (uncommenting it would lose all data)",
          not re.search(r"ANOSYS_API_URL\s*=\s*https?://www\.anosys\.ai", env_example.read_text()))

broken = []
for md in ["README.md"] + [f for f in tracked if f.endswith("README.md") and f.startswith("packages/")]:
    p = ROOT / md
    for link in re.findall(r"\]\(([^)#\s]+)\)", p.read_text()):
        if not re.match(r"^[a-z]+:", link) and not (p.parent / link).exists():
            broken.append(f"{md} -> {link}")
check("README links point to files that exist", not broken, "; ".join(broken[:6]))

# ── npm packages ship src and nothing private ─────────────────────────────────
for d in sorted(JS.iterdir()):
    if not (d / "package.json").exists() or d.name == "node_modules":
        continue
    r = subprocess.run(["npm", "pack", "--dry-run", "--json"], cwd=d, capture_output=True, text=True)
    try:
        data = json.loads(r.stdout)
        entry = data[0] if isinstance(data, list) else next(iter(data.values()))   # npm 9 list / npm 10+ object
        files = [x["path"] for x in entry["files"]]
    except Exception:  # noqa: BLE001
        check(f"npm pack {d.name}", False, r.stderr[-200:])
        continue
    bad = [f for f in files if re.search(r"(^|/)(\.env|.*\.pem|.*\.key|test/|consent\.json)", f)]
    check(f"npm pack {d.name}: ships src/, nothing private", any(f.startswith("src/") for f in files) and not bad, ", ".join(bad[:5]))

finish()
