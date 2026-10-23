from __future__ import annotations

from typing import Any, Final

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_COORDINATOR,
    ATTR_VEHICLE,
    DOMAIN,
    LOCK_STATE_ENTITIES,
    is_invalid_state,
)
from .coordinator import VehicleCoordinator
from .data_classes import RivianLockEntityDescription
from .entity import RivianVehicleControlEntity, vehicle_control_enabled
from .rivian_client import VehicleCommand


def _usable_closure_values(coordinator: VehicleCoordinator) -> list[Any]:
    return [
        value
        for key in LOCK_STATE_ENTITIES
        if (value := coordinator.get(key)) is not None and not is_invalid_state(value)
    ]


def _closures_are_locked(coordinator: VehicleCoordinator) -> bool | None:
    usable = _usable_closure_values(coordinator)
    if not usable:
        return None
    return not any(value == "unlocked" for value in usable)


def _closure_coverage(coordinator: VehicleCoordinator) -> tuple[int, int]:
    return len(_usable_closure_values(coordinator)), len(LOCK_STATE_ENTITIES)


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
    data: dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    vehicles: dict[str, dict[str, Any]] = data[ATTR_VEHICLE]
    coordinators: dict[str, VehicleCoordinator] = data[ATTR_COORDINATOR][ATTR_VEHICLE]

    entities = [
        RivianLockEntity(coordinators[vehicle_id], entry, description, vehicle)
        for vehicle_id, vehicle in vehicles.items()
        if vehicle_control_enabled(vehicle)
        for description in LOCKS
    ]
    async_add_entities(entities)


class RivianLockEntity(RivianVehicleControlEntity, LockEntity):
    entity_description: RivianLockEntityDescription

    @property
    def is_locked(self) -> bool | None:
        return self.entity_description.is_locked(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = dict(super().extra_state_attributes or {})
        if self.entity_description.key == "closures":
            usable, total = _closure_coverage(self.coordinator)
            attrs["usable_closure_count"] = usable
            attrs["total_closure_count"] = total
            attrs["state_is_partial"] = usable < total
        return attrs

    async def async_lock(self, **kwargs: Any) -> None:
        await self._run_action(
            self.entity_description.command_lock,
            self.entity_description.command_lock_params,
            self.entity_description.lock,
        )

    async def async_unlock(self, **kwargs: Any) -> None:
        await self._run_action(
            self.entity_description.command_unlock,
            self.entity_description.command_unlock_params,
            self.entity_description.unlock,
        )
