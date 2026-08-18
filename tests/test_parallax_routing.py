"""VehicleCoordinator._process_parallax_data: where each decoded field goes.

This is upstream 1.5.3b5's router, and it was at 0% coverage after the merge --
which is where both merge defects were found. The rules it encodes are not
obvious and each exists for a recorded reason.
"""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.rivian.coordinator import VehicleCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

RVM = "some.rvm.type"


@pytest.fixture
def coordinator(hass: HomeAssistant, mock_config_entry: ConfigEntry):
    api = MagicMock()
    coord = VehicleCoordinator(
        hass=hass,
        config_entry=mock_config_entry,
        client=api,
        vehicle_id="test_vehicle_123",
    )
    coord.async_set_updated_data = MagicMock(
        side_effect=lambda d: setattr(coord, "data", d)
    )
    coord.charging_coordinator.update_from_parallax = MagicMock()
    return coord


def _message() -> dict:
    return {
        "payload": {
            "data": {"parallaxMessages": {"rvm": RVM, "payload": "x", "timestamp": "t"}}
        }
    }


def _route(coordinator, decoded: dict) -> None:
    with patch(
        "custom_components.rivian.coordinator.decode_parallax_message",
        return_value=decoded,
    ):
        coordinator._process_parallax_data(_message())


class TestRouting:
    def test_charging_fields_go_to_the_charging_coordinator(self, coordinator) -> None:
        _route(coordinator, {"power": 11, "totalChargedEnergy": 5})
        coordinator.charging_coordinator.update_from_parallax.assert_called_once()

    def test_vehicle_fields_are_wrapped_with_a_history(self, coordinator) -> None:
        # Vehicle state entities read {"value": ..., "history": {...}}; a bare
        # scalar would break every sensor reading this field.
        _route(coordinator, {"batteryLevel": 82})
        assert coordinator.data["batteryLevel"] == {"value": 82, "history": {82}}

    def test_gnss_location_is_passed_through_unwrapped(self, coordinator) -> None:
        # The device tracker reads latitude/longitude off it directly.
        loc = {"latitude": 1.0, "longitude": 2.0}
        _route(coordinator, {"gnssLocation": loc})
        assert coordinator.data["gnssLocation"] == loc

    def test_time_to_end_of_charge_goes_to_BOTH(self, coordinator) -> None:
        # It is declared in VEHICLE_SENSORS and is also a charging field, so the
        # router deliberately sends it to both coordinators.
        _route(coordinator, {"timeToEndOfCharge": 30})
        coordinator.charging_coordinator.update_from_parallax.assert_called_once()
        assert coordinator.data["timeToEndOfCharge"] == {"value": 30, "history": {30}}

    def test_internal_underscore_fields_are_dropped(self, coordinator) -> None:
        _route(coordinator, {"_raw": b"x", "batteryLevel": 50})
        assert "_raw" not in coordinator.data


class TestOdometerMonotonicGuard:
    """upstream ab760d1. Parallax encodes the odometer as integer km while GraphQL
    supplies float metres; with both live the value oscillated, and a decreasing
    odometer corrupts Home Assistant utility meters permanently."""

    def test_an_increase_is_accepted(self, coordinator) -> None:
        coordinator.data = {"vehicleMileage": {"value": 1000, "history": {1000}}}
        _route(coordinator, {"vehicleMileage": 1200})
        assert coordinator.data["vehicleMileage"]["value"] == 1200

    def test_an_equal_reading_is_accepted(self, coordinator) -> None:
        coordinator.data = {"vehicleMileage": {"value": 1000, "history": {1000}}}
        _route(coordinator, {"vehicleMileage": 1000})
        assert coordinator.data["vehicleMileage"]["value"] == 1000

    def test_a_DECREASE_is_rejected(self, coordinator) -> None:
        coordinator.data = {"vehicleMileage": {"value": 1000, "history": {1000}}}
        _route(coordinator, {"vehicleMileage": 900, "batteryLevel": 50})
        assert coordinator.data["vehicleMileage"]["value"] == 1000
        # ...and the rest of the message still lands
        assert coordinator.data["batteryLevel"]["value"] == 50

    def test_a_non_numeric_reading_is_rejected(self, coordinator) -> None:
        coordinator.data = {"vehicleMileage": {"value": 1000, "history": {1000}}}
        _route(coordinator, {"vehicleMileage": "not-a-number"})
        assert coordinator.data["vehicleMileage"]["value"] == 1000


class TestMalformedMessages:
    @pytest.mark.parametrize(
        "message",
        [
            {},
            {"payload": {}},
            {"payload": {"data": {}}},
            {"payload": {"data": {"parallaxMessages": None}}},
        ],
    )
    def test_malformed_messages_are_ignored(self, coordinator, message) -> None:
        coordinator._process_parallax_data(message)
        coordinator.async_set_updated_data.assert_not_called()

    def test_an_undecodable_payload_is_ignored(self, coordinator) -> None:
        _route(coordinator, {})
        coordinator.async_set_updated_data.assert_not_called()
