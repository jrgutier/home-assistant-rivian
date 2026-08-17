#!/usr/bin/env bash
# S9b — the 4 survivors wired onto decoded data.
source "$(dirname "$0")/_lib.sh"
echo "S9b — wire verified RVMs"
CC="$HA/custom_components/rivian"
contains "climate hold uses the Parallax write" 'climate_hold_setting' "$CC/switch.py"
absent "ota_config is not routed through time.py (charging-only)" 'ota_config' "$CC/time.py"
absent "no OTA write builder shipped" 'build_ota_schedule_command' "$CC/rivian_client/parallax.py"
summary S9b
