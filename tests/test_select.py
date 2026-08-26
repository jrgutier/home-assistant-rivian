"""Tests for Rivian select platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.data_classes import RivianSelectEntityDescription
from custom_components.rivian.rivian_client import VehicleCommand
from custom_components.rivian.select import (
    LEVEL_MAP,
    LEVELS,
    SELECTS,
    RivianFrontSeatSelectEntity,
    RivianSelectEntity,
    async_setup_entry,
    get_seat_command_and_level,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


class TestGetSeatCommandAndLevel:
    """Test get_seat_command_and_level function."""

    @pytest.mark.parametrize(
        ("option", "is_left_seat", "command", "level"),
        [
            ("Off", True, "CABIN_HVAC_LEFT_SEAT_HEAT", 0),
            ("Off", False, "CABIN_HVAC_RIGHT_SEAT_HEAT", 0),
            ("Heat Level 1", True, "CABIN_HVAC_LEFT_SEAT_HEAT", 2),
            ("Heat Level 2", False, "CABIN_HVAC_RIGHT_SEAT_HEAT", 3),
            ("Heat Level 3", True, "CABIN_HVAC_LEFT_SEAT_HEAT", 4),
            ("Cool Level 1", True, "CABIN_HVAC_LEFT_SEAT_VENT", 2),
            ("Cool Level 2", False, "CABIN_HVAC_RIGHT_SEAT_VENT", 3),
            ("Cool Level 3", True, "CABIN_HVAC_LEFT_SEAT_VENT", 4),
        ],
    )
    def test_the_option_maps_to_a_command_and_level(
        self, option: str, is_left_seat: bool, command: str, level: int
    ) -> None:
        """Each seat option picks the heat/vent command for its side and a level."""
        assert get_seat_command_and_level(option, is_left_seat=is_left_seat) == (
            command,
            level,
        )


class TestRivianSelectEntity:
    """Test RivianSelectEntity class."""

    async def test_current_option(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test current_option returns field value."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

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
            vehicle=mock_vehicle_paired,
        )

        # Mock _get_value
        entity._get_value = MagicMock(return_value="Level_2")

        assert entity.current_option == "Level_2"

    async def test_async_select_option(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test async_select_option calls select function."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}
        coordinator.send_vehicle_command = AsyncMock()

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
            vehicle=mock_vehicle_paired,
        )

        await entity.async_select_option("Level_3")

        # Should call send_vehicle_command with mapped level
        coordinator.send_vehicle_command.assert_called_once_with(
            command="CABIN_HVAC_REAR_LEFT_SEAT_HEAT",
            params={"level": 4},  # Level_3 maps to "4"
        )


def _front_seat_entity(
    mock_config_entry: ConfigEntry, vehicle: dict, *, is_left: bool = True
) -> RivianFrontSeatSelectEntity:
    """Build the front-seat heat/vent select for one side."""
    side = "left" if is_left else "right"
    cap = "Left" if is_left else "Right"
    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator.is_online = MagicMock(return_value=True)
    coordinator.data = {"gearStatus": {"value": "park"}}
    return RivianFrontSeatSelectEntity(
        coordinator=coordinator,
        entry=mock_config_entry,
        vehicle=vehicle,
        seat_config={
            "key": f"seat_front_{side}_heat_vent",
            "translation_key": f"seat_front_{side}_heat_vent",
            "heat_field": f"seatFront{cap}Heat",
            "cool_field": f"seatFront{cap}Vent",
            "is_left": is_left,
        },
    )


def _reads(**fields: str) -> MagicMock:
    """Return a _get_value stand-in reporting `fields`, Off for everything else."""
    return MagicMock(side_effect=lambda field: fields.get(field, "Off"))


class TestRivianFrontSeatSelectEntity:
    """Test RivianFrontSeatSelectEntity class."""

    @pytest.mark.parametrize(
        ("is_left", "reported", "expected"),
        [
            (True, {}, "Off"),
            (True, {"seatFrontLeftHeat": "Level_1"}, "Heat Level 1"),
            (False, {"seatFrontRightVent": "Level_2"}, "Cool Level 2"),
        ],
    )
    async def test_current_option(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
        is_left: bool,
        reported: dict,
        expected: str,
    ) -> None:
        """Test current_option reports the level reported for either side."""
        entity = _front_seat_entity(
            mock_config_entry, mock_vehicle_paired, is_left=is_left
        )

        entity._get_value = _reads(**reported)

        assert entity.current_option == expected

    @pytest.mark.parametrize(
        ("reported", "expected_icon"),
        [
            ({}, "mdi:car-seat"),
            ({"seatFrontLeftHeat": "Level_2"}, "mdi:car-seat-heater"),
            ({"seatFrontLeftVent": "Level_3"}, "mdi:car-seat-cooler"),
        ],
    )
    async def test_icon(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
        reported: dict,
        expected_icon: str,
    ) -> None:
        """Test icon follows whether the seat is off, heating or cooling."""
        entity = _front_seat_entity(mock_config_entry, mock_vehicle_paired)

        entity._get_value = _reads(**reported)

        assert entity.icon == expected_icon

    async def test_async_select_option_left_seat_heat(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test async_select_option for left seat heat."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}
        coordinator.send_vehicle_command = AsyncMock()

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
            vehicle=mock_vehicle_paired,
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
        mock_vehicle_paired: dict,
    ) -> None:
        """Test async_select_option for right seat cool."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}
        coordinator.send_vehicle_command = AsyncMock()

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
            vehicle=mock_vehicle_paired,
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

    # Should have created 6 select entities (2 rear + 2 front + 2 PARALLAX_SELECTS)
    # - seat_rear_left_heat, seat_rear_right_heat
    # - seat_front_left_heat_vent, seat_front_right_heat_vent
    # - halloween_mode, cabin_ventilation_mode
    # The two PARALLAX_SELECTS were removed in s09a (their RVMs return
    # INTERNAL_SERVER_ERROR); the four seat/steering selects remain.
    # Third-row heat selects require HEATED_SEATS_THIRD and are not in this set.
    assert len(entities_added) == 4


