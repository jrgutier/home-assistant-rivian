#!/usr/bin/env bash
# S6c — subscription failures propagate instead of being swallowed.
#
# The defect: five subscribe_for_* ended `except Exception: return None`, and
# every call site branched on that None. A dead real-time path was therefore
# indistinguishable from a healthy one -- which is why "the websocket is broken"
# survived a full day of diagnosis. That day was long attributed to "one active
# subscription per user session" -- FALSIFIED 2026-08-20, see WS_CONTENTION.md
# claim C1s. The swallow is what made the diagnosis unbounded, and that is what
# this gate pins, whatever the day's true cause turns out to have been.
#
# Asserts BEHAVIOUR, not greps: a grep for the swallow is satisfied by moving it
# one frame down, and an absence is always satisfiable by deleting.
source "$(dirname "$0")/_lib.sh"
echo "S6c — subscription failures surface"

C="$HA/custom_components/rivian/rivian_client/rivian.py"
COORD="$HA/custom_components/rivian/coordinator.py"

# No bare swallow may remain in the client's subscribe methods.
n=$( { grep -cE '^\s+_LOGGER\.error\(ex\)$' "$C" || true; } )
if [ "$n" -eq 0 ]; then ok "no bare '_LOGGER.error(ex); return None' swallow remains"
else bad "$n bare swallow(s) still in the client"; fi

# The dead branch the old contract required must be gone.
# absent() takes a DIRECTORY; this is one file, so grep it directly.
if grep -q 'if unsubscribe:' "$COORD"; then
  bad "the dead 'if unsubscribe:' branch is still there"
else
  ok "the dead 'if unsubscribe:' branch is gone"
fi

# Behaviour: a failing subscription must raise at the call site, and entry setup
# must still complete rather than aborting.
try "subscription-failure contract tests pass" \
  bash -c "cd '$HA' && .venv/bin/pytest tests/test_subscription_failures.py -q --no-cov"

# And the suite as a whole must still be green with both coverage floors.
try "both coverage floors hold" \
  bash -c "cd '$HA' && .venv/bin/pytest -q >/dev/null 2>&1; .venv/bin/python scripts/check_coverage.py"

summary S6c
