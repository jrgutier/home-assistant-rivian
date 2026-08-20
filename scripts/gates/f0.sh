#!/usr/bin/env bash
# f0 — a binary sensor reports `unknown` for a value the vehicle flags unusable,
# not a confident Closed/Locked.
#
# Two things this gate is careful about, because the cheapest green for each is
# wrong:
#
#   * `unknown`, not `unavailable`. Returning None from is_on does not change
#     availability. Making the entity unavailable instead would take the matching
#     CONTROL down with it -- the mistake made and reverted twice in the
#     coordinator. So the gate asserts availability is UNCHANGED, positively.
#
#   * The aggregate branch must stay byte-identical. binary_sensor.py:79-82
#     already ignores unusable values structurally, and adding a filter there
#     would change `available`, which is `any(member values)`.

source "$(dirname "$0")/_lib.sh"

echo "f0 — binary sensors stop reporting error codes as states"

BS="$HA/custom_components/rivian/binary_sensor.py"
T="$HA/tests/test_binary_sensor_invalid_states.py"

have_path "binary_sensor.py present" "$BS"
have_path "the f0 test module exists" "$T"

contains "binary_sensor.py imports INVALID_SENSOR_STATES" \
         'INVALID_SENSOR_STATES' "$BS"
contains "binary_sensor.py filters on it" \
         'str(val).lower() in INVALID_SENSOR_STATES' "$BS"

# The filter must precede the negation. `not False` is True, so filtering after
# the negate turns an unusable value into a confident True on every negated
# description -- a silent inversion that no count-based check would see.
filter_line=$(grep -n 'str(val).lower() in INVALID_SENSOR_STATES' "$BS" | head -1 | cut -d: -f1)
negate_line=$(grep -n 'entity_description.negate' "$BS" | head -1 | cut -d: -f1)
if [ -n "$filter_line" ] && [ -n "$negate_line" ] && [ "$filter_line" -lt "$negate_line" ]; then
  ok "the filter runs BEFORE the negate (line $filter_line < $negate_line)"
else
  bad "the filter does not precede the negate (filter=$filter_line negate=$negate_line)"
fi

# The aggregate branch is untouched: still a plain membership test, no filter.
if grep -qF 'self.entity_description.on_value in (' "$BS"; then
  ok "the aggregate branch is still a plain membership test"
else
  bad "the aggregate branch changed -- it must stay byte-identical"
fi

PY="$(resolve_pytest "$HA")"
if [ ! -x "$PY" ]; then bad "pytest not found"; summary f0; exit 1; fi

# Positive assertion. A negative-only gate ("no confident state") is satisfiable
# by deleting the entity, so the behaviour is asserted by running the tests that
# prove it -- including the ones that prove availability is UNCHANGED and the
# aggregate is unchanged.
if (cd "$HA" && "$PY" tests/test_binary_sensor_invalid_states.py -q --no-cov \
      -p no:cacheprovider >/dev/null 2>&1); then
  ok "the f0 test module is green"
else
  bad "the f0 test module fails"
fi

for t in test_the_entity_stays_available_it_only_goes_unknown \
         test_negate_does_not_resurrect_an_invalid_value \
         test_filter_is_reachable_on_a_first_update_with_no_history \
         test_the_entity_set_is_exactly_what_binary_sensors_declares; do
  if grep -qF "def $t" "$T"; then ok "asserts: $t"
  else bad "missing required assertion: $t"; fi
done

for t in test_one_member_open_among_unusable_ones_is_still_on \
         test_all_members_unusable_is_off_and_still_available \
         test_no_member_reports_at_all_is_unavailable; do
  if grep -qF "def $t" "$T"; then ok "aggregate guard: $t"
  else bad "missing aggregate guard: $t"; fi
done

# The whole suite, not just this module -- f0 must not regress anything.
pytest_green "$HA" "$PY" "suite"
test_count "$HA" 1314

summary f0
