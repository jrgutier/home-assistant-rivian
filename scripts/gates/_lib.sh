#!/usr/bin/env bash
# Shared helpers for ralph-port gate scripts.
#
# Contract: every gate exits 0 (pass) or non-zero (fail). Gates are bash, not
# zsh — the interactive shell here is zsh, which consumes `:c` in
# `$TAG:path/to/file` as a parameter modifier and silently mangles git revspecs.
#
# `grep` on this machine is ugrep, not GNU grep. Two consequences the gates must
# respect:
#   * inside `grep -E`, `\|` is a LITERAL PIPE, not alternation. Always write
#     `(from|import)`, never `(from\|import)`.
#   * grep exits 2 (not 1) when a path is missing, with empty stdout. A gate
#     phrased "grep returns empty" therefore PASSES before the work exists.
#     Use have_path/absent below, which distinguish the two.

set -euo pipefail

# Derived from this script's own location (repo/scripts/gates/_lib.sh -> repo -> workspace),
# so the gates work from any checkout and from any cwd. Override with WORKSPACE= if the
# two repos are not siblings.
_GATES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_REPO_ROOT="$(cd "$_GATES_DIR/../.." && pwd)"
WORKSPACE="${WORKSPACE:-$(dirname "$_REPO_ROOT")}"
HA="$WORKSPACE/home-assistant-rivian"
CLIENT="$WORKSPACE/rivian-python-client"

_fails=0
_passes=0

ok()   { printf '  \033[32mPASS\033[0m  %s\n' "$1"; _passes=$((_passes + 1)); }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; _fails=$((_fails + 1)); }
note() { printf '        %s\n' "$1"; }

# check <description> <exit-status>
check() { if [ "$2" -eq 0 ]; then ok "$1"; else bad "$1"; fi; }

# try <description> <command...> -- runs a command that is EXPECTED to fail
# sometimes. Never write `somecmd; check "..." $?` under `set -e`: the failing
# command aborts the gate before check() is reached, so a failing assertion
# looks like a crash instead of a FAIL line.
try() {
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then ok "$desc"; else bad "$desc"; fi
}

# contains <description> <pattern> <file> -- fixed-string match, path must exist
contains() {
  local desc="$1" pat="$2" file="$3"
  if [ ! -e "$file" ]; then bad "$desc  (missing: $file)"; return; fi
  if grep -qF -- "$pat" "$file"; then ok "$desc"; else bad "$desc"; fi
}

# absent <description> <ere> <dir> -- fails if dir is missing, so a not-yet-created
# path can never masquerade as "clean"
absent() {
  local desc="$1" ere="$2" dir="$3"
  if [ ! -d "$dir" ]; then bad "$desc  (missing dir: $dir)"; return; fi
  local hits
  # `|| true`: grep exits 1 on zero matches, which under `set -e` + `pipefail`
  # would abort the gate on the success case.
  hits=$( { grep -rnE -- "$ere" "$dir" || true; } | wc -l | tr -d ' ')
  if [ "$hits" -eq 0 ]; then ok "$desc"; else bad "$desc  ($hits matches)"; fi
}

have_path() {
  local desc="$1" path="$2"
  if [ -e "$path" ]; then ok "$desc"; else bad "$desc  (missing: $path)"; fi
}

# git_has <description> <repo> <revspec:path> <pattern>
git_has() {
  local desc="$1" repo="$2" rev="$3" pat="$4" tmp
  tmp=$(mktemp)
  if git -C "$repo" show "$rev" > "$tmp" 2>/dev/null && grep -qF -- "$pat" "$tmp"; then
    ok "$desc"
  else
    bad "$desc"
  fi
  rm -f "$tmp"
}

# on_branch <repo> <expected> -- guardrail; pre-release.yaml fires on dev and dev-*
on_branch() {
  local repo="$1" want="$2" got
  got=$(git -C "$repo" branch --show-current)
  if [ "$got" = "$want" ]; then ok "branch $(basename "$repo") = $want"
  else bad "branch $(basename "$repo") = $got (must be $want)"; fi
}

# test_count <repo> <floor> -- guards against "pytest green by deleting tests".
# Distinguishes an unusable interpreter from a genuinely shrunken suite: reporting
# "tests deleted" when pytest merely will not start is a false accusation, and the
# executor would chase the wrong problem. (The checked-in venv/ in
# home-assistant-rivian is currently broken — stale python3.13 interpreter path —
# so PYTEST must point at a rebuilt environment.)
test_count() {
  local repo="$1" floor="$2" py n
  py="${PYTEST:-}"
  if [ -z "$py" ]; then
    # repo convention here is venv/, not .venv/
    if   [ -x "$repo/venv/bin/pytest" ];  then py="$repo/venv/bin/pytest"
    elif [ -x "$repo/.venv/bin/pytest" ]; then py="$repo/.venv/bin/pytest"
    elif command -v pytest >/dev/null 2>&1; then py=pytest
    fi
  fi
  if [ -z "$py" ] || ! "$py" --version >/dev/null 2>&1; then
    bad "test count: pytest unavailable — set PYTEST=/path/to/pytest (env problem, NOT a deleted-test finding)"
    return
  fi
  n=$( { cd "$repo" && "$py" --collect-only -q 2>/dev/null | tail -1 | grep -oE '^[0-9]+'; } || echo 0)
  if [ "${n:-0}" -ge "$floor" ]; then ok "test count $n >= $floor"
  else bad "test count ${n:-0} < $floor (tests deleted to go green?)"; fi
}

summary() {
  printf '\n  %s: %d passed, %d failed\n' "${1:-gate}" "$_passes" "$_fails"
  [ "$_fails" -eq 0 ]
}
