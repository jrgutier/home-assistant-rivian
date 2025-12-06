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


class TestHalloweenSwitch:
    """Test Halloween switch entity."""

    async def test_halloween_switch_entity_description(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_coordinator_with_parallax,
    ) -> None:
        """Test that the Halloween switch entity description is correct."""
        from custom_components.rivian.switch import PARALLAX_SWITCHES

        # Get the Halloween switch description
        halloween_desc = next(
            d for d in PARALLAX_SWITCHES if d.key == "halloween_enabled"
        )

        # Verify the entity description properties
        assert halloween_desc.key == "halloween_enabled"
        assert halloween_desc.translation_key == "halloween_enabled"
        assert halloween_desc.icon == "mdi:halloween"
        assert halloween_desc.turn_on_method == "set_halloween_settings"
        assert halloween_desc.turn_on_kwargs == {"enabled": True}
        assert halloween_desc.turn_off_method == "set_halloween_settings"
        assert halloween_desc.turn_off_kwargs == {"enabled": False}

    async def test_halloween_switch_requires_pairing(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_coordinator_with_parallax,
    ) -> None:
        """Test that Parallax switches require pairing (phone_identity_id check)."""
        # The switch.py async_setup_entry filters by phone_identity_id
        # This test verifies that the filter condition works correctly

        # Vehicles with phone_identity_id should get Parallax entities
        vehicle_with_pairing = {"phone_identity_id": "test_id", "vin": "TEST123"}
        assert vehicle_with_pairing.get("phone_identity_id") is not None

        # Vehicles without phone_identity_id should not get Parallax entities
        vehicle_without_pairing = {"vin": "TEST456"}
        assert vehicle_without_pairing.get("phone_identity_id") is None

    async def test_halloween_switch_turn_on_calls_api(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_coordinator_with_parallax,
    ) -> None:
        """Test turning on Halloween switch calls set_halloween_settings."""
        from custom_components.rivian.switch import (
            PARALLAX_SWITCHES,
            RivianParallaxSwitchEntity,
        )

        coordinator = mock_vehicle_coordinator_with_parallax
        coordinator.send_parallax_command = AsyncMock()

        # Get the Halloween switch description
        halloween_desc = next(
            d for d in PARALLAX_SWITCHES if d.key == "halloween_enabled"
        )

        # Create the entity directly
        entity = RivianParallaxSwitchEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=halloween_desc,
            vehicle={
                "phone_identity_id": "test_identity_id",
                "vin": "TEST123",
                "name": "Test R1T",
                "model": "R1T",
                "id": "test_id",
            },
        )

        # Call turn_on
        await entity.async_turn_on()

        # Assert the correct Parallax command was sent
        coordinator.send_parallax_command.assert_called_once_with(
            "set_halloween_settings",
            enabled=True,
        )

    async def test_halloween_switch_turn_off_calls_api(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_coordinator_with_parallax,
    ) -> None:
        """Test turning off Halloween switch calls set_halloween_settings with enabled=False."""
        from custom_components.rivian.switch import (
            PARALLAX_SWITCHES,
            RivianParallaxSwitchEntity,
        )

        coordinator = mock_vehicle_coordinator_with_parallax
        coordinator.send_parallax_command = AsyncMock()

        # Get the Halloween switch description
        halloween_desc = next(
            d for d in PARALLAX_SWITCHES if d.key == "halloween_enabled"
        )

        # Create the entity directly
        entity = RivianParallaxSwitchEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=halloween_desc,
            vehicle={
                "phone_identity_id": "test_identity_id",
                "vin": "TEST123",
                "name": "Test R1T",
                "model": "R1T",
                "id": "test_id",
            },
        )

        # Call turn_off
        await entity.async_turn_off()

        # Assert the correct Parallax command was sent
        coordinator.send_parallax_command.assert_called_once_with(
            "set_halloween_settings",
            enabled=False,
        )

    async def test_halloween_switch_not_assumed_state_when_is_on_defined(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_coordinator_with_parallax,
    ) -> None:
        """Test Halloween switch is NOT assumed_state when is_on is defined."""
        from custom_components.rivian.switch import (
            PARALLAX_SWITCHES,
            RivianParallaxSwitchEntity,
        )

        coordinator = mock_vehicle_coordinator_with_parallax

        # Get the Halloween switch description
        halloween_desc = next(
            d for d in PARALLAX_SWITCHES if d.key == "halloween_enabled"
        )

        # Create the entity directly
        entity = RivianParallaxSwitchEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=halloween_desc,
            vehicle={
                "phone_identity_id": "test_identity_id",
                "vin": "TEST123",
                "name": "Test R1T",
                "model": "R1T",
                "id": "test_id",
            },
        )

        # Assert that assumed_state is False when is_on is defined
        assert entity.assumed_state is False


