#!/usr/bin/env bash
# S2 — CI reaches the working branch, and its checks pass locally.
#
# "and green" cannot be a gate: the guardrails forbid the loop pushing, so a real
# CI run can never legitimately be observed from here. Assert the workflow exists,
# triggers on vendor-client, and that the checks it runs pass locally instead.
#
# Correction to an earlier draft: the client repo ALREADY had ci.yaml (ruff, mypy,
# pytest on 3.9-3.13). It triggered on main only. The task was extending it, not
# creating it. The HA repo genuinely had no test workflow.

source "$(dirname "$0")/_lib.sh"

echo "S2 — CI on vendor-client"

CI="$CLIENT/.github/workflows/ci.yaml"
have_path "client ci.yaml exists"                 "$CI"
contains  "client ci.yaml triggers on vendor-client" 'vendor-client' "$CI"
# NOT a grep for "--cov". The first version of this gate did exactly that and passed
# a workflow that could never run: --cov was added while pytest-cov was absent from
# both pyproject.toml and poetry.lock, so pytest exits 4 with "unrecognized arguments"
# before collecting. Assert the flags and the dependency agree instead.
# strip comments first — an explanatory comment mentioning --cov is not a flag
if grep -v '^\s*#' "$CI" | grep -q -- '--cov'; then
  if grep -q 'pytest-cov' "$CLIENT/pyproject.toml" && grep -qE '^name = "pytest-cov"' "$CLIENT/poetry.lock"; then
    ok "client ci.yaml uses --cov and pytest-cov is declared + locked"
  else
    bad "client ci.yaml uses --cov but pytest-cov is not declared/locked (pytest would exit 4)"
  fi
else
  ok "client ci.yaml uses no coverage flags (consistent: pytest-cov is not a dependency)"
fi

HAWF="$HA/.github/workflows/test.yaml"
have_path "HA test workflow created"              "$HAWF"
contains  "HA workflow triggers on vendor-client" 'vendor-client' "$HAWF"

# Must not fire on PUSH to dev/dev-*, where pre-release.yaml publishes a beta zip.
# A pull_request trigger targeting dev is fine and desirable — it runs no publish.
push_block=$(awk '/^  push:/{f=1;next} /^  [a-z_]+:/{f=0} f' "$HAWF")
if printf '%s' "$push_block" | grep -qE '^\s*- dev'; then
  bad "HA test workflow PUSHES on dev/dev-* (pre-release.yaml territory)"
else
  ok "HA test workflow has no dev/dev-* push trigger"
fi

# The checks the workflow runs, run here.
PY="${PYTEST:-$HA/venv/bin/pytest}"
RUFF="$HA/venv/bin/python -m ruff"
# Blocking scope is tests/ only. custom_components/ has 25 pre-existing ruff errors
# and 5 unformatted files; s02b cleans them AFTER the merges, so the loop does not
# lint code that s03/s05 are about to rewrite.
try "ruff check passes (tests/)"        env -C "$HA" $RUFF check tests/
try "ruff format --check passes (tests/)" env -C "$HA" $RUFF format --check tests/
n=$( { env -C "$HA" $RUFF check custom_components/ 2>/dev/null | grep -cE '^\s*--> ' || true; } )
note "custom_components/ ruff errors outstanding: $n (deferred to s02b, informational)"
if [ -x "$PY" ]; then
  try "pytest passes with the coverage floor" env -C "$HA" "$PY" -q
else
  bad "pytest not found at $PY"
fi

summary S2
