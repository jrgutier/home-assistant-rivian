from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_COORDINATOR,
    ATTR_VEHICLE,
    BINARY_SENSORS,
    DOMAIN,
    is_invalid_state,
)
from .coordinator import VehicleCoordinator
from .data_classes import RivianBinarySensorEntityDescription
from .entity import RivianVehicleEntity
from .helpers import vehicle_supports


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data: dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    vehicles: dict[str, Any] = data[ATTR_VEHICLE]
    coordinators: dict[str, VehicleCoordinator] = data[ATTR_COORDINATOR][ATTR_VEHICLE]

    entities = [
        RivianBinarySensorEntity(coordinators[vehicle_id], entry, description, vehicle)
        for vehicle_id, vehicle in vehicles.items()
        for description in BINARY_SENSORS
        if vehicle_supports(description, vehicle)
    ]

    entities.extend(
        [
            RivianCloudConnectionBinarySensor(coordinators[vehicle_id], entry, vehicle)
            for vehicle_id, vehicle in vehicles.items()
        ]
    )

    async_add_entities(entities)


class RivianBinarySensorEntity(RivianVehicleEntity, BinarySensorEntity):
    entity_description: RivianBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: VehicleCoordinator,
        config_entry: ConfigEntry,
        description: RivianBinarySensorEntityDescription,
        vehicle: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, config_entry, description, vehicle)
        self._aggregate = isinstance(self.entity_description.field, set)

    @property
    def available(self) -> bool:
        if self._aggregate:
            return self._available and any(
                self._get_value(entity_key)
                for entity_key in self.entity_description.field
            )
        return super().available

    @property
    def is_on(self) -> bool | None:
        fields = self.entity_description.field
        if self._aggregate:
            values = self.entity_description.on_values
            return any(self._get_value(entity_key) in values for entity_key in fields)
        if (val := self._get_value(fields)) is not None:
            if is_invalid_state(val):
                return None
            result = val in self.entity_description.on_values
            return result if not self.entity_description.negate else not result
        return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        if self._aggregate:
            return None
        try:
            entity = self.coordinator.data[self.entity_description.field]
            if entity is None:
                return None
            return {
                "value": entity["value"],
                "last_update": entity["timeStamp"],
                "history": str(entity["history"]),
            }
        except KeyError:
            return None


class RivianCloudConnectionBinarySensor(RivianVehicleEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        coordinator: VehicleCoordinator,
        config_entry: ConfigEntry,
        vehicle: dict[str, Any],
    ) -> None:
        from homeassistant.helpers.entity import EntityDescription

        description = EntityDescription(
            key="cloud_connected",
            name="Cloud Connected",
        )
        super().__init__(coordinator, config_entry, description, vehicle)

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.is_online())

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        return {
            "last_sync": self.coordinator.last_sync(),
        }
