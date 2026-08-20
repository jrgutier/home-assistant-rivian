#!/usr/bin/env bash
# s15 — three-state connectivity, wake-first dispatch, and the re-keyed ceiling.
#
# What this gate CAN prove: the derivation is a total function matching the app's
# C1611c.java:141-158 across all fifteen input cells (executed, not grepped); the
# coordinator's cloud flag is genuinely tri-state; exactly ONE of the five
# availability gates moved and the other four are still there verbatim; the
# cloud_connected sensor still reads the raw flag and never the derived state; the
# blocking wake-wait and the Event it waited on are gone; the command ceiling is
# 60/120 and f9's LOWERING interlock is still armed; the deleted per-description
# opt-out flag has no occurrences left anywhere; and the named unit tests behind
# all of the above exist, pass, and are not skipped.
#
# What this gate CANNOT prove, and no repo check can: that a real sleeping vehicle
# accepts a cloud command dispatched behind a non-awaited wake. Every check here is
# repo-local. The live run is a separate story; this gate proves the logic, only a
# vehicle proves the wire.

source "$(dirname "$0")/_lib.sh"

echo "s15 — connectivity states, wake-first dispatch, 60/120 ceiling"

VENV_PY="$(resolve_python "$HA")"
PYTEST="$(resolve_pytest "$HA")"

CONN="$HA/custom_components/rivian/connectivity.py"
COORD="$HA/custom_components/rivian/coordinator.py"
E="$HA/custom_components/rivian/entity.py"
BS="$HA/custom_components/rivian/binary_sensor.py"
BTN="$HA/custom_components/rivian/button.py"
DC="$HA/custom_components/rivian/data_classes.py"
DOC="$HA/docs/E2E_ACCEPTANCE.md"

have_path "connectivity.py" "$CONN"
have_path "coordinator.py" "$COORD"
have_path "entity.py" "$E"
have_path "binary_sensor.py" "$BS"
have_path "button.py" "$BTN"
have_path "data_classes.py" "$DC"
have_path "the E2E record" "$DOC"

# --- 1. the truth table, EXECUTED -------------------------------------------
# A grep cannot prove a truth table. All fifteen cells are run in-process and the
# first mismatch is named, so a wrong cell reports which cell.
if "$VENV_PY" - "$HA" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from custom_components.rivian.connectivity import (
    ConnectivityState as S,
    derive_connectivity_state as d,
)

TABLE = [
    (None,  "sleep",   S.SLEEPING), (None,  "standby", S.ONLINE),
    (None,  "ready",   S.ONLINE),   (None,  "go",      S.ONLINE),
    (None,  None,      S.ONLINE),
    (True,  "sleep",   S.SLEEPING), (True,  "standby", S.ONLINE),
    (True,  "ready",   S.ONLINE),   (True,  "go",      S.ONLINE),
    (True,  None,      S.ONLINE),
    (False, "sleep",   S.SLEEPING), (False, "standby", S.SLEEPING),
    (False, "ready",   S.OFFLINE),  (False, "go",      S.OFFLINE),
    (False, None,      S.OFFLINE),
]
if len(TABLE) != 15:
    raise SystemExit(f"table has {len(TABLE)} cells, want 15")
for is_online, power, want in TABLE:
    got = d(is_online, power)
    if got is not want:
        raise SystemExit(
            f"cell (isOnline={is_online!r}, powerState={power!r}): "
            f"got {got}, want {want}"
        )
print("all 15 cells match C1611c.java:141-158")
PY
then ok "the derivation matches the app across all 15 cells"
else bad "the derivation matches the app across all 15 cells"
fi

# --- 2. enum surface --------------------------------------------------------
if "$VENV_PY" - "$HA" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from custom_components.rivian.connectivity import ConnectivityState

got = [m.value for m in ConnectivityState]
if got != ["online", "sleeping", "offline"]:
    raise SystemExit(f"members {got!r}")
print("three members: online sleeping offline")
PY
then ok "ConnectivityState has exactly three members with lowercase values"
else bad "ConnectivityState has exactly three members with lowercase values"
fi

# --- 3. the coordinator's cloud flag is tri-state ---------------------------
# The `False` default is the whole point: with it, a frame that OMITS isOnline
# collapses to offline, which is a different rule from the app's null case. One
# rule for both spellings of "unknown", or it is not mirroring.
contains "_is_online initialises to None" '_is_online: bool | None = None' "$COORD"
contains "isOnline is read with no default" 'connection_data.get("isOnline")' "$COORD"
try "no False default on isOnline" \
  bash -c "! grep -qF 'get(\"isOnline\", False)' '$COORD'"
contains "connectivity_state() exists on the coordinator" "def connectivity_state" "$COORD"
contains "the transition log renders three states" "def _online_label" "$COORD"
contains "the unknown label exists" '"unknown"' "$COORD"