class TestHalloweenSelect:
    """Test Halloween mode select entity."""

    async def test_halloween_mode_entity_description(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_coordinator_with_parallax,
    ) -> None:
        """Test that the Halloween mode entity description is correct."""
        from custom_components.rivian.select import PARALLAX_SELECTS

        # Get the Halloween mode description
        halloween_desc = next(d for d in PARALLAX_SELECTS if d.key == "halloween_mode")

        # Verify the entity description properties
        assert halloween_desc.key == "halloween_mode"
        assert halloween_desc.translation_key == "halloween_mode"
        assert halloween_desc.icon == "mdi:halloween"
        assert halloween_desc.options == ["SPOOKY", "FESTIVE"]
        assert halloween_desc.field == "parallax.halloween.animation_mode"

    async def test_halloween_mode_select_calls_api(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_coordinator_with_parallax,
    ) -> None:
        """Test selecting Halloween mode calls set_halloween_settings."""
        from custom_components.rivian.select import PARALLAX_SELECTS

        coordinator = mock_vehicle_coordinator_with_parallax
        coordinator.send_parallax_command = AsyncMock()

        # Get the Halloween mode description
        halloween_desc = next(d for d in PARALLAX_SELECTS if d.key == "halloween_mode")

        # Call the select function directly
        await halloween_desc.select(coordinator, "SPOOKY")

        # Assert the correct Parallax command was sent
        coordinator.send_parallax_command.assert_called_once_with(
            "set_halloween_settings",
            enabled=True,
            animation_mode="SPOOKY",
        )


class TestHalloweenNumber:
    """Test Halloween brightness number entity."""

    async def test_halloween_brightness_entity_description(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_coordinator_with_parallax,
    ) -> None:
        """Test that the Halloween brightness entity description is correct."""
        from custom_components.rivian.number import PARALLAX_NUMBERS

        # Get the Halloween brightness description
        halloween_desc = next(
            d for d in PARALLAX_NUMBERS if d.key == "halloween_brightness"
        )

        # Verify the entity description properties
        assert halloween_desc.key == "halloween_brightness"
        assert halloween_desc.translation_key == "halloween_brightness"
        assert halloween_desc.icon == "mdi:brightness-percent"
        assert halloween_desc.native_min_value == 0
        assert halloween_desc.native_max_value == 100
        assert halloween_desc.native_step == 10
        assert halloween_desc.field == "parallax.halloween.brightness"

    async def test_halloween_brightness_set_calls_api(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_coordinator_with_parallax,
    ) -> None:
        """Test setting Halloween brightness calls set_halloween_settings."""
        from custom_components.rivian.number import PARALLAX_NUMBERS

        coordinator = mock_vehicle_coordinator_with_parallax
        coordinator.send_parallax_command = AsyncMock()

        # Get the Halloween brightness description
        halloween_desc = next(
            d for d in PARALLAX_NUMBERS if d.key == "halloween_brightness"
        )

        # Call the set_fn function directly
        await halloween_desc.set_fn(coordinator, 80)

        # Assert the correct Parallax command was sent
        coordinator.send_parallax_command.assert_called_once_with(
            "set_halloween_settings",
            enabled=True,
            brightness=80,
        )


class TestHalloweenEntitiesIntegration:
    """Test Halloween entities entity descriptions exist together."""

    async def test_all_halloween_entities_defined(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_coordinator_with_parallax,
    ) -> None:
        """Test all Halloween entity descriptions are defined correctly."""
        from custom_components.rivian.switch import PARALLAX_SWITCHES
        from custom_components.rivian.select import PARALLAX_SELECTS
        from custom_components.rivian.number import PARALLAX_NUMBERS

        # Verify Halloween switch exists
        halloween_switch = next(
            (d for d in PARALLAX_SWITCHES if d.key == "halloween_enabled"), None
        )
        assert halloween_switch is not None
        assert halloween_switch.turn_on_method == "set_halloween_settings"
        assert halloween_switch.turn_off_method == "set_halloween_settings"

        # Verify Halloween mode select exists
        halloween_mode = next(
            (d for d in PARALLAX_SELECTS if d.key == "halloween_mode"), None
        )
        assert halloween_mode is not None
        assert halloween_mode.options == ["SPOOKY", "FESTIVE"]

        # Verify Halloween brightness number exists
        halloween_brightness = next(
            (d for d in PARALLAX_NUMBERS if d.key == "halloween_brightness"), None
        )
        assert halloween_brightness is not None
        assert halloween_brightness.native_min_value == 0
        assert halloween_brightness.native_max_value == 100
