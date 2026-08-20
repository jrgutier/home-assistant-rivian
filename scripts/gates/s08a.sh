#!/usr/bin/env bash
#
# RETIRED 2026-08-20 -- this gate can no longer assert anything, by design.
#
# It gated the story "capture RVM payload fixtures from the live vehicle" in PRD
# vendor-rivian-client-parallax, which is COMPLETE: all 20 stories show
# passes:true, and its branch `vendor-client` no longer exists.
#
# Every check below is conditional on the sibling repo rivian-python-client being
# present. It is not, and it will not be again: story s07 VENDORED the client into
# custom_components/rivian/rivian_client/, which is exactly what this gate helped
# verify. So S8a now skips and reports "0 passed, 0 failed" -- it exits 0 without
# checking anything.
#
# It is kept, not deleted, because it is the executable record of how the vendoring
# was verified. Read its exit 0 as "not applicable", NEVER as "verified". A sweep
# that counts this as a pass is counting a check that cannot fail -- the same defect
# s16.sh exists to catch elsewhere.
#
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

if [ ! -d "$CLIENT" ]; then
  note "sibling rivian-python-client not present — skipping fixture checks"
  summary S8a
  exit 0
fi

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
