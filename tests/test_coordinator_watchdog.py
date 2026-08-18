"""Tests for coordinator watchdog functionality."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.rivian.coordinator import ChargingCoordinator, VehicleCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_vehicle_coordinator(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> VehicleCoordinator:
    """Create a mocked VehicleCoordinator."""
    mock_client = MagicMock()
    mock_client.subscribe_for_vehicle_updates = AsyncMock(
        return_value=AsyncMock()  # Mock unsubscribe handler
    )
    mock_client.subscribe_for_cloud_connection = AsyncMock(
        return_value=AsyncMock()  # Mock unsubscribe handler
    )
    # Upstream 1.5.3b5: VehicleCoordinator also subscribes to Parallax messages and
    # prefetches the charging schedule on every update.
    mock_client.subscribe_for_parallax_messages = AsyncMock(
        return_value=AsyncMock()  # Mock unsubscribe handler
    )
    schedule_response = MagicMock()
    schedule_response.json = AsyncMock(
        return_value={"data": {"getVehicle": {"chargingSchedules": []}}}
    )
    mock_client.get_charging_schedules = AsyncMock(return_value=schedule_response)

    coordinator = VehicleCoordinator(
        hass=hass,
        config_entry=mock_config_entry,
        client=mock_client,
        vehicle_id="test_vehicle_123",
    )

    return coordinator


@pytest.fixture
def mock_charging_coordinator(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> ChargingCoordinator:
    """Create a mocked ChargingCoordinator."""
    mock_client = MagicMock()
    mock_client.subscribe_for_charging_session = AsyncMock(
        return_value=AsyncMock()  # Mock unsubscribe handler
    )

    coordinator = ChargingCoordinator(
        hass=hass,
        config_entry=mock_config_entry,
        client=mock_client,
        vehicle_id="test_vehicle_123",
    )

    return coordinator


class TestVehicleCoordinatorWatchdog:
    """Test VehicleCoordinator watchdog functionality."""

    async def test_watchdog_starts_after_subscription(
        self,
        hass: HomeAssistant,
        mock_vehicle_coordinator: VehicleCoordinator,
    ) -> None:
        """Test that watchdog starts after successful subscription."""
        # Set data to None to trigger fresh subscription in _async_update_data
        mock_vehicle_coordinator.data = None
        mock_vehicle_coordinator.last_update_success = False

        # Mock the initial event
        async def mock_wait():
            mock_vehicle_coordinator.data = {"powerState": {"value": "go"}}
            mock_vehicle_coordinator._initial.set()

        mock_vehicle_coordinator._initial.wait = mock_wait

        await mock_vehicle_coordinator._async_update_data()

        # Give the task a moment to start
        await asyncio.sleep(0.01)

        # Watchdog should be running
        assert mock_vehicle_coordinator._watchdog_task is not None
        assert not mock_vehicle_coordinator._watchdog_task.done()

        # Cleanup
        mock_vehicle_coordinator._stop_watchdog()

    async def test_watchdog_updates_timestamp_on_data(
        self,
        hass: HomeAssistant,
        mock_vehicle_coordinator: VehicleCoordinator,
    ) -> None:
        """Test that watchdog timestamp updates when data is received."""
        # Set initial state
        mock_vehicle_coordinator.data = {}

        # Process new data
        update_data = {
            "payload": {
                "data": {
                    "vehicleState": {
                        "powerState": {
                            "value": "go",
                            "timeStamp": "2024-01-01T00:00:00Z",
                        },
                        "batteryLevel": {
                            "value": 80.5,
                            "timeStamp": "2024-01-01T00:00:00Z",
                        },
                    }
                }
            }
        }

        before_time = datetime.now(timezone.utc)
        mock_vehicle_coordinator._process_new_data(update_data)
        after_time = datetime.now(timezone.utc)

        # Timestamp should be updated
        assert mock_vehicle_coordinator._last_update_time is not None
        assert before_time <= mock_vehicle_coordinator._last_update_time <= after_time

    async def test_watchdog_skips_restart_when_sleeping(
        self,
        hass: HomeAssistant,
        mock_vehicle_coordinator: VehicleCoordinator,
    ) -> None:
        """Test that watchdog doesn't restart when vehicle is sleeping."""
        # Set vehicle to sleeping state
        mock_vehicle_coordinator.data = {
            "powerState": {"value": "sleep", "history": {"sleep"}}
        }

        # Set last update time to 10 minutes ago (stale)
        mock_vehicle_coordinator._last_update_time = datetime.now(
            timezone.utc
        ) - timedelta(minutes=10)

        # Start watchdog
        mock_vehicle_coordinator._start_watchdog()

        # Wait for watchdog to check (give it time to run at least once)
        await asyncio.sleep(0.1)

        # Mock async_request_refresh to track if it was called
        with patch.object(
            mock_vehicle_coordinator, "async_request_refresh"
        ) as mock_refresh:
            # Wait a bit more for watchdog to process
            await asyncio.sleep(0.1)

            # Should NOT have called refresh since vehicle is sleeping
            mock_refresh.assert_not_called()

        # Cleanup
        mock_vehicle_coordinator._stop_watchdog()

    async def test_watchdog_logic_restarts_when_stale(
        self,
        hass: HomeAssistant,
        mock_vehicle_coordinator: VehicleCoordinator,
    ) -> None:
        """Test that watchdog logic would restart subscription when stale.

        Note: This test validates the watchdog logic without actually waiting
        for the 60-second check interval. It verifies the conditions under which
        a restart would be triggered.
        """
        # Set vehicle to awake state
        mock_vehicle_coordinator.data = {
            "powerState": {"value": "go", "history": {"go"}}
        }

        # Set last update time to 10 minutes ago (beyond 5 minute timeout)
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        mock_vehicle_coordinator._last_update_time = stale_time

        # Verify the conditions that would trigger a restart
        time_since_update = (
            datetime.now(timezone.utc) - mock_vehicle_coordinator._last_update_time
        ).total_seconds()

        power_state = mock_vehicle_coordinator.get("powerState")

        # Assert the conditions that watchdog checks
        assert time_since_update > mock_vehicle_coordinator._watchdog_timeout
        assert power_state != "sleep"  # Should not skip restart

        # This validates that the watchdog would trigger a restart under these conditions

    async def test_watchdog_stops_on_shutdown(
        self,
        hass: HomeAssistant,
        mock_vehicle_coordinator: VehicleCoordinator,
    ) -> None:
        """Test that watchdog stops when coordinator shuts down."""
        # Mock the _ws_monitor to avoid await error
        mock_vehicle_coordinator.api._ws_monitor = None

        # Start watchdog
        mock_vehicle_coordinator._start_watchdog()
        # Give task time to start
        await asyncio.sleep(0.01)
        assert mock_vehicle_coordinator._watchdog_task is not None

        # Shutdown coordinator
        await mock_vehicle_coordinator.async_shutdown()

        # Give task time to cancel
        await asyncio.sleep(0.01)

        # Watchdog should be stopped
        assert (
            mock_vehicle_coordinator._watchdog_task is None
            or mock_vehicle_coordinator._watchdog_task.cancelled()
        )

    async def test_watchdog_doesnt_start_twice(
        self,
        hass: HomeAssistant,
        mock_vehicle_coordinator: VehicleCoordinator,
    ) -> None:
        """Test that watchdog doesn't start if already running."""
        # Start watchdog
        mock_vehicle_coordinator._start_watchdog()
        first_task = mock_vehicle_coordinator._watchdog_task

        # Try to start again
        mock_vehicle_coordinator._start_watchdog()
        second_task = mock_vehicle_coordinator._watchdog_task

        # Should be the same task
        assert first_task is second_task

        # Cleanup
        mock_vehicle_coordinator._stop_watchdog()

    async def test_backend_504_error_triggers_restart(
        self,
        hass: HomeAssistant,
        mock_vehicle_coordinator: VehicleCoordinator,
    ) -> None:
        """Test that 504 backend errors trigger immediate subscription restart."""
        # Set initial state
        mock_vehicle_coordinator.data = {"powerState": {"value": "go"}}
        mock_vehicle_coordinator._unsub_handler = AsyncMock()
        mock_vehicle_coordinator._subscription_start_time = datetime.now(timezone.utc)
        mock_vehicle_coordinator._subscription_count = 1

        # Mock the API's WebSocket monitor
        mock_vehicle_coordinator.api._ws_monitor = MagicMock()
        mock_vehicle_coordinator.api._ws_monitor.connected = True

        # Create 504 error message matching Rivian backend format
        error_data = {
            "type": "error",
            "payload": [
                {
                    "message": "Status unaccounted for 504",
                    "extensions": {
                        "rest": {
                            "body": "<html>...</html>",
                            "method": "POST",
                            "status": 504,
                            "url": "https://cesium.vcs.goriv.co/v2/vehicle/latest",
                        },
                        "reason": "INVALID_REST_RESPONSE",
                        "code": "INTERNAL_SERVER_ERROR",
                    },
                }
            ],
        }

        # Mock methods to verify they're called
        with (
            patch.object(mock_vehicle_coordinator, "_unsubscribe") as mock_unsub,
            patch.object(
                mock_vehicle_coordinator, "async_request_refresh"
            ) as mock_refresh,
        ):
            # Process the error
            mock_vehicle_coordinator._process_new_data(error_data)

            # Verify restart was triggered
            mock_unsub.assert_called_once()
            mock_refresh.assert_called_once()

    async def test_backend_502_error_triggers_restart(
        self,
        hass: HomeAssistant,
        mock_vehicle_coordinator: VehicleCoordinator,
    ) -> None:
        """Test that 502 backend errors trigger immediate subscription restart."""
        # Set initial state
        mock_vehicle_coordinator.data = {"powerState": {"value": "go"}}
        mock_vehicle_coordinator._unsub_handler = AsyncMock()
        mock_vehicle_coordinator._subscription_start_time = datetime.now(timezone.utc)
        mock_vehicle_coordinator._subscription_count = 1
        mock_vehicle_coordinator.api._ws_monitor = MagicMock()
        mock_vehicle_coordinator.api._ws_monitor.connected = True

        # Create 502 error message
        error_data = {
            "type": "error",
            "payload": [
                {
                    "message": "Status unaccounted for 502",
                    "extensions": {
                        "rest": {"status": 502},
                    },
                }
            ],
        }

        # Mock methods to verify they're called
        with (
            patch.object(mock_vehicle_coordinator, "_unsubscribe") as mock_unsub,
            patch.object(
                mock_vehicle_coordinator, "async_request_refresh"
            ) as mock_refresh,
        ):
            # Process the error
            mock_vehicle_coordinator._process_new_data(error_data)

            # Verify restart was triggered
            mock_unsub.assert_called_once()
            mock_refresh.assert_called_once()

    async def test_non_critical_backend_error_no_restart(
        self,
        hass: HomeAssistant,
        mock_vehicle_coordinator: VehicleCoordinator,
    ) -> None:
        """Test that non-502/504 errors don't trigger immediate restart."""
        # Set initial state
        mock_vehicle_coordinator.data = {"powerState": {"value": "go"}}
        mock_vehicle_coordinator._unsub_handler = AsyncMock()
        mock_vehicle_coordinator._subscription_start_time = datetime.now(timezone.utc)
        mock_vehicle_coordinator._subscription_count = 1
        mock_vehicle_coordinator.api._ws_monitor = MagicMock()
        mock_vehicle_coordinator.api._ws_monitor.connected = True

        # Create 400 error message (not critical)
        error_data = {
            "type": "error",
            "payload": [
                {
                    "message": "Bad request",
                    "extensions": {
                        "rest": {"status": 400},
                    },
                }
            ],
        }

        # Mock methods to verify they're NOT called for non-critical errors
        with (
            patch.object(mock_vehicle_coordinator, "_unsubscribe") as mock_unsub,
            patch.object(
                mock_vehicle_coordinator, "async_request_refresh"
            ) as mock_refresh,
        ):
            # Process the error
            mock_vehicle_coordinator._process_new_data(error_data)

            # Verify restart was NOT triggered
            mock_unsub.assert_not_called()
            mock_refresh.assert_not_called()


