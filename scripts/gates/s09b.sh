#!/usr/bin/env bash
# S9b — the verified RVMs wired onto decoded data.
#
# The previous version passed FILE paths to absent(), which expects a directory,
# so two of its three assertions failed for the wrong reason. Same defect as S6c.
source "$(dirname "$0")/_lib.sh"
echo "S9b — wire verified RVMs"

CC="$HA/custom_components/rivian"

# The climate hold must write through Parallax, not a VehicleCommand.
contains "climate hold writes via the Parallax path" 'async_set_climate_hold' "$CC/switch.py"
# Code only -- a comment mentioning the old commands must not fail the gate.
# (Fourth self-triggering-comment defect in this project's gates.)
if sed 's/#.*//' "$CC/switch.py" | grep -qE 'CLIMATE_HOLD_(ON|OFF)'; then
  bad "the switch still uses VehicleCommand.CLIMATE_HOLD_ON/OFF"
else
  ok "no VehicleCommand climate-hold write remains"
fi

# ...and read the DECODED status, so read and write share one source.
contains "climate hold reads the decoded status" 'climateHoldStatus' "$CC/switch.py"

# vehicle_wheels ships read-only.
contains "vehicle wheels surfaced read-only" 'wheelsInstalled' "$CC/const.py"

# ota_config must NOT be routed through time.py, which is charging-only, and no
# OTA write may ship: the server accepts the RVM but returns an empty payload,
# so any write would be built against an imagined layout.
if grep -q 'ota_config' "$CC/time.py"; then
  bad "ota_config routed through time.py, which is charging-only"
else
  ok "ota_config is not routed through time.py"
fi
if grep -q 'build_ota_schedule_command' "$CC/rivian_client/parallax.py"; then
  bad "an OTA write builder is shipped"
else
  ok "no OTA write builder shipped"
fi

try "climate-hold wiring tests pass" \
  bash -c "cd '$HA' && .venv/bin/pytest tests/test_climate_hold_wiring.py -q --no-cov"

summary S9b
