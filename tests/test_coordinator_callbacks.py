"""The two subscription callbacks that were never tested.

Both are entry points for data arriving off the websocket, so they are exposed to
whatever the server sends -- including shapes it is not supposed to send. What is
pinned here is that malformed input is handled deliberately rather than raising
inside a callback, where the exception would be swallowed by the event loop and
the subscription would appear healthy while delivering nothing.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from custom_components.rivian.coordinator import VehicleCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


@pytest.fixture
def coordinator(hass: HomeAssistant, mock_config_entry: ConfigEntry):
    c = VehicleCoordinator(
        hass=hass, config_entry=mock_config_entry, client=MagicMock(), vehicle_id="v1"
    )
    c.async_set_updated_data = MagicMock(side_effect=lambda d: setattr(c, "data", d))
    return c


def _cloud(**fields) -> dict:
    return {"payload": {"data": {"vehicleCloudConnection": fields}}}


class TestCloudConnection:
    def test_online_state_is_recorded(self, coordinator) -> None:
        coordinator._process_cloud_connection_data(
            _cloud(isOnline=True, lastSync="2026-08-18T00:00:00Z")
        )
        assert coordinator._is_online is True
        assert coordinator._last_sync == "2026-08-18T00:00:00Z"

    def test_going_offline_is_recorded(self, coordinator) -> None:
        coordinator._is_online = True
        coordinator._process_cloud_connection_data(_cloud(isOnline=False))
        assert coordinator._is_online is False

    def test_a_missing_isOnline_is_treated_as_offline(self, coordinator) -> None:
        """Absent must not mean 'unchanged': a payload that omits the field would
        otherwise leave a stale online state forever."""
        coordinator._is_online = True
        coordinator._process_cloud_connection_data(_cloud())
        assert coordinator._is_online is False

    @pytest.mark.parametrize(
        "message", [{}, {"payload": {}}, {"payload": {"data": None}}]
    )
    def test_a_malformed_message_does_not_raise(self, coordinator, message) -> None:
        # Raising inside a websocket callback is swallowed by the event loop: the
        # subscription looks healthy while delivering nothing.
        coordinator._process_cloud_connection_data(message)


class TestCommandState:
    def _state(self, **fields) -> dict:
        return {"payload": {"data": {"vehicleCommandState": fields}}}

    def test_a_state_update_is_stored(self, coordinator) -> None:
        coordinator._command_states = {}
        coordinator._process_command_state(
            "cmd-1", self._state(state="COMPLETED", command="WAKE_VEHICLE")
        )
        assert coordinator._command_states["cmd-1"]["command"] == "WAKE_VEHICLE"

    async def test_a_null_state_unsubscribes_rather_than_looping(
        self, coordinator
    ) -> None:
        """A subscription that keeps emitting stateless updates would otherwise be
        held open forever, one per command."""
        from unittest.mock import AsyncMock

        coordinator._command_states = {}
        # It is handed to asyncio.create_task, so the stub must be awaitable.
        coordinator._unsubscribe_command_state = AsyncMock()
        coordinator._process_command_state("cmd-2", self._state(state=None))
        assert "cmd-2" not in coordinator._command_states
        coordinator._unsubscribe_command_state.assert_called_once_with("cmd-2")
        # let the scheduled task run so it does not leak into the next test
        await asyncio.sleep(0)

    @pytest.mark.parametrize("message", [{}, {"payload": {}}])
    def test_a_malformed_message_does_not_raise(self, coordinator, message) -> None:
        coordinator._process_command_state("cmd-3", message)
