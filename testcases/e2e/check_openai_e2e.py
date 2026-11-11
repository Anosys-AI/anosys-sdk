"""
End-to-end OpenAI and Anthropic SDK check (Python and JS): a real `openai` client calls the
local fake model, the AnoSys logger sends to the local fake ingestion, and we
check what arrives at each level. JS is checked with `require` and with ESM
`import`, and alongside an app that has its own OpenTelemetry logs and traces.

Needs FAKE_URL and FAKE_OUT (set by run_all.sh).
"""

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import check, finish, ingested, is_encrypted  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
JS_OPENAI = ROOT / "packages" / "js" / "openai"
FAKE_URL, FAKE_OUT = os.environ["FAKE_URL"], os.environ["FAKE_OUT"]
SECRET = "sk-proj-abcdefghijklmnopqrstuvwx"


def env_for(tag, **extra):
    home = tempfile.mkdtemp(prefix="anosys-sdk-")
    env = {k: v for k, v in os.environ.items() if not k.startswith("ANOSYS_") and not k.startswith("OTEL_")}
    env.update(HOME=home, ANOSYS_API_URL=f"{FAKE_URL}/{tag}", **extra)
    return env


def run(cmd, env, cwd=None):
    return subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True, timeout=120)


def assert_level(name, records, level, encrypted=False):
    blob = json.dumps(records)
    if not check(f"{name}: one record arrives", len(records) == 1, f"{len(records)} records"):
        return
    r = records[0]
    check(f"{name}: cvs198 says {level};app", r.get("cvs198") == f"{level};app", str(r.get("cvs198")))
    check(f"{name}: secrets never leave", SECRET not in blob)
    if level == "metadata":
        check(f"{name}: no prompt or answer", "LEAK_PROMPT" not in blob and "LEAK_ANSWER" not in blob)
        check(f"{name}: user context (cvs5) is dropped", "cvs5" not in r)
        check(f"{name}: the app's user/session id is not sent in clear", "sess-tc" not in blob,
              [k for k, v in r.items() if "sess-tc" in json.dumps(v)])
    elif encrypted:
        check(f"{name}: nothing readable", "LEAK_PROMPT" not in blob and "LEAK_ANSWER" not in blob)
        check(f"{name}: prompt columns are encrypted", any(is_encrypted(v) for v in r.values()))
    else:
        check(f"{name}: prompt is captured", "LEAK_PROMPT" in blob)
        check(f"{name}: answer is captured", "LEAK_ANSWER" in blob)
        check(f"{name}: user context in cvs5", "sess-tc" in str(r.get("cvs5", "")))


# ── Python ─────────────────────────────────────────────────────────────────────
PY = f"""
import time
from anosys_sdk_openai import AnosysOpenAILogger
from openai import OpenAI
AnosysOpenAILogger(get_user_context=lambda: {{"session_id": "sess-tc", "token": "t"}})
OpenAI(api_key="x", base_url="{FAKE_URL}/v1").chat.completions.create(
    model="gpt-4o-mini", messages=[{{"role": "user", "content": "LEAK_PROMPT"}}])
time.sleep(3)
"""
for level, extra, enc in (("full", {}, False), ("metadata", {}, False),
                          ("full", {"ANOSYS_ENCRYPTION_KEY": "k", "ANOSYS_ENCRYPTION_SALT": "s"}, True)):
    tag = f"oa-py-{uuid.uuid4().hex[:6]}"
    r = run([sys.executable, "-c", PY], env_for(tag, ANOSYS_COLLECTION_LEVEL=level, **extra))
    assert_level(f"py openai {level}{' + key' if enc else ''}", ingested(FAKE_OUT, tag), level, enc)
    if r.returncode:
        check("py openai: script ran", False, r.stderr[-300:])

# Anthropic (Python SDK with its built-in OpenTelemetry)
PY_ANTHROPIC = f"""
import time, anthropic
from anosys_sdk_anthropic import AnosysAnthropicLogger
AnosysAnthropicLogger(get_user_context=lambda: {{"session_id": "sess-tc", "token": "t"}})
anthropic.Anthropic(api_key="x", base_url="{FAKE_URL}").messages.create(
    model="claude-sonnet-5-5", max_tokens=10, messages=[{{"role": "user", "content": "LEAK_PROMPT"}}])
time.sleep(3)
"""
try:
    import anthropic  # noqa: F401
    for level in ("full", "metadata"):
        tag = f"an-py-{uuid.uuid4().hex[:6]}"
        run([sys.executable, "-c", PY_ANTHROPIC], env_for(tag, ANOSYS_COLLECTION_LEVEL=level))
        assert_level(f"py anthropic {level}", ingested(FAKE_OUT, tag), level)
except ImportError:
    print("SKIP py anthropic: the anthropic package is not installed")

tag = f"oa-py-off-{uuid.uuid4().hex[:6]}"
run([sys.executable, "-c", PY], env_for(tag, ANOSYS_DISABLE="1"))
check("py openai ANOSYS_DISABLE: nothing sent", not ingested(FAKE_OUT, tag))