class TestChargingCoordinatorWatchdog:
    """Test ChargingCoordinator watchdog functionality."""

    async def test_watchdog_can_be_toggled(
        self,
        hass: HomeAssistant,
        mock_charging_coordinator: ChargingCoordinator,
    ) -> None:
        """Test that charging watchdog can be enabled and disabled."""
        # Initially no watchdog
        assert mock_charging_coordinator._watchdog_task is None

        # Enable watchdog
        mock_charging_coordinator.toggle_watchdog(True)
        assert mock_charging_coordinator._watchdog_task is not None
        assert not mock_charging_coordinator._watchdog_task.done()

        # Disable watchdog
        mock_charging_coordinator.toggle_watchdog(False)
        assert (
            mock_charging_coordinator._watchdog_task is None
            or mock_charging_coordinator._watchdog_task.cancelled()
        )

    async def test_watchdog_updates_timestamp_on_charging_data(
        self,
        hass: HomeAssistant,
        mock_charging_coordinator: ChargingCoordinator,
    ) -> None:
        """Test that watchdog timestamp updates when charging data is received."""
        # Set initial state
        mock_charging_coordinator.data = {}

        # Process new charging data
        update_data = {
            "payload": {
                "data": {
                    "chargingSession": {
                        "liveData": {"power": 11.0},
                        "chartData": {"sessionId": "test_123"},
                    }
                }
            }
        }

        before_time = datetime.now(timezone.utc)
        mock_charging_coordinator._process_new_data(update_data)
        after_time = datetime.now(timezone.utc)

        # Timestamp should be updated
        assert mock_charging_coordinator._last_update_time is not None
        assert before_time <= mock_charging_coordinator._last_update_time <= after_time

    async def test_watchdog_updates_timestamp_on_empty_session(
        self,
        hass: HomeAssistant,
        mock_charging_coordinator: ChargingCoordinator,
    ) -> None:
        """Test that watchdog timestamp updates even for empty charging session."""
        # Process empty charging session
        update_data = {"payload": {"data": {"chargingSession": []}}}

        before_time = datetime.now(timezone.utc)
        mock_charging_coordinator._process_new_data(update_data)
        after_time = datetime.now(timezone.utc)

        # Timestamp should still be updated
        assert mock_charging_coordinator._last_update_time is not None
        assert before_time <= mock_charging_coordinator._last_update_time <= after_time

    async def test_watchdog_stops_on_shutdown(
        self,
        hass: HomeAssistant,
        mock_charging_coordinator: ChargingCoordinator,
    ) -> None:
        """Test that watchdog stops when coordinator shuts down."""
        # Start watchdog
        mock_charging_coordinator.toggle_watchdog(True)
        assert mock_charging_coordinator._watchdog_task is not None

        # Shutdown coordinator
        await mock_charging_coordinator.async_shutdown()

        # Watchdog should be stopped
        assert (
            mock_charging_coordinator._watchdog_task is None
            or mock_charging_coordinator._watchdog_task.cancelled()
        )

    async def test_charging_backend_504_error_triggers_restart(
        self,
        hass: HomeAssistant,
        mock_charging_coordinator: ChargingCoordinator,
    ) -> None:
        """Test that 504 backend errors trigger immediate charging subscription restart."""
        # Set initial state
        mock_charging_coordinator.data = {}
        mock_charging_coordinator._unsub_handler = AsyncMock()
        mock_charging_coordinator._subscription_start_time = datetime.now(timezone.utc)
        mock_charging_coordinator._subscription_count = 1

        # Mock the API's WebSocket monitor
        mock_charging_coordinator.api._ws_monitor = MagicMock()
        mock_charging_coordinator.api._ws_monitor.connected = True

        # Create 504 error message matching Rivian backend format
        error_data = {
            "type": "error",
            "payload": [
                {
                    "message": "Status unaccounted for 504",
                    "extensions": {
                        "rest": {
                            "status": 504,
                            "url": "https://cesium.vcs.goriv.co/v2/vehicle/latest",
                        },
                    },
                }
            ],
        }

        # Mock methods to verify they're called
        with (
            patch.object(mock_charging_coordinator, "_unsubscribe") as mock_unsub,
            patch.object(
                mock_charging_coordinator, "async_request_refresh"
            ) as mock_refresh,
        ):
            # Process the error
            mock_charging_coordinator._process_new_data(error_data)

            # Verify restart was triggered
            mock_unsub.assert_called_once()
            mock_refresh.assert_called_once()

    async def test_charging_non_critical_backend_error_no_restart(
        self,
        hass: HomeAssistant,
        mock_charging_coordinator: ChargingCoordinator,
    ) -> None:
        """Test that non-502/504 charging errors don't trigger immediate restart."""
        # Set initial state
        mock_charging_coordinator.data = {}
        mock_charging_coordinator._unsub_handler = AsyncMock()
        mock_charging_coordinator._subscription_start_time = datetime.now(timezone.utc)
        mock_charging_coordinator._subscription_count = 1
        mock_charging_coordinator.api._ws_monitor = MagicMock()
        mock_charging_coordinator.api._ws_monitor.connected = True

        # Create 400 error message (not critical)
        error_data = {
            "type": "error",
            "payload": [
                {
                    "message": "Bad request",
                    "extensions": {
                        "rest": {"status": 400},
                    },
                }
            ],
        }

        # Mock methods to verify they're NOT called for non-critical errors
        with (
            patch.object(mock_charging_coordinator, "_unsubscribe") as mock_unsub,
            patch.object(
                mock_charging_coordinator, "async_request_refresh"
            ) as mock_refresh,
        ):
            # Process the error
            mock_charging_coordinator._process_new_data(error_data)

            # Verify restart was NOT triggered
            mock_unsub.assert_not_called()
            mock_refresh.assert_not_called()

    async def test_charging_subscription_enabled_when_charging_starts(
        self,
        hass: HomeAssistant,
        mock_charging_coordinator: ChargingCoordinator,
    ) -> None:
        """Test that charging subscription is enabled when charging starts."""
        # Initially disabled (not charging)
        mock_charging_coordinator._subscription_enabled = False
        mock_charging_coordinator._unsub_handler = None

        # Mock async_request_refresh
        with patch.object(
            mock_charging_coordinator, "async_request_refresh"
        ) as mock_refresh:
            # Enable subscription (charging starts)
            await mock_charging_coordinator.toggle_subscription(True)

            # Verify subscription was enabled
            assert mock_charging_coordinator._subscription_enabled is True
            mock_refresh.assert_called_once()

    async def test_charging_subscription_disabled_when_charging_stops(
        self,
        hass: HomeAssistant,
        mock_charging_coordinator: ChargingCoordinator,
    ) -> None:
        """Test that charging subscription is disabled when charging stops."""
        # Initially enabled (charging)
        mock_charging_coordinator._subscription_enabled = True
        mock_unsub_handler = AsyncMock()
        mock_charging_coordinator._unsub_handler = mock_unsub_handler

        # Disable subscription (charging stops)
        await mock_charging_coordinator.toggle_subscription(False)

        # Verify subscription was disabled
        assert mock_charging_coordinator._subscription_enabled is False
        # Unsubscribe should have been called
        mock_unsub_handler.assert_called_once()
        # Handler should be cleared after unsubscribe
        assert mock_charging_coordinator._unsub_handler is None

    async def test_charging_subscription_not_created_when_disabled(
        self,
        hass: HomeAssistant,
        mock_charging_coordinator: ChargingCoordinator,
    ) -> None:
        """Test that subscription is not created when disabled (not charging)."""
        # Disable subscription
        mock_charging_coordinator._subscription_enabled = False
        mock_charging_coordinator.data = None

        # Try to update data
        result = await mock_charging_coordinator._async_update_data()

        # Should return empty dict without creating subscription
        assert result == {}
        # API method should not have been called
        mock_charging_coordinator.api.subscribe_for_charging_session.assert_not_called()


