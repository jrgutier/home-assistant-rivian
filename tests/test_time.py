"""Tests for the Rivian time platform (upstream 1.5.3b5's charging schedule).

The interesting behaviour here is minute arithmetic around midnight: a schedule is
stored as a start-minute plus a duration, but presented as two wall-clock times.
Every test below states which of those two representations it is pinning, because a
conversion that silently loses the wrap is the failure mode this platform invites.
"""

from datetime import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.time import (
    TIME_ENTITIES,
    RivianChargingScheduleTimeEntity,
    _async_set_schedule_time,
    _get_schedule_time,
    async_setup_entry,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

VEHICLE = {
    "id": "test_vehicle_123",
    "vin": "TEST123456789",
    "name": "Test R1T",
    "model": "R1T",
}


def _coordinator(schedule: dict | None) -> MagicMock:
    coord = MagicMock(spec=VehicleCoordinator)
    coord.charging_schedule = schedule if schedule is not None else {}
    coord.get_charging_schedule_data = AsyncMock(
        return_value=schedule if schedule is not None else {}
    )
    coord.update_charging_schedule_data = AsyncMock()
    return coord


class TestGetScheduleTime:
    """_get_schedule_time converts stored minutes to a wall-clock time."""

    def test_start_time_is_the_stored_start_minute(self) -> None:
        # 1320 minutes == 22:00
        assert _get_schedule_time(_coordinator({"startTime": 1320})) == time(22, 0)

    def test_end_time_is_start_plus_duration(self) -> None:
        # 06:00 + 2h == 08:00, no wrap involved
        coord = _coordinator({"startTime": 360, "duration": 120})
        assert _get_schedule_time(coord, is_end_time=True) == time(8, 0)

    def test_end_time_wraps_past_midnight(self) -> None:
        # The whole point of the modulo: 22:00 + 8h is 06:00 the NEXT day, not 30:00.
        coord = _coordinator({"startTime": 1320, "duration": 480})
        assert _get_schedule_time(coord, is_end_time=True) == time(6, 0)

    def test_end_time_landing_exactly_on_midnight_is_zero(self) -> None:
        coord = _coordinator({"startTime": 1320, "duration": 120})
        assert _get_schedule_time(coord, is_end_time=True) == time(0, 0)

    def test_falls_back_to_defaults_when_schedule_is_empty(self) -> None:
        # An empty schedule must still yield a usable time rather than raising.
        assert _get_schedule_time(_coordinator({})) == time(22, 0)
        assert _get_schedule_time(_coordinator({}), is_end_time=True) == time(6, 0)


class TestSetScheduleTime:
    """_async_set_schedule_time writes back start/duration, never wall-clock."""

    async def test_setting_end_time_adjusts_duration_only(self) -> None:
        coord = _coordinator({"startTime": 1320, "duration": 480})
        await _async_set_schedule_time(coord, time(7, 0), is_end_time=True)
        # 22:00 -> 07:00 is 9h, and start must be left alone.
        coord.update_charging_schedule_data.assert_awaited_once_with({"duration": 540})

    async def test_setting_end_time_before_start_wraps_rather_than_going_negative(
        self,
    ) -> None:
        # A naive subtraction gives -120 here; the schedule would be nonsense.
        coord = _coordinator({"startTime": 1320, "duration": 480})
        await _async_set_schedule_time(coord, time(20, 0), is_end_time=True)
        coord.update_charging_schedule_data.assert_awaited_once_with({"duration": 1320})

    async def test_setting_start_time_preserves_the_end_time(self) -> None:
        # Start 22:00 + 8h = end 06:00. Moving start to 23:00 must keep end at 06:00,
        # which means the duration shrinks to 7h -- not that it stays 8h.
        coord = _coordinator({"startTime": 1320, "duration": 480})
        await _async_set_schedule_time(coord, time(23, 0), is_end_time=False)
        coord.update_charging_schedule_data.assert_awaited_once_with(
            {"startTime": 1380, "duration": 420}
        )

    async def test_setting_start_time_wraps_when_it_moves_past_the_end(self) -> None:
        coord = _coordinator({"startTime": 360, "duration": 120})  # 06:00 -> 08:00
        await _async_set_schedule_time(coord, time(9, 0), is_end_time=False)
        # 09:00 -> 08:00 next day is 23h, not -1h.
        coord.update_charging_schedule_data.assert_awaited_once_with(
            {"startTime": 540, "duration": 1380}
        )


class TestTimeEntity:
    """The entity delegates to its description; it holds no logic of its own."""

    def test_native_value_delegates_to_value_fn(
        self, mock_config_entry: ConfigEntry
    ) -> None:
        coord = _coordinator({"startTime": 1320, "duration": 480})
        entity = RivianChargingScheduleTimeEntity(
            coord, mock_config_entry, TIME_ENTITIES[0], VEHICLE
        )
        assert entity.native_value == time(22, 0)

    async def test_async_set_value_delegates_to_set_fn(
        self, mock_config_entry: ConfigEntry
    ) -> None:
        coord = _coordinator({"startTime": 1320, "duration": 480})
        entity = RivianChargingScheduleTimeEntity(
            coord, mock_config_entry, TIME_ENTITIES[1], VEHICLE
        )
        await entity.async_set_value(time(7, 0))
        coord.update_charging_schedule_data.assert_awaited_once_with({"duration": 540})

    def test_available_tracks_the_coordinator(
        self, mock_config_entry: ConfigEntry
    ) -> None:
        coord = _coordinator({})
        entity = RivianChargingScheduleTimeEntity(
            coord, mock_config_entry, TIME_ENTITIES[0], VEHICLE
        )
        entity._available = False
        assert entity.available is False
        entity._available = True
        assert entity.available is True


@pytest.mark.asyncio
async def test_async_setup_entry_creates_both_times_per_vehicle(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Both a start and an end entity, and they need no vehicle-control pairing."""
    coord = _coordinator({"startTime": 1320, "duration": 480})
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            ATTR_VEHICLE: {"test_vehicle_123": VEHICLE},
            ATTR_COORDINATOR: {ATTR_VEHICLE: {"test_vehicle_123": coord}},
        }
    }
    added: list = []
    await async_setup_entry(hass, mock_config_entry, added.extend)

    assert len(added) == 2
    assert all(isinstance(e, RivianChargingScheduleTimeEntity) for e in added)
    assert {e.entity_description.key for e in added} == {
        "charging_schedule_start",
        "charging_schedule_end",
    }
