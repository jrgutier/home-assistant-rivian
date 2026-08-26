#!/usr/bin/env bash
# f3c — the tailgate entities stay ungated, and the reasoning is written down
# where it will be found again.
#
# This gate is unusual: it asserts that something did NOT happen. The pressure it
# resists is real -- an R1S has a liftgate, not a tailgate, so `closure_tailgate_*`
# looks like obvious dead weight there. It is not, for two reasons the gate
# checks directly: f0 already turned the false "Closed" into "unknown", and
# removing them takes two entities from every R1S owner on a hardware inference
# with no recorded live failure. That inference is what the tonneau falsified.
#
# Optional-hardware gating (s26) did not move these onto a feature/option_code.
# They stay on the BINARY_SENSORS tuple with both gates None, so every model
# including R2 still receives them under features=().

source "$(dirname "$0")/_lib.sh"

echo "f3c — tailgate documented, not removed"

DOC="$HA/docs/development/MODEL_SPECIFIC_ENTITIES.md"
T="$HA/tests/test_model_entity_groups.py"
FIX="$HA/tests/fixtures/entity_sets.json"

have_path "the decision is documented" "$DOC"
contains "the doc names the entities" 'closure_tailgate_closed' "$DOC"
contains "the doc states what removal would require" 'recorded owner decision' "$DOC"
contains "the doc states the general rule" \
         'Remove one only on a recorded live failure' "$DOC"
contains "the doc records the unknown-not-unavailable distinction" \
         '`unknown`, not' "$DOC"
if git -C "$HA" ls-files --error-unmatch docs/development/MODEL_SPECIFIC_ENTITIES.md \
     >/dev/null 2>&1; then
  ok "the doc is tracked in git"
else
  bad "the doc is not tracked — a decision in an untracked file is not recorded"
fi

# The entities themselves, checked against the source of truth rather than the
# doc that describes it. Needs the venv interpreter: const.py imports Home
# Assistant, which the system python3 does not have.
VENV_PY="$(resolve_python "$HA")"
"$VENV_PY" - "$HA" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from custom_components.rivian.const import BINARY_SENSORS

keys = {"closure_tailgate_closed", "closure_tailgate_locked"}
found = {d.key: d for d in BINARY_SENSORS if d.key in keys}

problems = []
missing = keys - set(found)
if missing:
    problems.append(f"missing from BINARY_SENSORS: {sorted(missing)}")
for key, d in found.items():
    if d.feature is not None:
        problems.append(f"{key} has feature={d.feature!r}")
    if d.option_code is not None:
        problems.append(f"{key} has option_code={d.option_code!r}")
if problems:
    print("\n".join(problems))
    print("Removal requires a recorded live failure and an owner decision.")
    sys.exit(1)
PYEOF
check "closure_tailgate_* is on the BINARY_SENSORS tuple, ungated" $?

# The committed baseline still lists them for every dump scenario that is not
# hardware-specific -- including models that are not an R1T.
python3 - "$FIX" <<'PYEOF'
import json, sys
data = json.load(open(sys.argv[1]))
keys = {"closure_tailgate_closed", "closure_tailgate_locked"}
bad = [m for m in ("R1T", "R1S", "R2", "__absent__")
       if not keys <= set(data[m]["binary_sensors"])]
if bad:
    print("missing from the committed fixture for:", bad)
    sys.exit(1)
PYEOF
check "the committed fixture still lists them for every model" $?

for t in test_the_tailgate_entities_have_no_feature_or_option_code \
         test_they_appear_under_no_flags \
         test_every_model_still_receives_them \
         test_an_unusable_tailgate_field_reads_unknown_not_closed \
         test_the_decision_is_written_down_where_it_will_be_found; do
  if grep -qF "def $t" "$T"; then ok "asserts: $t"
  else bad "missing required assertion: $t"; fi
done

PY="$(resolve_pytest "$HA")"
if [ ! -x "$PY" ]; then bad "pytest not found"; summary f3c; exit 1; fi
if (cd "$HA" && "$PY" tests/test_model_entity_groups.py -q --no-cov \
      -p no:cacheprovider >/dev/null 2>&1); then
  ok "the f3c test module is green"
else
  bad "the f3c test module fails"
fi

summary f3c
