"""Tests for Parallax control entities."""

from unittest.mock import AsyncMock

import pytest

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


class TestParallaxCoordinator:
    """Test VehicleCoordinator.send_parallax_command() method."""

    async def test_send_parallax_command_delegates_to_api(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_coordinator_with_parallax,
    ) -> None:
        """Test that send_parallax_command calls the correct API method."""
        # Setup coordinator with mock API
        coordinator = mock_vehicle_coordinator_with_parallax
        coordinator.api.set_halloween_settings = AsyncMock()

        # Call send_parallax_command
        await coordinator.send_parallax_command(
            "set_halloween_settings", enabled=True, animation_mode="SPOOKY"
        )

        # Assert API method was called with correct args
        coordinator.api.set_halloween_settings.assert_called_once_with(
            vehicle_id=coordinator.vehicle_id,
            enabled=True,
            animation_mode="SPOOKY",
        )

    async def test_send_parallax_command_passes_vehicle_id(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_coordinator_with_parallax,
    ) -> None:
        """Test that vehicle_id is automatically passed to API method."""
        coordinator = mock_vehicle_coordinator_with_parallax
        coordinator.api.set_halloween_settings = AsyncMock()

        # Call without explicitly passing vehicle_id
        await coordinator.send_parallax_command("set_halloween_settings", enabled=False)

        # Assert vehicle_id was automatically included
        coordinator.api.set_halloween_settings.assert_called_once()
        call_kwargs = coordinator.api.set_halloween_settings.call_args.kwargs
        assert "vehicle_id" in call_kwargs
        assert call_kwargs["vehicle_id"] == coordinator.vehicle_id

    async def test_send_parallax_command_raises_on_missing_method(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_coordinator_with_parallax,
    ) -> None:
        """Test that send_parallax_command raises error for invalid method."""
        coordinator = mock_vehicle_coordinator_with_parallax

        # Configure api mock to raise AttributeError for invalid method
        # (simulating real behavior where getattr fails for non-existent methods)
        del coordinator.api.invalid_method_name  # Remove auto-created MagicMock attr

        # Call with invalid method name should raise TypeError (MagicMock not awaitable)
        # or AttributeError (method doesn't exist)
        with pytest.raises((AttributeError, TypeError)):
            await coordinator.send_parallax_command(
                "invalid_method_name", some_param=123
            )

    async def test_send_parallax_command_propagates_api_errors(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_coordinator_with_parallax,
    ) -> None:
        """Test that API errors are propagated to caller."""
        coordinator = mock_vehicle_coordinator_with_parallax
        coordinator.api.set_halloween_settings = AsyncMock(
            side_effect=Exception("API Error")
        )

        # Call should raise the API error
        with pytest.raises(Exception, match="API Error"):
            await coordinator.send_parallax_command(
                "set_halloween_settings", enabled=True
            )


# The Halloween switch/select/number tests that used to live below this line were
# deleted with their entities in s09a. Every one of those RVMs returns
# INTERNAL_SERVER_ERROR to sendVehicleOperation (see
# docs/development/SENDVEHICLEOPERATION_TEST_RESULTS.md), so the entities could
# never have worked. send_parallax_command itself survives -- s09b routes the one
# verified write through it -- so its tests stay.
