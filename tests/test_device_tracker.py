"""Tests for Rivian device tracker platform."""

from unittest.mock import MagicMock

import pytest
from homeassistant.components.device_tracker import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.data_classes import RivianTrackerEntityDescription
from custom_components.rivian.device_tracker import (
    RivianDeviceEntity,
    async_setup_entry,
)


class TestRivianDeviceEntity:
    """Test RivianDeviceEntity class."""

    async def test_initialization(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test device tracker initialization."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {
            "gnssLocation": {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "timeStamp": "2024-01-01T00:00:00Z",
            }
        }
        coordinator.get = MagicMock(return_value=None)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianTrackerEntityDescription(
            key="location",
            translation_key="location",
        )

        entity = RivianDeviceEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity._attribute == "gnssLocation"
        assert entity._tracker_data["latitude"] == 37.7749
        assert entity._tracker_data["longitude"] == -122.4194

    async def test_latitude_property(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test latitude property."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {
            "gnssLocation": {
                "latitude": 40.7128,
                "longitude": -74.0060,
                "timeStamp": "2024-01-01T00:00:00Z",
            }
        }
        coordinator.get = MagicMock(return_value=None)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianTrackerEntityDescription(
            key="location",
            translation_key="location",
        )

        entity = RivianDeviceEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.latitude == 40.7128

    async def test_longitude_property(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test longitude property."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {
            "gnssLocation": {
                "latitude": 40.7128,
                "longitude": -74.0060,
                "timeStamp": "2024-01-01T00:00:00Z",
            }
        }
        coordinator.get = MagicMock(return_value=None)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianTrackerEntityDescription(
            key="location",
            translation_key="location",
        )

        entity = RivianDeviceEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.longitude == -74.0060

    async def test_source_type(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test source_type is GPS."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {
            "gnssLocation": {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "timeStamp": "2024-01-01T00:00:00Z",
            }
        }
        coordinator.get = MagicMock(return_value=None)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianTrackerEntityDescription(
            key="location",
            translation_key="location",
        )

        entity = RivianDeviceEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.source_type == SourceType.GPS

    async def test_force_update(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test force_update is False (polling via coordinator)."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {
            "gnssLocation": {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "timeStamp": "2024-01-01T00:00:00Z",
            }
        }
        coordinator.get = MagicMock(return_value=None)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianTrackerEntityDescription(
            key="location",
            translation_key="location",
        )

        entity = RivianDeviceEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.force_update is False

    async def test_extra_state_attributes(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test extra_state_attributes includes last_update."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {
            "gnssLocation": {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "timeStamp": "2024-01-01T12:30:45Z",
            }
        }
        coordinator.get = MagicMock(return_value=None)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianTrackerEntityDescription(
            key="location",
            translation_key="location",
        )

        entity = RivianDeviceEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        attrs = entity.extra_state_attributes
        assert attrs["last_update"] == "2024-01-01T12:30:45Z"

    async def test_handle_coordinator_update(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test _handle_coordinator_update updates tracker data when timestamp changes."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {
            "gnssLocation": {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "timeStamp": "2024-01-01T00:00:00Z",
            }
        }
        coordinator.get = MagicMock(return_value=None)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianTrackerEntityDescription(
            key="location",
            translation_key="location",
        )

        entity = RivianDeviceEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Initial location
        assert entity.latitude == 37.7749
        assert entity.longitude == -122.4194

        # Update coordinator data with new location
        coordinator.data = {
            "gnssLocation": {
                "latitude": 40.7128,
                "longitude": -74.0060,
                "timeStamp": "2024-01-01T01:00:00Z",  # Different timestamp
            }
        }

        # Mock async_write_ha_state
        entity.async_write_ha_state = MagicMock()

        # Trigger update
        entity._handle_coordinator_update()

        # Should have updated tracker data
        assert entity._tracker_data["latitude"] == 40.7128
        assert entity._tracker_data["longitude"] == -74.0060
        assert entity._tracker_data["timeStamp"] == "2024-01-01T01:00:00Z"
        entity.async_write_ha_state.assert_called_once()

    async def test_handle_coordinator_update_same_timestamp(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test _handle_coordinator_update doesn't update when timestamp is the same."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {
            "gnssLocation": {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "timeStamp": "2024-01-01T00:00:00Z",
            }
        }
        coordinator.get = MagicMock(return_value=None)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianTrackerEntityDescription(
            key="location",
            translation_key="location",
        )

        entity = RivianDeviceEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock async_write_ha_state
        entity.async_write_ha_state = MagicMock()

        # Update coordinator data with same timestamp
        coordinator.data = {
            "gnssLocation": {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "timeStamp": "2024-01-01T00:00:00Z",  # Same timestamp
            }
        }

        # Trigger update
        entity._handle_coordinator_update()

        # Should not have called async_write_ha_state
        entity.async_write_ha_state.assert_not_called()

    async def test_handle_coordinator_update_exception(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test _handle_coordinator_update handles exception gracefully."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {
            "gnssLocation": {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "timeStamp": "2024-01-01T00:00:00Z",
            }
        }
        coordinator.get = MagicMock(return_value=None)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianTrackerEntityDescription(
            key="location",
            translation_key="location",
        )

        entity = RivianDeviceEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Update coordinator data without timestamp (will cause KeyError)
        coordinator.data = {
            "gnssLocation": {
                "latitude": 40.7128,
                "longitude": -74.0060,
                # Missing timeStamp
            }
        }

        # Should handle exception and update tracker data anyway
        entity._handle_coordinator_update()

        # Should have updated tracker data despite exception
        assert entity._tracker_data["latitude"] == 40.7128
        assert entity._tracker_data["longitude"] == -74.0060


@pytest.mark.asyncio
async def test_async_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test device tracker platform setup."""
    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator.data = {
        "gnssLocation": {
            "latitude": 37.7749,
            "longitude": -122.4194,
            "timeStamp": "2024-01-01T00:00:00Z",
        }
    }

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

    # Should have created one device tracker entity
    assert len(entities_added) == 1
    assert isinstance(entities_added[0], RivianDeviceEntity)
    assert entities_added[0].latitude == 37.7749
    assert entities_added[0].longitude == -122.4194


@pytest.mark.asyncio
async def test_async_setup_entry_multiple_vehicles(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test device tracker platform setup with multiple vehicles."""
    vehicle_coordinator_1 = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator_1.data = {
        "gnssLocation": {
            "latitude": 37.7749,
            "longitude": -122.4194,
            "timeStamp": "2024-01-01T00:00:00Z",
        }
    }

    vehicle_coordinator_2 = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator_2.data = {
        "gnssLocation": {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "timeStamp": "2024-01-01T00:00:00Z",
        }
    }

    vehicle_data = {
        "vehicle_1": {
            "id": "vehicle_1",
            "vin": "VIN1234567890",
            "name": "R1T One",
            "model": "R1T",
        },
        "vehicle_2": {
            "id": "vehicle_2",
            "vin": "VIN0987654321",
            "name": "R1S Two",
            "model": "R1S",
        },
    }

    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            ATTR_VEHICLE: vehicle_data,
            ATTR_COORDINATOR: {
                ATTR_VEHICLE: {
                    "vehicle_1": vehicle_coordinator_1,
                    "vehicle_2": vehicle_coordinator_2,
                },
            },
        }
    }

    entities_added = []

    def mock_add_entities(entities):
        entities_added.extend(entities)

    await async_setup_entry(hass, mock_config_entry, mock_add_entities)

    # Should have created two device tracker entities
    assert len(entities_added) == 2
    assert all(isinstance(e, RivianDeviceEntity) for e in entities_added)
