#!/usr/bin/env bash
#
# Release a single package from the anosys-sdk monorepo.
#
# Usage:   scripts/release.sh <component> <version>
# Example: scripts/release.sh openai-js 1.0.5
#
# Bumps the version in the package's manifest, commits, tags as
# "<component>-v<version>", and (after confirmation) pushes. The
# matching tag-prefix triggers .github/workflows/release-{python,js}.yml,
# which builds and publishes the package.

set -euo pipefail

# ─── helpers ──────────────────────────────────────────────────────────────────
err()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }
info() { printf '\033[36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }

confirm() {
  local prompt=$1 reply
  printf '%s [y/N] ' "$prompt"
  read -r reply
  [[ $reply =~ ^[Yy]$ ]]
}

usage() {
  cat <<'EOF'
Usage: scripts/release.sh <component> <version>

Components:
  core              packages/python/core              (anosys-sdk-core)
  openai-py         packages/python/openai            (anosys-sdk-openai)
  openai-agents-py  packages/python/openai_agents     (anosys-sdk-openai-agents)
  claude-code       packages/python/claude_code       (anosys-claude-code)
  openai-js         packages/js/openai                (anosys-sdk-openai)
  openai-agents-js  packages/js/openai-agents         (anosys-sdk-openai-agents)
  claude-code-js    packages/js/claude-code           (anosys-sdk-claude-code)

Version: semver, e.g. 1.0.5 or 2.0.0-rc.1

Example:
  scripts/release.sh openai-js 1.0.5
EOF
}

# ─── parse args ───────────────────────────────────────────────────────────────
if [[ $# -ne 2 ]]; then
  usage
  exit 1
fi

component=$1
version=$2

# Validate semver-ish (loose: x.y.z with optional prerelease/build metadata)
if ! [[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?(\+[A-Za-z0-9.-]+)?$ ]]; then
  err "version '$version' does not look like semver (e.g. 1.0.5)"
  exit 1
fi

# Map component → directory + language
case "$component" in
  core)              dir="packages/python/core";          lang="python" ;;
  openai-py)         dir="packages/python/openai";        lang="python" ;;
  openai-agents-py)  dir="packages/python/openai_agents"; lang="python" ;;
  claude-code)       dir="packages/python/claude_code";   lang="python" ;;
  openai-js)         dir="packages/js/openai";            lang="node"   ;;
  openai-agents-js)  dir="packages/js/openai-agents";     lang="node"   ;;
  claude-code-js)    dir="packages/js/claude-code";       lang="node"   ;;
  *)
    err "unknown component: $component"
    usage
    exit 1
    ;;
esac

tag="${component}-v${version}"

# ─── pre-flight checks ────────────────────────────────────────────────────────
cd "$(git rev-parse --show-toplevel)"

if ! git diff --quiet || ! git diff --cached --quiet; then
  err "working tree is not clean — commit or stash first"
  git status --short
  exit 1
fi

branch=$(git rev-parse --abbrev-ref HEAD)
if [[ $branch != "main" ]]; then
  warn "you are on branch '$branch', not main"
  confirm "continue anyway?" || exit 1
fi

if git rev-parse "$tag" >/dev/null 2>&1; then
  err "tag $tag already exists"
  exit 1
fi

# Pull to make sure we're not behind (non-fatal if no upstream)
if git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
  info "fetching from origin"
  git fetch --quiet --tags origin
  if [[ -n $(git log "HEAD..@{u}" --oneline) ]]; then
    err "local branch is behind upstream — pull first"
    exit 1
  fi
fi

# ─── bump version ─────────────────────────────────────────────────────────────
info "bumping $component to $version"
case "$lang" in
  python)
    file="$dir/pyproject.toml"
    if [[ ! -f $file ]]; then
      err "missing $file"
      exit 1
    fi
    # Portable sed across BSD (macOS) and GNU
    if sed --version >/dev/null 2>&1; then
      sed -i -E "s/^version = \".*\"/version = \"$version\"/" "$file"
    else
      sed -i '' -E "s/^version = \".*\"/version = \"$version\"/" "$file"
    fi
    ;;
  node)
    file="$dir/package.json"
    if [[ ! -f $file ]]; then
      err "missing $file"
      exit 1
    fi
    # npm version edits package.json in place; --no-git-tag-version skips
    # npm's own commit/tag because we do that ourselves with a prefixed tag.
    (cd "$dir" && npm version --no-git-tag-version "$version" >/dev/null)
    ;;
esac

# Sanity-check the change actually happened
if git diff --quiet -- "$file"; then
  err "no change written to $file (already at $version?)"
  exit 1
fi

echo
git --no-pager diff -- "$file"
echo

if ! confirm "commit + tag as $tag?"; then
  git checkout -- "$file"
  warn "aborted; reverted version change in $file"
  exit 1
fi

# ─── commit + tag ─────────────────────────────────────────────────────────────
git add -- "$file"
git commit -m "release($component): $version" >/dev/null
git tag -a "$tag" -m "$component v$version"
ok "committed and tagged $tag locally"

# ─── push ─────────────────────────────────────────────────────────────────────
echo
if confirm "push branch + tag to origin?"; then
  git push origin "$branch"
  git push origin "$tag"
  ok "pushed $tag — release workflow should fire shortly"
  ok "actions: https://github.com/anosys-ai/anosys-sdk/actions"
else
  info "skipped push. when ready, run:"
  printf '    git push origin %s\n' "$branch"
  printf '    git push origin %s\n' "$tag"
fi
