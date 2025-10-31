"""Tests for Rivian number platform."""

import sys
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from homeassistant.components.number import NumberDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant

# Mock VehicleCommand before importing
mock_rivian = Mock()
mock_rivian.VehicleCommand = Mock()
mock_rivian.VehicleCommand.CHARGING_LIMITS = "CHARGING_LIMITS"
sys.modules["rivian"] = mock_rivian

from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.data_classes import RivianNumberEntityDescription
from custom_components.rivian.number import RivianNumberEntity, async_setup_entry


class TestRivianNumberEntity:
    """Test RivianNumberEntity class."""

    async def test_native_value(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test native_value returns field value."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianNumberEntityDescription(
            key="battery_limit",
            translation_key="battery_limit",
            device_class=NumberDeviceClass.BATTERY,
            native_min_value=50,
            native_unit_of_measurement=PERCENTAGE,
            field="batteryLimit",
            set_fn=lambda coordinator, value: coordinator.send_vehicle_command(
                command="CHARGING_LIMITS", params={"SOC_limit": int(value)}
            ),
        )

        entity = RivianNumberEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _get_value
        entity._get_value = MagicMock(return_value=80)

        assert entity.native_value == 80

    async def test_native_unit_of_measurement(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test native_unit_of_measurement is percentage."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianNumberEntityDescription(
            key="battery_limit",
            translation_key="battery_limit",
            device_class=NumberDeviceClass.BATTERY,
            native_min_value=50,
            native_unit_of_measurement=PERCENTAGE,
            field="batteryLimit",
            set_fn=lambda coordinator, value: coordinator.send_vehicle_command(
                command="CHARGING_LIMITS", params={"SOC_limit": int(value)}
            ),
        )

        entity = RivianNumberEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.native_unit_of_measurement == PERCENTAGE

    async def test_device_class(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test device_class is BATTERY."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianNumberEntityDescription(
            key="battery_limit",
            translation_key="battery_limit",
            device_class=NumberDeviceClass.BATTERY,
            native_min_value=50,
            native_unit_of_measurement=PERCENTAGE,
            field="batteryLimit",
            set_fn=lambda coordinator, value: coordinator.send_vehicle_command(
                command="CHARGING_LIMITS", params={"SOC_limit": int(value)}
            ),
        )

        entity = RivianNumberEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.device_class == NumberDeviceClass.BATTERY

    async def test_async_set_native_value(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_set_native_value calls set_fn."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}
        coordinator.send_vehicle_command = AsyncMock()

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianNumberEntityDescription(
            key="battery_limit",
            translation_key="battery_limit",
            device_class=NumberDeviceClass.BATTERY,
            native_min_value=50,
            native_unit_of_measurement=PERCENTAGE,
            field="batteryLimit",
            set_fn=lambda coordinator, value: coordinator.send_vehicle_command(
                command="CHARGING_LIMITS", params={"SOC_limit": int(value)}
            ),
        )

        entity = RivianNumberEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        await entity.async_set_native_value(85)

        # Should call send_vehicle_command with charging limits
        coordinator.send_vehicle_command.assert_called_once_with(
            command="CHARGING_LIMITS", params={"SOC_limit": 85}
        )

    async def test_async_set_native_value_converts_to_int(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_set_native_value converts float to int."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}
        coordinator.send_vehicle_command = AsyncMock()

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianNumberEntityDescription(
            key="battery_limit",
            translation_key="battery_limit",
            device_class=NumberDeviceClass.BATTERY,
            native_min_value=50,
            native_unit_of_measurement=PERCENTAGE,
            field="batteryLimit",
            set_fn=lambda coordinator, value: coordinator.send_vehicle_command(
                command="CHARGING_LIMITS", params={"SOC_limit": int(value)}
            ),
        )

        entity = RivianNumberEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        await entity.async_set_native_value(85.7)

        # Should call send_vehicle_command with int value
        coordinator.send_vehicle_command.assert_called_once_with(
            command="CHARGING_LIMITS", params={"SOC_limit": 85}
        )


@pytest.mark.asyncio
async def test_async_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test number platform setup."""
    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator.data = {}

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

    # Should have created one number entity (battery_limit)
    assert len(entities_added) == 1
    assert isinstance(entities_added[0], RivianNumberEntity)


@pytest.mark.asyncio
async def test_async_setup_entry_no_phone_identity(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test number platform setup without phone_identity_id (vehicle control not enabled)."""
    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator.data = {}

    vehicle_data = {
        "test_vehicle_123": {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            # No phone_identity_id - vehicle control not enabled
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

    # Should not have created any number entities (no vehicle control)
    assert len(entities_added) == 0
