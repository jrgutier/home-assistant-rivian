#!/usr/bin/env bash
# f4 — gateway.graphql describes what the server accepts, and something reads it.
#
# The trap: an APK-derived schema is a LOWER BOUND, never the schema. Rebuilding
# type VehicleState from the app's documents and then asserting our field set is a
# subset of THAT would demand deleting fifteen fields the server demonstrably
# accepts, about ten of them backing live sensors. So the direction matters:
#
#   assertion (i)  everything subscribed must be DECLARED. Constrains the schema.
#                  Deleting a name from VEHICLE_STATE_API_FIELDS is never the fix.
#   assertion (ii) a drift guard, true by construction. Pins the delta so a future
#                  edit has to change it in a diff a reviewer sees.
#
# A correction this story made to its own brief: the plan said to adopt
# `tirePressureState`. That name is the OPERATION NAME of apj.java's subscription,
# not a field it selects -- a flat grep cannot tell the two apart, and the two
# retired flat extracts are how it reached the plan. Subscribing to it would have
# taken the whole subscription down, as wheelsInstalled did.

source "$(dirname "$0")/_lib.sh"

echo "f4 — schema rebuilt, scoped, and actually read"

SCHEMA="$HA/custom_components/rivian/rivian_client/schemas/gateway.graphql"
MIRROR="$CLIENT/src/rivian/schemas/gateway.graphql"
T="$HA/tests/test_gateway_schema.py"

have_path "the schema exists" "$SCHEMA"
have_path "the f4 test module exists" "$T"

VENV_PY="$(resolve_python "$HA")"

# (i) and the scoping, read out of the files rather than delegated.
"$VENV_PY" - "$HA" <<'PYEOF'
import re
import subprocess
import sys
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo))
sys.path.insert(0, str(repo / "scripts/gates/helpers"))
from custom_components.rivian.const import VEHICLE_STATE_API_FIELDS  # noqa: E402

schema = repo / "custom_components/rivian/rivian_client/schemas/gateway.graphql"


def definitions(text):
    out, name, cur = {}, None, []
    for line in text.split("\n"):
        m = re.match(
            r"^(type|input|enum|interface|union|scalar|schema|directive) (\w+)", line
        )
        if m:
            if name:
                out[name] = "\n".join(cur).rstrip()
            name, cur = m.group(2), [line]
        elif name is not None:
            cur.append(line)
    if name:
        out[name] = "\n".join(cur).rstrip()
    return out


new = definitions(schema.read_text())
fields = set(re.findall(r"^  (\w+):", new["VehicleState"], re.M))
problems = []

missing = VEHICLE_STATE_API_FIELDS - fields
if missing:
    problems.append(
        f"(i) subscribed but not declared: {sorted(missing)}. ADD THEM TO THE "
        "SCHEMA -- removing them from VEHICLE_STATE_API_FIELDS is never the fix."
    )

# The four fields the app never names but the integration reads. The plan's
# formula (app union + the fifteen) would have deleted all four, two of them
# load-bearing.
for f in ("supportedFeatures", "cloudConnection"):
    if f not in fields:
        problems.append(f"{f} was pruned -- the integration reads it")

# The rebuild is scoped to ONE of the 81 definitions.
old = subprocess.run(
    ["git", "-C", str(repo), "show",
     "HEAD:custom_components/rivian/rivian_client/schemas/gateway.graphql"],
    capture_output=True, text=True,
)
if old.returncode == 0:
    prev = definitions(old.stdout)
    if set(prev) != set(new):
        problems.append(
            f"definitions added/removed: "
            f"{sorted(set(prev) ^ set(new))}"
        )
    else:
        changed = {k for k in prev if prev[k] != new[k]} - {"VehicleState"}
        if changed:
            problems.append(f"edit is not scoped to VehicleState; also: {sorted(changed)}")

# The name the plan told us to adopt is an operation name, not a field.
if "tirePressureState" in VEHICLE_STATE_API_FIELDS:
    problems.append(
        "tirePressureState is subscribed. It is the OPERATION NAME of apj.java's "
        "subscription, not a field -- subscribing to a name the server does not "
        "know takes the ENTIRE subscription down (see wheelsInstalled)."
    )

if problems:
    print("\n".join(problems)); sys.exit(1)
print(f"type VehicleState: {len(fields)} fields, {len(new)} definitions, one edited")
PYEOF
check "(i) everything subscribed is declared, and the edit is scoped" $?

# (ii) the delta, re-derived from the classes when pre-flight has run.
if [ -f "$HA/docs/development/apk/wcm.java" ]; then
  "$VENV_PY" - "$HA" <<'PYEOF'