@pytest.mark.asyncio
async def test_async_setup_entry_with_heated_seats_third(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """HEATED_SEATS_THIRD adds two disabled-by-default third-row selects."""
    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator.data = {}

    vehicle_data = {
        "test_vehicle_123": {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1S",
            "model": "R1S",
            "phone_identity_id": "test_phone_id",
            "supported_features": ["HEATED_SEATS_THIRD"],
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

    assert len(entities_added) == 6
    extra = [
        e
        for e in entities_added
        if e.entity_description.key
        in {"seat_third_row_left_heat", "seat_third_row_right_heat"}
    ]
    assert {e.entity_description.key for e in extra} == {
        "seat_third_row_left_heat",
        "seat_third_row_right_heat",
    }
    assert all(
        e.entity_description.entity_registry_enabled_default is False for e in extra
    )


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


class TestThirdRowHeatSelects:
    """Third-row heat SELECTS: feature-gated, disabled by default."""

    @pytest.mark.parametrize(
        ("key", "command"),
        [
            (
                "seat_third_row_left_heat",
                VehicleCommand.CABIN_HVAC_3RD_ROW_REAR_LEFT_SEAT_HEAT,
            ),
            (
                "seat_third_row_right_heat",
                VehicleCommand.CABIN_HVAC_3RD_ROW_REAR_RIGHT_SEAT_HEAT,
            ),
        ],
    )
    def test_description(self, key: str, command: VehicleCommand) -> None:
        matches = [d for d in SELECTS if d.key == key]
        assert len(matches) == 1, key
        description = matches[0]
        assert description.feature == "HEATED_SEATS_THIRD"
        assert description.entity_registry_enabled_default is False
        assert description.options is LEVELS
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.send_vehicle_command = MagicMock()
        description.select(coordinator, LEVEL_MAP["Level_1"])
        coordinator.send_vehicle_command.assert_called_once_with(
            command=command,
            params={"level": int(LEVEL_MAP["Level_1"])},
        )