# --- 4. ONE gate moved, and only that one -----------------------------------
# This is the check that catches a "while I was in there" edit. The four survivors
# are pinned positively: dropping any of them would let a driving vehicle, an
# unpaired phone, a description's own guard, or the zone restriction be bypassed.
contains "gate 1 is an OFFLINE check" "ConnectivityState.OFFLINE" "$E"
try "entity.py no longer calls is_online()" \
  bash -c "! grep -qF 'coordinator.is_online()' '$E'"
contains "survivor: park gate" \
  'super().available and self._get_value("gearStatus") == "park"' "$E"
contains "survivor: per-description available lambda" \
  'getattr(self.entity_description, "available", None)' "$E"
contains "survivor: zone restriction (CONF_ZONE)" "CONF_ZONE" "$E"
contains "survivor: zone restriction (in_zone)" "in_zone" "$E"

# --- 5. scope respected: cloud_connected still reads the RAW flag -----------
# Positive pin is the bool() form, not the bare call: the coercion is what keeps
# the sensor rendering `off` rather than `unknown` once _is_online can be None.
contains "cloud_connected reads the raw flag, coerced" \
  "return bool(self.coordinator.is_online())" "$BS"
try "binary_sensor.py never derives connectivity_state" \
  bash -c "! grep -qF 'connectivity_state' '$BS'"

# --- 6. the wake is dispatched, never awaited -------------------------------
try "the _awake Event is gone from coordinator.py" \
  bash -c "! grep -qF '_awake' '$COORD'"
try "no wait_for on an Event in coordinator.py" \
  bash -c "! grep -qE 'wait_for\(self\._awake' '$COORD'"
contains "the no-nested-wake guard is retained" \
  "command != VehicleCommand.WAKE_VEHICLE" "$COORD"
contains "the wake trigger is the derived SLEEPING state" \
  "ConnectivityState.SLEEPING" "$COORD"

# --- 7. the ceiling, and f9's LOWERING interlock still armed ----------------
contains "awake ceiling is 60" "COMMAND_TIMEOUT_AWAKE: Final = 60" "$E"
contains "sleeping ceiling is 120" "COMMAND_TIMEOUT_SLEEPING: Final = 120" "$E"
try "the 30 s default is gone from entity.py" \
  bash -c "! grep -qF 'timeout: int = 30' '$E'"
# AC-15. Raising the ceiling required editing f9; it did NOT license disarming it.
# The token means "the owner ratified a LOWERED ceiling" and nobody did.
try "the lowering interlock is still armed (no ratification token)" \
  bash -c "! grep -qF 'CEILING RATIFIED BY OWNER' '$DOC'"
contains "f9 still checks the measurement token" \
  "NON-WAKE FIRST-FRAME LATENCY MEASURED:" "$HA/scripts/gates/f9.sh"
contains "f9 still checks the ratification token" \
  "CEILING RATIFIED BY OWNER" "$HA/scripts/gates/f9.sh"
try "f9 itself passes with the re-keyed pin" bash "$HA/scripts/gates/f9.sh"

# --- 8. the deleted opt-out flag has no occurrences left --------------------
# Four separate calls, because `absent` FAILS on a missing dir: a gate phrased
# "grep returns empty" would pass vacuously against a path that does not exist.
#
# The flag's name is ASSEMBLED, never written whole. One of the searched trees is
# scripts/, which is where this file lives -- spelling it out here would make the
# gate match itself and fail forever. (f9 has the same shape for the same reason,
# and learned it the hard way: an explanatory comment quoting a retired marker
# satisfied the very grep that was checking the marker was gone.)
FLAG="available"'_offline'
absent "no opt-out flag in custom_components" "$FLAG" "$HA/custom_components"
absent "no opt-out flag in tests" "$FLAG" "$HA/tests"
absent "no opt-out flag in scripts" "$FLAG" "$HA/scripts"
absent "no opt-out flag in docs" "$FLAG" "$HA/docs"
try "the field is gone from data_classes.py" \
  bash -c "! grep -qF '$FLAG' '$DC'"
contains "the wake button guards on SLEEPING" "ConnectivityState.SLEEPING" "$BTN"

