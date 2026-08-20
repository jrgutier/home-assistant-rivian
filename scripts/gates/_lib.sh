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
  # -I skips binary files and --exclude-dir skips caches: stale __pycache__ .pyc
  # files still hold old docstrings and were reported as live source matches,
  # failing a gate whose source tree was actually clean. (Only under bash's
  # /usr/bin/grep -- the interactive zsh here uses ugrep, which skips binaries by
  # default, so this reproduced in CI-shaped runs and not by hand.)
  hits=$( { grep -rnE -I --exclude-dir=__pycache__ --exclude-dir=.git \
              -- "$ere" "$dir" || true; } | wc -l | tr -d ' ')
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

# not_publishing_branch <repo> -- the same guardrail, keyed to what it protects
# rather than to a branch name that expired.
#
# s01/s05/s07 called `on_branch "$repo" vendor-client`. That branch is gone -- its
# PRD (vendor-rivian-client-parallax) completed, all 20 stories passes:true -- so
# those three gates could not pass on ANY current branch. Three permanent reds in a
# sweep is how a real failure gets lost, which is the same defect class as the
# `^FAILED ` verdict bug fixed alongside this.
#
# The NAME expired; the INTENT did not. prd.json's _guardrails give the reason:
# "pre-release.yaml fires on dev and dev-* and publishes a zip beta users install."
# The rule was never "be on vendor-client" -- it was "do not do this work on a
# branch that ships to users". That is what is asserted here.
#
# Consequence, deliberate: running these gates on dev FAILS. Verification sweeps
# belong on the feature branch; that is the guardrail working, not a regression.
not_publishing_branch() {
  local repo="$1" got
  got=$(git -C "$repo" branch --show-current)
  case "$got" in
    dev|dev-*)
      bad "branch $(basename "$repo") = $got -- dev and dev-* publish a beta zip to users" ;;
    "")
      bad "branch $(basename "$repo") is detached -- cannot confirm it does not publish" ;;
    *)
      ok "branch $(basename "$repo") = $got (does not publish)" ;;
  esac
}

# test_count <repo> <floor> -- guards against "pytest green by deleting tests".
# Distinguishes an unusable interpreter from a genuinely shrunken suite: reporting
# "tests deleted" when pytest merely will not start is a false accusation, and the
# executor would chase the wrong problem. (The checked-in venv/ in
# home-assistant-rivian is currently broken — stale python3.13 interpreter path —
# so PYTEST must point at a rebuilt environment.)
# Resolve a WORKING pytest for a repo. Prefers whichever interpreter can actually
# import the test suite, because a stale venv/ that merely EXISTS is worse than none:
# it makes gates fail with findings-shaped messages that are really env problems.
resolve_pytest() {
  local repo="$1" py
  for py in ${PYTEST:-} "$repo/.venv/bin/pytest" "$repo/venv/bin/pytest"; do
    [ -n "$py" ] && [ -x "$py" ] || continue
    if "$py" --collect-only -q --no-cov >/dev/null 2>&1 || \
       { cd "$repo" && "$py" --collect-only -q --no-cov >/dev/null 2>&1; }; then
      echo "$py"; return 0
    fi
  done
  # nothing collects; fall back to the first that at least runs, so callers can
  # still report a specific failure rather than a missing path
  for py in "$repo/.venv/bin/pytest" "$repo/venv/bin/pytest"; do
    [ -x "$py" ] && { echo "$py"; return 0; }
  done
  return 1
}

# resolve_python <repo> -- the interpreter that can import the package under test.
# The system python3 cannot: const.py and every platform module import
# homeassistant. A gate that shells out to `python3` to inspect the entity tables
# therefore dies with ModuleNotFoundError, which reads as a finding and is not
# one.
resolve_python() {
  local repo="$1" py
  py="$(dirname "$(resolve_pytest "$repo")")/python"
  if [ -x "$py" ]; then echo "$py"; else echo python3; fi
}

