"""The app's vehicle-state value vocabulary, checked against our binary sensors.

Transcribed from `com.rivian.android.consumer` 3.15.0 (build 4804), the same
artifact `docs/development/apk/REGENERATION.md` describes. Two sources:

  * `smali_classes2/com/rivian/android/consumer/data/model/VehicleStateKt.smali`
    -- the predicates the app applies to the GraphQL `VehicleState`. It declares
    exactly six string constants (`OPEN`, `OPENED`, `CLOSED`, `LOCKED`,
    `UNLOCKED`, `UNKNOWN`), and each `isXOpen` method names the ones it accepts.
  * `java_src/com/rivian/android/consumer/data/model/*.java` -- 84 enum-like
    model classes, one per field vocabulary, bound to field names by
    `VehicleState.java` / `VehicleState2.java`.

Like `test_apk_transcription.py`, nothing here reads the decompilation: it is
gitignored, so a clean checkout could not run such a test, and a skipped test is
worse than an absent one. The vocabulary is transcribed into the constants below
and compared against `const.py`.

The full reasoning, and the three rows where a keyword match was wrong and the
binding corrected it, are in `docs/development/BINARY_SENSOR_AUDIT.md`.
"""

from __future__ import annotations

import pytest

from custom_components.rivian.const import (
    BINARY_SENSORS,
    INVALID_SENSOR_STATES,
    SENSORS,
)

# --- transcription -----------------------------------------------------------

# `VehicleStateKt.isFrunkOpen` accepts three values; every other `isXOpen`
# accepts two. `ajar` is a distinct constant in `p069Ci/EnumC0996d.java`.
OPEN_VALUES = ("open", "opened")
FRUNK_OPEN_VALUES = ("open", "opened", "ajar")

# `VehicleStateKt` declares LOCKED/UNLOCKED and nothing else on the lock axis;
# `areDoorsLocked` tests `locked` alone. Two states -> binary is correct.
LOCK_VALUES = ("locked", "unlocked")

# `ChargePortStatus` (bound to `chargePortControlState` in VehicleState.java).
# Note the closed value is `close`, NOT `closed` -- it appears that way in our
# own fixtures too.
CHARGE_PORT_VALUES = (
    "open",
    "close",
    "in_transition",
    "fault",
    "opening",
    "closing",
    "unknown",
)

# `PowerState`: four non-invalid states, so `use_state` (device_class MOVING,
# on_value "go") deliberately collapses three of them to off. The full
# vocabulary is not lost -- `power_state` is a regular sensor on the same field.
POWER_STATE_VALUES = ("go", "ready", "sleep", "standby", "unknown")

# Fields whose app enum has exactly two non-invalid members, so a binary sensor
# is the correct platform. key -> (enum class, on_value).
TWO_STATE_BINARY = {
    "btm_ff_hardware_failure_status": ("BtmFaultStatus", "detected"),
    "btm_oc_hardware_failure_status": ("BtmFaultStatus", "detected"),
    "btm_rf_hardware_failure_status": ("BtmFaultStatus", "detected"),
    "btm_ic_hardware_failure_status": ("BtmFaultStatus", "detected"),
    "btm_rfd_hardware_failure_status": ("BtmFaultStatus", "detected"),
    "btm_lfd_hardware_failure_status": ("BtmFaultStatus", "detected"),
    "battery_hv_thermal_event": ("BatteryThermalEvent", "detected"),
    "battery_hv_thermal_event_propagation": ("BatteryThermalEvent", "detected"),
    "twelve_volt_battery_health": ("TwelveVoltBatteryHealth", "low"),
    "service_mode": ("ServiceModeStatus", "on"),
    "ota_install_ready": ("OverTheAirInstallReady", "available"),
    "car_wash_mode": ("CarWashModeStatus", "on"),
}


def _descriptions(collection):
    return {d.key: d for group in collection.values() for d in group}


BINARY = _descriptions(BINARY_SENSORS)
SENSOR = _descriptions(SENSORS)


def _on_values(description) -> list[str]:
    """`on_value` as a list, via the description's own normalization.

    Deliberately NOT a local reimplementation: that is what these tests exist to
    pin, and a copy here would keep passing after the real one drifted.
    """
    return list(description.on_values)


# --- closures ----------------------------------------------------------------


