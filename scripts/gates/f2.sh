#!/usr/bin/env bash
# f2 — the five accepted-but-never-populated fields are investigated, not deleted.
#
# This gate exists to make a NON-removal auditable. Every other gate here guards
# against a change going wrong; this one guards against a change being made at
# all, because the pressure is real: four validity binary sensors and one
# notification sensor read `unavailable` forever, and deleting them would look
# like tidying.
#
# It is not tidying. The server accepts all five -- it validates the subscription
# document name by name and rejects the WHOLE thing on one unknown name, and the
# live subscription carries all 124 -- so these are empty, not wrong. Removal
# needs a live failure, and "never carried a value" is silence.

source "$(dirname "$0")/_lib.sh"

echo "f2 — unpopulated fields investigated and kept"

DOC="$HA/docs/development/UNPOPULATED_FIELDS.md"
CONST="$HA/custom_components/rivian/const.py"
T="$HA/tests/test_apk_transcription.py"

have_path "the finding is recorded" "$DOC"
if git -C "$HA" ls-files --error-unmatch docs/development/UNPOPULATED_FIELDS.md \
     >/dev/null 2>&1; then
  ok "the finding is tracked in git"
else
  bad "the finding is not tracked"
fi

VENV_PY="$(resolve_python "$HA")"

# All five still subscribed, checked against const.py rather than the doc.
"$VENV_PY" - "$HA" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from custom_components.rivian.const import VEHICLE_STATE_API_FIELDS  # noqa: E402

five = [
    "tirePressureStatusValidFrontLeft",
    "tirePressureStatusValidFrontRight",
    "tirePressureStatusValidRearLeft",
    "tirePressureStatusValidRearRight",
    "cabinHoldNotification",
]
missing = [f for f in five if f not in VEHICLE_STATE_API_FIELDS]
if missing:
    print("REMOVED without a recorded live failure:", missing)
    print("Principle: an entity is removed only on a live FAILURE. Never carrying")
    print("a value is silence, which is what the tonneau cover falsified.")
    sys.exit(1)
PYEOF
check "all five fields are still subscribed" $?

# Each has a finding in the doc, named.
for f in tirePressureStatusValidFrontLeft cabinHoldNotification tirePressureState; do
  contains "the doc records $f" "$f" "$DOC"
done
contains "the doc states the verdict for each" 'Left in place' "$DOC"
contains "the doc distinguishes accepted from populated" \
         'accepted but empty' "$DOC"

# The ^ trap is closed, in the SOURCE not merely in the value. Rebuilding the set
# in a check cannot catch this: the check would rebuild it correctly either way.
line=$(grep -n '^VEHICLE_STATE_SANS_TPMS_API_FIELDS' "$CONST" | head -1)
if printf '%s' "$line" | grep -qF 'VEHICLE_STATE_API_FIELDS - {'; then
  ok "VEHICLE_STATE_SANS_TPMS_API_FIELDS uses subtraction"
else
  bad "VEHICLE_STATE_SANS_TPMS_API_FIELDS is not built with '-': $line"
fi
if printf '%s' "$line" | grep -qF '^'; then
  bad "symmetric difference is back — a tire name leaving the base set re-adds it"
else
  ok "no symmetric difference in that expression"
fi

# Both third-row spellings, side by side.
"$VENV_PY" - "$HA" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from custom_components.rivian.rivian_client import VehicleCommand  # noqa: E402

ours = {c.value for c in VehicleCommand}
want = [
    "CABIN_HVAC_THIRD_ROW_LEFT_SEAT_HEAT",
    "CABIN_HVAC_THIRD_ROW_RIGHT_SEAT_HEAT",
    "CABIN_HVAC_3RD_ROW_REAR_LEFT_SEAT_HEAT",
    "CABIN_HVAC_3RD_ROW_REAR_RIGHT_SEAT_HEAT",
]
missing = [c for c in want if c not in ours]
if missing:
    print("missing:", missing)
    print("The 3RD_ROW pair is ADDED ALONGSIDE the THIRD_ROW pair, never instead:")
    print("the older spelling may serve older firmware, and an app-side absence")
    print("is the weakest evidence there is.")
    sys.exit(1)
PYEOF
check "both third-row spellings exist side by side" $?

# The vendored client and the sibling repo must agree; s14.sh enforces byte
# identity, and this story edits the client's const.py.
if [ -f "$HA/scripts/gates/s14.sh" ]; then
  if bash "$HA/scripts/gates/s14.sh" >/dev/null 2>&1; then
    ok "s14 (vendored client byte identity) still green"
  else
    bad "s14 fails — the sibling repo did not get the same const.py edit"
  fi
fi

for t in test_all_five_are_still_subscribed \
         test_none_of_them_is_named_by_the_app \
         test_no_offline_candidate_exists_for_the_validity_fields \
         test_each_field_has_a_recorded_finding \
         test_both_third_row_spellings_exist_side_by_side; do
  if grep -qF "def $t" "$T"; then ok "asserts: $t"
  else bad "missing required assertion: $t"; fi
done
for t in test_the_sans_tpms_variant_is_still_a_strict_subset \
         test_the_sans_tpms_set_uses_subtraction_in_the_source; do
  if grep -qF "def $t" "$HA/tests/test_init.py"; then ok "asserts: $t"
  else bad "missing required assertion: $t"; fi
done

PY="$(resolve_pytest "$HA")"
if [ ! -x "$PY" ]; then bad "pytest not found"; summary f2; exit 1; fi
pytest_green "$HA" "$PY" "suite"
test_count "$HA" 1433

summary f2
