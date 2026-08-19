#!/usr/bin/env bash
# f5 — Parallax decoders transcribed from the app's protobuf classes.
#
# The finding this gate protects is the method itself. R8 renames
# GeneratedMessageLite to `com.google.protobuf.e` and every message class to two
# or three letters, so the app LOOKS like it carries no protobuf schema -- this
# work nearly recorded that as fact. It carries 326 message classes, and R8 leaves
# `<FIELD>_FIELD_NUMBER`, the `<field>_` members and the enum constants intact.
#
# Two failure modes it refuses:
#   * rewriting a working decoder. dynamics.tires.state and
#     vehicle.wheels.vehicle_wheels were ALREADY decoded; naming them in a queue
#     of "undecoded topics" sends someone to redo working code.
#   * presenting constructed payloads as captures. Capture needs sole-subscriber
#     websocket access, i.e. production stopped. These are transcription tests and
#     the docs say so.

source "$(dirname "$0")/_lib.sh"

echo "f5 — Parallax decoders"

P="$HA/custom_components/rivian/rivian_client/parallax.py"
MIRROR="$CLIENT/src/rivian/parallax.py"
T="$HA/tests/client/test_f5_decoders.py"
DOC="$HA/docs/development/PARALLAX_DECODERS.md"

have_path "the f5 test module exists" "$T"
have_path "the findings are recorded" "$DOC"
if git -C "$HA" ls-files --error-unmatch docs/development/PARALLAX_DECODERS.md >/dev/null 2>&1
then ok "the findings doc is tracked"; else bad "the findings doc is not tracked"; fi

VENV_PY="$(resolve_python "$HA")"

"$VENV_PY" - "$HA" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from custom_components.rivian.coordinator import SUBSCRIBED_RVMS  # noqa: E402
from custom_components.rivian.rivian_client.parallax import (  # noqa: E402
    RVM_DECODERS,
    decode_tires,
    decode_vehicle_wheels,
)

NEW = {
    "body.trailer.state", "comfort.cabin.pet_mode_status",
    "dynamics.vehicle.drive_mode", "dynamics.vehicle.gear",
    "dynamics.vehicle.location", "dynamics.vehicle.range",
    "energy.high_voltage.battery_characteristics",
    "energy.low_voltage.battery_state", "security.access.btm",
    "security.access.immobilizer_state", "security.access.passive_entry_debug",
    "security.access.vas_fault", "security.alarm.state",
    "security.video_monitoring.state",
}
problems = []
missing = NEW - set(RVM_DECODERS)
if missing:
    problems.append(f"not registered: {sorted(missing)}")
unsubscribed = NEW - set(SUBSCRIBED_RVMS)
if unsubscribed:
    problems.append(
        f"registered but not subscribed: {sorted(unsubscribed)} -- SUBSCRIBED_RVMS "
        "is the intersection, so this means a topic is not in PARALLAX_RVMS"
    )
if len(RVM_DECODERS) != 32:
    problems.append(f"{len(RVM_DECODERS)} decoders, expected 32 (18 + 14)")

# Working decoders must not have been replaced.
if RVM_DECODERS.get("dynamics.tires.state") is not decode_tires:
    problems.append("dynamics.tires.state decoder was replaced")
if RVM_DECODERS.get("vehicle.wheels.vehicle_wheels") is not decode_vehicle_wheels:
    problems.append("vehicle.wheels.vehicle_wheels decoder was replaced")

# The double-consumer topic must NOT be duplicated: the subscription code
# documents that a duplicated topic is delivered twice, and the app's own getter
# for the flag has no caller.
doubled = "comfort.cabin.climate_hold_status"
if SUBSCRIBED_RVMS.count(doubled) != 1:
    problems.append(f"{doubled} appears {SUBSCRIBED_RVMS.count(doubled)} times")

if problems:
    print("\n".join(problems)); sys.exit(1)
print(f"{len(RVM_DECODERS)} decoders, {len(SUBSCRIBED_RVMS)} subscribed topics")
PYEOF
check "14 new decoders registered, subscribed, and nothing overwritten" $?

contains "unknown-topic logging is deduped" '_WARNED_UNKNOWN_RVMS' "$P"
contains "the doc states the tests are transcription, not capture" \
         'transcription tests, not captures' "$DOC"
contains "the doc records the second RVM enum" 'iol.java' "$DOC"
contains "the doc records the unused double-consumer flag" \
         'has no caller' "$DOC"

if [ -f "$MIRROR" ]; then
  if diff -q "$P" "$MIRROR" >/dev/null; then
    ok "the sibling repo's parallax.py is identical"
  else
    bad "parallax.py was not mirrored to the sibling repo"
  fi
fi

for t in test_field_numbers_skip_two_through_seven \
         test_an_unmapped_value_is_dropped_not_invented \
         test_the_vocabulary_matches_what_the_sensor_already_maps \
         test_no_previously_working_decoder_was_replaced \
         test_an_unknown_topic_warns_once_not_once_per_message \
         test_the_double_consumer_flag_is_recorded_and_not_acted_on \
         test_immobilizer_treats_zero_as_a_real_value; do
  if grep -qF "def $t" "$T"; then ok "asserts: $t"
  else bad "missing required assertion: $t"; fi
done

PY="$(resolve_pytest "$HA")"
if (cd "$HA" && "$PY" tests/client/test_f5_decoders.py -q --no-cov \
      -p no:cacheprovider >/dev/null 2>&1); then
  ok "the f5 test module is green"
else
  bad "the f5 test module fails"
fi

out=$(cd "$HA" && "$PY" -q --no-cov -p no:cacheprovider 2>&1 || true)
note "$(echo "$out" | tail -1)"
if echo "$out" | grep -qE '^FAILED '; then bad "suite has failures"; else ok "suite green"; fi
# WITH coverage. The suite above runs --no-cov for speed, which leaves whatever
# coverage.json happened to be on disk -- and a single-module run leaves a partial
# one reporting 38%. check_coverage.py now refuses a partial report outright, but
# regenerating here is what makes this check mean anything.
if (cd "$HA" && "$PY" -q -p no:cacheprovider >/dev/null 2>&1 \
    && "$VENV_PY" scripts/check_coverage.py >/dev/null 2>&1); then
  ok "both coverage floors hold"
else
  bad "a coverage floor broke"
fi
test_count "$HA" 1510

summary f5
