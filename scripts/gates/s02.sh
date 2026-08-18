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
  # Lock file depends on the build backend: poetry.lock before the uv migration,
  # uv.lock after. Check whichever exists rather than hardcoding one.
  LOCK=""
  [ -f "$CLIENT/uv.lock" ] && LOCK="$CLIENT/uv.lock"
  [ -z "$LOCK" ] && [ -f "$CLIENT/poetry.lock" ] && LOCK="$CLIENT/poetry.lock"
  if grep -q 'pytest-cov' "$CLIENT/pyproject.toml" && [ -n "$LOCK" ] && grep -qE '^name = "pytest-cov"' "$LOCK"; then
    ok "client ci.yaml uses --cov, pytest-cov declared + locked in $(basename "$LOCK")"
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
PY="$(resolve_pytest "$HA")"   # never hardcode venv/: see resolve_pytest
RUFF="uvx ruff@latest"   # NOT pinned by choice (s05 review): the gate must run
                         # what a fresh checkout resolves, not a frozen version
# Blocking repo-wide. The "25 pre-existing errors" that once justified deferring
# custom_components/ were REAL findings under a newer ruff and are now fixed; the
# pinned version, so there is no debt and no deferral.
try "ruff check passes (repo-wide)"        env -C "$HA" $RUFF check .
try "ruff format --check passes (repo-wide)" env -C "$HA" $RUFF format --check .
if [ -x "$PY" ]; then
  try "pytest passes with the coverage floor" env -C "$HA" "$PY" -q
else
  bad "pytest not found at $PY"
fi

summary S2
