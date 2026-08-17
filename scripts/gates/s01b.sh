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

PY="${PYTEST:-$HA/venv/bin/pytest}"
if [ ! -x "$PY" ]; then bad "pytest not found at $PY"; summary S1b; exit 1; fi

out=$(cd "$HA" && "$PY" -q -p no:cacheprovider --no-cov 2>&1 || true)
line=$(echo "$out" | tail -1)
note "$line"

fails=$(echo "$out" | { grep -cE '^FAILED ' || true; })
if [ "$fails" -eq 0 ]; then ok "no failures in a full run"
else bad "$fails failing tests in a full run"; fi

# The root cause must be gone, not worked around by reordering or skipping.
absent "no module-level sys.modules assignment in tests" \
       '^[[:space:]]*sys\.modules\[' "$HA/tests"

if echo "$out" | grep -qE '^[0-9]+ (skipped|deselected)'; then
  bad "tests skipped/deselected — not a legitimate fix"
else
  ok "nothing skipped or deselected"
fi

# Ordering independence: the pair that currently breaks must pass together.
if (cd "$HA" && "$PY" tests/test_update.py tests/test_coordinator_base.py \
      -q -p no:cacheprovider --no-cov >/dev/null 2>&1); then
  ok "test_update + test_coordinator_base pass together (the canary pair)"
else
  bad "canary pair still order-dependent"
fi

summary S1b
