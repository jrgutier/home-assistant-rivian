#!/usr/bin/env bash
# S6b — watchdog de-duplicated, diagnostics extended.
source "$(dirname "$0")/_lib.sh"
echo "S6b — watchdog dedup + diagnostics"
C="$HA/custom_components/rivian/coordinator.py"
n=$( { grep -cE '_start_watchdog|_watchdog_loop' "$C" || true; } )
note "watchdog references: $n (was triplicated across 3 coordinators)"
contains "diagnostics includes Parallax" 'parallax' "$HA/custom_components/rivian/diagnostics.py"
summary S6b
