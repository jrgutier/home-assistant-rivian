"""Support for Rivian select entities."""

from __future__ import annotations

import logging
from typing import Any, Final

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from .coordinator import VehicleCoordinator
from .data_classes import RivianSelectEntityDescription
from .entity import RivianVehicleControlEntity
from .rivian_client import VehicleCommand

_LOGGER = logging.getLogger(__name__)

LEVEL_MAP = {"Off": "0", "On": "1", "Level_1": "2", "Level_2": "3", "Level_3": "4"}
LEVELS = ["Off", "Level_1", "Level_2", "Level_3"]
SEAT_CLIMATE_OPTIONS = [
    "Off",
    "Heat Level 1",
    "Heat Level 2",
    "Heat Level 3",
    "Cool Level 1",
    "Cool Level 2",
    "Cool Level 3",
]


# Mapping for combined seat heat/cool controls
# Maps option names to (command, level) tuples
def get_seat_command_and_level(
    option: str, is_left_seat: bool
) -> tuple[VehicleCommand, int]:
    """Get the appropriate command and level for a seat climate option."""
    heat_command = (
        VehicleCommand.CABIN_HVAC_LEFT_SEAT_HEAT
        if is_left_seat
        else VehicleCommand.CABIN_HVAC_RIGHT_SEAT_HEAT
    )
    cool_command = (
        VehicleCommand.CABIN_HVAC_LEFT_SEAT_VENT
        if is_left_seat
        else VehicleCommand.CABIN_HVAC_RIGHT_SEAT_VENT
    )

    option_map = {
        "Off": (heat_command, 0),  # Can use either command for off
        "Heat Level 1": (heat_command, 2),
        "Heat Level 2": (heat_command, 3),
        "Heat Level 3": (heat_command, 4),
        "Cool Level 1": (cool_command, 2),
        "Cool Level 2": (cool_command, 3),
        "Cool Level 3": (cool_command, 4),
    }
    return option_map[option]


SELECTS: Final[tuple[RivianSelectEntityDescription, ...]] = (
    RivianSelectEntityDescription(
        key="seat_rear_left_heat",
        translation_key="seat_rear_left_heat",
        icon="mdi:car-seat-heater",
        options=LEVELS,
        field="seatRearLeftHeat",
        select=lambda coordinator, option: coordinator.send_vehicle_command(
            command=VehicleCommand.CABIN_HVAC_REAR_LEFT_SEAT_HEAT,
            params={"level": int(option)},
        ),
    ),
    RivianSelectEntityDescription(
        key="seat_rear_right_heat",
        translation_key="seat_rear_right_heat",
        icon="mdi:car-seat-heater",
        options=LEVELS,
        field="seatRearRightHeat",
        select=lambda coordinator, option: coordinator.send_vehicle_command(
            command=VehicleCommand.CABIN_HVAC_REAR_RIGHT_SEAT_HEAT,
            params={"level": int(option)},
        ),
    ),
)


# Front seat combined heat/cool entities use a custom entity class
FRONT_SEAT_SELECTS: Final[list[dict[str, Any]]] = [
    {
        "key": "seat_front_left_heat_vent",
        "translation_key": "seat_front_left_heat_vent",
        "heat_field": "seatFrontLeftHeat",
        "cool_field": "seatFrontLeftVent",
        "is_left": True,
    },
    {
        "key": "seat_front_right_heat_vent",
        "translation_key": "seat_front_right_heat_vent",
        "heat_field": "seatFrontRightHeat",
        "cool_field": "seatFrontRightVent",
        "is_left": False,
    },
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the select entities."""
    data: dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    vehicles: dict[str, dict[str, Any]] = data[ATTR_VEHICLE]
    coordinators: dict[str, VehicleCoordinator] = data[ATTR_COORDINATOR][ATTR_VEHICLE]

    entities = []

    # Add regular select entities (rear seats)
    entities.extend(
        [
            RivianSelectEntity(coordinators[vehicle_id], entry, description, vehicle)
            for vehicle_id, vehicle in vehicles.items()
            if vehicle.get("phone_identity_id")
            for description in SELECTS
        ]
    )

    # Add front seat combined heat/cool entities
    entities.extend(
        [
            RivianFrontSeatSelectEntity(
                coordinators[vehicle_id],
                entry,
                vehicle,
                seat_config,
            )
            for vehicle_id, vehicle in vehicles.items()
            if vehicle.get("phone_identity_id")
            for seat_config in FRONT_SEAT_SELECTS
        ]
    )

    async_add_entities(entities)


class RivianSelectEntity(RivianVehicleControlEntity, SelectEntity):
    """Representation of a Rivian select entity."""

    entity_description: RivianSelectEntityDescription

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        return self._get_value(self.entity_description.field)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.entity_description.select(self.coordinator, LEVEL_MAP[option])


class RivianFrontSeatSelectEntity(RivianVehicleControlEntity, SelectEntity):
    """Representation of a Rivian front seat combined heat/cool select entity."""

    _attr_options = SEAT_CLIMATE_OPTIONS

    def __init__(
        self,
        coordinator: VehicleCoordinator,
        entry: ConfigEntry,
        vehicle: dict[str, Any],
        seat_config: dict[str, Any],
    ) -> None:
        """Initialize the front seat select entity."""
        self._heat_field = seat_config["heat_field"]
        self._cool_field = seat_config["cool_field"]
        self._is_left = seat_config["is_left"]

        # Create a minimal entity description for the parent class
        description = SelectEntityDescription(
            key=seat_config["key"],
            translation_key=seat_config.get("translation_key"),
        )

        super().__init__(coordinator, entry, description, vehicle)

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        heat_value = self._get_value(self._heat_field)
        cool_value = self._get_value(self._cool_field)

        # Map level values to option names
        # "Off", "Level_1", "Level_2", "Level_3"
        level_to_option = {
            "Level_1": "1",
            "Level_2": "2",
            "Level_3": "3",
        }

        # Check if heat is active
        if heat_value and heat_value != "Off":
            level = level_to_option.get(heat_value)
            if level:
                return f"Heat Level {level}"

        # Check if cool is active
        if cool_value and cool_value != "Off":
            level = level_to_option.get(cool_value)
            if level:
                return f"Cool Level {level}"

        # Default to Off
        return "Off"

    @property
    def icon(self) -> str:
        """Return dynamic icon based on current state."""
        current = self.current_option
        if current and current.startswith("Heat"):
            return "mdi:car-seat-heater"
        elif current and current.startswith("Cool"):
            return "mdi:car-seat-cooler"
        else:
            return "mdi:car-seat"

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        command, level = get_seat_command_and_level(option, self._is_left)
        await self.coordinator.send_vehicle_command(
            command=command,
            params={"level": level},
        )
