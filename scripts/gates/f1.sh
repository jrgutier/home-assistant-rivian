#!/usr/bin/env bash
# f1 — the capability inventory, and the lint that would have caught TONNEAU_CMD.
#
# Division of labour, on purpose:
#
#   tests/test_apk_transcription.py  transcription <-> the integration. Always
#                                    runnable, because the transcription ships.
#   this gate                        transcription <-> the decompiled CLASSES.
#                                    Only possible when pre-flight has run, since
#                                    the classes are gitignored -- and a skipped
#                                    test is worse than an absent one, so this
#                                    half lives here rather than as a skip marker
#                                    in the suite.
#
# The re-derivation below is deliberately INDEPENDENT of the extractor that wrote
# the transcription. A gate that re-runs the generator proves only that the
# generator is deterministic.

source "$(dirname "$0")/_lib.sh"

echo "f1 — capability inventory transcribed from classes"

APKDIR="$HA/docs/development/apk"
T="$HA/tests/test_apk_transcription.py"
TR="$HA/tests/apk/transcription.py"
MATRIX="$HA/docs/development/CAPABILITY_MATRIX.md"
OBS="$HA/tests/fixtures/supported_features_observed.json"

have_path "the transcription module exists" "$TR"
have_path "the f1 test module exists" "$T"
have_path "the capability matrix is committed" "$MATRIX"
have_path "the observed-features fixture is committed" "$OBS"

# No line numbers in the transcription. They drift with every app release, and an
# earlier revision of this work cited several that were already wrong.
if grep -qE '\.java:[0-9]+' "$TR"; then
  bad "the transcription cites line numbers — they drift; cite members and values"
else
  ok "the transcription cites no line numbers"
fi

VENV_PY="$(resolve_python "$HA")"

if [ -d "$APKDIR" ] && [ -f "$APKDIR/VehicleFeature.java" ]; then
  "$VENV_PY" - "$HA" <<'PYEOF'
import re
import sys
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo))
from tests.apk.transcription import (  # noqa: E402
    RVM_TOPICS,
    VAS_COMMAND_KT_CONSTANTS,
    VAS_COMMANDS,
    VEHICLE_FEATURES,
)

apk = repo / "docs/development/apk"
problems = []

# --- VehicleFeature ---------------------------------------------------------
pairs = re.findall(
    r'^    ([A-Z0-9_]+)\("([^"]*)"\)', (apk / "VehicleFeature.java").read_text(), re.M
)
if tuple(pairs) != VEHICLE_FEATURES:
    only_apk = set(pairs) - set(VEHICLE_FEATURES)
    only_tr = set(VEHICLE_FEATURES) - set(pairs)
    problems.append(
        f"VehicleFeature drift: {len(pairs)} in the class, "
        f"{len(VEHICLE_FEATURES)} transcribed; "
        f"only-in-class={sorted(only_apk)} only-transcribed={sorted(only_tr)}"
    )

# --- l6e --------------------------------------------------------------------
# Re-derived from the default-argument mask, not from the literal arguments:
#   isVehicleState                 = (mask & 2) ? false   : given
#   subscriptionScope              = (mask & 4) ? fug.App : given
#   needDoubleConsumerSubscription = (mask & 8) ? false   : given
rvm_pat = re.compile(
    r'new l6e\("(\w+)",\s*(\d+),\s*"([^"]+)",\s*(true|false),\s*'
    r"(null|fug\.\w+),\s*(true|false),\s*(\d+)"
)
derived = []
for member, idx, rvm, vs, scope, dbl, mask in rvm_pat.findall(
    (apk / "l6e.java").read_text()
):
    mask = int(mask)
    derived.append(
        {
            "member": member,
            "index": int(idx),
            "rvm_name": rvm,
            "is_vehicle_state": False if mask & 2 else vs == "true",
            "subscription_scope": "App" if mask & 4 else scope.split(".")[-1],
            "need_double_consumer_subscription": False if mask & 8 else dbl == "true",
        }
    )
derived.sort(key=lambda r: r["index"])
if derived != sorted(RVM_TOPICS, key=lambda r: r["index"]):
    problems.append(
        f"l6e drift: {len(derived)} in the class, {len(RVM_TOPICS)} transcribed"
    )
gaps = set(range(len(derived))) - {r["index"] for r in derived}
if gaps:
    problems.append(
        f"l6e indices are not contiguous: {sorted(gaps)} — the static block at the "
        "top of the class was probably not read"
    )

# --- VASCommand -------------------------------------------------------------
# Bound each subclass at the next class declaration OF ANY KIND. Bounding at the
# next `extends VASCommand` swallows the Companion class, whose body DEFINES
# generateInvalidCloudDataWrapper, and misreads CloseTonneauCover as
# invalid-wrapped.
kt_src = (apk / "VASCommandKt.java").read_text()
const = dict(re.findall(r'static final String (\w+) = "([^"]*)"', kt_src))
lines = (apk / "VASCommand.java").read_text().split("\n")
decls = [
    (i, m)
    for i, line in enumerate(lines)
    if (m := re.search(r"class (\w+)( extends VASCommand)? \{", line))
    and re.search(r"^    \S.*class \w+.*\{", line)
]
starts = [i for i, _ in decls] + [len(lines)]
rederived = []
for i, m in decls:
    if not m.group(2):
        continue
    j = next(s for s in starts if s > i)
    body = "\n".join(lines[i:j])
    if inv := re.search(r'generateInvalidCloudDataWrapper\(\s*("?[\w.()]+"?)\s*\)', body):
        wrapper, arg = "invalid", inv.group(1)
    elif cl := re.search(
        r"generateCloudDataWrapper\$default\(\s*VASCommand\.INSTANCE,\s*([^,]+),", body
    ):
        wrapper, arg = "cloud", cl.group(1).strip()
    else:
        wrapper, arg = None, None
    if arg and arg.startswith('"'):
        command = arg.strip('"')
    elif arg:
        command = const.get(arg.split(".", 1)[-1].removeprefix("get").removesuffix("()"))
    else:
        command = None
    rederived.append({"cls": m.group(1), "wrapper": wrapper, "command": command})
