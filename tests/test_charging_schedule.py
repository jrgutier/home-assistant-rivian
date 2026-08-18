"""Tests for upstream 1.5.3b5's charging-schedule plumbing on the coordinators.

These cover the parts that carry real logic rather than delegation: the refresh
cooldown, the fallback to a default schedule when the API gives nothing usable,
and the Parallax session-reset rule.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.rivian.const import DEFAULT_CHARGING_SCHEDULE
from custom_components.rivian.coordinator import ChargingCoordinator, VehicleCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


def _api(schedules=None, raises=False):
    api = MagicMock()
    response = MagicMock()
    response.json = AsyncMock(
        return_value={"data": {"getVehicle": {"chargingSchedules": schedules or []}}}
    )
    if raises:
        api.get_charging_schedules = AsyncMock(side_effect=RuntimeError("boom"))
    else:
        api.get_charging_schedules = AsyncMock(return_value=response)
    api.set_charging_schedules = AsyncMock()
    return api


@pytest.fixture
def vehicle_coordinator(hass: HomeAssistant, mock_config_entry: ConfigEntry):
    def _make(api):
        return VehicleCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=api,
            vehicle_id="test_vehicle_123",
        )

    return _make


class TestChargingScheduleFetch:
    async def test_uses_the_schedule_the_api_returns(self, vehicle_coordinator) -> None:
        api = _api([{"startTime": 60, "duration": 120, "amperage": 32}])
        coord = vehicle_coordinator(api)
        assert (await coord.get_charging_schedule_data())["startTime"] == 60

    async def test_falls_back_to_the_default_when_the_api_returns_none(
        self, vehicle_coordinator
    ) -> None:
        # Without this, every schedule entity would render unavailable on a fresh
        # install rather than showing the documented default.
        coord = vehicle_coordinator(_api([]))
        assert await coord.get_charging_schedule_data() == dict(
            DEFAULT_CHARGING_SCHEDULE
        )

    async def test_an_api_error_does_not_propagate(self, vehicle_coordinator) -> None:
        coord = vehicle_coordinator(_api(raises=True))
        assert await coord.get_charging_schedule_data() == dict(
            DEFAULT_CHARGING_SCHEDULE
        )

    async def test_second_call_is_served_from_cache(self, vehicle_coordinator) -> None:
        api = _api([{"startTime": 60}])
        coord = vehicle_coordinator(api)
        await coord.get_charging_schedule_data()
        await coord.get_charging_schedule_data()
        # The cooldown exists so entity reads do not each hit the API.
        assert api.get_charging_schedules.await_count == 1

    async def test_force_refresh_uses_the_shorter_cooldown(
        self, vehicle_coordinator
    ) -> None:
        api = _api([{"startTime": 60}])
        coord = vehicle_coordinator(api)
        await coord.get_charging_schedule_data()
        with patch(
            "custom_components.rivian.coordinator.time.time",
            return_value=coord._last_schedule_fetch + 60,
        ):
            await coord.get_charging_schedule_data(force_refresh=True)
        assert api.get_charging_schedules.await_count == 2

    async def test_charging_schedule_property_is_empty_before_any_fetch(
        self, vehicle_coordinator
    ) -> None:
        assert vehicle_coordinator(_api()).charging_schedule == {}


class TestChargingScheduleUpdate:
    async def test_update_merges_into_the_current_schedule(
        self, vehicle_coordinator
    ) -> None:
        api = _api([{"startTime": 60, "duration": 120, "amperage": 32}])
        coord = vehicle_coordinator(api)
        await coord.update_charging_schedule_data({"amperage": 24})
        sent = api.set_charging_schedules.await_args.args[1][0]
        assert sent["amperage"] == 24
        # The untouched fields must survive -- a PUT-style overwrite would drop them.
        assert sent["startTime"] == 60 and sent["duration"] == 120

    async def test_local_state_updates_even_if_the_mutation_fails(
        self, vehicle_coordinator
    ) -> None:
        api = _api([{"startTime": 60}])
        api.set_charging_schedules = AsyncMock(side_effect=RuntimeError("boom"))
        coord = vehicle_coordinator(api)
        await coord.update_charging_schedule_data({"amperage": 24})
        assert coord.charging_schedule["amperage"] == 24


class TestChargingCoordinatorParallax:
    def _coord(self, hass, entry):
        return ChargingCoordinator(
            hass=hass,
            config_entry=entry,
            client=MagicMock(),
            vehicle_id="test_vehicle_123",
        )

    def test_internal_fields_are_stripped(self, hass, mock_config_entry) -> None:
        coord = self._coord(hass, mock_config_entry)
        coord.async_set_updated_data = MagicMock()
        coord.update_from_parallax({"power": 11, "_raw": b"x"})
        assert "_raw" not in coord.async_set_updated_data.call_args.args[0]

    def test_an_all_internal_payload_is_ignored(self, hass, mock_config_entry) -> None:
        coord = self._coord(hass, mock_config_entry)
        coord.async_set_updated_data = MagicMock()
        coord.update_from_parallax({"_raw": b"x"})
        coord.async_set_updated_data.assert_not_called()

    def test_a_new_start_time_clears_the_previous_session(
        self, hass, mock_config_entry
    ) -> None:
        # Stale metrics leaking across sessions is the bug this guards. Seeded
        # through update_from_parallax rather than by poking .data, because the
        # coordinator resolves its view from per-source namespaces.
        coord = self._coord(hass, mock_config_entry)
        coord.update_from_parallax({"startTime": "A", "totalChargedEnergy": 42})
        coord.async_set_updated_data = MagicMock()
        coord.update_from_parallax({"startTime": "B"})
        new = coord.async_set_updated_data.call_args.args[0]
        assert new["startTime"] == "B"
        assert "totalChargedEnergy" not in new

    def test_the_same_start_time_keeps_session_metrics(
        self, hass, mock_config_entry
    ) -> None:
        coord = self._coord(hass, mock_config_entry)
        coord.update_from_parallax({"startTime": "A", "totalChargedEnergy": 42})
        coord.async_set_updated_data = MagicMock()
        coord.update_from_parallax({"startTime": "A", "power": 11})
        new = coord.async_set_updated_data.call_args.args[0]
        assert new["totalChargedEnergy"] == 42 and new["power"] == 11

    def test_power_without_a_start_time_synthesises_one(
        self, hass, mock_config_entry
    ) -> None:
        coord = self._coord(hass, mock_config_entry)
        coord.async_set_updated_data = MagicMock()
        coord.update_from_parallax({"power": 11})
        assert coord.async_set_updated_data.call_args.args[0]["startTime"]

    def test_adjust_update_interval_is_a_no_op_under_push(
        self, hass, mock_config_entry
    ) -> None:
        # Kept only for VehicleCoordinator's chargerStatus handler; polling is off.
        # Assert update_interval, NOT _update_interval_seconds: Home Assistant's own
        # DataUpdateCoordinator defines an attribute of that name and overwrites it
        # in __init__ (update_coordinator.py:83), so the class attribute here is
        # shadowed on every instance.
        coord = self._coord(hass, mock_config_entry)
        assert coord.update_interval is None
        coord.adjust_update_interval(is_plugged_in=True)
        coord.adjust_update_interval(is_plugged_in=False)
        assert coord.update_interval is None
