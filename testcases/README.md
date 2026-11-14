<p align="center">
  <a href="https://anosys.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="../assets/anosys-new-white-darkmode.svg">
      <img src="../assets/anosys-new-black-lightmode.svg" alt="Anosys.ai" width="240">
    </picture>
  </a>
</p>

# Release health check

Run this before every release. It checks the things that matter for users: no
data leaks, every privacy setting respected, nothing lost, nothing broken. It
also re-checks every bug found in the reviews of this branch, so they can't come
back unnoticed.

```bash
make install-dev                 # once: Python packages in development mode
(cd packages/js && npm install)  # once: JS workspace

testcases/run_all.sh             # everything, about 2 minutes
testcases/run_all.sh --quick     # skip unit suites and end-to-end runs (about 30 s)
testcases/run_all.sh leaks e2e   # only some steps
PYTHON=.venv/bin/python testcases/run_all.sh   # use a specific Python
```

The summary at the end lists each step as PASS or FAIL. The exit code is 0 only
when everything passed, so CI can use it too. Each step's full output is saved
under `testcases/.results/<time>/`, which git ignores. Nothing leaves the machine:
the end-to-end steps talk to a fake model and a fake ingestion server on
127.0.0.1 (`lib/fake_server.py`), and every check uses its own throwaway HOME.

## Steps

| Step | What it proves | Files |
| --- | --- | --- |
| `unit` | Every package's own test suite passes (pytest + `npm test` in each JS package) | — |
| `lint` | ruff is clean | — |
| `static` | Every name a JS package takes from `anosys-sdk-core` is exported, and every Python import from `anosys_sdk_core` exists. Packages require a core version this repo has, and integration versions match package versions. No local machine paths are committed, README links resolve, `.env.example` doesn't point at the website, and npm packages ship `src/` and nothing private | `static/check_repo.py` |
| `leaks` | Every field the Claude Code, Codex and Antigravity mappers read is filled with a marker, for every record type and both column layouts, in Python and JS. At `metadata`, only allow-listed columns leave and no content does. At `full` with a key, every other column is encrypted | `python/check_hook_leaks.py`, `js/check_hook_leaks.cjs` |
| `levels` | Precedence rules: consent, `.anosys` (in subfolders too), `ANOSYS_COLLECTION_LEVEL`, `REDACTION`, `ANOSYS_DISABLE`. Nothing can raise a saved `off`, and `full` needs the accepted policy. An Antigravity workspace file can't change the user's key or endpoint. App SDK defaults and ceilings | `python/check_levels.py`, `js/check_levels.cjs` |
| `e2e` | The real hook processes run, Python and JS. Claude Code: content at `full`; nothing written while `off` is ever sent; collection resumes; no duplicates; the project `.anosys` is respected. Codex: the same for notify events. Antigravity: runs with and without workspace files, applies the workspace limit, and files records under the user's own key. A real `openai` client (Python, JS `require` and JS `import`) and `anthropic` client (Python): content at `full`, none at `metadata`, encryption, secret scrubbing, `ANOSYS_DISABLE`. JS OpenAI next to an app's own OpenTelemetry logs and traces: both keep working | `e2e/check_hooks_e2e.py`, `e2e/check_openai_e2e.py` |

## Adding a check

Print one line per check, starting with `PASS ` or `FAIL ` (helpers: `check()` in
`lib/common.py` and `js/common.cjs`), and exit non-zero on any failure. Then add
the file to its step in `run_all.sh`. When a review finds a bug, add a check that
fails on the buggy code before fixing it.

Not covered end to end (unit tests only): the OpenAI Agents SDK, the Claude Agent
SDK, the JS Anthropic SDK, and Windows.
