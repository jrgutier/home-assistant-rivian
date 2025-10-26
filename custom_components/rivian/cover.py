"""Support for Rivian cover entities."""

from __future__ import annotations

import logging
from typing import Any, Final

from rivian import VehicleCommand

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from .coordinator import VehicleCoordinator
from .data_classes import RivianCoverEntityDescription
from .entity import RivianVehicleControlEntity

_LOGGER = logging.getLogger(__name__)

WINDOWS: Final[tuple[str, ...]] = (
    "windowFrontLeftClosed",
    "windowFrontRightClosed",
    "windowRearLeftClosed",
    "windowRearRightClosed",
)

COVERS: Final[dict[str | None, tuple[RivianCoverEntityDescription, ...]]] = {
    None: (
        RivianCoverEntityDescription(
            key="windows",
            device_class=CoverDeviceClass.WINDOW,
            name="Windows",
            is_closed=lambda coor: not any(coor.get(key) == "open" for key in WINDOWS),
            command_close=VehicleCommand.CLOSE_ALL_WINDOWS,
            command_open=VehicleCommand.OPEN_ALL_WINDOWS,
        ),
    ),
    "CHARG_PORT_DOOR_COMMAND": (
        RivianCoverEntityDescription(
            key="charge_port",
            device_class=CoverDeviceClass.DOOR,
            translation_key="charge_port",
            is_closed=lambda coor: coor.get("chargePortState") != "open",
            command_close=VehicleCommand.CLOSE_CHARGE_PORT_DOOR,
            command_open=VehicleCommand.OPEN_CHARGE_PORT_DOOR,
        ),
    ),
    "LIFTGATE_CMD": (
        RivianCoverEntityDescription(
            key="liftgate",
            device_class=CoverDeviceClass.DOOR,
            name="Liftgate",
            is_closed=lambda coor: coor.get("closureLiftgateClosed") != "open",
            command_close=VehicleCommand.CLOSE_LIFTGATE,
            command_open=VehicleCommand.OPEN_LIFTGATE_UNLATCH_TAILGATE,
        ),
    ),
    "FRUNK_NXT_ACT": (
        RivianCoverEntityDescription(
            key="frunk",
            device_class=CoverDeviceClass.DOOR,
            name="Front Trunk",
            is_closed=lambda coor: coor.get("closureFrunkClosed") != "open",
            command_close=VehicleCommand.CLOSE_FRUNK,
            command_open=VehicleCommand.OPEN_FRUNK,
        ),
    ),
    "TONNEAU_CMD": (
        RivianCoverEntityDescription(
            key="tonneau",
            device_class=CoverDeviceClass.DOOR,
            name="Tonneau",
            is_closed=lambda coor: coor.get("closureTonneauClosed") != "open",
            command_close=VehicleCommand.CLOSE_TONNEAU_COVER,
            command_open=VehicleCommand.OPEN_TONNEAU_COVER,
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor entities"""
    data: dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    vehicles: dict[str, dict[str, Any]] = data[ATTR_VEHICLE]
    coordinators: dict[str, VehicleCoordinator] = data[ATTR_COORDINATOR][ATTR_VEHICLE]

    entities = [
        RivianCoverEntity(coordinators[vehicle_id], entry, description, vehicle)
        for vehicle_id, vehicle in vehicles.items()
        if vehicle.get("phone_identity_id")
        for feature, descriptions in COVERS.items()
        if feature is None or feature in (vehicle.get("supported_features", []))
        for description in descriptions
    ]
    async_add_entities(entities)


class RivianCoverEntity(RivianVehicleControlEntity, CoverEntity):
    """Representation of a Rivian sensor entity."""

    entity_description: RivianCoverEntityDescription
    _attr_supported_features = CoverEntityFeature.CLOSE | CoverEntityFeature.OPEN

    @property
    def is_closed(self) -> bool:
        """Return if the cover is closed or not."""
        return self.entity_description.is_closed(self.coordinator)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        if self.entity_description.command_close:
            await self._execute_command(
                self.entity_description.command_close,
                self.entity_description.command_close_params,
            )
        elif self.entity_description.close_cover:
            await self.entity_description.close_cover(self.coordinator)
        else:
            _LOGGER.error(
                "Cover %s has neither command_close nor close_cover defined",
                self.entity_id,
            )

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        if self.entity_description.command_open:
            await self._execute_command(
                self.entity_description.command_open,
                self.entity_description.command_open_params,
            )
        elif self.entity_description.open_cover:
            await self.entity_description.open_cover(self.coordinator)
        else:
            _LOGGER.error(
                "Cover %s has neither command_open nor open_cover defined",
                self.entity_id,
            )
