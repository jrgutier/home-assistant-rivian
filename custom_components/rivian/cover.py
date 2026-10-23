from __future__ import annotations

from typing import Any, Final

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
from .entity import RivianVehicleControlEntity, vehicle_control_enabled
from .helpers import vehicle_supports
from .next_action_states import (
    ChargePortDoorNextActionState,
    FrunkNextActionState,
    LiftgateNextActionState,
    WindowsNextActionState,
)
from .rivian_client import VehicleCommand

WINDOWS: Final[tuple[str, ...]] = (
    "windowFrontLeftClosed",
    "windowFrontRightClosed",
    "windowRearLeftClosed",
    "windowRearRightClosed",
)

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

NEXT_ACTION_CONDITION_FLAGS: Final[tuple[tuple[str, str], ...]] = (
    ("is_faulted", "faulted"),
    ("is_obstructed", "obstructed"),
    ("has_trailer_detected", "trailer_detected"),
    ("has_obstacle_detected", "obstacle_detected"),
    ("needs_calibration", "needs_calibration"),
    ("needs_vehicle_angle_confirmation", "vehicle_angle_confirmation_needed"),
)

COVERS: Final[dict[str | None, tuple[RivianCoverEntityDescription, ...]]] = {
    None: (
        RivianCoverEntityDescription(
            key="frunk",
            translation_key="frunk",
            device_class=CoverDeviceClass.DOOR,
            is_closed=lambda coor: coor.get("closureFrunkClosed") != "open",
            command_close=VehicleCommand.CLOSE_FRUNK,
            command_open=VehicleCommand.OPEN_FRUNK,
        ),
        RivianCoverEntityDescription(
            key="tonneau",
            translation_key="tonneau",
            device_class=CoverDeviceClass.DOOR,
            option_code="TON-P01",
            is_closed=lambda coor: coor.get("closureTonneauClosed") != "open",
            command_close=VehicleCommand.CLOSE_TONNEAU_COVER,
            command_open=VehicleCommand.OPEN_TONNEAU_COVER,
        ),
    ),
    "WINDOWS_CMD": (
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
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data: dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    vehicles: dict[str, dict[str, Any]] = data[ATTR_VEHICLE]
    coordinators: dict[str, VehicleCoordinator] = data[ATTR_COORDINATOR][ATTR_VEHICLE]

    entities = [
        RivianCoverEntity(coordinators[vehicle_id], entry, description, vehicle)
        for vehicle_id, vehicle in vehicles.items()
        if vehicle_control_enabled(vehicle)
        for feature, descriptions in COVERS.items()
        if feature is None or feature in (vehicle.get("supported_features", []))
        for description in descriptions
        if vehicle_supports(description, vehicle)
    ]
    async_add_entities(entities)


class RivianCoverEntity(RivianVehicleControlEntity, CoverEntity):
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
        if self.entity_description.key not in NEXT_ACTION_MAPPING:
            return None

        field_name, enum_class = NEXT_ACTION_MAPPING[self.entity_description.key]
        value = self.coordinator.get(field_name)

        if not value:
            return None

        return enum_class.from_api_value(value)

    @property
    def is_closed(self) -> bool:
        next_action = self._get_next_action_state()
        if next_action and hasattr(next_action, "is_closed"):
            return next_action.is_closed()

        return self.entity_description.is_closed(self.coordinator)

    @property
    def is_opening(self) -> bool:
        next_action = self._get_next_action_state()
        if next_action and hasattr(next_action, "is_opening"):
            return next_action.is_opening()
        return False

    @property
    def is_closing(self) -> bool:
        next_action = self._get_next_action_state()
        if next_action and hasattr(next_action, "is_closing"):
            return next_action.is_closing()
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = super().extra_state_attributes or {}

        next_action = self._get_next_action_state()
        if next_action:
            attrs["next_action"] = next_action.value.replace("_", " ").title()

            for method, attr in NEXT_ACTION_CONDITION_FLAGS:
                if hasattr(next_action, method) and getattr(next_action, method)():
                    attrs[attr] = True

        return attrs

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._run_action(
            self.entity_description.command_close,
            self.entity_description.command_close_params,
            self.entity_description.close_cover,
        )

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._run_action(
            self.entity_description.command_open,
            self.entity_description.command_open_params,
            self.entity_description.open_cover,
        )
