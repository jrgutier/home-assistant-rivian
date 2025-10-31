"""Tests for Rivian select platform."""

import sys
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

# Mock VehicleCommand before importing
mock_rivian = Mock()
mock_rivian.VehicleCommand = Mock()
mock_rivian.VehicleCommand.CABIN_HVAC_REAR_LEFT_SEAT_HEAT = (
    "CABIN_HVAC_REAR_LEFT_SEAT_HEAT"
)
mock_rivian.VehicleCommand.CABIN_HVAC_REAR_RIGHT_SEAT_HEAT = (
    "CABIN_HVAC_REAR_RIGHT_SEAT_HEAT"
)
mock_rivian.VehicleCommand.CABIN_HVAC_LEFT_SEAT_HEAT = "CABIN_HVAC_LEFT_SEAT_HEAT"
mock_rivian.VehicleCommand.CABIN_HVAC_RIGHT_SEAT_HEAT = "CABIN_HVAC_RIGHT_SEAT_HEAT"
mock_rivian.VehicleCommand.CABIN_HVAC_LEFT_SEAT_VENT = "CABIN_HVAC_LEFT_SEAT_VENT"
mock_rivian.VehicleCommand.CABIN_HVAC_RIGHT_SEAT_VENT = "CABIN_HVAC_RIGHT_SEAT_VENT"
sys.modules["rivian"] = mock_rivian

from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.select import (
    RivianFrontSeatSelectEntity,
    RivianSelectEntity,
    async_setup_entry,
    get_seat_command_and_level,
)


class TestGetSeatCommandAndLevel:
    """Test get_seat_command_and_level function."""

    def test_off_left_seat(self):
        """Test Off option for left seat."""
        command, level = get_seat_command_and_level("Off", is_left_seat=True)
        assert command == "CABIN_HVAC_LEFT_SEAT_HEAT"
        assert level == 0

    def test_off_right_seat(self):
        """Test Off option for right seat."""
        command, level = get_seat_command_and_level("Off", is_left_seat=False)
        assert command == "CABIN_HVAC_RIGHT_SEAT_HEAT"
        assert level == 0

    def test_heat_level_1_left(self):
        """Test Heat Level 1 for left seat."""
        command, level = get_seat_command_and_level("Heat Level 1", is_left_seat=True)
        assert command == "CABIN_HVAC_LEFT_SEAT_HEAT"
        assert level == 2

    def test_heat_level_2_right(self):
        """Test Heat Level 2 for right seat."""
        command, level = get_seat_command_and_level("Heat Level 2", is_left_seat=False)
        assert command == "CABIN_HVAC_RIGHT_SEAT_HEAT"
        assert level == 3

    def test_heat_level_3_left(self):
        """Test Heat Level 3 for left seat."""
        command, level = get_seat_command_and_level("Heat Level 3", is_left_seat=True)
        assert command == "CABIN_HVAC_LEFT_SEAT_HEAT"
        assert level == 4

    def test_cool_level_1_left(self):
        """Test Cool Level 1 for left seat."""
        command, level = get_seat_command_and_level("Cool Level 1", is_left_seat=True)
        assert command == "CABIN_HVAC_LEFT_SEAT_VENT"
        assert level == 2

    def test_cool_level_2_right(self):
        """Test Cool Level 2 for right seat."""
        command, level = get_seat_command_and_level("Cool Level 2", is_left_seat=False)
        assert command == "CABIN_HVAC_RIGHT_SEAT_VENT"
        assert level == 3

    def test_cool_level_3_left(self):
        """Test Cool Level 3 for left seat."""
        command, level = get_seat_command_and_level("Cool Level 3", is_left_seat=True)
        assert command == "CABIN_HVAC_LEFT_SEAT_VENT"
        assert level == 4


