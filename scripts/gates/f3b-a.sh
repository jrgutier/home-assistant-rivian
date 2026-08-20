#!/usr/bin/env bash
# f3b-a — the tonneau cover is keyed on the field the vehicle reports, not on
# TONNEAU_CMD, a flag no server emits and no decompiled file contains.
#
# The failure this gate is built against is the opposite of the usual one. Here
# the cheap green would be to DELETE the tonneau cover -- "no vehicle advertises
# the flag, so drop it" -- which is exactly the inference the live test
# falsified: both commands physically move the cover on an R1T. So the gate's
# central assertion is POSITIVE: a vehicle reporting the field must get the
# entity, with the two live-proven commands still attached.

source "$(dirname "$0")/_lib.sh"

echo "f3b-a — tonneau gated on the field, not on a dead flag"

COVER="$HA/custom_components/rivian/cover.py"
BUTTON="$HA/custom_components/rivian/button.py"
DC="$HA/custom_components/rivian/data_classes.py"
T="$HA/tests/test_cover_tonneau_gate.py"

have_path "cover.py present" "$COVER"
have_path "the f3b-a test module exists" "$T"

# The dead flag is gone from cover.py's CODE -- but the ENTITY is still there.
#
# Code, not raw text. The comment beside the new gate explains what TONNEAU_CMD
# was and why it went, so a raw grep finds the explanation of the fix and reports
# the bug is still present. That defect has now bitten this repo twice; strip
# comments and docstrings first.
code_only() { python3 "$(dirname "$0")/helpers/py_code_only.py" "$@"; }
if code_only "$COVER" | grep -qF 'TONNEAU_CMD'; then
  bad "cover.py still uses TONNEAU_CMD in code"
else
  ok "cover.py no longer uses TONNEAU_CMD in code"
fi
contains "the tonneau cover still exists" 'key="tonneau"' "$COVER"
contains "keyed on the field it reports" \
         'required_field="closureTonneauClosed"' "$COVER"
contains "still sends the live-proven open command" \
         'VehicleCommand.OPEN_TONNEAU_COVER' "$COVER"
contains "still sends the live-proven close command" \
         'VehicleCommand.CLOSE_TONNEAU_COVER' "$COVER"
contains "the description type carries required_field" \
         'required_field: str | None = None' "$DC"
contains "setup honours required_field" 'description.required_field' "$COVER"

# Presence in `data`, not truthiness of get(). A get()-truthiness gate silently
# drops a field whose legitimate value is falsy, and passes vacuously against a
# MagicMock coordinator -- which is what the existing tests use.
contains "gated on presence in data, not on get() truthiness" \
         'in (coordinators[vehicle_id].data or {})' "$COVER"

# The remaining gate strings are real VehicleFeature featureNames. This is a
# whitelist, not a count: it goes red when a gate string is added or changed, so
# a future typo cannot ride in unnoticed. featureName, NOT member name -- 19 of
# the 64 differ (CHARGE_PORT_DOOR_COMMAND is the member, CHARG_PORT_DOOR_COMMAND
# the featureName).
gate_code=$(code_only "$COVER" "$BUTTON")
for f in TAILGATE_CMD LIFTGATE_CMD SIDE_BIN_NXT_ACT CHARG_PORT_DOOR_COMMAND; do
  if printf '%s' "$gate_code" | grep -qF "\"$f\""; then
    ok "gate kept (real featureName): $f"
  else
    bad "gate string vanished: $f — removal needs a recorded live failure"
  fi
done

# Cross-check those four against the app's own enum when pre-flight has run.
VF="$HA/docs/development/apk/VehicleFeature.java"
if [ -f "$VF" ]; then
  for f in TAILGATE_CMD LIFTGATE_CMD SIDE_BIN_NXT_ACT CHARG_PORT_DOOR_COMMAND; do
    if grep -qE "\(\"$f\"\)" "$VF"; then ok "VehicleFeature emits featureName $f"
    else bad "$f is NOT a VehicleFeature featureName"; fi
  done
  if grep -qF 'TONNEAU_CMD' "$VF"; then
    bad "TONNEAU_CMD IS in VehicleFeature — this story's premise is wrong"
  else
    ok "TONNEAU_CMD is absent from VehicleFeature, as this story assumes"
  fi
else
  note "VehicleFeature.java absent — run scripts/gates/pf.sh first (skipped, not failed)"
fi

PY="$(resolve_pytest "$HA")"
if [ ! -x "$PY" ]; then bad "pytest not found"; summary f3b-a; exit 1; fi

if (cd "$HA" && "$PY" tests/test_cover_tonneau_gate.py -q --no-cov \
      -p no:cacheprovider >/dev/null 2>&1); then
  ok "the f3b-a test module is green"
else
  bad "the f3b-a test module fails"
fi

# The positive branch specifically. Without this the gate is satisfiable by
# deleting the cover, which is the outcome this whole story exists to prevent.
for t in test_a_vehicle_reporting_the_field_gets_the_cover \
         test_the_tonneau_still_uses_the_live_proven_commands \
         test_a_vehicle_not_reporting_the_field_does_not \
         test_the_flag_alone_no_longer_conjures_the_cover \
         test_the_other_gates_are_real_feature_names; do
  if grep -qF "def $t" "$T"; then ok "asserts: $t"
  else bad "missing required assertion: $t"; fi
done

# The test that fabricated the flag is updated, not deleted. Again: code only,
# because the updated test explains in a comment what it used to fabricate.
if code_only "$HA/tests/test_cover.py" | grep -qF 'TONNEAU_CMD'; then
  bad "tests/test_cover.py still fabricates TONNEAU_CMD"
else
  ok "tests/test_cover.py no longer fabricates the flag"
fi
if grep -qF 'def test_async_setup_entry_with_all_features' "$HA/tests/test_cover.py"; then
  ok "the fabricating test was updated, not deleted"
else
  bad "test_async_setup_entry_with_all_features was deleted rather than updated"
fi
contains "the translation key survives the re-gating" \
         '"tonneau"' "$HA/custom_components/rivian/translations/en.json"

pytest_green "$HA" "$PY" "suite"
test_count "$HA" 1325

summary f3b-a
