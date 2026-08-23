"""Support for Rivian cover entities."""

from __future__ import annotations

import logging
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
from .entity import RivianVehicleControlEntity
from .next_action_states import (
    ChargePortDoorNextActionState,
    FrunkNextActionState,
    LiftgateNextActionState,
    WindowsNextActionState,
)
from .rivian_client import VehicleCommand

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
        # Gated on the vehicle's option codes, not on TONNEAU_CMD and not on
        # field presence.
        #
        # TONNEAU_CMD (a supportedFeatures flag) appears in NONE of the app's
        # 32,941 decompiled files and in no vehicle's supportedFeatures, so
        # that gate never created this cover for anyone -- while the commands
        # beneath it work: tested live on an R1T, OPEN_TONNEAU_COVER
        # physically opened the cover and CLOSE_TONNEAU_COVER returned it to
        # closed and locked (docs/development/MODEL_SPECIFIC_ENTITIES.md).
        #
        # The replacement for TONNEAU_CMD was `required_field="closureTonneauClosed"`
        # (key presence in `coordinator.data`, not its value) -- s19 removed
        # that too, and this is a live bug fix, not a design tidy-up:
        # closureTonneauClosed is in VEHICLE_STATE_SUBSCRIPTION_FIELDS
        # (const.py), the ONE wire document sent identically to every
        # vehicle, so the key is present in every vehicle's `data` regardless
        # of hardware. Confirmed directly on two real R1S vehicles (no
        # tonneau option exists on any R1S) whose diagnostics both carry
        # `closureTonneauClosed` with an SNA value
        # (docs/development/GATE_FIELD_EVIDENCE.md) -- so this cover was
        # created for R1S and R2 owners who have no tonneau. `option_code`
        # is gated below at TON-P01, the vehicle's actual factory option for
        # a powered tonneau (coordinator.py's `_extract_option_codes()`,
        # from `mobileConfiguration.tonneauOption`), which is what the app
        # itself checks (`java_src/.../UserVehicle.java:616-618`).
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
        # Same shape as the feature check above, and deliberately not a
        # presence-in-`data` check any more: s19 removed `required_field`
        # after finding it created `cover.tonneau` for R1S/R2 owners with no
        # tonneau at all (see RivianCoverEntityDescription's tonneau
        # comment). Membership, not equality -- vehicle_supports()
        # (helpers.py) implements this same containment for
        # `option_code`, but is not called here: wiring a platform over to
        # that predicate is a separate story, and this fix is scoped to the
        # one broken gate.
        if description.option_code is None
        or description.option_code in (vehicle.get("option_codes") or [])
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

    # The command/fallback/else dispatch below is repeated in cover.py, lock.py and
    # switch.py, and the repetition is deliberate. Lifting it onto
    # RivianVehicleControlEntity was built and measured (s25): a 3-argument
    # _dispatch_command helper returning False for "neither defined" came to a NET
    # +7 lines, because the helper costs more than the four lines each call site
    # saves. It also introduces a silent-failure mode this form cannot have -- a
    # caller that forgets to check the return value drops a vehicle command with no
    # log at all. Explicit here beats shared.
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
