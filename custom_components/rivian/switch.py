"""Support for Rivian switch entities."""

from __future__ import annotations

import logging
from typing import Any, Final

from rivian import VehicleCommand

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from .coordinator import VehicleCoordinator
from .data_classes import RivianSwitchEntityDescription
from .entity import RivianVehicleControlEntity, RivianVehicleEntity

_LOGGER = logging.getLogger(__name__)


SWITCHES: Final[tuple[RivianSwitchEntityDescription, ...]] = (
    RivianSwitchEntityDescription(
        key="alarm",
        translation_key="alarm",
        icon="mdi:alarm-light",
        is_on=lambda coor: coor.get("alarmSoundStatus") == "true",
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
    # NOTE: Climate Hold requires Rivian software 2025.38+ and rivian-python-client
    # with CLIMATE_HOLD_ON/CLIMATE_HOLD_OFF commands. If these commands are not available
    # in the installed rivian-python-client version, this switch will fail to operate.
    # State fields (cabinHoldStatus, cabinHoldNotification) are confirmed in GraphQL subscription.
    # Duration is controlled by the vehicle firmware and cannot be set via the mobile app API.
    RivianSwitchEntityDescription(
        key="cabin_climate_hold",
        translation_key="cabin_climate_hold",
        icon="mdi:hvac",
        is_on=lambda coor: coor.get("cabinHoldStatus") in ("on", "ON", "On"),
        command_off=VehicleCommand.CLIMATE_HOLD_OFF,
        command_on=VehicleCommand.CLIMATE_HOLD_ON,
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
    """Set up the switch entities."""
    data: dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    vehicles: dict[str, dict[str, Any]] = data[ATTR_VEHICLE]
    coordinators: dict[str, VehicleCoordinator] = data[ATTR_COORDINATOR][ATTR_VEHICLE]

    entities = [
        RivianSwitchEntity(coordinators[vehicle_id], entry, description, vehicle)
        for vehicle_id, vehicle in vehicles.items()
        if vehicle.get("phone_identity_id")
        for description in SWITCHES
    ]

    # Upstream 1.5.3b5: one charging-schedule switch per vehicle, no pairing needed.
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


class RivianChargingScheduleEnabledEntity(RivianVehicleEntity, SwitchEntity):
    """Charging Schedule Enabled Entity."""

    entity_description: RivianSwitchEntityDescription

    @property
    def available(self) -> bool:
        """Return availability."""
        return self._available

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        return self.entity_description.is_on(self.coordinator)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        await self.entity_description.turn_on(self.coordinator)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self.entity_description.turn_off(self.coordinator)


class RivianSwitchEntity(RivianVehicleControlEntity, SwitchEntity):
    """Representation of a Rivian switch entity."""

    entity_description: RivianSwitchEntityDescription

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        return self.entity_description.is_on(self.coordinator)

    @property
    def available(self) -> bool:
        """Return the availability of the entity."""
        return super().available and (
            _fn(self.coordinator)
            if (_fn := self.entity_description.available)
            else True
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        if self.entity_description.command_off:
            await self._execute_command(
                self.entity_description.command_off,
                self.entity_description.command_off_params,
            )
        elif self.entity_description.turn_off:
            await self.entity_description.turn_off(self.coordinator)
        else:
            _LOGGER.error(
                "Switch %s has neither command_off nor turn_off defined", self.entity_id
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        if self.entity_description.command_on:
            await self._execute_command(
                self.entity_description.command_on,
                self.entity_description.command_on_params,
            )
        elif self.entity_description.turn_on:
            await self.entity_description.turn_on(self.coordinator)
        else:
            _LOGGER.error(
                "Switch %s has neither command_on nor turn_on defined", self.entity_id
            )
