"""One get() for every coordinator.

There used to be three with incompatible signatures: the base took
(key, default), VehicleCoordinator took (key) only, and ParallaxCoordinator read
a separate _rvm_data store. So `vehicle_coordinator.get("x", False)` raised
TypeError while `charging_coordinator.get("x", False)` worked -- the same call
succeeding or failing purely on which coordinator the caller happened to hold.

The two data shapes it must serve:
  VehicleCoordinator   {"field": {"value": X, "history": {...}}}
  ChargingCoordinator  {"field": X}
"""

from unittest.mock import MagicMock

import pytest

from custom_components.rivian.coordinator import ChargingCoordinator, VehicleCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


@pytest.fixture
def vehicle(hass: HomeAssistant, mock_config_entry: ConfigEntry):
    return VehicleCoordinator(
        hass=hass,
        config_entry=mock_config_entry,
        client=MagicMock(),
        vehicle_id="v1",
    )


@pytest.fixture
def charging(hass: HomeAssistant, mock_config_entry: ConfigEntry):
    return ChargingCoordinator(
        hass=hass,
        config_entry=mock_config_entry,
        client=MagicMock(),
        vehicle_id="v1",
    )


class TestTheWrappedShape:
    def test_unwraps_value(self, vehicle) -> None:
        vehicle.data = {"gearStatus": {"value": "park", "history": {"park"}}}
        assert vehicle.get("gearStatus") == "park"

    def test_accepts_a_default_without_raising(self, vehicle) -> None:
        # The whole point: this used to be a TypeError on VehicleCoordinator.
        vehicle.data = {"gearStatus": {"value": "park", "history": set()}}
        assert vehicle.get("missing", False) is False

    def test_missing_key_returns_the_default(self, vehicle) -> None:
        vehicle.data = {"gearStatus": {"value": "park", "history": set()}}
        assert vehicle.get("nope", "fallback") == "fallback"

    def test_no_data_returns_the_default(self, vehicle) -> None:
        vehicle.data = None
        assert vehicle.get("gearStatus", "fallback") == "fallback"


class TestTheFlatShape:
    def test_returns_the_value_directly(self, charging) -> None:
        charging.data = {"power": 11}
        assert charging.get("power") == 11

    def test_default_still_applies(self, charging) -> None:
        charging.data = {"power": 11}
        assert charging.get("absent", 0) == 0


class TestDotNotation:
    def test_traverses_nested_keys(self, charging) -> None:
        charging.data = {"gnssLocation": {"latitude": 37.7}}
        assert charging.get("gnssLocation.latitude") == 37.7

    def test_a_missing_branch_returns_the_default(self, charging) -> None:
        charging.data = {"gnssLocation": {"latitude": 37.7}}
        assert charging.get("gnssLocation.altitude", -1) == -1

    def test_traversing_through_a_scalar_returns_the_default(self, charging) -> None:
        charging.data = {"power": 11}
        assert charging.get("power.nested", "d") == "d"


class TestSignatureIsUniform:
    def test_both_coordinators_accept_two_arguments(self, vehicle, charging) -> None:
        """The regression that started this: the same call had to work on both."""
        vehicle.data = {}
        charging.data = {}
        assert vehicle.get("anything", False) is False
        assert charging.get("anything", False) is False
