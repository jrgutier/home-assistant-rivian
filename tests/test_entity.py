"""Tests for Rivian entity base classes."""

from unittest.mock import MagicMock, PropertyMock

import pytest

from custom_components.rivian.button import RivianButtonEntity
from custom_components.rivian.const import DOMAIN
from custom_components.rivian.coordinator import (
    ChargingCoordinator,
    VehicleCoordinator,
    WallboxCoordinator,
)
from custom_components.rivian.entity import (
    RivianChargingEntity,
    RivianVehicleControlEntity,
    RivianVehicleEntity,
    RivianWallboxEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription


@pytest.fixture
def mock_vehicle_data() -> dict:
    """Return mock vehicle data."""
    return {
        "id": "test_vehicle_123",
        "vin": "TEST123456789",
        "name": "Test R1T",
        "model": "R1T",
    }


@pytest.fixture
def mock_vehicle_coordinator_data() -> dict:
    """Return mock vehicle coordinator data."""
    return {
        "powerState": {"value": "go"},
        "gearStatus": {"value": "park"},
        "batteryLevel": {"value": 80.5},
        "otaCurrentVersion": {"value": "2024.10.1"},
        "gnssLocation": {
            "latitude": 37.7749,
            "longitude": -122.4194,
        },
    }


class TestRivianVehicleEntity:
    """Test RivianVehicleEntity class."""

    async def test_initialization(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_data: dict,
    ) -> None:
        """Test entity initialization."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {"powerState": {"value": "go"}}
        coordinator.get = MagicMock(return_value="2024.10.1")

        description = EntityDescription(
            key="test_sensor",
            name="Test Sensor",
        )

        entity = RivianVehicleEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle_data,
        )

        assert entity._vin == "TEST123456789"
        assert entity.unique_id == "TEST123456789-test_sensor"
        assert entity.entity_description == description

    async def test_device_info(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_data: dict,
    ) -> None:
        """Test device info contains correct vehicle data."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {}
        coordinator.get = MagicMock(return_value="2024.10.1")

        description = EntityDescription(key="test", name="Test")

        entity = RivianVehicleEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle_data,
        )

        device_info = entity.device_info
        assert device_info["name"] == "Test R1T"
        assert device_info["manufacturer"] == "Rivian"
        assert device_info["model"] == "R1T"
        assert device_info["serial_number"] == "TEST123456789"
        assert device_info["sw_version"] == "2024.10.1"
        assert (DOMAIN, "TEST123456789") in device_info["identifiers"]
        assert (DOMAIN, "test_vehicle_123") in device_info["identifiers"]

    async def test_get_value(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_data: dict,
    ) -> None:
        """Test _get_value method retrieves data from coordinator."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(
            side_effect=lambda key: {"batteryLevel": 85.5}.get(key)
        )

        description = EntityDescription(key="test", name="Test")

        entity = RivianVehicleEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle_data,
        )

        assert entity._get_value("batteryLevel") == 85.5
        assert entity._get_value("nonexistent") is None

    async def test_available_with_field(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_data: dict,
    ) -> None:
        """Test availability based on field existence."""
        from dataclasses import dataclass

        from homeassistant.helpers.entity import EntityDescription

        # Create custom description class with field attribute
        @dataclass
        class TestDescription(EntityDescription):
            """Test description with field."""

            field: str | None = None

        coordinator = MagicMock(spec=VehicleCoordinator)

        # Create description with field attribute
        description = TestDescription(key="test", name="Test", field="batteryLevel")

        entity = RivianVehicleEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle_data,
        )

        # Field exists
        coordinator.get = MagicMock(return_value=80.5)
        assert entity.available is True

        # Field is None
        coordinator.get = MagicMock(return_value=None)
        assert entity.available is False

    async def test_device_info_uses_model_when_no_name(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test device info uses model when vehicle has no name."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value=None)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "",  # Empty name
            "model": "R1S",
        }

        description = EntityDescription(key="test", name="Test")

        entity = RivianVehicleEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.device_info["name"] == "R1S"


class TestRivianVehicleControlEntity:
    """Test RivianVehicleControlEntity class."""

    async def test_initialization(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_data: dict,
    ) -> None:
        """Test control entity initialization."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {"gearStatus": {"value": "park"}}
        coordinator.get = MagicMock(return_value=None)
        coordinator.is_online = MagicMock(return_value=True)

        description = EntityDescription(key="test_control", name="Test Control")

        entity = RivianVehicleControlEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle_data,
        )

        assert entity._command_in_progress is None
        assert entity._current_command_id is None
        assert entity._last_command_status == {}

    async def test_available_offline(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_data: dict,
    ) -> None:
        """Test entity unavailable when offline."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=False)
        coordinator.get = MagicMock(return_value=None)

        description = EntityDescription(key="test", name="Test")

        entity = RivianVehicleControlEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle_data,
        )

        assert entity.available is False

    async def test_available_not_in_park(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_data: dict,
    ) -> None:
        """Test entity unavailable when not in park gear."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.get = MagicMock(
            side_effect=lambda key: {"gearStatus": "drive"}.get(key)
        )
        coordinator.data = {}

        description = EntityDescription(key="test", name="Test")

        entity = RivianVehicleControlEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle_data,
        )

        assert entity.available is False

    async def test_available_with_zone_restriction_inside_zone(
        self,
        hass: HomeAssistant,
        mock_vehicle_data: dict,
    ) -> None:
        """Test entity available when inside restricted zone."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        # Create config entry with zone restriction
        mock_config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={"username": "test@test.com", "password": "test"},
            options={"zone": ["zone.home"]},
        )

        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.get = MagicMock(
            side_effect=lambda key: {"gearStatus": "park"}.get(key)
        )
        coordinator.data = {
            "gnssLocation": {
                "latitude": 37.7749,
                "longitude": -122.4194,
            }
        }

        description = EntityDescription(key="test", name="Test")

        # Create zone state
        hass.states.async_set(
            "zone.home",
            "zoning",
            {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "radius": 100,
            },
        )

        entity = RivianVehicleControlEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle_data,
        )

        # Assign hass to entity
        entity.hass = hass

        # Should be available when inside zone
        assert entity.available is True

    async def test_available_with_zone_restriction_outside_zone(
        self,
        hass: HomeAssistant,
        mock_vehicle_data: dict,
    ) -> None:
        """Test entity unavailable when outside restricted zone."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        # Create config entry with zone restriction
        mock_config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={"username": "test@test.com", "password": "test"},
            options={"zone": ["zone.home"]},
        )

        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.get = MagicMock(
            side_effect=lambda key: {"gearStatus": "park"}.get(key)
        )
        coordinator.data = {
            "gnssLocation": {
                "latitude": 40.7128,  # Different location (NYC)
                "longitude": -74.0060,
            }
        }

        description = EntityDescription(key="test", name="Test")

        # Create zone state
        hass.states.async_set(
            "zone.home",
            "zoning",
            {
                "latitude": 37.7749,  # SF
                "longitude": -122.4194,
                "radius": 100,
            },
        )

        entity = RivianVehicleControlEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle_data,
        )

        # Assign hass to entity
        entity.hass = hass

        # Should be unavailable when outside zone
        assert entity.available is False

    async def test_extra_state_attributes_with_command_in_progress(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_data: dict,
    ) -> None:
        """Test extra state attributes when command is in progress."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value=None)

        description = EntityDescription(key="test", name="Test")

        entity = RivianVehicleControlEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle_data,
        )

        entity._command_in_progress = "UNLOCK_ALL_CLOSURES"

        attrs = entity.extra_state_attributes
        assert attrs["current_command"] == "UNLOCK_ALL_CLOSURES"

    async def test_extra_state_attributes_with_last_command_status(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_data: dict,
    ) -> None:
        """Test extra state attributes with last command status."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value=None)

        description = EntityDescription(key="test", name="Test")

        entity = RivianVehicleControlEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle_data,
        )

        entity._last_command_status = {
            "command": "UNLOCK_ALL_CLOSURES",
            "state": "COMPLETED_SUCCESS",
            "timestamp": "2024-01-01T00:00:00Z",
        }

        attrs = entity.extra_state_attributes
        assert attrs["last_command"] == "UNLOCK_ALL_CLOSURES"
        assert attrs["last_command_state"] == "COMPLETED_SUCCESS"
        assert attrs["last_command_time"] == "2024-01-01T00:00:00Z"