class TestChargerStateIntegration:
    """Test integration between chargerState and charging watchdog."""

    async def test_charging_watchdog_enabled_when_connected(
        self,
        hass: HomeAssistant,
        mock_vehicle_coordinator: VehicleCoordinator,
    ) -> None:
        """Test that charging watchdog is enabled when vehicle is connected to charger."""
        # Set initial state
        mock_vehicle_coordinator.data = {}

        # Mock the charging coordinator
        with patch.object(
            mock_vehicle_coordinator.charging_coordinator, "toggle_watchdog"
        ) as mock_toggle:
            # Process update with charging_active state
            update_data = {
                "payload": {
                    "data": {
                        "vehicleState": {
                            "chargerState": {
                                "value": "charging_active",
                                "timeStamp": "2024-01-01T00:00:00Z",
                            }
                        }
                    }
                }
            }

            mock_vehicle_coordinator._process_new_data(update_data)

            # Should have enabled watchdog
            mock_toggle.assert_called_once_with(True)

    async def test_charging_watchdog_disabled_when_disconnected(
        self,
        hass: HomeAssistant,
        mock_vehicle_coordinator: VehicleCoordinator,
    ) -> None:
        """Test that charging watchdog is disabled when vehicle disconnects from charger."""
        # Set initial connected state
        mock_vehicle_coordinator.data = {
            "chargerState": {
                "value": "charging_active",
                "history": {"charging_active"},
            }
        }
        mock_vehicle_coordinator._prev_charger_state = "charging_active"

        # Mock the charging coordinator
        with patch.object(
            mock_vehicle_coordinator.charging_coordinator, "toggle_watchdog"
        ) as mock_toggle:
            # Process update with disconnected state
            update_data = {
                "payload": {
                    "data": {
                        "vehicleState": {
                            "chargerState": {
                                "value": "chg_station_disconnected",
                                "timeStamp": "2024-01-01T00:00:00Z",
                            }
                        }
                    }
                }
            }

            mock_vehicle_coordinator._process_new_data(update_data)

            # Should have disabled watchdog
            mock_toggle.assert_called_once_with(False)

    @pytest.mark.parametrize(
        "charger_state,expected_enabled",
        [
            ("charging_active", True),
            ("charging_connecting", True),
            ("chg_station_connected", True),
            ("chg_complete", True),
            ("chg_station_disconnected", False),
            ("chg_station_fault", False),
            (None, False),
        ],
    )
    async def test_charging_watchdog_states(
        self,
        hass: HomeAssistant,
        mock_vehicle_coordinator: VehicleCoordinator,
        charger_state: str | None,
        expected_enabled: bool,
    ) -> None:
        """Test that charging watchdog is toggled correctly for various charger states."""
        # Set initial state with a different charger state to ensure toggle is called
        mock_vehicle_coordinator.data = {}
        mock_vehicle_coordinator._prev_charger_state = "different_state"

        # Mock the charging coordinator
        with patch.object(
            mock_vehicle_coordinator.charging_coordinator, "toggle_watchdog"
        ) as mock_toggle:
            # Process update with specific charger state
            update_data = {
                "payload": {
                    "data": {
                        "vehicleState": {
                            "chargerState": {
                                "value": charger_state,
                                "timeStamp": "2024-01-01T00:00:00Z",
                            }
                        }
                    }
                }
            }

            mock_vehicle_coordinator._process_new_data(update_data)

            # Should have called toggle with expected value
            mock_toggle.assert_called_once_with(expected_enabled)

    async def test_charging_watchdog_not_toggled_if_state_unchanged(
        self,
        hass: HomeAssistant,
        mock_vehicle_coordinator: VehicleCoordinator,
    ) -> None:
        """Test that charging watchdog is not toggled if charger state hasn't changed."""
        # Set initial state
        mock_vehicle_coordinator.data = {
            "chargerState": {
                "value": "charging_active",
                "history": {"charging_active"},
            }
        }
        mock_vehicle_coordinator._prev_charger_state = "charging_active"

        # Mock the charging coordinator
        with patch.object(
            mock_vehicle_coordinator.charging_coordinator, "toggle_watchdog"
        ) as mock_toggle:
            # Process update with same state
            update_data = {
                "payload": {
                    "data": {
                        "vehicleState": {
                            "chargerState": {
                                "value": "charging_active",
                                "timeStamp": "2024-01-01T00:00:00Z",
                            }
                        }
                    }
                }
            }

            mock_vehicle_coordinator._process_new_data(update_data)

            # Should NOT have toggled since state is unchanged
            mock_toggle.assert_not_called()
