"""Support for Rivian number entities."""

from __future__ import annotations

import logging
from typing import Any, Final

from rivian import VehicleCommand

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from .coordinator import VehicleCoordinator
from .data_classes import RivianNumberEntityDescription
from .entity import RivianVehicleControlEntity

_LOGGER = logging.getLogger(__name__)


NUMBERS: Final[tuple[RivianNumberEntityDescription, ...]] = (
    RivianNumberEntityDescription(
        key="battery_limit",
        translation_key="battery_limit",
        device_class=NumberDeviceClass.BATTERY,
        icon="mdi:battery-charging-70",
        native_min_value=50,
        native_unit_of_measurement=PERCENTAGE,
        field="batteryLimit",
        set_fn=lambda coordinator, value: coordinator.send_vehicle_command(
            command=VehicleCommand.CHARGING_LIMITS, params={"SOC_limit": int(value)}
        ),
    ),
)

PARALLAX_NUMBERS: Final[tuple[RivianNumberEntityDescription, ...]] = (
    RivianNumberEntityDescription(
        key="halloween_brightness",
        translation_key="halloween_brightness",
        icon="mdi:brightness-percent",
        native_min_value=0,
        native_max_value=100,
        native_step=10,
        native_unit_of_measurement=PERCENTAGE,
        field="",  # Write-only, no state field
        set_fn=lambda coordinator, value: coordinator.send_parallax_command(
            "set_halloween_settings", enabled=True, brightness=int(value)
        ),
    ),
    RivianNumberEntityDescription(
        key="cabin_ventilation_windows",
        translation_key="cabin_ventilation_windows",
        icon="mdi:car-door",
        native_min_value=0,
        native_max_value=100,
        native_step=25,
        native_unit_of_measurement=PERCENTAGE,
        field="",  # Write-only
        set_fn=lambda coordinator, value: coordinator.send_parallax_command(
            "set_cabin_ventilation", enabled=True, windows_open_percent=int(value)
        ),
    ),
    RivianNumberEntityDescription(
        key="cabin_ventilation_sunroof",
        translation_key="cabin_ventilation_sunroof",
        icon="mdi:car-convertible",
        native_min_value=0,
        native_max_value=100,
        native_step=25,
        native_unit_of_measurement=PERCENTAGE,
        field="",  # Write-only
        set_fn=lambda coordinator, value: coordinator.send_parallax_command(
            "set_cabin_ventilation", enabled=True, sunroof_open_percent=int(value)
        ),
    ),
    RivianNumberEntityDescription(
        key="cabin_ventilation_duration",
        translation_key="cabin_ventilation_duration",
        icon="mdi:timer",
        native_min_value=1,
        native_max_value=60,
        native_step=1,
        native_unit_of_measurement="min",
        field="",  # Write-only
        set_fn=lambda coordinator, value: coordinator.send_parallax_command(
            "set_cabin_ventilation", enabled=True, duration_minutes=int(value)
        ),
    ),
    RivianNumberEntityDescription(
        key="passive_entry_distance",
        translation_key="passive_entry_distance",
        icon="mdi:map-marker-distance",
        native_min_value=1.0,
        native_max_value=10.0,
        native_step=0.5,
        native_unit_of_measurement=UnitOfLength.METERS,
        field="",  # Write-only
        set_fn=lambda coordinator, value: coordinator.send_parallax_command(
            "set_passive_entry_settings",
            enabled=True,
            approach_distance_meters=float(value),
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the number entities"""
    data: dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    vehicles: dict[str, dict[str, Any]] = data[ATTR_VEHICLE]
    coordinators: dict[str, VehicleCoordinator] = data[ATTR_COORDINATOR][ATTR_VEHICLE]

    entities = [
        RivianNumberEntity(coordinators[vehicle_id], entry, description, vehicle)
        for vehicle_id, vehicle in vehicles.items()
        if vehicle.get("phone_identity_id")
        for description in NUMBERS
    ]

    # Add Parallax number entities (require pairing)
    parallax_entities = [
        RivianNumberEntity(coordinators[vehicle_id], entry, description, vehicle)
        for vehicle_id, vehicle in vehicles.items()
        if vehicle.get("phone_identity_id")
        for description in PARALLAX_NUMBERS
    ]

    async_add_entities(entities + parallax_entities)


class RivianNumberEntity(RivianVehicleControlEntity, NumberEntity):
    """Representation of a Rivian number entity."""

    entity_description: RivianNumberEntityDescription

    @property
    def native_value(self) -> str | None:
        """Return the value reported by the number."""
        return self._get_value(self.entity_description.field)

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        await self.entity_description.set_fn(self.coordinator, value)
