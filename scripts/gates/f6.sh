#!/usr/bin/env bash
# f6 — every sendable command the app declares is in the enum, and every command
# that is NOT wired has a written reason.
#
# The pressure here runs the other way from most gates: the temptation is to wire
# everything, or to delete what the current app does not name. Both are wrong.
# Wiring the seven generateInvalidCloudDataWrapper commands blind yields dead
# controls -- the exact defect that shipped eleven of them once. Deleting the
# seven the app does not name repeats the tonneau inference, which is falsified.

source "$(dirname "$0")/_lib.sh"

echo "f6 — command coverage"

DOC="$HA/docs/development/COMMAND_COVERAGE.md"
T="$HA/tests/test_apk_transcription.py"

have_path "the decisions are recorded" "$DOC"
if git -C "$HA" ls-files --error-unmatch docs/development/COMMAND_COVERAGE.md \
     >/dev/null 2>&1; then
  ok "the doc is tracked"
else
  bad "the doc is not tracked"
fi

VENV_PY="$(resolve_python "$HA")"

"$VENV_PY" - "$HA" <<'PYEOF'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from custom_components.rivian.button import BUTTONS  # noqa: E402
from custom_components.rivian.rivian_client import VehicleCommand  # noqa: E402
from tests.apk.transcription import (  # noqa: E402
    INVALID_WRAPPER_COMMANDS,
    SENDABLE_COMMANDS,
)

ours = {c.value for c in VehicleCommand}
problems = []

unqueued = SENDABLE_COMMANDS - ours
if unqueued:
    problems.append(f"sendable but absent from VehicleCommand: {sorted(unqueued)}")

# INVERTED by owner ruling 11 (2026-08-19). Until then this asserted the seven
# generateInvalidCloudDataWrapper commands were ABSENT from the enum. Ruling 11
# adds them so f7 can send them through probe_vehicle_command.py, which raises on
# a non-member. The half that dies is "not in the enum". The half that SURVIVES,
# and is the real invariant, is "in the enum and wired to no entity" -- wiring
# them blind is the defect that shipped eleven dead controls once.
absent_members = INVALID_WRAPPER_COMMANDS - ours
if absent_members:
    problems.append(
        f"invalid-wrapper commands missing from the enum: {sorted(absent_members)}. "
        "Owner ruling 11 requires them present so f7 can send them."
    )

_platform_src = "".join(
    (Path(sys.argv[1]) / "custom_components/rivian" / name).read_text()
    for name in ("select.py", "switch.py", "button.py", "cover.py",
                 "number.py", "climate.py", "lock.py")
)
wired_blind = sorted(c for c in INVALID_WRAPPER_COMMANDS if c in _platform_src)
if wired_blind:
    problems.append(
        f"invalid-wrapper commands were wired to an entity: {wired_blind}. "
        "They are enum members so f7 can send them by hand; wiring them blind "
        "is how eleven dead controls shipped once."
    )

# The seven the app does not name must survive.
KEPT = {
    "CABIN_HVAC_THIRD_ROW_LEFT_SEAT_HEAT", "CABIN_HVAC_THIRD_ROW_RIGHT_SEAT_HEAT",
    "HONK_AND_FLASH_LIGHTS", "UNLOCK_ALL_AND_OPEN_WINDOWS", "UNLOCK_DRIVER_DOOR",
    "UNLOCK_PASSENGER_DOOR", "UNLOCK_USER_PREFERENCES_AND_DISABLE_ALARM",
}
lost = KEPT - ours
if lost:
    problems.append(
        f"commands removed without a recorded live failure: {sorted(lost)}"
    )

# Closure-openers must be disabled by default.
by_key = {d.key: d for group in BUTTONS.values() for d in group}
for key in ("open_tailgate", "open_liftgate"):
    d = by_key.get(key)
    if d is None:
        problems.append(f"{key} is not wired")
    elif d.entity_registry_enabled_default is not False:
        problems.append(f"{key} ships ENABLED -- it moves a closure and is untested")

if problems:
    print("\n".join(problems)); sys.exit(1)
print(f"{len(ours)} commands; all {len(SENDABLE_COMMANDS)} sendable ones present")
PYEOF
check "every sendable command present, the seven present-but-unwired, none lost" $?

# Every unwired command has a reason IN THE DOC, by name.
"$VENV_PY" - "$HA" <<'PYEOF'
import sys
from pathlib import Path
repo = Path(sys.argv[1]); sys.path.insert(0, str(repo))
from tests.apk.transcription import INVALID_WRAPPER_COMMANDS  # noqa: E402

text = (repo / "docs/development/COMMAND_COVERAGE.md").read_text()
KEPT = {
    "CABIN_HVAC_THIRD_ROW_LEFT_SEAT_HEAT", "CABIN_HVAC_THIRD_ROW_RIGHT_SEAT_HEAT",
    "HONK_AND_FLASH_LIGHTS", "UNLOCK_ALL_AND_OPEN_WINDOWS", "UNLOCK_DRIVER_DOOR",
    "UNLOCK_PASSENGER_DOOR", "UNLOCK_USER_PREFERENCES_AND_DISABLE_ALARM",
}
missing = [c for c in sorted(INVALID_WRAPPER_COMMANDS | KEPT | {
    "START_GEAR_GUARD_MASTER_SESSION"}) if c not in text]
if missing:
    print("undocumented:", missing); sys.exit(1)
PYEOF
check "every unwired command is named in the doc" $?

contains "the doc cites class:line for the invalid-wrapper seven" \
         'VASCommand.java:476' "$DOC"
contains "the doc refuses deprecation-by-absence" \
         'false provenance' "$DOC"
contains "the doc records why the count is seven and not eight" \
         'Companion' "$DOC"

# The client edit must be mirrored; s14 holds them byte identical.
if [ -f "$HA/scripts/gates/s14.sh" ]; then
  if bash "$HA/scripts/gates/s14.sh" >/dev/null 2>&1; then
    ok "s14 (vendored client byte identity) still green"
  else
    bad "s14 fails -- the sibling repo did not get the same const.py edit"
  fi
fi

for t in test_the_two_new_closure_openers_are_wired \
         test_both_ship_disabled_by_default \
         test_the_dedicated_commands_are_distinct_from_the_combined_one \
         test_both_have_a_translation \
         test_start_gear_guard_master_session_is_declared_but_unwired \
         test_the_invalid_wrapper_seven_are_still_unwired \
         test_the_seven_apk_absent_commands_are_still_here; do
  if grep -qF "def $t" "$T"; then ok "asserts: $t"
  else bad "missing required assertion: $t"; fi
done

PY="$(resolve_pytest "$HA")"
out=$(cd "$HA" && "$PY" -q --no-cov -p no:cacheprovider 2>&1 || true)
note "$(echo "$out" | tail -1)"
if echo "$out" | grep -qE '^FAILED '; then bad "suite has failures"; else ok "suite green"; fi
test_count "$HA" 1518

summary f6
