"""Tests for Rivian binary sensor platform."""

from unittest.mock import MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.rivian.binary_sensor import (
    RivianBinarySensorEntity,
    RivianCloudConnectionBinarySensor,
    async_setup_entry,
)
from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.data_classes import RivianBinarySensorEntityDescription


class TestRivianBinarySensorEntity:
    """Test RivianBinarySensorEntity class."""

    async def test_is_on_simple_field(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_on with simple field and matching value."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="closed")
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianBinarySensorEntityDescription(
            key="door_test",
            translation_key="door_test",
            field="doorFrontLeftClosed",
            on_value="closed",
        )

        entity = RivianBinarySensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.is_on is True

    async def test_is_on_list_of_values(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_on with list of on_values."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="charging_active")
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianBinarySensorEntityDescription(
            key="charging",
            translation_key="charging",
            field="chargeStatus",
            on_value=["charging_active", "charging_limited"],
        )

        entity = RivianBinarySensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.is_on is True

    async def test_is_on_not_matching(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_on returns False when value doesn't match."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="open")
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianBinarySensorEntityDescription(
            key="door_test",
            translation_key="door_test",
            field="doorFrontLeftClosed",
            on_value="closed",
        )

        entity = RivianBinarySensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.is_on is False

    async def test_is_on_with_negate(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_on with negate flag inverts result."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="closed")
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianBinarySensorEntityDescription(
            key="door_open",
            translation_key="door_open",
            field="doorFrontLeftClosed",
            on_value="closed",
            negate=True,
        )

        entity = RivianBinarySensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Value is "closed" which matches on_value, but negate=True inverts it
        assert entity.is_on is False

    async def test_is_on_none_when_value_none(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_on returns None when field value is None."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value=None)
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianBinarySensorEntityDescription(
            key="door_test",
            translation_key="door_test",
            field="doorFrontLeftClosed",
            on_value="closed",
        )

        entity = RivianBinarySensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.is_on is None

    async def test_is_on_aggregate_field(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_on with aggregate field (set of fields)."""
        coordinator = MagicMock(spec=VehicleCoordinator)

        def mock_get(key):
            return {
                "doorFrontLeftClosed": "closed",
                "doorFrontRightClosed": "open",
            }.get(key)

        coordinator.get = MagicMock(side_effect=mock_get)
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianBinarySensorEntityDescription(
            key="any_door_open",
            translation_key="any_door_open",
            field={"doorFrontLeftClosed", "doorFrontRightClosed"},
            on_value="open",
        )

        entity = RivianBinarySensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should be True because one door is "open"
        assert entity.is_on is True

    async def test_available_aggregate_field(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test available with aggregate field."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {}

        def mock_get(key):
            return {
                "doorFrontLeftClosed": "closed",
                "doorFrontRightClosed": "open",
            }.get(key)

        coordinator.get = MagicMock(side_effect=mock_get)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianBinarySensorEntityDescription(
            key="any_door_open",
            translation_key="any_door_open",
            field={"doorFrontLeftClosed", "doorFrontRightClosed"},
            on_value="open",
        )

        entity = RivianBinarySensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should be available because at least one field has a value
        assert entity.available is True

    async def test_extra_state_attributes(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test extra_state_attributes includes value, timestamp, and history."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {
            "doorFrontLeftClosed": {
                "value": "closed",
                "timeStamp": "2024-01-01T00:00:00Z",
                "history": ["closed", "open", "closed"],
            }
        }
        coordinator.get = MagicMock(return_value="closed")

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianBinarySensorEntityDescription(
            key="door_test",
            translation_key="door_test",
            field="doorFrontLeftClosed",
            on_value="closed",
        )

        entity = RivianBinarySensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        attrs = entity.extra_state_attributes
        assert attrs["value"] == "closed"
        assert attrs["last_update"] == "2024-01-01T00:00:00Z"
        assert "history" in attrs

    async def test_extra_state_attributes_none_for_aggregate(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test extra_state_attributes returns None for aggregate fields."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {}
        coordinator.get = MagicMock(return_value="open")

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianBinarySensorEntityDescription(
            key="any_door_open",
            translation_key="any_door_open",
            field={"doorFrontLeftClosed", "doorFrontRightClosed"},
            on_value="open",
        )

        entity = RivianBinarySensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.extra_state_attributes is None

    async def test_extra_state_attributes_none_when_field_missing(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test extra_state_attributes returns None when field is missing."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {}
        coordinator.get = MagicMock(return_value=None)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianBinarySensorEntityDescription(
            key="door_test",
            translation_key="door_test",
            field="doorFrontLeftClosed",
            on_value="closed",
        )

        entity = RivianBinarySensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.extra_state_attributes is None


class TestRivianCloudConnectionBinarySensor:
    """Test RivianCloudConnectionBinarySensor class."""

    async def test_device_class(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test device class is CONNECTIVITY."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.last_sync = MagicMock(return_value="2024-01-01T00:00:00Z")
        coordinator.data = {}
        coordinator.get = MagicMock(return_value=None)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        entity = RivianCloudConnectionBinarySensor(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            vehicle=vehicle_data,
        )

        assert entity.device_class == BinarySensorDeviceClass.CONNECTIVITY

    async def test_is_on_when_online(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_on returns True when coordinator reports online."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.last_sync = MagicMock(return_value="2024-01-01T00:00:00Z")
        coordinator.data = {}
        coordinator.get = MagicMock(return_value=None)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        entity = RivianCloudConnectionBinarySensor(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            vehicle=vehicle_data,
        )

        assert entity.is_on is True

    async def test_is_on_when_offline(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_on returns False when coordinator reports offline."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=False)
        coordinator.last_sync = MagicMock(return_value=None)
        coordinator.data = {}
        coordinator.get = MagicMock(return_value=None)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        entity = RivianCloudConnectionBinarySensor(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            vehicle=vehicle_data,
        )

        assert entity.is_on is False

    async def test_extra_state_attributes(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test extra_state_attributes includes last_sync."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.last_sync = MagicMock(return_value="2024-01-01T12:00:00Z")
        coordinator.data = {}
        coordinator.get = MagicMock(return_value=None)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        entity = RivianCloudConnectionBinarySensor(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            vehicle=vehicle_data,
        )

        attrs = entity.extra_state_attributes
        assert attrs["last_sync"] == "2024-01-01T12:00:00Z"


@pytest.mark.asyncio
async def test_async_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test binary sensor platform setup."""
    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator.data = {}

    vehicle_data = {
        "test_vehicle_123": {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
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

    # Should have created binary sensor entities plus cloud connection sensor
    assert len(entities_added) > 0

    # Verify we have at least one cloud connection sensor
    cloud_sensors = [
        e for e in entities_added if isinstance(e, RivianCloudConnectionBinarySensor)
    ]
    assert len(cloud_sensors) == 1

    # Verify we have binary sensors
    binary_sensors = [
        e for e in entities_added if isinstance(e, RivianBinarySensorEntity)
    ]
    assert len(binary_sensors) > 0


class TestRivianBinarySensorEntityEdgeCases:
    """Test RivianBinarySensorEntity edge cases."""

    async def test_available_aggregate_calls_super(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test available property with aggregate calls super."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.data = {
            "field1": {"value": "open"},
            "field2": {"value": "closed"},
        }

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        from custom_components.rivian.data_classes import (
            RivianBinarySensorEntityDescription,
        )

        # Create aggregate description
        description = RivianBinarySensorEntityDescription(
            key="test_aggregate",
            translation_key="test_aggregate",
            field=["field1", "field2"],  # Multiple fields = aggregate
            on_value="open",
        )

        entity = RivianBinarySensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should call super().available (line 73)
        result = entity.available
        assert isinstance(result, bool)

    async def test_extra_state_attributes_entity_none(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test extra_state_attributes returns None when entity is None."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.data = {
            "test_field": None,  # Entity is None
        }

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        from custom_components.rivian.data_classes import (
            RivianBinarySensorEntityDescription,
        )

        description = RivianBinarySensorEntityDescription(
            key="test_sensor",
            translation_key="test_sensor",
            field="test_field",
            on_value="open",
        )

        entity = RivianBinarySensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should return None when entity is None (line 98)
        result = entity.extra_state_attributes
        assert result is None
