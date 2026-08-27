#!/usr/bin/env bash
# S12b — release hardening. BOTH workflows; pre-release fires on every dev push
# and what it publishes is what beta users install.
source "$(dirname "$0")/_lib.sh"
echo "S12b — release hardening"

REL="$HA/.github/workflows/release.yaml"
PRE="$HA/.github/workflows/pre-release.yaml"
TEST="$HA/.github/workflows/test.yaml"

# Inspect the shell these workflows RUN, not their raw text. Every comment in
# them names the bug it fixed, so a raw grep finds the description of the fix and
# reports the bug still present -- six gates in this project were defeated exactly
# that way. workflow_runs.py also joins backslash continuations, without which
# `zip ... \` + `-i '*.py'` matches neither line.
PY_BIN="$(resolve_pytest "$HA")"; PY_BIN="${PY_BIN%/pytest}/python"
runs_of() { "$PY_BIN" "$HA/scripts/gates/workflow_runs.py" "$1"; }

# --- the zips ----------------------------------------------------------------
for f in "$REL" "$PRE"; do
  b=$(basename "$f")
  runs=$(runs_of "$f")
  if echo "$runs" | grep -qE "^[[:space:]]*zip .*(-x|-i) "; then
    ok "$b zip has an allow/deny list"
  else bad "$b still does a bare recursive zip"; fi
  if echo "$runs" | grep -q 'scan_artifact.sh'; then
    ok "$b scans the artifact before publishing"
  else bad "$b publishes without scanning"; fi
done

# --- release.yaml's version rewrite ------------------------------------------
rel_runs=$(runs_of "$REL")
# The old rewrite was `sed -i '/version/c\...'`, which replaces EVERY line
# containing the substring "version" rather than the version key.
if echo "$rel_runs" | grep -qE "sed -i.*/version/c"; then
  bad "release.yaml version rewrite is unanchored (hits every line containing 'version')"
else ok "release.yaml version rewrite anchored"; fi
if echo "$rel_runs" | grep -qE "sed -i.*\^VERSION = " || echo "$rel_runs" | grep -q "jq --arg v"; then
  ok "release.yaml edits the version key, not lines mentioning it"
else bad "release.yaml no longer rewrites the version at all"; fi
# GitHub disabled ::set-output in 2023; a step still using it sets nothing.
if echo "$rel_runs" | grep -q '::set-output'; then
  bad "release.yaml uses ::set-output, which GitHub disabled — the step sets nothing"
else ok "release.yaml uses \$GITHUB_OUTPUT"; fi

# --- the shared scripts exist and work ---------------------------------------
have_path "scan_artifact.sh exists" "$HA/scripts/scan_artifact.sh"
have_path "load_test.sh exists" "$HA/scripts/load_test.sh"
test_runs=$(runs_of "$TEST")
if echo "$test_runs" | grep -q 'load_test.sh' && echo "$test_runs" | grep -q 'scan_artifact.sh'; then
  ok "CI runs both on every push"
else
  bad "test.yaml does not run the load test and artifact scan"
fi
for f in "$REL" "$PRE" "$TEST"; do
  b=$(basename "$f")
  runs=$(runs_of "$f")
  if echo "$runs" | grep -Fq "'*.js'"; then
    ok "$b zip includes *.js (Gear Guard card)"
  else
    bad "$b zip omits *.js — Lovelace card would not ship"
  fi
done

# --- positive assertions: actually build one and check it --------------------
# An absence is always satisfiable by deleting; these run the real thing.
ZIP="$(mktemp -d)/rivian.zip"
if (cd "$HA/custom_components/rivian" && zip -q -r "$ZIP" ./ \
      -i '*.py' '*.json' '*.js' '*.graphql' '*.proto' '*.yaml' 'py.typed'); then
  try "built artifact passes the secret/content scan" \
      bash "$HA/scripts/scan_artifact.sh" "$ZIP"
else
  bad "could not build the artifact"
fi
try "artifact imports under only the manifest's requirements" \
    bash "$HA/scripts/load_test.sh"

# --- the on: blocks are immutable --------------------------------------------
# S12b legitimately edits jobs:, so a blanket "don't touch .github" is not
# available -- but a loop blocked on a gate must not be able to neuter the
# trigger instead.
drift=0
for f in "$REL" "$PRE" "$TEST"; do
  b=$(basename "$f")
  if ! diff -q <(cd "$HA" && git show "origin/vendor-client:.github/workflows/$b" 2>/dev/null \
                   | awk '/^on:/,/^jobs:/') \
                <(awk '/^on:/,/^jobs:/' "$f") >/dev/null 2>&1; then
    # No pushed baseline to compare against is not a pass; fall back to HEAD.
    if ! diff -q <(cd "$HA" && git show "HEAD:.github/workflows/$b" 2>/dev/null \
                     | awk '/^on:/,/^jobs:/') \
                  <(awk '/^on:/,/^jobs:/' "$f") >/dev/null 2>&1; then
      note "on: block changed in $b"; drift=$((drift + 1))
    fi
  fi
done
check "workflow on: blocks unchanged" "$drift"

summary S12b
