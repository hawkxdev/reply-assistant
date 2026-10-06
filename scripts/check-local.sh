#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
base=origin/main
title=''
output=''
repository=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    --base) base=$2; shift 2 ;;
    --title) title=$2; shift 2 ;;
    --output-dir) output=$2; shift 2 ;;
    --repo) repository=$2; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
if [ -z "$output" ]; then
  output=$(mktemp -d "${TMPDIR:-/tmp}/reply-assistant-checks.XXXXXX")
else
  mkdir -p "$output"
  if [ -e "$output/commit.txt" ]; then
    echo 'A fresh output directory is required.' >&2
    exit 2
  fi
fi
output=$(cd "$output" && pwd)
checked_head=$(git rev-parse HEAD)
printf '%s\n' "$checked_head" > "$output/commit.txt"

finish() {
  local result=$?
  if [ "$result" -eq 0 ] && {
    [ "$(git rev-parse HEAD)" != "$checked_head" ] ||
    [ -n "$(git status --porcelain --untracked-files=all)" ];
  }; then
    echo 'Checked inputs changed during verification.' >&2
    result=1
  fi
  printf '%s\n' "$result" > "$output/exit-code.txt"
  echo "LOCAL_RC=$result"
  echo "Local evidence: $output"
  exit "$result"
}
trap finish EXIT

if [ -n "$(git status --porcelain --untracked-files=all)" ]; then
  echo 'Clean working tree required.' >&2
  exit 2
fi
base_sha=$(git rev-parse --verify "$base^{commit}")
printf '%s\n' "$base_sha" > "$output/base.txt"
if [ -z "$title" ]; then
  title=$(git log -1 --format=%s)
fi
printf '%s\n' "$title" > "$output/title.txt"
if ! printf '%s\n' "$title" | grep -Eq \
  '^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^()]+\))?(!)?: .+'; then
  echo 'Conventional Commit title required.' >&2
  exit 2
fi
deleted=$(git diff --diff-filter=D --name-only "$base_sha" "$checked_head" -- tests)
if [ -n "$deleted" ]; then
  printf 'Test files deleted: %s\n' "$deleted" >&2
  exit 2
fi

run_gate() {
  local name=$1
  shift
  local result=0
  "$@" > "$output/$name.log" 2>&1 || result=$?
  printf '%s=%s\n' "$name" "$result" >> "$output/gates.txt"
  echo "$name: $result"
  if [ "$result" -ne 0 ]; then
    cat "$output/$name.log" >&2
  fi
  return "$result"
}

export UV_LOCKED=1
run_gate sync uv sync --locked
run_gate lint uv run ruff check .
run_gate format uv run ruff format --check .
run_gate types uv run mypy .
run_gate tests uv run pytest --cov
run_gate conventions uv run python scripts/check_conventions.py

manifests=$(git diff --name-only "$base_sha" "$checked_head" -- pyproject.toml uv.lock)
if [ -n "$manifests" ]; then
  command -v gh >/dev/null
  if [ -z "$repository" ]; then
    remote=$(git remote get-url origin)
    case "$remote" in
      https://github.com/*) repository=${remote#https://github.com/} ;;
      git@github.com:*) repository=${remote#git@github.com:} ;;
      *) echo 'Use --repo OWNER/REPO for dependency review.' >&2; exit 2 ;;
    esac
    repository=${repository%.git}
  fi
  gh api "repos/$repository/dependency-graph/compare/$base_sha...$checked_head" \
    > "$output/dependency-review.json"
  python3 - "$output/dependency-review.json" <<'PY'
import json
import sys
from pathlib import Path

items = json.loads(Path(sys.argv[1]).read_text())
if not isinstance(items, list) or not items:
    raise SystemExit('Changed manifests require an available dependency review.')
if any(
    not isinstance(item, dict)
    or item.get('change_type') not in ('added', 'removed')
    or item.get('scope', 'runtime') not in ('runtime', 'development', 'unknown')
    or not isinstance(item.get('vulnerabilities'), list)
    for item in items
):
    raise SystemExit('Invalid dependency review data.')
if any(
    item['change_type'] == 'added'
    and item.get('scope', 'runtime') == 'runtime'
    and item['vulnerabilities']
    for item in items
):
    raise SystemExit('New vulnerable dependencies are rejected.')
PY
  echo 'dependency-review=0' >> "$output/gates.txt"
else
  echo 'dependency-review=unchanged-manifests' >> "$output/gates.txt"
fi
