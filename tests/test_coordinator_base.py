"""Tests for base coordinator functionality."""

import sys
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from rivian.exceptions import (
    RivianApiException,
    RivianApiRateLimitError,
    RivianExpiredTokenError,
    RivianUnauthenticated,
)

# Mock exceptions before importing coordinators
mock_rivian_exceptions = Mock()
mock_rivian_exceptions.RivianApiException = RivianApiException
mock_rivian_exceptions.RivianApiRateLimitError = RivianApiRateLimitError
mock_rivian_exceptions.RivianExpiredTokenError = RivianExpiredTokenError
mock_rivian_exceptions.RivianUnauthenticated = RivianUnauthenticated
sys.modules["rivian.exceptions"] = mock_rivian_exceptions

from custom_components.rivian.coordinator import (
    UserCoordinator,
    WallboxCoordinator,
)


class TestRivianDataUpdateCoordinatorBase:
    """Test base coordinator error handling and interval management."""

    async def test_set_update_interval_doubles_on_error(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that update interval doubles on error."""
        mock_client = MagicMock()
        mock_client.get_user_information = AsyncMock(return_value={})

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )

        # Set initial data without refresh
        coordinator.data = {}
        coordinator.update_interval = timedelta(seconds=300)

        # Initial interval
        initial_interval = coordinator._update_interval_seconds
        assert initial_interval == 300  # 5 minutes

        # Simulate error
        coordinator._error_count = 1
        coordinator._set_update_interval()

        # Should double
        assert coordinator.update_interval.total_seconds() == initial_interval * 2

    async def test_set_update_interval_caps_at_900_seconds(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that update interval caps at 15 minutes."""
        mock_client = MagicMock()

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )

        # Simulate many errors
        coordinator._error_count = 10
        coordinator._set_update_interval()

        # Should cap at 900 seconds (15 minutes)
        assert coordinator.update_interval.total_seconds() == 900

    async def test_set_update_interval_with_explicit_seconds(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test setting explicit update interval."""
        mock_client = MagicMock()

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )

        coordinator._set_update_interval(seconds=600)

        assert coordinator.update_interval.total_seconds() == 600

    async def test_async_update_data_handles_expired_token(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that expired token triggers refresh."""
        mock_client = MagicMock()
        mock_client.create_csrf_token = AsyncMock()
        mock_client.get_user_information = AsyncMock(
            side_effect=[
                RivianExpiredTokenError("Token expired"),
                {"userId": "test_user"},
            ]
        )

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )

        data = await coordinator._async_update_data()

        # Should have refreshed token and retried
        mock_client.create_csrf_token.assert_called_once()
        assert data == {"userId": "test_user"}
        assert coordinator._error_count == 0

    async def test_async_update_data_handles_rate_limit(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that rate limit increases interval."""
        mock_client = MagicMock()
        mock_client.get_user_information = AsyncMock(
            side_effect=RivianApiRateLimitError("Rate limited")
        )

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator.data = {"userId": "test_user"}  # Existing data

        result = await coordinator._async_update_data()

        # Should return existing data
        assert result == {"userId": "test_user"}
        assert coordinator._error_count == 1

    async def test_async_update_data_handles_unauthenticated(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that unauthenticated raises ConfigEntryAuthFailed."""
        mock_client = MagicMock()
        mock_client.close = AsyncMock()
        mock_client.get_user_information = AsyncMock(
            side_effect=RivianUnauthenticated("Not authenticated")
        )

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )

        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()

        mock_client.close.assert_called_once()

    async def test_async_update_data_handles_api_exception(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that API exception returns existing data."""
        mock_client = MagicMock()
        mock_client.get_user_information = AsyncMock(
            side_effect=RivianApiException("API error")
        )

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator.data = {"userId": "test_user"}

        result = await coordinator._async_update_data()

        assert result == {"userId": "test_user"}
        assert coordinator._error_count == 1

    async def test_async_update_data_handles_unknown_exception(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that unknown exception returns existing data."""
        mock_client = MagicMock()
        mock_client.get_user_information = AsyncMock(side_effect=ValueError("Unknown"))

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator.data = {"userId": "test_user"}

        result = await coordinator._async_update_data()

        assert result == {"userId": "test_user"}
        assert coordinator._error_count == 1

    async def test_async_update_data_raises_on_error_with_no_data(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that error with no existing data raises UpdateFailed."""
        mock_client = MagicMock()
        mock_client.get_user_information = AsyncMock(
            side_effect=RivianApiException("API error")
        )

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    async def test_async_update_data_resets_error_count_on_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that error count resets on successful fetch."""
        mock_client = MagicMock()
        mock_client.get_user_information = AsyncMock(return_value={"userId": "test"})

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator._error_count = 5

        await coordinator._async_update_data()

        assert coordinator._error_count == 0


class TestUserCoordinator:
    """Test UserCoordinator functionality."""

    async def test_fetch_data(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test fetching user data."""
        mock_client = MagicMock()
        mock_client.get_user_information = AsyncMock(
            return_value={"userId": "test_user", "email": "test@example.com"}
        )

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )

        data = await coordinator._fetch_data()

        assert data["userId"] == "test_user"
        assert data["email"] == "test@example.com"
        mock_client.get_user_information.assert_called_once()


class TestWallboxCoordinator:
    """Test WallboxCoordinator functionality."""

    async def test_fetch_data_with_wallbox(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test fetching wallbox data."""
        mock_client = MagicMock()
        mock_client.get_registered_wallboxes = AsyncMock(
            return_value=[
                {
                    "wallboxId": "wallbox_123",
                    "power": 11.5,
                    "name": "Home Charger",
                }
            ]
        )

        coordinator = WallboxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )

        data = await coordinator._fetch_data()

        assert len(data) == 1
        assert data[0]["wallboxId"] == "wallbox_123"
        mock_client.get_registered_wallboxes.assert_called_once()

    async def test_fetch_data_no_wallbox(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test fetching wallbox data with no wallboxes."""
        mock_client = MagicMock()
        mock_client.get_registered_wallboxes = AsyncMock(return_value=[])

        coordinator = WallboxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )

        data = await coordinator._fetch_data()

        assert data == []


class TestCoordinatorGetMethod:
    """Test coordinator get() method."""

    async def test_get_method_returns_value(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get() method returns value from data."""
        mock_client = MagicMock()

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator.data = {"batteryLevel": {"value": 80}}

        # Should return nested value
        result = coordinator.get("batteryLevel.value")
        assert result == 80

    async def test_get_method_returns_none_for_missing(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get() method returns None for missing key."""
        mock_client = MagicMock()

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator.data = {}

        # Should return None for missing key
        result = coordinator.get("nonexistent")
        assert result is None

    async def test_get_method_with_default(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get() method returns default for missing key."""
        mock_client = MagicMock()

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator.data = {}

        # Should return default for missing key
        result = coordinator.get("nonexistent", "default_value")
        assert result == "default_value"


class TestUserCoordinatorMethods:
    """Test UserCoordinator specific methods."""

    async def test_get_vehicles(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get_vehicles method."""
        mock_client = MagicMock()

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator.data = {
            "vehicles": [
                {
                    "id": "v1",
                    "name": "Vehicle 1",
                    "vehicle": {"vin": "VIN1"},
                    "vas": {
                        "vasVehicleId": "vas_v1",
                        "vehiclePublicKey": "key1",
                    },
                },
                {
                    "id": "v2",
                    "name": "Vehicle 2",
                    "vehicle": {"vin": "VIN2"},
                    "vas": {
                        "vasVehicleId": "vas_v2",
                        "vehiclePublicKey": "key2",
                    },
                },
            ]
        }

        vehicles = coordinator.get_vehicles()

        assert len(vehicles) == 2
        assert "v1" in vehicles
        assert vehicles["v1"]["name"] == "Vehicle 1"
        assert vehicles["v1"]["vin"] == "VIN1"

    async def test_get_enrolled_phone_data_no_phones(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get_enrolled_phone_data with no enrolled phones."""
        mock_client = MagicMock()

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator.data = {}

        result = coordinator.get_enrolled_phone_data("test_key")

        assert result is None
