#!/usr/bin/env bash
# S7 — client vendored into custom_components/rivian/rivian_client/.
#
# The first draft of this gate was:
#     grep -rnE '^\s*(from\|import) rivian\b' custom_components/
# which returns 0 matches against a tree with 20 real violations, because `\|`
# inside grep -E is a literal pipe. It would have marked S7 complete without a
# single file being moved. Hence the alternation fix below, and hence the
# positive assertions: an absence is always satisfiable by deleting.

source "$(dirname "$0")/_lib.sh"

echo "S7 — client vendored, no top-level 'rivian' imports"

on_branch "$HA" vendor-client

# Negative: no module imports the client as a top-level package any more.
# ^[[:space:]]* (not ^) so indented imports inside functions and try: blocks count.
absent "no top-level 'rivian' imports remain" \
       '^[[:space:]]*(from|import) rivian\b' \
       "$HA/custom_components"

# Positive 1: the vendored package actually exists and is substantial.
VC="$HA/custom_components/rivian/rivian_client"
if [ -d "$VC" ]; then
  n=$(find "$VC" -name '*.py' | wc -l | tr -d ' ')
  if [ "$n" -ge 20 ]; then ok "vendored package has $n modules (>= 20)"
  else bad "vendored package has only $n modules — expected >= 20"; fi
else
  bad "vendored package missing: $VC"
fi

# Positive 2: every vendored module imports individually, under only the
# requirements the manifest declares at this phase. Catches a missed rewrite
# that resolves locally because a stale PyPI 'rivian' is installed.
# The SYSTEM python has neither Home Assistant nor aiohttp, so it would fail
# every import for environment reasons and read as 28 broken modules.
PY="$(resolve_pytest "$HA")"; PY="${PY%/pytest}/python"
if [ -d "$VC" ]; then
  failed=0
  while IFS= read -r f; do
    mod=$(python3 -c "import sys,os;p=os.path.relpath(sys.argv[1],sys.argv[2])[:-3];print(p.replace('/','.'))" "$f" "$HA")
    if ! (cd "$HA" && "$PY" -c "import $mod" >/dev/null 2>&1); then
      note "cannot import: $mod"; failed=$((failed + 1))
    fi
  done < <(find "$VC" -name '*.py' ! -name '__pycache__')
  check "every vendored module imports cleanly" $([ "$failed" -eq 0 ] && echo 0 || echo 1)
fi

# The manifest must declare what we import and HA core does not guarantee.
# bleak always; protobuf only until Phase 4.4 (S10) removes it.
MAN="$HA/custom_components/rivian/manifest.json"
contains "manifest declares bleak" 'bleak' "$MAN"
contains "manifest declares the interim protobuf pin" 'protobuf' "$MAN"

# Coverage is now two populations with separate floors; --cov-fail-under
# cannot express that.
# Runs pytest itself rather than trusting a coverage.json some earlier gate may
# have left behind -- a stale artifact makes this pass or fail for the wrong tree.
try "both coverage floors hold" \
  bash -c "cd '$HA' && .venv/bin/pytest -q >/dev/null 2>&1; .venv/bin/python scripts/check_coverage.py"

summary S7
