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
#   * presenting constructed payloads as captures. These are transcription tests
#     and the docs say so -- because no capture has been taken, NOT because one
#     is hard to take. The old reason ("capture needs sole-subscriber websocket
#     access, i.e. production stopped") is FALSIFIED 2026-08-20: arm 3b received
#     the full 33-topic RVM set with production subscribed. See
#     docs/development/WS_CONTENTION.md, claim C8. Capture is now schedulable
#     with no outage; until it happens these stay transcription tests.

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
# s34 added four, each backed by a captured frame and a value assertion in
# tests/test_parallax_s34_decoders.py. They are pinned by NAME rather than
# folded into the total, because a count alone cannot tell "four shipped" from
# "four different ones shipped and four regressed".
S34 = {
    "comfort.cabin.cabin_ventilation_setting",
    "gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent",
    "gearguard_streaming.privacy.gearguard_streaming_daily_limit",
    "energy_edge_compute.graphs.parked_energy_distributions",
}
if missing_s34 := S34 - set(RVM_DECODERS):
    problems.append(f"s34 decoder not registered: {sorted(missing_s34)}")
if unsub_s34 := S34 - set(SUBSCRIBED_RVMS):
    problems.append(f"s34 registered but not subscribed: {sorted(unsub_s34)}")

# 33 + the four above. This gate read `!= 33` from s34's merge until 2026-09-01
# and was RED on master the whole time -- s34 shipped the decoders and left the
# count. Adding a decoder is a live-behaviour change (SUBSCRIBED_RVMS derives
# from RVM_DECODERS), so the number stays explicit and stays enforced.
if len(RVM_DECODERS) != 37:
    problems.append(
        f"{len(RVM_DECODERS)} decoders, expected 37 (18 + 14 transcribed + "
        "vehicle.network.state, taken on an inference, + the four s34 above)"
    )

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
# Was: 'has no caller'. That claim was FALSE -- a case-sensitive grep for the
# lowercase Kotlin property missed the generated getter -- and the gate was
# enforcing the error. It now asserts the corrected finding.
contains "the doc records what the double-consumer flag actually routes" \
         'flow down **both**' "$DOC"
contains "the doc records the group subscription centre" \
         'PVMParallaxGroupSubscriptionCenter' "$DOC"

if [ -f "$MIRROR" ]; then
  if diff -q "$P" "$MIRROR" >/dev/null; then
    ok "the sibling repo's parallax.py is identical"
  else
    bad "parallax.py was not mirrored to the sibling repo"
  fi
else
  note "sibling rivian-python-client not present — skipping the parallax-mirror check"
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

pytest_green "$HA" "$PY" "suite"
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