class TestOpenClosedVocabulary:
    """Every closure must accept `opened`, not only `open`."""

    # Everything whose on_value is the open axis, minus the charge port, which
    # has its own richer vocabulary and its own test below.
    CLOSURE_KEYS = sorted(
        key
        for key, d in BINARY.items()
        if "open" in _on_values(d) and key != "charge_port_state"
    )

    def test_the_closure_set_is_what_we_think_it_is(self) -> None:
        """Guards the parametrization: a new closure must not slip past."""
        assert len(self.CLOSURE_KEYS) == 16, self.CLOSURE_KEYS

    @pytest.mark.parametrize("key", CLOSURE_KEYS)
    def test_every_closure_accepts_opened(self, key: str) -> None:
        """`isLeftFrontDoorOpen` and its siblings all test `open` OR `opened`.

        Accepting only `open` is why this was a defect and not a nicety: a value
        the app treats as open does not equal "open", so it falls through to
        `off` and the entity reports a confident Closed. Not `unknown` -- `off`.
        """
        assert "opened" in _on_values(BINARY[key]), key

    def test_only_the_frunk_accepts_ajar(self) -> None:
        """`isFrunkOpen` is the one predicate of the fourteen testing `ajar`.

        Widening the others to match would exceed the app, which this repo
        treats as a defect in its own right -- the app is a lower bound for
        which fields exist, never a licence to invent values for them.
        """
        accepts_ajar = {k for k in self.CLOSURE_KEYS if "ajar" in _on_values(BINARY[k])}
        assert accepts_ajar == {"closure_frunk_closed"}

    def test_the_frunk_carries_the_full_three(self) -> None:
        assert set(_on_values(BINARY["closure_frunk_closed"])) == set(FRUNK_OPEN_VALUES)


class TestAggregateDescriptionsWereWidenedToo:
    """`door_state` and `closure_state` take a set of fields, not one.

    They run a different `is_on` branch (`binary_sensor.py`, the `_aggregate`
    path). Widening them without widening that branch would have reported Closed
    forever rather than raising -- see TestAggregateOnValueNormalization.
    """

    @pytest.mark.parametrize("key", ["door_state", "closure_state"])
    def test_aggregate_accepts_opened(self, key: str) -> None:
        assert isinstance(BINARY[key].field, set), f"{key} stopped being an aggregate"
        assert "opened" in _on_values(BINARY[key])


# --- locks -------------------------------------------------------------------


class TestLockVocabulary:
    """Two states, so these are correct as binary sensors and stay that way."""

    LOCK_KEYS = sorted(k for k, d in BINARY.items() if "unlocked" in _on_values(d))

    def test_there_are_eleven_lock_descriptions_plus_the_aggregate(self) -> None:
        assert len(self.LOCK_KEYS) == 12, self.LOCK_KEYS

    @pytest.mark.parametrize("key", LOCK_KEYS)
    def test_locks_were_not_widened(self, key: str) -> None:
        """`VehicleStateKt` has LOCKED and UNLOCKED and no third lock value.

        There is nothing to widen here, and adding a value the app does not
        declare would be the inverse mistake of the closure defect.
        """
        assert set(_on_values(BINARY[key])) <= set(LOCK_VALUES), key


# --- charge port -------------------------------------------------------------


class TestChargePortVocabulary:
    """Five non-invalid states, the most of any binary-sensor field."""

    def test_travel_states_are_not_reported_closed(self) -> None:
        """`opening`, `closing` and `in_transition` are not a closed port.

        `closing` is deliberately absent from on_value: a port that is closing
        is on its way to closed, and reporting the DOOR device class as still
        open through the whole travel would keep a "did I leave it open" alert
        firing. `opening` and `in_transition` are not closed by any reading.
        """
        values = set(_on_values(BINARY["charge_port_state"]))
        assert {"open", "opening", "in_transition"} == values

    def test_close_is_spelled_without_the_d(self) -> None:
        """`ChargePortStatus.CLOSE`, not CLOSED. Matching `closed` would be a
        value the field never emits, silently doing nothing."""
        assert "close" in CHARGE_PORT_VALUES
        assert "closed" not in CHARGE_PORT_VALUES

    def test_the_richer_vocabulary_reaches_the_user(self) -> None:
        """A five-state field behind one boolean needs a companion sensor.

        `powerState` already had both platforms (`use_state` binary,
        `power_state` sensor) and is the precedent this follows.
        """
        assert SENSOR["charge_port_status"].field == "chargePortState"
        assert BINARY["charge_port_state"].field == "chargePortState"


class TestChargePortSensorSurvivesEveryValueItCanReceive:
    """No value in the app's vocabulary may fall outside the ENUM options.

    `sensor.py` applies `value_lambda` BEFORE testing INVALID_SENSOR_STATES, and
    `_to_title_case` turns underscores into spaces. So a lambda that special-cases
    the string "sna" lets "signal_not_available" through as "Signal Not Available",
    which matches nothing in the set, misses the filter, logs an error, and
    appends itself to the entity's own options list for the life of the process.

    Asserting `"Fault" not in options` would pin the symptom. This pins the
    property: every value the app can emit resolves to something renderable.
    """

    @pytest.mark.parametrize("value", CHARGE_PORT_VALUES)
    def test_every_app_value_is_renderable(self, value: str) -> None:
        description = SENSOR["charge_port_status"]
        options = description.options or []
        rendered = description.value_lambda(value)
        # Either sensor.py will resolve it to None, or it must be a valid option.
        filtered = str(rendered).lower() in INVALID_SENSOR_STATES
        assert filtered or rendered in options, (
            f"{value!r} -> {rendered!r} is neither filtered nor in options {options}"
        )

    def test_fault_is_unreachable_so_it_is_not_an_option(self) -> None:
        """Kept out of `options` deliberately, not by oversight."""
        assert "fault" in CHARGE_PORT_VALUES  # the app really does emit it
        assert "Fault" not in (SENSOR["charge_port_status"].options or [])


