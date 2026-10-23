from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from typing import Any, Final, TypeVar

from homeassistant.components.zone import in_zone
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ZONE
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .connectivity import ConnectivityState
from .const import ATTR_COORDINATOR, ATTR_USER, DOMAIN
from .coordinator import (
    SEND_COMMAND_ERRORS,
    ChargingCoordinator,
    RivianDataUpdateCoordinator,
    UserCoordinator,
    VehicleCoordinator,
    WallboxCoordinator,
)
from .rivian_client import VehicleCommand

_LOGGER = logging.getLogger(__name__)
T = TypeVar("T", bound=RivianDataUpdateCoordinator)

COMMAND_TIMEOUT_AWAKE: Final = 60
COMMAND_TIMEOUT_SLEEPING: Final = 120


class RivianEntity(CoordinatorEntity[T]):
    _attr_has_entity_name = True


class RivianVehicleEntity(RivianEntity[VehicleCoordinator]):
    def __init__(
        self,
        coordinator: VehicleCoordinator,
        config_entry: ConfigEntry,
        description: EntityDescription,
        vehicle: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._config_entry = config_entry
        self.entity_description = description
        self._vin = (vin := vehicle["vin"])
        self._attr_unique_id = f"{vin}-{description.key}"

        self._available = True

        name = vehicle.get("name")
        model = vehicle.get("model")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vin), (DOMAIN, vehicle["id"])},
            name=name or model or vin,
            manufacturer="Rivian",
            model=model,
            serial_number=vin,
            sw_version=self._get_value("otaCurrentVersion"),
        )

    @property
    def available(self) -> bool:
        field = getattr(self.entity_description, "field", None)
        if field and self._get_value(field) is None:
            return False
        return self._available

    def _get_value(self, key: str) -> Any | None:
        return self.coordinator.get(key)


class RivianChargingScheduleEntity(RivianVehicleEntity):
    @property
    def available(self) -> bool:
        return self._available


def vehicle_control_enabled(vehicle: dict[str, Any]) -> bool:
    return bool(vehicle.get("phone_identity_id"))


