#!/usr/bin/env bash
# S9a — unverified entities and builders pruned.
#
# Everything removed here targets an RVM that returns INTERNAL_SERVER_ERROR to
# sendVehicleOperation in BOTH directions
# (docs/development/SENDVEHICLEOPERATION_TEST_RESULTS.md). The entities could
# never have worked; they reported their defaults forever.
#
# Resolves the client copy until S7 vendors it, for the same reason S8b does:
# vendoring MOVES parallax.py, so keying the gate to the post-vendor path would
# make this story falsely depend on S7.
source "$(dirname "$0")/_lib.sh"
echo "S9a — prune unverified entities/builders"

CC="$HA/custom_components/rivian"
absent "PARALLAX_SWITCHES gone" 'PARALLAX_SWITCHES' "$CC"
absent "PARALLAX_NUMBERS gone"  'PARALLAX_NUMBERS'  "$CC"
absent "PARALLAX_SELECTS gone"  'PARALLAX_SELECTS'  "$CC"
absent "parallax.* prefix routing gone" '"parallax\\.' "$CC"
absent "set_geofences service gone" 'set_geofences' "$CC"

VENDORED="$CC/rivian_client/parallax.py"
if [ -f "$VENDORED" ]; then P="$VENDORED"; else P="$CLIENT/src/rivian/parallax.py"; fi
n=$( { grep -cE '^def build_' "$P" || true; } )
if [ "$n" -eq 4 ]; then ok "exactly 4 build_* remain (was 21)"
else bad "$n build_* functions remain — expected 4"; fi

# RVMType must shrink with them, or the enum still advertises RVMs that fail.
m=$( { grep -cE '^    [A-Z_]+ = ' "$P" || true; } )
if [ "$m" -eq 4 ]; then ok "RVMType pruned to the 4 verified RVMs (was 18)"
else bad "RVMType has $m members — expected 4"; fi

# The client methods that drove the removed entities must go too, or they remain
# callable and reference builders that no longer exist.
for meth in set_halloween_settings set_cabin_ventilation set_vehicle_geofences \
            set_gear_guard_consents set_passive_entry_settings; do
  absent "client method $meth gone" "def $meth" "$(dirname "$P")"
done

# Orphaned translation keys would leave dead strings shipping forever.
try "no translation keys orphaned by the pruning" \
  bash -c "cd '$HA' && python3 -c \"
import json
d = json.load(open('custom_components/rivian/translations/en.json'))
ent = d.get('entity', {})
dead = ['halloween_enabled','cabin_ventilation','gear_guard_video_consent','passive_entry',
        'halloween_brightness','cabin_ventilation_windows','cabin_ventilation_sunroof',
        'cabin_ventilation_duration','passive_entry_distance','halloween_mode',
        'cabin_ventilation_mode']
found = [k for plat in ent.values() for k in plat if k in dead]
assert not found, found
\""

summary S9a
