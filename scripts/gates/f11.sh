#!/usr/bin/env bash
# f11 -- the citation-drift gate. N9/N14/N20/N25 are the same defect
# recurring: a `file.py:N` citation in a comment or docstring goes stale the
# moment an unrelated edit shifts lines above it, and each time it was
# caught only at the next hand audit, by which point recovering intent cost
# a full read. This gate fails at the moment drift is INTRODUCED instead.
#
# --check (DEFAULT, and the only mode anything automated runs) reports and
# writes nothing. --fix is a human-run local opt-in that rewrites drifted
# citations AND atomically updates their sidecar row (see
# scripts/gates/helpers/citations.py's run_fix docstring for why atomic is
# load-bearing) -- read the diff before committing it.
#
# Ordered BEFORE ruff-format in .pre-commit-config.yaml: the formatter can
# rewrap a widened comment and re-drift a citation in the same file that
# THIS gate just fixed, in the same commit.
#
# Two corpora, different standing (see citations.py's module docstring):
#   in-code    (default) -- custom_components/, committed, CI-runnable.
#   plan       (--corpus plan) -- a local audit over BOTH plan documents
#              below, neither of which is in the repo's committed tree (one
#              under ~/.claude/plans/, one under gitignored .omc/plans/), so
#              this half is machine-local and never wired into CI or
#              pre-commit. It is bounds-checking, not content verification
#              (see plan_citations.py's module docstring for why, and for
#              the 11+ drifted-but-in-bounds citations a hand audit found
#              that this mode cannot see) -- its output is always labelled
#              UNVERIFIED, never PASS, so a clean run can't be misread as
#              "these citations are correct".

source "$(dirname "$0")/_lib.sh"

HELPERS="$(dirname "$0")/helpers"
PLAN_MD_1="${PLAN_MD_1:-$HOME/.claude/plans/lets-emulate-the-apk-memoized-summit.md}"
PLAN_MD_2="${PLAN_MD_2:-/Users/jrgutier/src/ha-rivian/.omc/plans/ralplan-audit-apk-parity-plan.md}"
VENV_PY="$(resolve_python "$HA")"

MODE="--check"
CORPUS="code"
for arg in "$@"; do
  case "$arg" in
    --check) MODE="--check" ;;
    --fix) MODE="--fix" ;;
    --list) MODE="--list" ;;
    --corpus=*) CORPUS="${arg#--corpus=}" ;;
    --corpus) : ;; # value comes as the next arg; handled by the loop below
    *) : ;;
  esac
done
# --corpus plan (space form)
prev=""
for arg in "$@"; do
  if [ "$prev" = "--corpus" ]; then CORPUS="$arg"; fi
  prev="$arg"
done

if [ ! -x "$VENV_PY" ] && ! command -v "$VENV_PY" >/dev/null 2>&1; then
  bad "no working python interpreter found (resolve_python)"
  summary F11
  exit 1
fi

if [ "$CORPUS" = "plan" ]; then
  echo "f11 --corpus plan -- local audit, NOT CI-bound (bounds-only; never a correctness signal)"
  plan_files=()
  for p in "$PLAN_MD_1" "$PLAN_MD_2"; do
    if [ -f "$p" ]; then
      plan_files+=("$p")
    else
      note "plan document not found at $p -- skipped (machine-local path)"
    fi
  done
  if [ "${#plan_files[@]}" -eq 0 ]; then
    note "no plan documents found -- arm skipped entirely"
    summary F11
    exit 0
  fi
  set +e
  out=$("$VENV_PY" "$HELPERS/plan_citations.py" "${plan_files[@]}")
  rc=$?
  set -e
  while IFS=$'\t' read -r tag loc target detail; do
    case "$tag" in
      UNRESOLVED|OUT-OF-BOUNDS) bad "$tag $loc $target :: $detail" ;;
      CENSUS) note "$loc" ;;
      UNVERIFIED) note "UNVERIFIED -- $loc" ;; # never `ok`: see plan_citations.py's docstring
    esac
  done <<< "$out"
  if [ "$rc" -eq 0 ]; then
    note "0 unresolved/out-of-bounds across ${#plan_files[@]} plan document(s) -- NOT evidence the citations are accurate, only that none are mechanically impossible"
  fi
  summary F11
  exit 0
fi

echo "f11 $MODE -- citation drift over custom_components/ (in-code corpus)"

case "$MODE" in
  --list)
    "$VENV_PY" "$HELPERS/citations.py" --list
    exit 0
    ;;
  --fix)
    out=$("$VENV_PY" "$HELPERS/citations.py" --fix)
    n="${out#FIXED	}"
    echo "$out"
    note "$n citation(s) rewritten and their sidecar rows updated -- READ THE DIFF, then run f11.sh --check"
    exit 0
    ;;
esac

# --check: translate each PASS/FAIL line from citations.py into ok/bad, and
# the trailing CENSUS line into the authority for every number below --
# nothing here is hand-written (a prior revision hard-coded "20 citations, 8
# stale" and both numbers were wrong).
# citations.py exits non-zero whenever anything is stale -- that is the
# expected, common case here, not a crash. Capture the status explicitly
# rather than letting `set -e` (sourced from _lib.sh) abort the gate on the
# assignment before a single PASS/FAIL line is printed.
set +e
out=$("$VENV_PY" "$HELPERS/citations.py" --check)
rc=$?
set -e

while IFS=$'\t' read -r tag loc target detail; do
  case "$tag" in
    PASS) ok "$loc -> $target" ;;
    FAIL) bad "$loc -> $target :: $detail" ;;
    CENSUS) note "$loc" ;; # CENSUS's own fields land in $loc since it has no tabs
  esac
done <<< "$out"

if [ "$rc" -ne 0 ]; then
  note "run 'scripts/gates/f11.sh --fix' to repair, then re-run --check and read the diff"
fi

summary F11
