#!/usr/bin/env bash
#
# Release health check for the AnoSys SDKs. Run before every release:
#
#   testcases/run_all.sh            # everything (about 2 minutes)
#   testcases/run_all.sh --quick    # skip unit suites and end-to-end runs
#   testcases/run_all.sh leaks e2e  # only the named steps
#
# Steps: unit, lint, static, leaks, levels, e2e. Each step's output is saved in
# testcases/.results/<time>/<step>.log; the summary at the end lists what failed.
# Exit code 0 only when every step passed.
#
# Needs: the packages installed for development (make install-dev), node >= 18,
# and npm install in packages/js. Nothing leaves the machine: end-to-end checks
# use a local fake model and fake ingestion server on 127.0.0.1.

set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TC="$ROOT/testcases"
PY="${PYTHON:-python3}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$TC/.results/$STAMP"
mkdir -p "$OUT"

ALL_STEPS=(unit lint static leaks levels e2e)
STEPS=()
for a in "$@"; do
  case "$a" in
    --quick) STEPS=(lint static leaks levels) ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) STEPS+=("$a") ;;
  esac
done
[[ ${#STEPS[@]} -eq 0 ]] && STEPS=("${ALL_STEPS[@]}")

declare -a SUMMARY
FAILED=0
step() {  # step <name> <command...>
  local name=$1; shift
  printf '\n\033[36m==> %s\033[0m\n' "$name"
  if "$@" >"$OUT/$name.log" 2>&1; then
    SUMMARY+=("PASS  $name")
  else
    SUMMARY+=("FAIL  $name   (see $OUT/$name.log)")
    FAILED=1
  fi
  grep -E '^(FAIL|PASS)' "$OUT/$name.log" | grep '^FAIL' | head -20
  local p f
  p=$(grep -c '^PASS' "$OUT/$name.log"); f=$(grep -c '^FAIL' "$OUT/$name.log")
  [[ $p -gt 0 || $f -gt 0 ]] && echo "   $p passed, $f failed"
  tail -3 "$OUT/$name.log" | grep -Ev '^(PASS|FAIL)' || true
}

want() { local s; for s in "${STEPS[@]}"; do [[ $s == "$1" ]] && return 0; done; return 1; }

# Preflight
if ! "$PY" -c "import anosys_sdk_core, anosys_sdk_claude_code, anosys_sdk_codex, anosys_sdk_antigravity, anosys_sdk_openai" 2>/dev/null; then
  echo "The Python packages are not installed for development. Run: make install-dev  (or set PYTHON=<venv python>)"
  exit 2
fi
[[ -d "$ROOT/packages/js/node_modules" ]] || { echo "Run: (cd packages/js && npm install)"; exit 2; }

unit_suites() {
  local rc=0
  (cd "$ROOT" && env -u CODEX_HOME "$PY" -m pytest -q packages/python) || rc=1
  for p in "$ROOT"/packages/js/*/; do
    [[ -f "$p/package.json" && "$p" != *node_modules* ]] || continue
    echo "-- npm test $(basename "$p")"
    (cd "$p" && npm test --silent) || rc=1
  done
  return $rc
}

with_fake_server() {  # runs a check with FAKE_URL/FAKE_OUT pointing at a fresh local server
  local port fake_out pid rc
  port=$("$PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')
  fake_out="$OUT/fake-server"
  "$PY" "$TC/lib/fake_server.py" "$fake_out" "$port" & pid=$!
  for _ in $(seq 1 50); do "$PY" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$port/')" 2>/dev/null && break; sleep 0.1; done
  FAKE_URL="http://127.0.0.1:$port" FAKE_OUT="$fake_out" "$@"; rc=$?
  kill $pid 2>/dev/null; wait $pid 2>/dev/null
  return $rc
}

want unit   && step unit   unit_suites
want lint   && step lint   bash -c "cd '$ROOT' && '$PY' -m ruff check packages/python testcases"
want static && step static "$PY" "$TC/static/check_repo.py"
want leaks  && step leaks  bash -c "'$PY' '$TC/python/check_hook_leaks.py'; a=\$?; node '$TC/js/check_hook_leaks.cjs'; b=\$?; exit \$((a|b))"
want levels && step levels bash -c "'$PY' '$TC/python/check_levels.py'; a=\$?; node '$TC/js/check_levels.cjs'; b=\$?; exit \$((a|b))"
want e2e    && step e2e    with_fake_server bash -c "PATH='$(dirname "$(command -v "$PY")")':\$PATH; '$PY' '$TC/e2e/check_hooks_e2e.py'; a=\$?; '$PY' '$TC/e2e/check_openai_e2e.py'; b=\$?; exit \$((a|b))"

printf '\n\033[1mRelease health check — %s\033[0m\n' "$STAMP"
printf '%s\n' "${SUMMARY[@]}"
if [[ $FAILED -eq 0 ]]; then
  printf '\033[32mAll steps passed.\033[0m\n'
else
  printf '\033[31mSome steps failed: do not release until they pass.\033[0m\n'
fi
exit $FAILED
