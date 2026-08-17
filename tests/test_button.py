"""Tests for Rivian button platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from rivian import VehicleCommand as _RealVehicleCommand

from custom_components.rivian.button import (
    RivianButtonEntity,
    RivianPairPhoneButtonEntity,
    async_setup_entry,
)
from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import (
    DriverKeyCoordinator,
    VehicleCoordinator,
)
from custom_components.rivian.data_classes import RivianButtonEntityDescription
from homeassistant.components.button import ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, HomeAssistantError


@pytest.mark.asyncio
async def test_async_setup_entry_with_control_enabled(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test button platform setup with vehicle control enabled."""
    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator.data = {}

    drivers_coordinator = MagicMock(spec=DriverKeyCoordinator)
    drivers_coordinator.get_device_details = MagicMock(return_value={"isPaired": False})
    vehicle_coordinator.drivers_coordinator = drivers_coordinator

    vehicle_data = {
        "test_vehicle_123": {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
            "supported_features": ["SIDE_BIN_NXT_ACT"],
        }
    }

    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            ATTR_VEHICLE: vehicle_data,
            ATTR_COORDINATOR: {
                ATTR_VEHICLE: {"test_vehicle_123": vehicle_coordinator},
            },
        }
    }

    entities_added = []

    def mock_add_entities(entities):
        entities_added.extend(entities)

    await async_setup_entry(hass, mock_config_entry, mock_add_entities)

    # Should have wake button + 2 gear tunnel buttons + pair button
    assert len(entities_added) == 4
    assert any(isinstance(e, RivianButtonEntity) for e in entities_added)
    assert any(isinstance(e, RivianPairPhoneButtonEntity) for e in entities_added)


@pytest.mark.asyncio
async def test_async_setup_entry_without_control(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test button platform setup without vehicle control."""
    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator.data = {}

    # Add drivers_coordinator mock for the pair button logic
    drivers_coordinator = MagicMock(spec=DriverKeyCoordinator)
    drivers_coordinator.get_device_details = MagicMock(return_value=None)
    vehicle_coordinator.drivers_coordinator = drivers_coordinator

    vehicle_data = {
        "test_vehicle_123": {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            # No phone_identity_id - control not enabled
        }
    }

    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            ATTR_VEHICLE: vehicle_data,
            ATTR_COORDINATOR: {
                ATTR_VEHICLE: {"test_vehicle_123": vehicle_coordinator},
            },
        }
    }

    entities_added = []

    def mock_add_entities(entities):
        entities_added.extend(entities)

    await async_setup_entry(hass, mock_config_entry, mock_add_entities)

    # Should have no entities without phone_identity_id
    assert len(entities_added) == 0


@pytest.mark.asyncio
async def test_async_setup_entry_already_paired(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test button platform setup with already paired device."""
    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator.data = {}

    drivers_coordinator = MagicMock(spec=DriverKeyCoordinator)
    drivers_coordinator.get_device_details = MagicMock(
        return_value={"isPaired": True}  # Already paired
    )
    vehicle_coordinator.drivers_coordinator = drivers_coordinator

    vehicle_data = {
        "test_vehicle_123": {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }
    }

    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            ATTR_VEHICLE: vehicle_data,
            ATTR_COORDINATOR: {
                ATTR_VEHICLE: {"test_vehicle_123": vehicle_coordinator},
            },
        }
    }

    entities_added = []

    def mock_add_entities(entities):
        entities_added.extend(entities)

    await async_setup_entry(hass, mock_config_entry, mock_add_entities)

    # Should have wake button but no pair button (already paired)
    assert len(entities_added) == 1
    assert isinstance(entities_added[0], RivianButtonEntity)


class TestRivianButtonEntity:
    """Test RivianButtonEntity class."""

    async def test_async_press_with_command(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test pressing button with command."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.data = {}
        coordinator.send_vehicle_command = AsyncMock()

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianButtonEntityDescription(
            key="wake",
            translation_key="wake",
            command=_RealVehicleCommand.WAKE_VEHICLE,
        )

        entity = RivianButtonEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _execute_command to bypass zone/park checks
        entity._execute_command = AsyncMock()

        await entity.async_press()

        # Should call _execute_command with the command
        entity._execute_command.assert_called_once_with(
            _RealVehicleCommand.WAKE_VEHICLE, None
        )

    async def test_async_press_with_press_fn(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test pressing button with press_fn."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        press_fn = AsyncMock()
        description = RivianButtonEntityDescription(
            key="custom",
            translation_key="custom",
            press_fn=press_fn,
        )

        entity = RivianButtonEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        await entity.async_press()

        # Should call press_fn
        press_fn.assert_called_once_with(coordinator)

    async def test_async_press_with_command_params(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test pressing button with command and parameters."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        command_params = {"param1": "value1"}
        description = RivianButtonEntityDescription(
            key="custom",
            translation_key="custom",
            command=_RealVehicleCommand.WAKE_VEHICLE,
            command_params=command_params,
        )

        entity = RivianButtonEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _execute_command to bypass zone/park checks
        entity._execute_command = AsyncMock()

        await entity.async_press()

        # Should call _execute_command with command and params
        entity._execute_command.assert_called_once_with(
            _RealVehicleCommand.WAKE_VEHICLE, command_params
        )


class TestRivianPairPhoneButtonEntity:
    """Test RivianPairPhoneButtonEntity class."""

    async def test_async_press_pairing_in_progress(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test pressing button when pairing is already in progress."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.vehicle_id = "test_vehicle_123"

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = ButtonEntityDescription(key="pair", translation_key="pair")

        entity = RivianPairPhoneButtonEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Set pairing flag
        entity._pairing = True

        # Should raise error
        with pytest.raises(HomeAssistantError):
            await entity.async_press()

    async def test_handle_driver_update(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test _handle_driver_update does nothing (intentionally blank)."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = ButtonEntityDescription(key="pair", translation_key="pair")

        entity = RivianPairPhoneButtonEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should not raise any error
        result = entity._handle_driver_update()

        # Should return None (method is intentionally blank)
        assert result is None