class TestRivianSelectEntity:
    """Test RivianSelectEntity class."""

    async def test_current_option(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test current_option returns field value."""
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

        from custom_components.rivian.data_classes import RivianSelectEntityDescription

        description = RivianSelectEntityDescription(
            key="seat_rear_left_heat",
            translation_key="seat_rear_left_heat",
            options=["Off", "Level_1", "Level_2", "Level_3"],
            field="seatRearLeftHeat",
            select=lambda coordinator, option: coordinator.send_vehicle_command(
                command="CABIN_HVAC_REAR_LEFT_SEAT_HEAT",
                params={"level": int(option)},
            ),
        )

        entity = RivianSelectEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _get_value
        entity._get_value = MagicMock(return_value="Level_2")

        assert entity.current_option == "Level_2"

    async def test_async_select_option(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_select_option calls select function."""
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

        from custom_components.rivian.data_classes import RivianSelectEntityDescription

        description = RivianSelectEntityDescription(
            key="seat_rear_left_heat",
            translation_key="seat_rear_left_heat",
            options=["Off", "Level_1", "Level_2", "Level_3"],
            field="seatRearLeftHeat",
            select=lambda coordinator, option: coordinator.send_vehicle_command(
                command="CABIN_HVAC_REAR_LEFT_SEAT_HEAT",
                params={"level": int(option)},
            ),
        )

        entity = RivianSelectEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        await entity.async_select_option("Level_3")

        # Should call send_vehicle_command with mapped level
        coordinator.send_vehicle_command.assert_called_once_with(
            command="CABIN_HVAC_REAR_LEFT_SEAT_HEAT",
            params={"level": 4},  # Level_3 maps to "4"
        )


class TestRivianFrontSeatSelectEntity:
    """Test RivianFrontSeatSelectEntity class."""

    async def test_current_option_off(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test current_option returns Off when both heat and cool are off."""
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

        seat_config = {
            "key": "seat_front_left_heat_vent",
            "translation_key": "seat_front_left_heat_vent",
            "heat_field": "seatFrontLeftHeat",
            "cool_field": "seatFrontLeftVent",
            "is_left": True,
        }

        entity = RivianFrontSeatSelectEntity(
            coordinator=coordinator,
            entry=mock_config_entry,
            vehicle=vehicle_data,
            seat_config=seat_config,
        )

        # Mock _get_value to return Off for both
        entity._get_value = MagicMock(return_value="Off")

        assert entity.current_option == "Off"

    async def test_current_option_heat_level_1(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test current_option returns Heat Level 1 when heat is Level_1."""
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

        seat_config = {
            "key": "seat_front_left_heat_vent",
            "translation_key": "seat_front_left_heat_vent",
            "heat_field": "seatFrontLeftHeat",
            "cool_field": "seatFrontLeftVent",
            "is_left": True,
        }

        entity = RivianFrontSeatSelectEntity(
            coordinator=coordinator,
            entry=mock_config_entry,
            vehicle=vehicle_data,
            seat_config=seat_config,
        )

        # Mock _get_value
        def mock_get_value(field):
            if field == "seatFrontLeftHeat":
                return "Level_1"
            return "Off"

        entity._get_value = MagicMock(side_effect=mock_get_value)

        assert entity.current_option == "Heat Level 1"

    async def test_current_option_cool_level_2(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test current_option returns Cool Level 2 when cool is Level_2."""
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

        seat_config = {
            "key": "seat_front_right_heat_vent",
            "translation_key": "seat_front_right_heat_vent",
            "heat_field": "seatFrontRightHeat",
            "cool_field": "seatFrontRightVent",
            "is_left": False,
        }

        entity = RivianFrontSeatSelectEntity(
            coordinator=coordinator,
            entry=mock_config_entry,
            vehicle=vehicle_data,
            seat_config=seat_config,
        )

        # Mock _get_value
        def mock_get_value(field):
            if field == "seatFrontRightVent":
                return "Level_2"
            return "Off"

        entity._get_value = MagicMock(side_effect=mock_get_value)

        assert entity.current_option == "Cool Level 2"

    async def test_icon_off(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test icon is car-seat when off."""
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

        seat_config = {
            "key": "seat_front_left_heat_vent",
            "translation_key": "seat_front_left_heat_vent",
            "heat_field": "seatFrontLeftHeat",
            "cool_field": "seatFrontLeftVent",
            "is_left": True,
        }

        entity = RivianFrontSeatSelectEntity(
            coordinator=coordinator,
            entry=mock_config_entry,
            vehicle=vehicle_data,
            seat_config=seat_config,
        )

        # Mock _get_value and current_option
        entity._get_value = MagicMock(return_value="Off")

        assert entity.icon == "mdi:car-seat"

    async def test_icon_heat(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test icon is car-seat-heater when heating."""
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

        seat_config = {
            "key": "seat_front_left_heat_vent",
            "translation_key": "seat_front_left_heat_vent",
            "heat_field": "seatFrontLeftHeat",
            "cool_field": "seatFrontLeftVent",
            "is_left": True,
        }

        entity = RivianFrontSeatSelectEntity(
            coordinator=coordinator,
            entry=mock_config_entry,
            vehicle=vehicle_data,
            seat_config=seat_config,
        )

        # Mock _get_value
        def mock_get_value(field):
            if field == "seatFrontLeftHeat":
                return "Level_2"
            return "Off"

        entity._get_value = MagicMock(side_effect=mock_get_value)

        assert entity.icon == "mdi:car-seat-heater"

    async def test_icon_cool(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test icon is car-seat-cooler when cooling."""
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

        seat_config = {
            "key": "seat_front_left_heat_vent",
            "translation_key": "seat_front_left_heat_vent",
            "heat_field": "seatFrontLeftHeat",
            "cool_field": "seatFrontLeftVent",
            "is_left": True,
        }

        entity = RivianFrontSeatSelectEntity(
            coordinator=coordinator,
            entry=mock_config_entry,
            vehicle=vehicle_data,
            seat_config=seat_config,
        )

        # Mock _get_value
        def mock_get_value(field):
            if field == "seatFrontLeftVent":
                return "Level_3"
            return "Off"

        entity._get_value = MagicMock(side_effect=mock_get_value)

        assert entity.icon == "mdi:car-seat-cooler"

    async def test_async_select_option_left_seat_heat(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_select_option for left seat heat."""
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

        seat_config = {
            "key": "seat_front_left_heat_vent",
            "translation_key": "seat_front_left_heat_vent",
            "heat_field": "seatFrontLeftHeat",
            "cool_field": "seatFrontLeftVent",
            "is_left": True,
        }

        entity = RivianFrontSeatSelectEntity(
            coordinator=coordinator,
            entry=mock_config_entry,
            vehicle=vehicle_data,
            seat_config=seat_config,
        )

        await entity.async_select_option("Heat Level 2")

        # Should call send_vehicle_command with heat command
        coordinator.send_vehicle_command.assert_called_once_with(
            command="CABIN_HVAC_LEFT_SEAT_HEAT",
            params={"level": 3},
        )

    async def test_async_select_option_right_seat_cool(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_select_option for right seat cool."""
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

        seat_config = {
            "key": "seat_front_right_heat_vent",
            "translation_key": "seat_front_right_heat_vent",
            "heat_field": "seatFrontRightHeat",
            "cool_field": "seatFrontRightVent",
            "is_left": False,
        }

        entity = RivianFrontSeatSelectEntity(
            coordinator=coordinator,
            entry=mock_config_entry,
            vehicle=vehicle_data,
            seat_config=seat_config,
        )

        await entity.async_select_option("Cool Level 1")

        # Should call send_vehicle_command with cool command
        coordinator.send_vehicle_command.assert_called_once_with(
            command="CABIN_HVAC_RIGHT_SEAT_VENT",
            params={"level": 2},
        )


@pytest.mark.asyncio
async def test_async_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test select platform setup."""
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

    # Should have created 4 select entities (2 rear + 2 front)
    assert len(entities_added) == 4


@pytest.mark.asyncio
async def test_async_setup_entry_no_phone_identity(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test select platform setup without phone_identity_id (vehicle control not enabled)."""
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

    # Should not have created any select entities (no vehicle control)
    assert len(entities_added) == 0
