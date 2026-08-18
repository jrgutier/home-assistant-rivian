"""Support for Rivian number entities."""

from __future__ import annotations

import logging
from typing import Any, Final

from rivian import VehicleCommand

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfElectricCurrent, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_COORDINATOR,
    ATTR_VEHICLE,
    CHARGING_SCHEDULE_AMPERAGE_MAXIMUM,
    CHARGING_SCHEDULE_AMPERAGE_MINIMUM,
    CHARGING_SCHEDULE_AMPERAGE_STEP,
    DEFAULT_CHARGING_SCHEDULE_AMPERAGE,
    DOMAIN,
)
from .coordinator import VehicleCoordinator
from .data_classes import RivianNumberEntityDescription
from .entity import RivianVehicleControlEntity, RivianVehicleEntity

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
        field="parallax.halloween.brightness",
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
        field="parallax.cabin_ventilation.windows_open_percent",
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
        field="parallax.cabin_ventilation.sunroof_open_percent",
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
        field="parallax.cabin_ventilation.duration_minutes",
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
        field="parallax.passive_entry_setting.approach_distance_meters",
        set_fn=lambda coordinator, value: coordinator.send_parallax_command(
            "set_passive_entry_settings",
            enabled=True,
            approach_distance_meters=float(value),
        ),
    ),
)

CHARGING_SCHEDULE_AMPERAGE_NUMBER = RivianNumberEntityDescription(
    key="charging_schedule_amperage",
    translation_key="charging_schedule_amperage",
    device_class=NumberDeviceClass.CURRENT,
    native_min_value=CHARGING_SCHEDULE_AMPERAGE_MINIMUM,
    native_max_value=CHARGING_SCHEDULE_AMPERAGE_MAXIMUM,
    native_step=CHARGING_SCHEDULE_AMPERAGE_STEP,
    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    field="charging_schedule_amperage",
    set_fn=lambda c, v: c.update_charging_schedule_data({"amperage": int(v)}),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the number entities."""
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

    # Upstream 1.5.3b5: charging-schedule amperage, one per vehicle, no pairing.
    for vehicle_id, vehicle in vehicles.items():
        entities.append(
            RivianChargingScheduleAmperageEntity(
                coordinators[vehicle_id],
                entry,
                CHARGING_SCHEDULE_AMPERAGE_NUMBER,
                vehicle,
            )
        )

    async_add_entities(entities + parallax_entities)


class RivianChargingScheduleAmperageEntity(RivianVehicleEntity, NumberEntity):
    """Charging Schedule Amperage Entity."""

    entity_description: RivianNumberEntityDescription

    @property
    def available(self) -> bool:
        """Return availability."""
        return self._available

    @property
    def native_value(self) -> int | None:
        """Return native value."""
        sched = self.coordinator.charging_schedule
        val = sched.get("amperage", DEFAULT_CHARGING_SCHEDULE_AMPERAGE)
        return int(val) if val is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        await self.entity_description.set_fn(self.coordinator, value)


class RivianNumberEntity(RivianVehicleControlEntity, NumberEntity):
    """Representation of a Rivian number entity."""

    entity_description: RivianNumberEntityDescription

    def _get_value(self, key: str) -> Any | None:
        """Get a data value from the coordinator.

        Routes parallax.* keys to ParallaxCoordinator.
        """
        if key.startswith("parallax."):
            # Route to ParallaxCoordinator (remove "parallax." prefix)
            parallax_key = key[9:]
            return self.coordinator.parallax_coordinator.get(parallax_key)
        return self.coordinator.get(key)

    @property
    def native_value(self) -> float | None:
        """Return the value reported by the number."""
        return self._get_value(self.entity_description.field)

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        await self.entity_description.set_fn(self.coordinator, value)
