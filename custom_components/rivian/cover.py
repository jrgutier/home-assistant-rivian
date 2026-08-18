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
from .next_action_states import (
    ChargePortDoorNextActionState,
    FrunkNextActionState,
    LiftgateNextActionState,
    WindowsNextActionState,
)

_LOGGER = logging.getLogger(__name__)

WINDOWS: Final[tuple[str, ...]] = (
    "windowFrontLeftClosed",
    "windowFrontRightClosed",
    "windowRearLeftClosed",
    "windowRearRightClosed",
)

# Map cover keys to their next action state field names and enum classes
NEXT_ACTION_MAPPING: Final[
    dict[
        str,
        tuple[
            str,
            type[
                FrunkNextActionState
                | LiftgateNextActionState
                | ChargePortDoorNextActionState
                | WindowsNextActionState
            ],
        ],
    ]
] = {
    "frunk": ("closureFrunkNextAction", FrunkNextActionState),
    "liftgate": ("closureLiftgateNextAction", LiftgateNextActionState),
    "charge_port": ("closureChargePortDoorNextAction", ChargePortDoorNextActionState),
    "windows": ("windowsNextAction", WindowsNextActionState),
}

COVERS: Final[dict[str | None, tuple[RivianCoverEntityDescription, ...]]] = {
    None: (
        # Unconditional, not gated on the FRUNK_NXT_ACT capability flag: vehicles
        # that do not advertise it would otherwise expose no frunk cover at all.
        # Kept in this fork's style (translation_key + command_*) rather than
        # upstream's (name= + lambdas); NEXT_ACTION_MAPPING is keyed on the entity
        # key, so next-action handling still applies here.
        RivianCoverEntityDescription(
            key="frunk",
            translation_key="frunk",
            device_class=CoverDeviceClass.DOOR,
            is_closed=lambda coor: coor.get("closureFrunkClosed") != "open",
            command_close=VehicleCommand.CLOSE_FRUNK,
            command_open=VehicleCommand.OPEN_FRUNK,
        ),
        RivianCoverEntityDescription(
            key="windows",
            translation_key="windows",
            device_class=CoverDeviceClass.WINDOW,
            is_closed=lambda coor: not any(coor.get(key) == "open" for key in WINDOWS),
            command_close=VehicleCommand.CLOSE_ALL_WINDOWS,
            command_open=VehicleCommand.OPEN_ALL_WINDOWS,
        ),
    ),
    "CHARG_PORT_DOOR_COMMAND": (
        RivianCoverEntityDescription(
            key="charge_port",
            translation_key="charge_port",
            device_class=CoverDeviceClass.DOOR,
            is_closed=lambda coor: coor.get("chargePortState") != "open",
            command_close=VehicleCommand.CLOSE_CHARGE_PORT_DOOR,
            command_open=VehicleCommand.OPEN_CHARGE_PORT_DOOR,
        ),
    ),
    "LIFTGATE_CMD": (
        RivianCoverEntityDescription(
            key="liftgate",
            translation_key="liftgate",
            device_class=CoverDeviceClass.DOOR,
            is_closed=lambda coor: coor.get("closureLiftgateClosed") != "open",
            command_close=VehicleCommand.CLOSE_LIFTGATE,
            command_open=VehicleCommand.OPEN_LIFTGATE_UNLATCH_TAILGATE,
        ),
    ),
    "TONNEAU_CMD": (
        RivianCoverEntityDescription(
            key="tonneau",
            translation_key="tonneau",
            device_class=CoverDeviceClass.DOOR,
            is_closed=lambda coor: coor.get("closureTonneauClosed") != "open",
            command_close=VehicleCommand.CLOSE_TONNEAU_COVER,
            command_open=VehicleCommand.OPEN_TONNEAU_COVER,
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the cover entities."""
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
    """Representation of a Rivian cover entity."""

    entity_description: RivianCoverEntityDescription
    _attr_supported_features = CoverEntityFeature.CLOSE | CoverEntityFeature.OPEN

    def _get_next_action_state(
        self,
    ) -> (
        FrunkNextActionState
        | LiftgateNextActionState
        | ChargePortDoorNextActionState
        | WindowsNextActionState
        | None
    ):
        """Get the next action state enum for this cover."""
        if self.entity_description.key not in NEXT_ACTION_MAPPING:
            return None

        field_name, enum_class = NEXT_ACTION_MAPPING[self.entity_description.key]
        value = self.coordinator.get(field_name)

        if not value:
            return None

        return enum_class.from_api_value(value)

    @property
    def is_closed(self) -> bool:
        """Return if the cover is closed or not."""
        # Try to use next action state first for more accurate status
        next_action = self._get_next_action_state()
        if next_action and hasattr(next_action, "is_closed"):
            return next_action.is_closed()

        # Fall back to the original method
        return self.entity_description.is_closed(self.coordinator)

    @property
    def is_opening(self) -> bool:
        """Return if the cover is opening."""
        next_action = self._get_next_action_state()
        if next_action and hasattr(next_action, "is_opening"):
            return next_action.is_opening()
        return False

    @property
    def is_closing(self) -> bool:
        """Return if the cover is closing."""
        next_action = self._get_next_action_state()
        if next_action and hasattr(next_action, "is_closing"):
            return next_action.is_closing()
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = super().extra_state_attributes or {}

        next_action = self._get_next_action_state()
        if next_action:
            # Add the raw next action state value
            attrs["next_action"] = next_action.value.replace("_", " ").title()

            # Add specific condition flags
            if hasattr(next_action, "is_faulted") and next_action.is_faulted():
                attrs["faulted"] = True

            if hasattr(next_action, "is_obstructed") and next_action.is_obstructed():
                attrs["obstructed"] = True

            if (
                hasattr(next_action, "has_trailer_detected")
                and next_action.has_trailer_detected()
            ):
                attrs["trailer_detected"] = True

            if (
                hasattr(next_action, "has_obstacle_detected")
                and next_action.has_obstacle_detected()
            ):
                attrs["obstacle_detected"] = True

            if (
                hasattr(next_action, "needs_calibration")
                and next_action.needs_calibration()
            ):
                attrs["needs_calibration"] = True

            if (
                hasattr(next_action, "needs_vehicle_angle_confirmation")
                and next_action.needs_vehicle_angle_confirmation()
            ):
                attrs["vehicle_angle_confirmation_needed"] = True

        return attrs

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
