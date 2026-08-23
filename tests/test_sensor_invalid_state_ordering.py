"""`sensor.py` and `binary_sensor.py` must filter the same value at the same point.

They did not. `binary_sensor.py` tested the RAW value against `INVALID_SENSOR_STATES`;
`sensor.py` tested the OUTPUT of `value_lambda`. Most lambdas run `_to_title_case`,
which turns underscores into spaces, so `signal_not_available` reached the check as
`"signal not available"` and matched nothing in the set. It then failed the ENUM
options check, logged an error, and appended itself to that entity's own `options`
list for the life of the process.

**27 of the 31** options-carrying sensors leaked that way. This file pins the class,
not the instance: a new ENUM sensor added tomorrow is covered without anyone
remembering to add a case.

All four spellings are the app's own -- `java_src/p069Ci/EnumC0996d.java` declares
`FAULT`, `SIGNAL_NOT_AVAILABLE`, `SNA` and `UNDEFINED` as distinct constants -- so
`INVALID_SENSOR_STATES` was already correct and APK-aligned. Only the comparison
point was wrong. Do not "fix" the constant.
"""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.rivian.const import INVALID_SENSOR_STATES, SENSORS
from custom_components.rivian.sensor import RivianSensorEntity

DESCRIPTIONS = {d.key: d for group in SENSORS.values() for d in group}
WITH_OPTIONS = sorted(k for k, d in DESCRIPTIONS.items() if getattr(d, "options", None))


class _FakeSensor:
    """The narrowest object `native_value` actually touches."""

    def __init__(self, description: Any, value: Any) -> None:
        self.entity_description = description
        self._value = value
        self.entity_id = f"sensor.fake_{description.key}"
        self.unique_id = self.entity_id
        self.options = list(description.options or [])
        self.device_class = description.device_class
        self.native_unit_of_measurement = description.native_unit_of_measurement

    def _get_value(self, _field: Any) -> Any:
        return self._value


def _native_value(description: Any, value: Any) -> Any:
    return RivianSensorEntity.native_value.fget(_FakeSensor(description, value))


class TestNoInvalidSpellingReachesTheOptionsCheck:
    """The property, stated once, for every sensor that has options."""

    def test_the_population_is_what_we_think_it_is(self) -> None:
        """Guards the parametrization below against silently shrinking."""
        assert len(WITH_OPTIONS) == 31, WITH_OPTIONS

    @pytest.mark.parametrize("key", WITH_OPTIONS)
    @pytest.mark.parametrize("spelling", sorted(INVALID_SENSOR_STATES))
    def test_invalid_spelling_resolves_to_none(self, key: str, spelling: str) -> None:
        """Every spelling the app can emit must resolve to `unknown`, not a state.

        Returning None yields HA's native `unknown`. The failure this replaces was
        worse than a wrong label: the entity MUTATED its own options list, so the
        vehicle's error code became a permanently valid state for that process.
        """
        assert _native_value(DESCRIPTIONS[key], spelling) is None, f"{key} / {spelling}"

    @pytest.mark.parametrize("key", WITH_OPTIONS)
    def test_options_are_never_mutated_by_an_invalid_value(self, key: str) -> None:
        """The append is the real damage; assert it never happens."""
        description = DESCRIPTIONS[key]
        entity = _FakeSensor(description, "signal_not_available")
        before = list(entity.options)
        RivianSensorEntity.native_value.fget(entity)
        assert entity.options == before, key


class TestOrderingMatchesBinarySensor:
    """The raw value is tested BEFORE the lambda, not after."""

    def test_the_raw_check_is_the_only_thing_protecting_the_entity(self) -> None:
        """There is no safety net under the raw check, and none is needed.

        This assertion used to read the other way round: the lambda mapped every
        invalid spelling to "Unknown", and the test showed the raw check won
        anyway. That guard has since been removed, precisely BECAUSE the raw
        check made it unreachable -- so the lambda now passes an invalid value
        straight through, and the property is stronger for it.

        `signal_not_available` -> "Signal Not Available" is a string that is not
        in `options` and is not a valid state. Nothing downstream would catch it.
        The raw check does, before the lambda is ever reached.
        """
        description = DESCRIPTIONS["charge_port_status"]
        rendered = description.value_lambda("signal_not_available")
        assert rendered == "Signal Not Available"
        assert rendered not in (description.options or [])
        assert _native_value(description, "signal_not_available") is None

    def test_the_same_holds_for_power_state(self) -> None:
        """The other lambda that carried a now-removed guard."""
        description = DESCRIPTIONS["power_state"]
        assert description.value_lambda("sna") == "Sna"
        assert _native_value(description, "sna") is None

    def test_the_empty_value_branch_is_still_load_bearing(self) -> None:
        """`""` passes the raw check, so the lambda's `if v` still matters.

        This is the half of the guard that was NOT removed. Deleting it too
        would make both entities render an empty string.
        """
        for key in ("charge_port_status", "power_state"):
            assert _native_value(DESCRIPTIONS[key], "") == "Unknown", key

    def test_valid_values_still_pass_through_the_lambda(self) -> None:
        """The fix must not break the normal path."""
        description = DESCRIPTIONS["charge_port_status"]
        assert _native_value(description, "in_transition") == "In Transition"
        assert _native_value(description, "close") == "Close"
