from __future__ import annotations

from typing import Any, Final

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from .coordinator import VehicleCoordinator
from .data_classes import RivianSwitchEntityDescription
from .entity import (
    RivianChargingScheduleEntity,
    RivianVehicleControlEntity,
    vehicle_control_enabled,
)
from .rivian_client import VehicleCommand

DEFAULT_CLIMATE_HOLD_MINUTES: Final[int] = 120


SWITCHES: Final[tuple[RivianSwitchEntityDescription, ...]] = (
    RivianSwitchEntityDescription(
        key="alarm",
        translation_key="alarm",
        icon="mdi:alarm-light",
        is_on=lambda coor: {"true": True, "false": False}.get(
            coor.get("alarmSoundStatus")
        ),
        command_off=VehicleCommand.PANIC_OFF,
        command_on=VehicleCommand.PANIC_ON,
    ),
    RivianSwitchEntityDescription(
        key="charging_enabled",
        translation_key="charging_enabled",
        icon="mdi:lightning-bolt",
        available=lambda coor: (
            coor.get("remoteChargingAvailable") == 1
            or coor.get("chargerState") == "charging_active"
        ),
        is_on=lambda coor: (
            coor.get("chargerState") in ("charging_active", "charging_connecting")
        ),
        command_off=VehicleCommand.STOP_CHARGING,
        command_on=VehicleCommand.START_CHARGING,
    ),
    RivianSwitchEntityDescription(
        key="gear_guard_video",
        translation_key="gear_guard_video",
        icon="mdi:cctv",
        is_on=lambda coor: coor.get("gearGuardVideoStatus") != "Disabled",
        command_off=VehicleCommand.DISABLE_GEAR_GUARD_VIDEO,
        command_on=VehicleCommand.ENABLE_GEAR_GUARD_VIDEO,
    ),
    RivianSwitchEntityDescription(
        key="steering_wheel_heat",
        translation_key="steering_wheel_heat",
        icon="mdi:steering",
        is_on=lambda coor: coor.get("steeringWheelHeat") != "Off",
        command_off=VehicleCommand.CABIN_HVAC_STEERING_HEAT,
        command_off_params={"level": 0},
        command_on=VehicleCommand.CABIN_HVAC_STEERING_HEAT,
        command_on_params={"level": 1},
    ),
    RivianSwitchEntityDescription(
        key="cabin_climate_hold",
        translation_key="cabin_climate_hold",
        icon="mdi:hvac",
        is_on=lambda coor: {"on": True, "off": False}.get(
            coor.get("climateHoldStatus")
        ),
        turn_on=lambda coor: coor.async_set_climate_hold(DEFAULT_CLIMATE_HOLD_MINUTES),
        turn_off=lambda coor: coor.async_set_climate_hold(0),
    ),
)


CHARGING_SCHEDULE_ENABLED_SWITCH = RivianSwitchEntityDescription(
    key="charging_schedule_enabled",
    translation_key="charging_schedule_enabled",
    is_on=lambda c: c.charging_schedule.get("enabled", True),
    turn_off=lambda c: c.update_charging_schedule_data({"enabled": False}),
    turn_on=lambda c: c.update_charging_schedule_data({"enabled": True}),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data: dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    vehicles: dict[str, dict[str, Any]] = data[ATTR_VEHICLE]
    coordinators: dict[str, VehicleCoordinator] = data[ATTR_COORDINATOR][ATTR_VEHICLE]

    entities = [
        RivianSwitchEntity(coordinators[vehicle_id], entry, description, vehicle)
        for vehicle_id, vehicle in vehicles.items()
        if vehicle_control_enabled(vehicle)
        for description in SWITCHES
    ]

    for vehicle_id, vehicle in vehicles.items():
        entities.append(
            RivianChargingScheduleEnabledEntity(
                coordinators[vehicle_id],
                entry,
                CHARGING_SCHEDULE_ENABLED_SWITCH,
                vehicle,
            )
        )

    async_add_entities(entities)


class RivianChargingScheduleEnabledEntity(RivianChargingScheduleEntity, SwitchEntity):
    entity_description: RivianSwitchEntityDescription

    @property
    def is_on(self) -> bool:
        return self.entity_description.is_on(self.coordinator)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.entity_description.turn_on(self.coordinator)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.entity_description.turn_off(self.coordinator)


class RivianSwitchEntity(RivianVehicleControlEntity, SwitchEntity):
    entity_description: RivianSwitchEntityDescription

    @property
    def is_on(self) -> bool:
        return self.entity_description.is_on(self.coordinator)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._run_action(
            self.entity_description.command_off,
            self.entity_description.command_off_params,
            self.entity_description.turn_off,
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._run_action(
            self.entity_description.command_on,
            self.entity_description.command_on_params,
            self.entity_description.turn_on,
        )
