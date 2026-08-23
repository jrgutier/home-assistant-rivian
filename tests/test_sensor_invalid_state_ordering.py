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

    def test_a_lambda_that_would_rescue_an_invalid_value_does_not_get_to(self) -> None:
        """`charge_port_status` maps every invalid spelling to "Unknown".

        That mapping is fine and stays -- but it must never be what decides the
        outcome, because a lambda that rescues an invalid value is exactly how the
        old ordering hid the bug. The raw check has to win first.
        """
        description = DESCRIPTIONS["charge_port_status"]
        assert description.value_lambda("signal_not_available") == "Unknown"
        assert _native_value(description, "signal_not_available") is None

    def test_valid_values_still_pass_through_the_lambda(self) -> None:
        """The fix must not break the normal path."""
        description = DESCRIPTIONS["charge_port_status"]
        assert _native_value(description, "in_transition") == "In Transition"
        assert _native_value(description, "close") == "Close"
