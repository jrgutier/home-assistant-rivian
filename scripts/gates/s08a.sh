#!/usr/bin/env bash
# S8a — HUMAN: 4 RVM payload fixtures captured from the live vehicle.
source "$(dirname "$0")/_lib.sh"
echo "S8a — RVM fixtures captured"
D="$CLIENT/tests/fixtures/parallax"
for r in climate_hold_status climate_hold_setting vehicle_wheels ota_config; do
  have_path "fixture: $r" "$D/$r.bin"
done
summary S8a
