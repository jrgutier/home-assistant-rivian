#!/usr/bin/env bash
# S6b — watchdog de-duplicated, diagnostics extended.
#
# The previous version only NOTED the watchdog reference count and asserted
# nothing, so it passed against the triplicated code it was written to catch.
source "$(dirname "$0")/_lib.sh"
echo "S6b — watchdog dedup + diagnostics"

C="$HA/custom_components/rivian/coordinator.py"

# Each piece of the watchdog must be defined exactly ONCE, on the base class.
for fn in _start_watchdog _stop_watchdog _watchdog_tick; do
  n=$( { grep -cE "^    (async )?def ${fn}\\(" "$C" || true; } )
  if [ "$n" -eq 1 ]; then ok "$fn defined once"
  else bad "$fn defined $n times (expected 1)"; fi
done

# The one deliberate difference survives as an override, not a copied loop.
contains "the sleep skip survives as an override" '_watchdog_skip_reason' "$C"

# Behaviour, not just shape: a stale subscription restarts and a fresh one does not.
try "the watchdog contract tests pass" \
  bash -c "cd '$HA' && .venv/bin/pytest tests/test_watchdog_contract.py -q --no-cov"

contains "diagnostics includes Parallax" 'parallax' "$HA/custom_components/rivian/diagnostics.py"
try "diagnostics tests pass" \
  bash -c "cd '$HA' && .venv/bin/pytest tests/test_diagnostics.py -q --no-cov"

summary S6b