if rederived != [
    {"cls": v["cls"], "wrapper": v["wrapper"], "command": v["command"]}
    for v in VAS_COMMANDS
]:
    problems.append(
        f"VASCommand drift: {len(rederived)} in the class, "
        f"{len(VAS_COMMANDS)} transcribed"
    )

# --- VASCommandKt -----------------------------------------------------------
kt = re.findall(
    r'(private|public) static final String (\w+) = "([^"]*)"', kt_src
)
if tuple(kt) != VAS_COMMAND_KT_CONSTANTS:
    problems.append(
        f"VASCommandKt drift: {len(kt)} in the class, "
        f"{len(VAS_COMMAND_KT_CONSTANTS)} transcribed"
    )

if problems:
    print("\n".join(problems))
    sys.exit(1)
print(
    f"re-derived and matched: {len(VEHICLE_FEATURES)} features, "
    f"{len(RVM_TOPICS)} RVM topics, {len(VAS_COMMANDS)} commands, "
    f"{len(VAS_COMMAND_KT_CONSTANTS)} constants"
)
PYEOF
  check "the transcription still matches the decompiled classes" $?
else
  note "pre-flight classes absent — the class re-derivation is SKIPPED, not passed."
  note "Run scripts/gates/pf.sh (see docs/development/apk/REGENERATION.md)."
fi

# The counts, asserted here too so the gate is not merely a delegate.
"$VENV_PY" - "$HA" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from tests.apk.transcription import (  # noqa: E402
    INVALID_WRAPPER_COMMANDS,
    RVM_TOPICS,
    SENDABLE_COMMANDS,
    VAS_COMMAND_KT_CONSTANTS,
    VAS_COMMAND_KT_NAMES,
    VAS_COMMANDS,
    VEHICLE_FEATURES,
)

want = {
    "VehicleFeature members": (len(VEHICLE_FEATURES), 64),
    "members whose featureName differs": (
        sum(1 for m, f in VEHICLE_FEATURES if m != f),
        19,
    ),
    "l6e RVM topics": (len(RVM_TOPICS), 56),
    "VASCommand subclasses": (len(VAS_COMMANDS), 57),
    "with a literal command name": (
        sum(1 for v in VAS_COMMANDS if v["command"]),
        53,
    ),
    "sendable": (len(SENDABLE_COMMANDS), 45),
    "invalid-wrapper": (len(INVALID_WRAPPER_COMMANDS), 7),
    "VASCommandKt constants": (len(VAS_COMMAND_KT_CONSTANTS), 24),
    "of those, command names": (len(VAS_COMMAND_KT_NAMES), 18),
}
bad = [f"{k}: {got}, expected {exp}" for k, (got, exp) in want.items() if got != exp]
if bad:
    print("\n".join(bad)); sys.exit(1)
print(", ".join(f"{k}={got}" for k, (got, _) in want.items()))
PYEOF
check "every transcribed count is what the plan recorded" $?

# The observed fixture must carry no VIN: this is a public repository.
if grep -qE '\b[A-HJ-NPR-Z0-9]{17}\b' "$OBS"; then
  bad "the observed-features fixture contains something VIN-shaped"
else
  ok "the observed-features fixture carries no VIN"
fi

contains "the matrix records the tonneau finding" 'TONNEAU_CMD' "$MATRIX"
contains "the matrix records switch.py as a decision" 'switch.py' "$MATRIX"
contains "the matrix warns it is not a list of what the vehicle can do" \
         'What this table is not' "$MATRIX"

for t in test_every_gate_string_is_a_name_something_emits \
         test_no_gate_uses_a_member_name_where_the_feature_name_differs \
         test_the_ungated_groups_are_skipped_not_flagged \
         test_switch_py_is_deliberately_ungated \
         test_indices_are_contiguous_from_zero \
         test_subscription_scope_defaults_to_app_not_none \
         test_climate_hold_status_is_the_only_double_consumer_topic \
         test_seven_use_the_invalid_wrapper \
         test_the_commands_absent_from_this_apk_are_exactly_the_recorded_seven \
         test_the_server_emits_names_the_app_enum_does_not_contain; do
  if grep -qF "def $t" "$T"; then ok "asserts: $t"
  else bad "missing required assertion: $t"; fi
done

PY="$(resolve_pytest "$HA")"
if [ ! -x "$PY" ]; then bad "pytest not found"; summary f1; exit 1; fi
if (cd "$HA" && "$PY" tests/test_apk_transcription.py -q --no-cov \
      -p no:cacheprovider >/dev/null 2>&1); then
  ok "the f1 test module is green"
else
  bad "the f1 test module fails"
fi

pytest_green "$HA" "$PY" "suite"
test_count "$HA" 1426

summary f1
