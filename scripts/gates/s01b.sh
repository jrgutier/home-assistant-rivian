#!/usr/bin/env bash
# S1b — the suite is green in a FULL run, not merely in isolation.
#
# Ten failures currently pass individually and fail together: five test modules
# permanently replace the client in sys.modules at import time with no teardown,
# and alphabetical collection lets test_update's bare Mock() clobber
# test_coordinator_base's carefully-built one. pytest.raises() then gets a Mock.
#
# This gate deliberately runs the WHOLE suite. A per-file run would pass while
# the defect is still present — which is the entire point.

source "$(dirname "$0")/_lib.sh"

echo "S1b — suite green in a full run"

PY="$(resolve_pytest "$HA")"   # never hardcode venv/: see resolve_pytest
if [ ! -x "$PY" ]; then bad "pytest not found at $PY"; summary S1b; exit 1; fi

pytest_green "$HA" "$PY" "full run"

# The root cause must be gone, not worked around by reordering or skipping.
absent "no module-level sys.modules assignment in tests" \
       '^[[:space:]]*sys\.modules\[' "$HA/tests"

# The skip check that stood here read `$out`, which pytest_green now owns; it
# also used the anchored regex that could never match. pytest_green does this
# check for every gate -- see _lib.sh.

# Ordering independence: the pair that currently breaks must pass together.
if (cd "$HA" && "$PY" tests/test_update.py tests/test_coordinator_base.py \
      -q -p no:cacheprovider --no-cov >/dev/null 2>&1); then
  ok "test_update + test_coordinator_base pass together (the canary pair)"
else
  bad "canary pair still order-dependent"
fi

summary S1b