class TestRivianChargingEntity:
    """Test RivianChargingEntity class."""

    async def test_initialization(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test charging entity initialization."""
        coordinator = MagicMock(spec=ChargingCoordinator)
        coordinator.data = {}

        description = EntityDescription(
            key="charging_power",
            name="Charging Power",
        )

        vin = "TEST123456789"

        entity = RivianChargingEntity(
            coordinator=coordinator,
            description=description,
            vin=vin,
        )

        assert entity.vin == vin
        assert entity.unique_id == f"{vin}-charging_power"
        assert entity.entity_description == description

    async def test_device_info(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test charging entity device info."""
        coordinator = MagicMock(spec=ChargingCoordinator)

        description = EntityDescription(key="test", name="Test")

        vin = "TEST123456789"

        entity = RivianChargingEntity(
            coordinator=coordinator,
            description=description,
            vin=vin,
        )

        device_info = entity.device_info
        assert (DOMAIN, vin) in device_info["identifiers"]


class TestRivianWallboxEntity:
    """Test RivianWallboxEntity class."""

    async def test_initialization(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test wallbox entity initialization."""
        coordinator = MagicMock(spec=WallboxCoordinator)

        wallbox_data = {
            "wallboxId": "wallbox_123",
            "serialNumber": "WB123456",
            "name": "Home Charger",
            "model": "Rivian Wall Charger",
            "softwareVersion": "1.2.3",
        }

        description = EntityDescription(
            key="wallbox_power",
            name="Wallbox Power",
        )

        entity = RivianWallboxEntity(
            coordinator=coordinator,
            description=description,
            wallbox=wallbox_data,
        )

        assert entity.wallbox == wallbox_data
        assert entity.unique_id == "WB123456-wallbox_power"
        assert entity.entity_description == description

    async def test_device_info(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test wallbox entity device info."""
        coordinator = MagicMock(spec=WallboxCoordinator)

        wallbox_data = {
            "wallboxId": "wallbox_123",
            "serialNumber": "WB123456",
            "name": "Home Charger",
            "model": "Rivian Wall Charger",
            "softwareVersion": "1.2.3",
        }

        description = EntityDescription(key="test", name="Test")

        entity = RivianWallboxEntity(
            coordinator=coordinator,
            description=description,
            wallbox=wallbox_data,
        )

        device_info = entity.device_info
        assert device_info["name"] == "Home Charger"
        assert device_info["manufacturer"] == "Rivian"
        assert device_info["model"] == "Rivian Wall Charger"
        assert device_info["serial_number"] == "WB123456"
        assert device_info["sw_version"] == "1.2.3"
        assert (DOMAIN, "WB123456") in device_info["identifiers"]

    async def test_handle_coordinator_update(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test wallbox entity handles coordinator updates."""
        coordinator = MagicMock(spec=WallboxCoordinator)

        wallbox_data = {
            "wallboxId": "wallbox_123",
            "serialNumber": "WB123456",
            "name": "Home Charger",
            "model": "Rivian Wall Charger",
            "softwareVersion": "1.2.3",
        }

        description = EntityDescription(key="test", name="Test")

        entity = RivianWallboxEntity(
            coordinator=coordinator,
            description=description,
            wallbox=wallbox_data,
        )

        # Mock coordinator data with updated wallbox
        updated_wallbox = wallbox_data.copy()
        updated_wallbox["softwareVersion"] = "1.3.0"
        coordinator.data = [updated_wallbox]

        entity.async_write_ha_state = MagicMock()

        # Trigger update
        entity._handle_coordinator_update()

        # Wallbox should be updated
        assert entity.wallbox["softwareVersion"] == "1.3.0"
        entity.async_write_ha_state.assert_called_once()


class TestRivianVehicleControlEntityAvailableEdgeCases:
    """Test RivianVehicleControlEntity available edge cases."""

    async def test_available_with_custom_fn_returns_false(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test available returns False when description.available returns False."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.data = {"powerState": "awake"}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        from custom_components.rivian.data_classes import RivianButtonEntityDescription

        # Create description with available function that returns False
        description = RivianButtonEntityDescription(
            key="test_button",
            translation_key="test_button",
            available=lambda coord: False,  # Always unavailable
        )

        entity = RivianButtonEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should return False (lines 102-103)
        assert entity.available is False

    async def test_available_with_zone_outside(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        monkeypatch,
    ) -> None:
        """Test available returns False when vehicle is outside all zones."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.data = {
            "gnssLocation": {"latitude": 10.0, "longitude": 20.0},
            "powerState": "awake",
        }

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        # Mock config entry with zone option
        monkeypatch.setattr(
            type(mock_config_entry),
            "options",
            PropertyMock(return_value={"zone": ["zone.home"]}),
            raising=False,
        )

        # Create zone state
        hass.states.async_set(
            "zone.home",
            "zoning",
            {
                "latitude": 50.0,  # Far from vehicle
                "longitude": 60.0,
                "radius": 100,
            },
        )

        from custom_components.rivian.data_classes import RivianButtonEntityDescription

        description = RivianButtonEntityDescription(
            key="test_button",
            translation_key="test_button",
        )

        entity = RivianButtonEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should return False when outside zone (line 111)
        assert entity.available is False