class RivianVehicleControlEntity(RivianVehicleEntity):
    def __init__(
        self,
        coordinator: VehicleCoordinator,
        config_entry: ConfigEntry,
        description: EntityDescription,
        vehicle: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, config_entry, description, vehicle)
        self._command_in_progress: str | None = None
        self._last_command_id: str | None = None
        self._last_command_status: dict[str, Any] = {}

    @property
    def available(self) -> bool:
        if self.coordinator.connectivity_state() is ConnectivityState.OFFLINE:
            return False
        if not (super().available and self._get_value("gearStatus") == "park"):
            return False
        _fn = getattr(self.entity_description, "available", None)
        if _fn and not _fn(self.coordinator):
            return False
        if zone_entity_ids := self._config_entry.options.get(CONF_ZONE, []):
            location = self.coordinator.data.get("gnssLocation", {})
            for entity_id in zone_entity_ids:
                zone = self.hass.states.get(entity_id)
                if in_zone(zone, location.get("latitude"), location.get("longitude")):
                    return True
            return False
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = {
            "response_code": None,
            "status_code": None,
            "state_frames_seen": 0,
            "state_is_lifecycle": None,
            "final_command_state": None,
        }
        if self._command_in_progress:
            attrs["current_command"] = self._command_in_progress
        if self._last_command_status:
            attrs.update(
                {
                    "last_command": self._last_command_status.get("command"),
                    "last_command_state": self._last_command_status.get("state"),
                    "last_command_time": self._last_command_status.get("timestamp"),
                    "response_code": self._last_command_status.get("response_code"),
                    "status_code": self._last_command_status.get("status_code"),
                }
            )
        if self._last_command_id and (
            live := self.coordinator.get_command_state(self._last_command_id)
        ):
            attrs["state_frames_seen"] = live.get("frames_seen", 0)
            attrs["state_is_lifecycle"] = live.get("is_lifecycle")
            attrs["final_command_state"] = live.get("state")
        return attrs

    async def _execute_command(
        self,
        command,
        params: dict[str, Any] | None = None,
        timeout: int | None = None,
        *,
        _clock=None,
        _sleep=None,
    ) -> dict[str, Any] | None:
        import asyncio

        from homeassistant.util import dt as dt_util

        clock = _clock or asyncio.get_event_loop().time
        sleep = _sleep or asyncio.sleep

        if timeout is None:
            timeout = (
                COMMAND_TIMEOUT_SLEEPING
                if self.coordinator.connectivity_state() is ConnectivityState.SLEEPING
                else COMMAND_TIMEOUT_AWAKE
            )

        self._command_in_progress = command.value
        self.async_write_ha_state()

        try:
            command_id = await self.coordinator.send_vehicle_command(command, params)

            if not command_id:
                _LOGGER.error(
                    "Failed to send command %s, no command ID returned", command
                )
                return None

            self._last_command_id = command_id

            start_time = clock()
            while (clock() - start_time) < timeout:
                if cmd_state := self.coordinator.get_command_state(command_id):
                    self._last_command_status = {
                        "command": command.value,
                        "state": cmd_state.get("state"),
                        "timestamp": dt_util.utcnow().isoformat(),
                        "response_code": cmd_state.get("responseCode"),
                        "status_code": cmd_state.get("statusCode"),
                    }
                    return cmd_state

                await sleep(0.5)

            _LOGGER.warning(
                "Command %s (ID: %s) timed out after %s seconds with zero well-formed frames",
                command,
                command_id,
                timeout,
            )
            self._last_command_status = {
                "command": command.value,
                "state": "TIMEOUT",
                "timestamp": dt_util.utcnow().isoformat(),
            }
            return None

        except SEND_COMMAND_ERRORS as ex:
            _LOGGER.error("Error executing command %s: %s", command, ex)
            return None
        finally:
            self._command_in_progress = None
            self.async_write_ha_state()

    async def _run_action(
        self,
        command: VehicleCommand | None,
        params: dict[str, Any] | None,
        fallback: Callable[[VehicleCoordinator], Awaitable[Any]] | None,
    ) -> None:
        if command:
            await self._execute_command(command, params)
        else:
            await fallback(self.coordinator)

    def _handle_driver_update(self) -> None:
        entry_data = self.hass.data[DOMAIN][self._config_entry.entry_id]
        user: UserCoordinator = entry_data[ATTR_COORDINATOR][ATTR_USER]
        phone_info = user.get_enrolled_phone_data(
            self._config_entry.options.get("public_key")
        )
        device = self.coordinator.drivers_coordinator.get_device_details(
            phone_info[1].get(self.coordinator.vehicle_id)
        )
        self._available = device["isPaired"]

    async def async_added_to_hass(self) -> None:
        self._handle_driver_update()
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.drivers_coordinator.async_add_listener(
                self._handle_driver_update
            )
        )


class RivianChargingEntity(RivianEntity[ChargingCoordinator]):
    def __init__(
        self,
        coordinator: ChargingCoordinator,
        description: EntityDescription,
        vin: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self.vin = vin
        self._attr_unique_id = f"{vin}-{description.key}"

        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, vin)})


class RivianWallboxEntity(RivianEntity[WallboxCoordinator]):
    def __init__(
        self,
        coordinator: WallboxCoordinator,
        description: EntityDescription,
        wallbox: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self.wallbox = wallbox

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, wallbox["serialNumber"])},
            name=wallbox["name"],
            manufacturer="Rivian",
            model=wallbox["model"],
            serial_number=wallbox["serialNumber"],
            sw_version=wallbox["softwareVersion"],
        )
        self._attr_unique_id = f"{wallbox['serialNumber']}-{description.key}"

    @callback
    def _handle_coordinator_update(self) -> None:
        wallbox = next(
            (
                wallbox
                for wallbox in self.coordinator.data
                if wallbox["wallboxId"] == self.wallbox["wallboxId"]
            ),
            self.wallbox,
        )
        if self.wallbox != wallbox:
            self.wallbox = wallbox
            self.async_write_ha_state()
