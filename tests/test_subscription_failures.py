"""A failed subscription must be visible, and must not abort setup.

Five subscribe_for_* in the client ended `except Exception: _LOGGER.error(ex);
return None`, and five coordinator call sites branched on that None. So a dead
real-time path looked exactly like a healthy one from every caller -- which is why
"the Parallax websocket is broken" survived a full day of diagnosis before the
real cause (the gateway permits one active subscription per user session) was
found.

Two obligations pull in opposite directions and both are pinned here:
  * the failure must SURFACE -- a caller must be able to tell
  * entry setup must still COMPLETE -- a transient failure must degrade, not
    take the integration down at startup
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.rivian_client.exceptions import RivianApiException
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

SUBSCRIBE_METHODS = [
    "subscribe_for_vehicle_updates",
    "subscribe_for_charging_session",
    "subscribe_for_parallax_messages",
    "subscribe_for_cloud_connection",
    "subscribe_for_command_state",
]


@pytest.fixture
def client() -> MagicMock:
    api = MagicMock()
    for name in SUBSCRIBE_METHODS:
        setattr(api, name, AsyncMock(return_value=AsyncMock()))
    schedule = MagicMock()
    schedule.json = AsyncMock(
        return_value={"data": {"getVehicle": {"chargingSchedules": []}}}
    )
    api.get_charging_schedules = AsyncMock(return_value=schedule)
    api._ws_monitor = MagicMock(connected=True)
    return api


@pytest.fixture
def coordinator(hass: HomeAssistant, mock_config_entry: ConfigEntry, client):
    c = VehicleCoordinator(
        hass=hass, config_entry=mock_config_entry, client=client, vehicle_id="v1"
    )
    c._initial.set()
    return c


class TestTheClientPropagates:
    @pytest.mark.parametrize("method", SUBSCRIBE_METHODS)
    async def test_a_failure_is_raised_not_returned_as_none(self, method) -> None:
        """Every one of the five, so a future copy-paste cannot reintroduce it."""
        from custom_components.rivian.rivian_client import Rivian

        api = Rivian(user_session_token="t")
        api._ws_connect = AsyncMock(side_effect=RuntimeError("gateway refused"))
        kwargs = {"vehicle_id": "v1", "callback": lambda _: None}
        if method == "subscribe_for_command_state":
            kwargs = {"command_id": "c1", "callback": lambda _: None}
        with pytest.raises(RivianApiException):
            await getattr(api, method)(**kwargs)
        await api.close()


class TestSetupStillCompletes:
    async def test_a_failed_subscription_does_not_abort_entry_setup(
        self, coordinator, client
    ) -> None:
        """Degrade, do not abort: a transient gateway failure at startup must not
        take the whole integration down."""
        client.subscribe_for_parallax_messages = AsyncMock(
            side_effect=RivianApiException("gateway refused")
        )
        # Must not raise, and the OTHER subscriptions must still be established --
        # losing Parallax should cost live telemetry, not the whole integration.
        await coordinator._async_update_data()
        client.subscribe_for_vehicle_updates.assert_awaited()
        client.subscribe_for_cloud_connection.assert_awaited()
        assert coordinator._unsub_parallax is None
        coordinator._stop_watchdog()

    async def test_the_failure_is_recorded_not_silent(
        self, coordinator, client, caplog
    ) -> None:
        client.subscribe_for_parallax_messages = AsyncMock(
            side_effect=RivianApiException("gateway refused")
        )
        await coordinator._async_update_data()
        assert "gateway refused" in caplog.text or "arallax" in caplog.text
        coordinator._stop_watchdog()


class TestNoDeadBranch:
    def test_the_none_branch_is_gone(self) -> None:
        """`if unsubscribe:` only made sense while failures returned None; leaving
        it implies a contract that no longer exists."""
        import pathlib

        src = pathlib.Path("custom_components/rivian/coordinator.py").read_text()
        assert "if unsubscribe:" not in src
