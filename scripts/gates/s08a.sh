#!/usr/bin/env bash
# S8a — RVM payload fixtures captured from the live vehicle.
#
# Rewritten after the original gate was found vacuous: it used have_path only, so
# four `touch`ed empty files passed it. Every RVM this plan ships must have a
# fixture that is NON-EMPTY and PARSES, because an empty payload is exactly what
# the live vehicle returns for an unconfigured RVM -- and a subscription error
# envelope is still a well-formed frame.
#
# ota.user_schedule.ota_config is deliberately absent. A signed GET was accepted
# by the server (SendVehicleOperationSuccess) and returned a 0-byte payload:
# no OTA schedule is configured on this vehicle. Capturing one would require
# either an unverified OTA *write* (which could schedule a software install) or
# a schedule set by hand in the Rivian app. Dropped under principle 3 -- no
# entity without a verified backing operation. See docs/development/RVM_FIXTURES.md.
source "$(dirname "$0")/_lib.sh"
echo "S8a — RVM fixtures captured"

D="$CLIENT/tests/fixtures/parallax"

if [ ! -d "$D" ]; then
  bad "fixture directory exists  (missing: $D)"
  summary S8a
fi

for r in climate_hold_status climate_hold_setting vehicle_wheels; do
  f="$D/$r.bin"
  if [ ! -s "$f" ]; then
    bad "fixture non-empty: $r  (missing or 0 bytes: $f)"
  else
    ok "fixture non-empty: $r  ($(wc -c < "$f" | tr -d ' ') bytes)"
  fi
done

# climate_hold_setting must parse as ClimateHoldSetting and round-trip. This is
# the one server-verified WRITE, captured by setting a 5-minute hold: 08ac02 = 300s.
# The other two must be valid protobuf wire format, not arbitrary bytes.
try "fixtures parse as protobuf and climate_hold_setting round-trips" \
  bash -c "cd '$CLIENT' && uv run python '$WORKSPACE/home-assistant-rivian/scripts/gates/helpers/check_fixtures.py' '$D'"

# The drop must be recorded, not silently omitted.
try "ota_config drop is documented" \
  test -f "$WORKSPACE/home-assistant-rivian/docs/development/RVM_FIXTURES.md"

summary S8a