test_count() {
  local repo="$1" floor="$2" py n
  # Try every candidate interpreter and use the first that actually yields a count.
  #
  # Previously this preferred "$repo/venv" over "$repo/.venv" and stopped there. A
  # STALE venv/ (present, pytest --version fine, but its deps predate the current
  # client) collects nothing, stderr was discarded, and the gate reported
  # "test count 0 < 301 (tests deleted to go green?)" against a tree with 987
  # passing tests. The existing guard only caught a MISSING pytest, not a broken
  # one -- and a false "tests deleted" accusation is worse than a missing gate.
  for py in ${PYTEST:-} "$repo/.venv/bin/pytest" "$repo/venv/bin/pytest" pytest; do
    [ -n "$py" ] || continue
    command -v "$py" >/dev/null 2>&1 || [ -x "$py" ] || continue
    "$py" --version >/dev/null 2>&1 || continue
    n=$( { cd "$repo" && "$py" --collect-only -q 2>/dev/null | tail -1 | grep -oE '^[0-9]+'; } || true)
    [ -n "${n:-}" ] && break
  done
  if [ -z "${n:-}" ]; then
    bad "test count: no pytest could collect in $repo -- set PYTEST=/path/to/pytest (ENVIRONMENT problem, NOT a deleted-test finding)"
    return
  fi
  if [ "$n" -ge "$floor" ]; then ok "test count $n >= $floor"
  else bad "test count $n < $floor (tests deleted to go green?)"; fi
}

# pytest_green <repo> <pytest-binary> <label> [extra pytest args...]
#
# Runs the suite and judges it by pytest's EXIT STATUS, then checks for skips.
# Replaces the idiom that stood in thirteen gates:
#
#     out=$(cd "$HA" && "$PY" -q --no-cov -p no:cacheprovider 2>&1 || true)
#     if echo "$out" | grep -qE '^FAILED '; then bad ...; else ok "suite green"; fi
#
# TWO DEFECTS, both measured, both fixed here rather than thirteen times over.
#
# 1. `^FAILED ` CANNOT SEE A SUITE THAT NEVER RAN. A collection error prints
#    `ERROR path/to/test.py`, `Interrupted: 1 error during collection` and
#    `1 error in 0.14s` -- and no `FAILED ` line at all. The grep matched zero,
#    the gate reported "suite green", and the suite had not run. Same for an
#    import error, a bad -k, or an interrupt. The `|| true` is what made this
#    possible: it discarded the one signal that was already correct. The exit
#    status is now the verdict, and the output is only used for detail.
#
# 2. THE SKIP REGEX WAS ANCHORED AND COULD NEVER MATCH. `^[0-9]+ (skipped|
#    deselected)` never fires, because `pytest -q` prints "22 passed, 1 skipped
#    in 0.5s" -- the passed count comes first. Skips were tolerated silently in
#    every gate that used it. Unanchored here, as s15 already does.
#
# Callers keep their own test_count floor; that check is orthogonal and catches
# a different failure (tests deleted to go green).
pytest_green() {
  local repo="$1" py="$2" label="$3"; shift 3
  local out rc
  # No `|| true`: we WANT the status. set -e is scoped off for this one call so
  # a red suite is reported by the gate rather than aborting it mid-run.
  set +e
  out=$(cd "$repo" && "$py" -q --no-cov -p no:cacheprovider "$@" 2>&1)
  rc=$?
  set -e
  note "$(echo "$out" | tail -1)"
  if [ "$rc" -eq 0 ]; then
    ok "$label passed (pytest exit 0)"
  else
    bad "$label FAILED (pytest exit $rc)"
    # Surface the reason: a collection error names no FAILED line, so printing
    # the matching lines is the only way the operator learns which mode it was.
    #
    # `|| true` is LOAD-BEARING, and its absence was a real bug: pytest exit 4
    # (a node id that no longer exists) and exit 5 (no tests ran) are non-zero
    # but print NO matching line, so grep exited 1, pipefail propagated it, and
    # errexit killed the whole gate right here -- every later section and the
    # summary silently skipped, leaving one FAIL line and no verdict. A helper
    # written to stop gates lying about failures was itself hiding them.
    #
    # `Interrupted` is unanchored: pytest prints it as
    # `!!!!!!!! Interrupted: 1 error during collection !!!!!!!!`, so `^Interrupted`
    # could never match.
    { echo "$out" | grep -E '^(FAILED|ERROR) |Interrupted:' | head -5 || true; } \
      | while IFS= read -r l; do note "  $l"; done
  fi
  if echo "$out" | grep -qE '[0-9]+ (skipped|deselected)'; then
    bad "$label: tests skipped or deselected"
  else
    ok "$label: nothing skipped or deselected"
  fi
}

summary() {
  printf '\n  %s: %d passed, %d failed\n' "${1:-gate}" "$_passes" "$_fails"
  [ "$_fails" -eq 0 ]
}