class TestPowerStateIsAlreadyHandled:
    """Four states, but both platforms already exist. No change was needed."""

    def test_both_platforms_read_the_same_field(self) -> None:
        assert BINARY["use_state"].field == "powerState"
        assert SENSOR["power_state"].field == "powerState"

    def test_only_go_counts_as_moving(self) -> None:
        assert _on_values(BINARY["use_state"]) == ["go"]
        assert len(POWER_STATE_VALUES) > 2


# --- the converted twelve ----------------------------------------------------


class TestTwoStateFieldsAreBinarySensors:
    """Fields whose app enum has exactly two non-invalid members."""

    @pytest.mark.parametrize(("key", "expected"), sorted(TWO_STATE_BINARY.items()))
    def test_is_a_binary_sensor_with_the_transcribed_on_value(
        self, key: str, expected: tuple[str, str]
    ) -> None:
        enum_class, on_value = expected
        assert key in BINARY, f"{key} should be a binary sensor ({enum_class})"
        assert key not in SENSOR, f"{key} is still a sensor as well"
        assert on_value in _on_values(BINARY[key]), f"{key} ({enum_class})"

    def test_the_alarm_keeps_both_spellings(self) -> None:
        """`SoundAlarm` is {ACTIVE, INACTIVE, SIGNAL_NOT_AVAILABLE}, but the
        sensor this replaced carried a value_lambda mapping "true"/"false" as
        well, so the field has been seen carrying booleans. Dropping either
        spelling reports a sounding alarm as silent."""
        assert set(_on_values(BINARY["alarm_sound_status"])) == {"active", "true"}


class TestFieldsDeliberatelyNotConverted:
    """Three keyword matches the field bindings overturned.

    Recorded as tests because the keyword heuristic that produced them is easy
    to re-run and would propose all three again.
    """

    def test_wiper_fluid_state_has_three_states_not_two(self) -> None:
        """`wiperFluidState` is typed `WiperFluidState` in VehicleState2.java --
        {EMPTY, LOW, NORMAL} -- NOT the two-member `FluidLevelLow` a name match
        suggests. The existing three-option sensor was already right."""
        assert "wiper_fluid_state" in SENSOR
        assert "wiper_fluid_state" not in BINARY
        options = SENSOR["wiper_fluid_state"].options
        assert options is not None and len(options) == 3

    def test_brake_fluid_low_has_no_binding_in_the_app(self) -> None:
        """`brakeFluidLow` appears in neither `VehicleState` nor
        `VehicleState2`. No vocabulary, so no verdict -- the same outcome as the
        four `tirePressureStatusValid*` in docs/development/UNPOPULATED_FIELDS.md.
        Left as a sensor rather than guessed into a boolean."""
        assert "brake_fluid_low" in SENSOR
        assert "brake_fluid_low" not in BINARY

    def test_ota_deployment_intent_is_two_members_but_not_boolean(self) -> None:
        """`OverTheAirDeploymentIntent` is {PERFORMANCE_UPGRADE, UNSPECIFIED}.

        Two members, and the binding is confirmed -- but UNSPECIFIED is not the
        negation of PERFORMANCE_UPGRADE, it is the absence of an answer. The
        two-state rule is a filter for candidates, not a conversion trigger.
        """
        assert "ota_deployment_intent" in SENSOR
        assert "ota_deployment_intent" not in BINARY


# --- the regression the widening could have caused ---------------------------


class TestNoDescriptionSilentlyLostItsAggregatePath:
    """Every aggregate description must still be reachable as a list.

    `binary_sensor.py`'s aggregate branch used `on_value in (values...)`, which
    is correct for a bare string and always False for a list. Widening an
    aggregate without fixing that branch turns the entity permanently off
    instead of raising, which no existing test would have caught.
    """

    def test_every_aggregate_on_value_is_normalizable(self) -> None:
        aggregates = {k: d for k, d in BINARY.items() if isinstance(d.field, set)}
        assert aggregates, "no aggregate descriptions found -- test is vacuous"
        for key, description in aggregates.items():
            values = _on_values(description)
            assert isinstance(values, list) and values, key
            assert all(isinstance(v, str) for v in values), key