import re
import sys
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "scripts/gates/helpers"))
from apk_vehicle_state_fields import fields_for  # noqa: E402

apk = repo / "docs/development/apk"
union = set()
for name in ("wcm", "cdm", "apj", "h9l", "lel"):
    union |= fields_for(apk / f"{name}.java")

schema = (repo / "custom_components/rivian/rivian_client/schemas/gateway.graphql").read_text()
block = schema.split("type VehicleState {", 1)[1].split("\n}", 1)[0]
fields = set(re.findall(r"^  (\w+):", block, re.M))

FIFTEEN = {
    "batteryCapacity", "brakeFluidLow", "cabinHoldNotification", "gearGuardLocked",
    "wiperFluidState", "otaAvailableVersionNumber", "otaAvailableVersionWeek",
    "otaAvailableVersionYear", "otaCurrentVersionNumber", "otaCurrentVersionWeek",
    "otaCurrentVersionYear", "tirePressureStatusValidFrontLeft",
    "tirePressureStatusValidFrontRight", "tirePressureStatusValidRearLeft",
    "tirePressureStatusValidRearRight",
}
FOUR = {"chargingDisabledAC", "closureTonneauNextAction", "cloudConnection",
        "supportedFeatures"}

problems = []
if len(union) != 137:
    problems.append(f"app document union is {len(union)}, expected 137")
delta = fields - union
if delta != FIFTEEN | FOUR:
    problems.append(
        f"(ii) delta drift: unexpected={sorted(delta - (FIFTEEN | FOUR))} "
        f"missing={sorted((FIFTEEN | FOUR) - delta)}"
    )
if problems:
    print("\n".join(problems)); sys.exit(1)
print(f"(ii) union {len(union)}, delta {len(delta)} = 15 recorded + 4 kept")
PYEOF
  check "(ii) the delta from the app's documents is exactly what is recorded" $?
else
  note "pre-flight classes absent — the delta re-derivation is SKIPPED, not passed"
fi

contains "the fifteen carry a marker comment" \
         'The server accepts it; this APK build does not request it.' "$SCHEMA"
contains "the four kept fields carry one too" \
         'Declared before f4 and not in any app document.' "$SCHEMA"

# The vendored schema and the sibling repo must be identical; s14 enforces it.
if [ -f "$MIRROR" ]; then
  if diff -q "$SCHEMA" "$MIRROR" >/dev/null; then
    ok "the sibling repo's schema is identical"
  else
    bad "the schema was not mirrored to the sibling repo"
  fi
else
  note "sibling rivian-python-client not present — skipping the schema-mirror check"
fi

# get_vehicle_state is gone, and the error-path tests were REPOINTED, not deleted.
code_only() { python3 "$(dirname "$0")/helpers/py_code_only.py" "$@"; }
if code_only "$HA/custom_components/rivian/rivian_client/rivian.py" \
     | grep -qF 'def get_vehicle_state'; then
  bad "get_vehicle_state is still defined"
else
  ok "get_vehicle_state is deleted"
fi
if grep -qF 'def test_graphql_errors' "$HA/tests/client/test_rivian.py"; then
  ok "the error-path tests survived (repointed, not deleted)"
else
  bad "test_graphql_errors was deleted — the client floor has under 0.5% headroom"
fi

# Both floors, which is the check the plan said to do BEFORE deleting.
if (cd "$HA" && "$(resolve_pytest "$HA")" -q -p no:cacheprovider >/dev/null 2>&1 \
    && "$VENV_PY" scripts/check_coverage.py); then
  ok "both coverage floors still hold after the deletion"
else
  bad "a coverage floor broke"
fi

for t in test_the_schema_is_actually_loaded_by_something \
         test_every_subscribed_field_is_declared \
         test_the_delta_from_the_apps_documents_is_exactly_what_is_recorded \
         test_supported_features_survived_the_rebuild \
         test_only_vehicle_state_was_edited \
         test_it_is_not_subscribed \
         test_apj_selects_exactly_the_eight_real_tire_fields \
         test_the_method_is_deleted \
         test_the_error_path_tests_were_repointed_not_deleted; do
  if grep -qF "def $t" "$T"; then ok "asserts: $t"
  else bad "missing required assertion: $t"; fi
done

PY="$(resolve_pytest "$HA")"
out=$(cd "$HA" && "$PY" -q --no-cov -p no:cacheprovider 2>&1 || true)
note "$(echo "$out" | tail -1)"
if echo "$out" | grep -qE '^FAILED '; then bad "suite has failures"; else ok "suite green"; fi
test_count "$HA" 1453

summary f4
