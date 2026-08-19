#!/usr/bin/env bash
# f3a — an R2 receives entities, and no vehicle receives any of them twice.
#
# The bug: `if model in vehicle["model"]` is a SUBSTRING test over the group keys
# R1 / R1T / R1S. "R1" in "R2" is False, so an R2 owner got ZERO sensors and ZERO
# binary sensors, silently.
#
# The two ways of "fixing" it that this gate refuses:
#
#   * Adding an "ALL" group populated from "R1". The comprehensions build LISTS
#     and every description shares unique_id = f"{vin}-{key}", so ALL + R1 + R1T
#     double-adds the shared group: 114 duplicate-unique-id errors per vehicle.
#     A set-equality assertion cannot see this -- the set is identical either way
#     -- so the counts here are NUMERIC and there is a direct duplicate check.
#
#   * Making the map strict. A KeyError on an unknown model removes every entity
#     for that vehicle, which is worse than the bug being fixed.

source "$(dirname "$0")/_lib.sh"

echo "f3a — model groups by explicit map, not by substring"

code_only() { python3 "$(dirname "$0")/helpers/py_code_only.py" "$@"; }

H="$HA/custom_components/rivian/helpers.py"
S="$HA/custom_components/rivian/sensor.py"
B="$HA/custom_components/rivian/binary_sensor.py"
E="$HA/custom_components/rivian/entity.py"
T="$HA/tests/test_model_entity_groups.py"
FIX="$HA/tests/fixtures/entity_sets.json"

have_path "the f3a test module exists" "$T"
have_path "the committed entity-set fixture exists" "$FIX"

contains "helpers.py defines the map" 'VEHICLE_MODEL_GROUPS' "$H"
contains "helpers.py exposes groups_for_model" 'def groups_for_model' "$H"
contains "unknown models fall back rather than raise" 'DEFAULT_MODEL_GROUPS' "$H"

# The substring predicate is gone from BOTH comprehensions. Code only: the
# comments explaining the change quote the old predicate verbatim.
for f in "$S" "$B"; do
  if code_only "$f" | grep -qF 'in vehicle["model"]'; then
    bad "$(basename "$f") still uses the substring predicate"
  else
    ok "$(basename "$f") no longer uses the substring predicate"
  fi
  contains "$(basename "$f") uses groups_for_model" 'groups_for_model' "$f"
done

# entity.py:54 -- the third site, and the widest: DeviceInfo is built for every
# platform, so an unguarded vehicle["model"] breaks device registration
# everywhere, not just in the two comprehensions.
if code_only "$E" | grep -qF 'vehicle["model"]'; then
  bad "entity.py still reads vehicle[\"model\"] unguarded"
else
  ok "entity.py guards the model lookup"
fi
contains "entity.py falls back for the device name" 'name or model or vin' "$E"

# No ALL group, in the tables or in the map.
if code_only "$HA/custom_components/rivian/const.py" | grep -qE '^"ALL"$'; then
  bad "an ALL group key exists in const.py"
else
  ok "no ALL group key in const.py"
fi
if code_only "$H" | grep -qF '"ALL"'; then
  bad "helpers.py returns an ALL group"
else
  ok "helpers.py returns no ALL group"
fi

PY="$(resolve_pytest "$HA")"
if [ ! -x "$PY" ]; then bad "pytest not found"; summary f3a; exit 1; fi

# The counts, asserted by the code rather than by this script re-deriving them
# from the same source. The literals live in the test module so they are
# reviewable next to what they describe; the gate checks they are still there.
# Raised from 90/33, 90/29, 87/27 when f5's follow-up added nine sensors for the
# fields the new Parallax decoders are the only source for. Binary sensors are
# unchanged, which is the check that says the addition was sensors only.
for pair in '"R1T": (99, 33)' '"R1S": (99, 29)' '"R2": (96, 27)' 'None: (96, 27)'; do
  if grep -qF "$pair" "$T"; then ok "count asserted: $pair"
  else bad "missing numeric count assertion: $pair"; fi
done

# And that the fixture agrees with those numbers, read independently here so a
# silently regenerated fixture cannot drift with the code.
python3 - "$FIX" <<'PYEOF'
import json, sys
want = {"R1T": (99, 33), "R1S": (99, 29), "R2": (96, 27), "__absent__": (96, 27)}
data = json.load(open(sys.argv[1]))
bad = []
for model, (ns, nb) in want.items():
    if model not in data:
        bad.append(f"{model}: absent from the fixture")
        continue
    got = (len(data[model]["sensors"]), len(data[model]["binary_sensors"]))
    if got != (ns, nb):
        bad.append(f"{model}: fixture has {got}, expected {(ns, nb)}")
    ids = data[model]["sensors"] + data[model]["binary_sensors"]
    if len(ids) != len(set(ids)):
        bad.append(f"{model}: fixture contains duplicate keys")
if bad:
    print("\n".join(bad)); sys.exit(1)
PYEOF
check "the committed fixture holds 90/33, 90/29, 87/27, 87/27 with no duplicates" $?

for t in test_an_r2_gets_entities_at_all \
         test_no_duplicate_unique_ids \
         test_r2_is_the_r1t_set_minus_the_r1t_only_group \
         test_r1t_only_entities_do_not_reach_an_r1s_and_vice_versa \
         test_unknown_or_missing_falls_back_to_the_shared_group \
         test_no_all_group_exists \
         test_absent_model_still_registers; do
  if grep -qF "def $t" "$T"; then ok "asserts: $t"
  else bad "missing required assertion: $t"; fi
done

if (cd "$HA" && "$PY" tests/test_model_entity_groups.py -q --no-cov \
      -p no:cacheprovider >/dev/null 2>&1); then
  ok "the f3a test module is green"
else
  bad "the f3a test module fails"
fi

# The fixture must be TRACKED -- an untracked baseline is no baseline.
if git -C "$HA" ls-files --error-unmatch tests/fixtures/entity_sets.json >/dev/null 2>&1; then
  ok "the entity-set fixture is tracked in git"
else
  bad "the entity-set fixture is not tracked"
fi

out=$(cd "$HA" && "$PY" -q --no-cov -p no:cacheprovider 2>&1 || true)
note "$(echo "$out" | tail -1)"
if echo "$out" | grep -qE '^FAILED '; then bad "suite has failures"; else ok "suite green"; fi
if echo "$out" | grep -qE '^[0-9]+ (skipped|deselected)'; then
  bad "tests skipped or deselected"
else
  ok "nothing skipped or deselected"
fi
test_count "$HA" 1358

summary f3a
