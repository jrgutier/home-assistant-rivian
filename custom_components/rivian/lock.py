"""Support for Rivian lock entities."""

from __future__ import annotations

import logging
from typing import Any, Final

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_COORDINATOR,
    ATTR_VEHICLE,
    DOMAIN,
    INVALID_SENSOR_STATES,
    LOCK_STATE_ENTITIES,
)
from .coordinator import VehicleCoordinator
from .data_classes import RivianLockEntityDescription
from .entity import RivianVehicleControlEntity
from .rivian_client import VehicleCommand

_LOGGER = logging.getLogger(__name__)


def _closures_are_locked(coordinator: VehicleCoordinator) -> bool | None:
    """True if every usable member is locked; False if any is unlocked.

    Invalid members are ignored rather than treated as locked. `not any(v ==
    "unlocked")` over the whole set reports a confident Locked while this
    truck's tailgate, tonneau and right gear tunnel hold
    `signal_not_available` (live 2026-08-19 12:31 CDT). Returning None if any
    member is invalid would make `lock.r1t_closures` unknown here -- MEASURED at
    ~105 s on one of three observed boots (unknown at 12:29:52, off by 12:31:37;
    the 12:41 and 13:10 boots went straight to off). An earlier version of this
    docstring said "permanently", which the recorder does not support. The shape
    still stands: unknown at startup takes the matching control down with the
    sensor. What it does NOT justify is treating the alternative as catastrophic:
    those three are genuine R1T closures, so model-scoping the member set
    does not remove them (const.py:BINARY_SENSORS; "R1" / "R1T").
    None only if no member has a usable value.
    """
    usable = []
    for key in LOCK_STATE_ENTITIES:
        value = coordinator.get(key)
        if value is not None and str(value).lower() not in INVALID_SENSOR_STATES:
            usable.append(value)
    if not usable:
        return None
    return not any(value == "unlocked" for value in usable)


def _closure_coverage(coordinator: VehicleCoordinator) -> tuple[int, int]:
    """(usable members, total members) behind the aggregate.

    The aggregate ignores invalid members, so it can report a confident `locked`
    while a member whose true state is `unlocked` reads `signal_not_available`.
    On this R1T three of ten members read SNA live (2026-08-19), so that is the
    normal case rather than an edge one. Exposing the count lets an automation
    require full coverage before acting on the state; nothing in the integration
    consumes it.
    """
    usable = sum(
        1
        for key in LOCK_STATE_ENTITIES
        if (value := coordinator.get(key)) is not None
        and str(value).lower() not in INVALID_SENSOR_STATES
    )
    return usable, len(LOCK_STATE_ENTITIES)


LOCKS: Final[tuple[RivianLockEntityDescription, ...]] = (
    RivianLockEntityDescription(
        key="closures",
        translation_key="closures",
        is_locked=_closures_are_locked,
        command_lock=VehicleCommand.LOCK_ALL_CLOSURES_FEEDBACK,
        command_unlock=VehicleCommand.UNLOCK_ALL_CLOSURES,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the lock entities."""
    data: dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    vehicles: dict[str, dict[str, Any]] = data[ATTR_VEHICLE]
    coordinators: dict[str, VehicleCoordinator] = data[ATTR_COORDINATOR][ATTR_VEHICLE]

    entities = [
        RivianLockEntity(coordinators[vehicle_id], entry, description, vehicle)
        for vehicle_id, vehicle in vehicles.items()
        if vehicle.get("phone_identity_id")
        for description in LOCKS
    ]
    async_add_entities(entities)


class RivianLockEntity(RivianVehicleControlEntity, LockEntity):
    """Representation of a Rivian lock entity."""

    entity_description: RivianLockEntityDescription

    @property
    def is_locked(self) -> bool | None:
        """Return true if the lock is locked."""
        return self.entity_description.is_locked(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose how much of the closure set the state actually rests on.

        `is_locked` ignores members holding an invalid value, so `locked` can be
        reported while a member that is genuinely unlocked reads
        signal_not_available. An automation acting on this entity cannot
        otherwise tell a full reading from a partial one.
        """
        attrs = dict(super().extra_state_attributes or {})
        if self.entity_description.key == "closures":
            usable, total = _closure_coverage(self.coordinator)
            attrs["usable_closure_count"] = usable
            attrs["total_closure_count"] = total
            attrs["state_is_partial"] = usable < total
        return attrs

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the lock."""
        if self.entity_description.command_lock:
            await self._execute_command(
                self.entity_description.command_lock,
                self.entity_description.command_lock_params,
            )
        elif self.entity_description.lock:
            await self.entity_description.lock(self.coordinator)
        else:
            _LOGGER.error(
                "Lock %s has neither command_lock nor lock defined", self.entity_id
            )

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the lock."""
        if self.entity_description.command_unlock:
            await self._execute_command(
                self.entity_description.command_unlock,
                self.entity_description.command_unlock_params,
            )
        elif self.entity_description.unlock:
            await self.entity_description.unlock(self.coordinator)
        else:
            _LOGGER.error(
                "Lock %s has neither command_unlock nor unlock defined", self.entity_id
            )
