#!/usr/bin/env bash
# S8b — decoders for the RVMs this fork actually ships, written and registered.
#
# Two premises of the original gate were wrong:
#
#  1. It expected FOUR decoders including decode_ota_config. There is no
#     ota_config fixture and there cannot be one without either an unverified OTA
#     write or an owner setting a schedule in the app: a signed GET is ACCEPTED by
#     the server and returns 0 bytes. The entity is dropped under principle 3, so
#     asserting its decoder would force someone to invent a layout. See
#     docs/development/RVM_FIXTURES.md.
#
#  2. It looked only at the VENDORED path, which does not exist until S7. But the
#     decoders live in the client and are merely MOVED by vendoring, so this gate
#     resolves whichever copy exists. That is what removes S8b's dependency on S7.
#
# It also asserts the decoders actually DECODE the captured fixtures, not merely
# that functions of the right name exist -- three `def`s returning {} would
# satisfy a grep while leaving every entity unavailable, which is the exact
# defect S8b exists to fix.
source "$(dirname "$0")/_lib.sh"
echo "S8b — decoders for the shipped RVMs"

VENDORED="$HA/custom_components/rivian/rivian_client/parallax.py"
if [ -f "$VENDORED" ]; then P="$VENDORED"; else P="$CLIENT/src/rivian/parallax.py"; fi
echo "  (checking $P)"

for d in decode_climate_hold_status decode_climate_hold_setting decode_vehicle_wheels; do
  contains "$d defined" "def $d" "$P"
done

absent "decode_ota_config NOT invented (no fixture exists)" '^def decode_ota_config' "$(dirname "$P")"

for r in comfort.cabin.climate_hold_status comfort.cabin.climate_hold_setting vehicle.wheels.vehicle_wheels; do
  contains "$r registered in RVM_DECODERS" "\"$r\":" "$P"
done

# Behavioural: every shipped RVM must decode its captured fixture to real data.
if [ -d "$CLIENT" ]; then
  try "each shipped RVM decodes its captured fixture to non-empty data" \
    bash -c "cd '$CLIENT' && uv run python '$WORKSPACE/home-assistant-rivian/scripts/gates/helpers/check_decoders.py'"
else
  note "sibling rivian-python-client not present — skipping decoder fixture checks"
fi

summary S8b