# --- 9. named unit tests exist and pass; nothing skipped --------------------
# Node ids, not a module glob. The `grep "def <name>"` pass is what catches a
# rename that was supposed to happen and did not: two of these tests do NOT go
# red when left unrewritten -- one passes for the wrong reason (via the park
# gate) -- so a green suite is not on its own evidence the rename landed.
NODES=(
  tests/test_connectivity.py::test_the_truth_table
  tests/test_connectivity.py::test_null_is_online_is_treated_as_online
  tests/test_connectivity.py::test_standby_only_sleeps_when_the_cloud_says_offline
  tests/test_connectivity.py::test_an_unknown_power_state_string_is_not_special_cased
  tests/test_entity.py::TestRivianVehicleControlEntity::test_available_when_sleeping
  tests/test_entity.py::TestRivianVehicleControlEntity::test_sleeping_does_not_bypass_the_park_gate
  tests/test_entity.py::TestRivianVehicleControlEntity::test_unavailable_when_offline
  tests/test_wake_sequencing.py::test_a_sleeping_command_dispatches_wake_first
  tests/test_wake_sequencing.py::test_a_sleeping_command_does_not_stall
  tests/test_wake_sequencing.py::test_wake_itself_does_not_recurse
  tests/test_wake_sequencing.py::test_no_event_wait_remains_in_send_vehicle_command
  tests/test_coordinator_callbacks.py::TestCloudConnection::test_a_missing_isOnline_becomes_unknown_not_stale
  tests/test_coordinator_callbacks.py::TestCloudConnection::test_an_absent_key_and_an_explicit_null_agree
  tests/test_button.py::TestTheWakeButtonIsUsableWhenAsleep::test_the_wake_button_is_available_only_while_sleeping
  tests/test_button.py::TestTheWakeButtonIsUsableWhenAsleep::test_no_description_declares_the_deleted_opt_out_flag
  tests/test_button.py::TestTheWakeButtonIsUsableWhenAsleep::test_an_offline_coordinator_still_hides_ordinary_controls
  tests/test_command_state.py::TestCeilingInterlockKeysOnTheRightQuantity::test_the_ceiling_is_now_sixty_and_one_twenty
  tests/test_command_state.py::TestCeilingInterlockKeysOnTheRightQuantity::test_the_gate_cites_the_docstring_that_fixes_the_quantity
  tests/test_command_state.py::TestCeilingInterlockKeysOnTheRightQuantity::test_the_gate_requires_both_tokens
  tests/test_command_state.py::TestTheCeilingFollowsTheConnectivityState::test_an_awake_vehicle_gets_sixty
  tests/test_command_state.py::TestTheCeilingFollowsTheConnectivityState::test_a_sleeping_vehicle_gets_the_longer_ceiling
  tests/test_command_state.py::TestTheCeilingFollowsTheConnectivityState::test_an_explicit_timeout_still_wins
)
for node in "${NODES[@]}"; do
  name="${node##*::}"
  file="$HA/${node%%::*}"
  if [ -f "$file" ] && grep -qF "def $name" "$file"; then
    ok "named test exists: $name"
  else
    bad "named test missing: $name"
  fi
done

if [ ! -x "$PYTEST" ]; then
  bad "pytest not found"
else
  out=$(cd "$HA" && "$PYTEST" -q --no-cov -p no:cacheprovider "${NODES[@]}" 2>&1 || true)
  note "$(echo "$out" | tail -1)"
  if echo "$out" | grep -qE '^FAILED '; then
    bad "named s15 tests failed"
  else
    ok "named s15 tests passed"
  fi
  # UNANCHORED, deliberately. `pytest -q` prints "22 passed, 1 skipped in 0.5s" --
  # the passed count comes first, so an anchored `^[0-9]+ skipped` matches only
  # when EVERY named node skipped and one skip among many slips straight through.
  # Any skip among these nodes is a defect by definition, not a judgement call.
  if echo "$out" | grep -qE '[0-9]+ skipped'; then
    bad "named s15 tests: something was skipped"
  else
    ok "named s15 tests: nothing skipped"
  fi
fi

# --- 10. full suite, skip count, and lint ----------------------------------
# The skip baseline is a LITERAL, measured before this change landed: 1695 passed,
# 0 skipped. "Green" reached by skipping is not green, and leaving that to a human
# reading a checklist is how it gets missed.
SKIP_BASELINE=0
if [ ! -x "$PYTEST" ]; then
  bad "pytest not found for the full suite"
else
  full=$(cd "$HA" && "$PYTEST" tests/ -q --no-cov -p no:cacheprovider 2>&1 || true)
  note "$(echo "$full" | tail -1)"
  if echo "$full" | grep -qE '^FAILED '; then
    bad "full suite passes"
  else
    ok "full suite passes"
  fi
  skipped=$(echo "$full" | grep -oE '[0-9]+ skipped' | head -1 | grep -oE '^[0-9]+' || true)
  skipped="${skipped:-0}"
  if [ "$skipped" -le "$SKIP_BASELINE" ]; then
    ok "skips $skipped <= baseline $SKIP_BASELINE"
  else
    bad "skips $skipped > baseline $SKIP_BASELINE (green by skipping is not green)"
  fi
fi

RUFF="$HA/.venv/bin/ruff"
if [ -x "$RUFF" ]; then
  try "ruff check clean" bash -c "cd '$HA' && '$RUFF' check ."
  try "ruff format clean" bash -c "cd '$HA' && '$RUFF' format --check ."
else
  bad "ruff not found at $RUFF"
fi

# --- 11. the suite did not shrink ------------------------------------------
# Floor = the pre-change collected count (1695) + 20. This change adds 15
# parametrized cells plus more than a dozen named tests; 20 is deliberately
# conservative. Must stay >= f5's own floor.
test_count "$HA" 1715

summary S15
