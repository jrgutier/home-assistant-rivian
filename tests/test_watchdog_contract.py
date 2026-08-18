"""The subscription watchdog contract, shared by every coordinator that has one.

The watchdog existed three times, copy-pasted, differing only in log wording and
one skip rule. The existing per-coordinator tests mostly re-derived the trigger
conditions in the test body -- e.g. asserting `time_since > timeout` and then
concluding "this validates that the watchdog WOULD restart". Such a test cannot
fail if the watchdog logic changes, which is the whole thing it is supposed to
protect.

These exercise ONE tick of the real logic instead, so they fail when it breaks.
A tick is a separate method precisely so it can be driven without waiting out the
60-second loop or patching asyncio.sleep globally (which breaks wait_for for the
whole session).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.coordinator import ChargingCoordinator, VehicleCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


def _api() -> MagicMock:
    api = MagicMock()
    api._ws_monitor = MagicMock()
    api._ws_monitor.connected = True
    return api


@pytest.fixture(params=["vehicle", "charging"])
def coordinator(request, hass: HomeAssistant, mock_config_entry: ConfigEntry):
    """Both coordinators must honour the same contract."""
    cls = VehicleCoordinator if request.param == "vehicle" else ChargingCoordinator
    c = cls(hass=hass, config_entry=mock_config_entry, client=_api(), vehicle_id="v1")
    c._unsubscribe = AsyncMock()
    c.async_request_refresh = MagicMock(return_value=None)
    c.config_entry.async_create_task = MagicMock()
    return c


def _stale(coordinator) -> None:
    coordinator._last_update_time = datetime.now(timezone.utc) - timedelta(
        seconds=coordinator._watchdog_timeout + 60
    )


def _fresh(coordinator) -> None:
    coordinator._last_update_time = datetime.now(timezone.utc)


class TestTheSharedContract:
    async def test_a_stale_subscription_is_restarted(self, coordinator) -> None:
        _stale(coordinator)
        assert await coordinator._watchdog_tick() is True
        coordinator._unsubscribe.assert_awaited_once()

    async def test_a_fresh_subscription_is_left_alone(self, coordinator) -> None:
        _fresh(coordinator)
        assert await coordinator._watchdog_tick() is False
        coordinator._unsubscribe.assert_not_awaited()

    async def test_no_data_yet_is_not_treated_as_stale(self, coordinator) -> None:
        # Before the first message there is nothing to be stale relative to;
        # restarting here would fight the initial subscription.
        coordinator._last_update_time = None
        assert await coordinator._watchdog_tick() is False
        coordinator._unsubscribe.assert_not_awaited()

    def test_starting_twice_does_not_create_a_second_task(self, coordinator) -> None:
        running = MagicMock()
        running.done.return_value = False
        coordinator._watchdog_task = running
        coordinator._start_watchdog()
        coordinator.config_entry.async_create_task.assert_not_called()

    def test_stopping_cancels_the_task(self, coordinator) -> None:
        task = MagicMock()
        task.done.return_value = False
        coordinator._watchdog_task = task
        coordinator._stop_watchdog()
        task.cancel.assert_called_once()


class TestTheSkipRule:
    """Only VehicleCoordinator knows about sleep; the difference is deliberate."""

    async def test_a_sleeping_vehicle_is_not_restarted(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        c = VehicleCoordinator(
            hass=hass, config_entry=mock_config_entry, client=_api(), vehicle_id="v1"
        )
        c._unsubscribe = AsyncMock()
        c.data = {"powerState": {"value": "sleep", "history": {"sleep"}}}
        _stale(c)
        assert await c._watchdog_tick() is False
        c._unsubscribe.assert_not_awaited()

    async def test_an_awake_vehicle_is_restarted(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        c = VehicleCoordinator(
            hass=hass, config_entry=mock_config_entry, client=_api(), vehicle_id="v1"
        )
        c._unsubscribe = AsyncMock()
        c.async_request_refresh = MagicMock(return_value=None)
        c.config_entry.async_create_task = MagicMock()
        c.data = {"powerState": {"value": "go", "history": {"go"}}}
        _stale(c)
        assert await c._watchdog_tick() is True

    async def test_charging_has_no_sleep_rule(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        # A charging session continues while the vehicle sleeps, so the same skip
        # would silently stop watching an active charge.
        c = ChargingCoordinator(
            hass=hass, config_entry=mock_config_entry, client=_api(), vehicle_id="v1"
        )
        c._unsubscribe = AsyncMock()
        c.async_request_refresh = MagicMock(return_value=None)
        c.config_entry.async_create_task = MagicMock()
        c.data = {"powerState": "sleep"}
        _stale(c)
        assert await c._watchdog_tick() is True