# ── JS ─────────────────────────────────────────────────────────────────────────
def js_script(mode):
    load = ("createRequire(import.meta.url)('openai')" if mode == "require"
            else "(await import('openai')).default")
    return f"""
import {{ createRequire }} from 'node:module';
import {{ AnosysOpenAILogger }} from './src/index.js';
new AnosysOpenAILogger({{ getUserContext: () => ({{ session_id: 'sess-tc', token: 't' }}) }});
const OpenAI = {load};
await new OpenAI({{ apiKey: 'x', baseURL: '{FAKE_URL}/v1' }}).chat.completions.create(
  {{ model: 'gpt-4o-mini', messages: [{{ role: 'user', content: 'LEAK_PROMPT' }}] }});
await new Promise((r) => setTimeout(r, 3000));
"""


def run_js(source, env):
    path = JS_OPENAI / f"_tc_{uuid.uuid4().hex[:8]}.mjs"   # inside the package so 'openai' resolves
    path.write_text(source)
    try:
        return run(["node", str(path)], env, cwd=str(JS_OPENAI))
    finally:
        path.unlink()


for mode in ("require", "import"):
    for level in ("full", "metadata"):
        tag = f"oa-js-{mode}-{uuid.uuid4().hex[:6]}"
        run_js(js_script(mode), env_for(tag, ANOSYS_COLLECTION_LEVEL=level))
        assert_level(f"js openai ({mode}) {level}", ingested(FAKE_OUT, tag), level)


# JS next to an app that has its own OpenTelemetry logs pipeline (registered before or after AnoSys)
APP_LOGS = f"""
import {{ createRequire }} from 'node:module';
const require = createRequire(import.meta.url);
const {{ logs }} = require('@opentelemetry/api-logs');
let appLogs = [];
function appLogging() {{
  // a minimal LoggerProvider, as an app's own logging SDK would register
  const provider = {{ getLogger: () => ({{ emit: (r) => appLogs.push(r) }}) }};
  logs.setGlobalLoggerProvider(provider);
}}
if (process.env.ORDER === 'app-first') appLogging();
const {{ AnosysOpenAILogger }} = await import('./src/index.js');
new AnosysOpenAILogger();
if (process.env.ORDER === 'anosys-first') appLogging();
logs.getLogger('app').emit({{ body: 'APP_OWN_LOG' }});
const OpenAI = require('openai');
await new OpenAI({{ apiKey: 'x', baseURL: '{FAKE_URL}/v1' }}).chat.completions.create(
  {{ model: 'gpt-4o-mini', messages: [{{ role: 'user', content: 'LEAK_PROMPT' }}] }});
await new Promise((r) => setTimeout(r, 3000));
console.log('APP_LOGS=' + JSON.stringify(appLogs.map((r) => r.body)));
console.log('APP_GOT_PROMPT=' + JSON.stringify(appLogs).includes('LEAK_PROMPT'));
"""
for order in ("app-first", "anosys-first"):
    tag = f"oa-js-logs-{order}-{uuid.uuid4().hex[:6]}"
    r = run_js(APP_LOGS, env_for(tag, ANOSYS_COLLECTION_LEVEL="full", ORDER=order))
    line = next((x for x in r.stdout.splitlines() if x.startswith("APP_LOGS=")), "APP_LOGS=[]")
    app_logs = json.loads(line.split("=", 1)[1])
    check(f"js openai with app log pipeline ({order}): the app still gets its own logs", "APP_OWN_LOG" in app_logs, str(app_logs)[:200])
    check(f"js openai with app log pipeline ({order}): AnoSys still captures content",
          "LEAK_PROMPT" in json.dumps(ingested(FAKE_OUT, tag)))
    check(f"js openai with app log pipeline ({order}): prompts are not copied into the app's own logs",
          "APP_GOT_PROMPT=true" not in r.stdout)

# JS next to an app that has its own TracerProvider
APP_TRACES = f"""
import {{ createRequire }} from 'node:module';
const require = createRequire(import.meta.url);
const {{ NodeTracerProvider }} = require('@opentelemetry/sdk-trace-node');
const {{ SimpleSpanProcessor }} = require('@opentelemetry/sdk-trace-base');
const {{ trace }} = require('@opentelemetry/api');
const appSpans = [];
const exporter = {{ export(s, cb) {{ appSpans.push(...s); cb({{ code: 0 }}); }}, shutdown() {{ return Promise.resolve(); }} }};
new NodeTracerProvider({{ spanProcessors: [new SimpleSpanProcessor(exporter)] }}).register();
const {{ AnosysOpenAILogger }} = await import('./src/index.js');
new AnosysOpenAILogger();
trace.getTracer('app').startSpan('app-own-span').end();
const OpenAI = require('openai');
await new OpenAI({{ apiKey: 'x', baseURL: '{FAKE_URL}/v1' }}).chat.completions.create(
  {{ model: 'gpt-4o-mini', messages: [{{ role: 'user', content: 'LEAK_PROMPT' }}] }});
await new Promise((r) => setTimeout(r, 3000));
console.log('APP_SPANS=' + JSON.stringify(appSpans.map((s) => s.name)));
"""
tag = f"oa-js-traces-{uuid.uuid4().hex[:6]}"
r = run_js(APP_TRACES, env_for(tag, ANOSYS_COLLECTION_LEVEL="full"))
line = next((x for x in r.stdout.splitlines() if x.startswith("APP_SPANS=")), "APP_SPANS=[]")
spans = json.loads(line.split("=", 1)[1])
got = ingested(FAKE_OUT, tag)
check("js openai with app tracer: the app still gets its own spans", "app-own-span" in spans, str(spans))
check("js openai with app tracer: AnoSys gets the OpenAI span only", len(got) == 1 and "app-own-span" not in json.dumps(got),
      f"{len(got)} records")
finish()
