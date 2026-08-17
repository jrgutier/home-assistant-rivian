#!/usr/bin/env bash
# S8b — the 4 missing decoders written and registered.
source "$(dirname "$0")/_lib.sh"
echo "S8b — decoders for the 4 shipped RVMs"
P="$HA/custom_components/rivian/rivian_client/parallax.py"
for d in decode_climate_hold_status decode_climate_hold_setting decode_vehicle_wheels decode_ota_config; do
  contains "$d defined" "def $d" "$P"
done
contains "climate_hold_status registered in RVM_DECODERS" 'comfort.cabin.climate_hold_status' "$P"
summary S8b
