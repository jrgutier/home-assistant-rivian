#!/usr/bin/env bash
# f3d — UserCoordinator and WallboxCoordinator poll on their own long schedule.
#
# The trap this gate is really about: `_set_update_interval` computes
# min(base * 2**error_count, 900) and NEVER reassigns the base. So a base above
# 900 is used verbatim at construction, collapses to 900 on the first error, and
# never climbs back -- a back-off that only ratchets downward.
#
# And the cheap green: asserting the class attribute. That passes while the poll
# still runs every 30 seconds, because what is scheduled is `update_interval`,
# which _set_update_interval assigns independently. Every assertion below that
# matters therefore reads the EFFECTIVE interval after a simulated error.

source "$(dirname "$0")/_lib.sh"

echo "f3d — long poll intervals, asserted effectively"

C="$HA/custom_components/rivian/coordinator.py"
T="$HA/tests/test_poll_intervals.py"

have_path "the f3d test module exists" "$T"

VENV_PY="$(resolve_python "$HA")"

# Both declare their own interval, it is at or below the cap, and it is not the
# base's. Read from the classes, not from the file's text.
"$VENV_PY" - "$HA" <<'PYEOF'
import sys
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, sys.argv[1])
from custom_components.rivian.coordinator import (  # noqa: E402
    RivianDataUpdateCoordinator,
    UserCoordinator,
    WallboxCoordinator,
)

CAP = 900
problems = []

for cls in (UserCoordinator, WallboxCoordinator):
    name = cls.__name__
    if "_update_interval_seconds" not in vars(cls):
        problems.append(f"{name}: still inherits the base interval")
        continue
    base = cls._update_interval_seconds
    if base <= RivianDataUpdateCoordinator._update_interval_seconds:
        problems.append(f"{name}: interval {base}s is not longer than the base")
    if base > CAP:
        problems.append(
            f"{name}: interval {base}s is ABOVE the {CAP}s cap -- it will collapse "
            f"to {CAP}s on the first error and never recover"
        )
    # The effective interval, which is the only one that schedules anything.
    for errors in (0, 1, 5):
        expected = min(base * 2**errors, CAP)
        if expected != base:
            problems.append(
                f"{name}: after {errors} errors the effective interval would be "
                f"{expected}s, not the declared {base}s"
            )

if problems:
    print("\n".join(problems))
    sys.exit(1)
print(f"UserCoordinator and WallboxCoordinator both at "
      f"{UserCoordinator._update_interval_seconds}s, stable across errors")
PYEOF
check "both declare a long interval that survives the back-off unchanged" $?

# The trap itself must still be documented in the code, not only in a test.
contains "coordinator.py records why the number is at the cap" \
         'never reassigns the base' "$C"

# Scope: the vehicle cadence is untouched.
"$VENV_PY" - "$HA" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from custom_components.rivian.coordinator import (  # noqa: E402
    ChargingCoordinator,
    DriverKeyCoordinator,
    RivianDataUpdateCoordinator,
    VehicleCoordinator,
)

want = {
    RivianDataUpdateCoordinator: 30,
    VehicleCoordinator: 900,
    DriverKeyCoordinator: 900,
    ChargingCoordinator: 0,
}
bad = [
    f"{cls.__name__}: {cls._update_interval_seconds}s, expected {n}s"
    for cls, n in want.items()
    if cls._update_interval_seconds != n
]
if bad:
    print("\n".join(bad)); sys.exit(1)
PYEOF
check "the other coordinators' cadences are unchanged" $?

for t in test_effective_interval_after_an_error_is_still_the_long_one \
         test_recovery_does_not_leave_it_faster_than_intended \
         test_a_base_above_the_cap_would_be_a_one_way_ratchet \
         test_the_vehicle_coordinator_cadence_is_untouched \
         test_capabilities_still_propagate_on_reload; do
  if grep -qF "def $t" "$T"; then ok "asserts: $t"
  else bad "missing required assertion: $t"; fi
done

PY="$(resolve_pytest "$HA")"
if [ ! -x "$PY" ]; then bad "pytest not found"; summary f3d; exit 1; fi
if (cd "$HA" && "$PY" tests/test_poll_intervals.py -q --no-cov \
      -p no:cacheprovider >/dev/null 2>&1); then
  ok "the f3d test module is green"
else
  bad "the f3d test module fails"
fi

out=$(cd "$HA" && "$PY" -q --no-cov -p no:cacheprovider 2>&1 || true)
note "$(echo "$out" | tail -1)"
if echo "$out" | grep -qE '^FAILED '; then bad "suite has failures"; else ok "suite green"; fi
test_count "$HA" 1387

summary f3d
