#!/usr/bin/env bash
# S9a — unverified entities and builders pruned.
source "$(dirname "$0")/_lib.sh"
echo "S9a — prune unverified entities/builders"
CC="$HA/custom_components/rivian"
absent "PARALLAX_SWITCHES gone" 'PARALLAX_SWITCHES' "$CC"
absent "PARALLAX_NUMBERS gone"  'PARALLAX_NUMBERS'  "$CC"
absent "PARALLAX_SELECTS gone"  'PARALLAX_SELECTS'  "$CC"
absent "parallax.* prefix routing gone" '"parallax\.' "$CC"
absent "set_geofences service gone" 'set_geofences' "$CC"
P="$CC/rivian_client/parallax.py"
if [ -f "$P" ]; then
  n=$( { grep -cE '^def build_' "$P" || true; } )
  if [ "$n" -eq 4 ]; then ok "exactly 4 build_* remain (was 21)"
  else bad "$n build_* functions remain — expected 4"; fi
else bad "parallax.py missing at $P"; fi
summary S9a
