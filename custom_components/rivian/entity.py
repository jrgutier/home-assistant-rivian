"""Rivian entities."""

from __future__ import annotations

import logging
from typing import Any, TypeVar

from homeassistant.components.zone import in_zone
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ZONE
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_COORDINATOR, ATTR_USER, DOMAIN
from .coordinator import (
    ChargingCoordinator,
    RivianDataUpdateCoordinator,
    UserCoordinator,
    VehicleCoordinator,
    WallboxCoordinator,
)

_LOGGER = logging.getLogger(__name__)
T = TypeVar("T", bound=RivianDataUpdateCoordinator)


class RivianEntity(CoordinatorEntity[T]):
    """Base class for Rivian entities."""

    _attr_has_entity_name = True


class RivianVehicleEntity(RivianEntity[VehicleCoordinator]):
    """Base class for Rivian vehicle entities."""

    def __init__(
        self,
        coordinator: VehicleCoordinator,
        config_entry: ConfigEntry,
        description: EntityDescription,
        vehicle: dict[str, Any],
    ) -> None:
        """Construct a Rivian vehicle entity."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self.entity_description = description
        self._vin = (vin := vehicle["vin"])
        self._attr_unique_id = f"{vin}-{description.key}"

        self._available = True

        name = vehicle.get("name")
        # The third and widest site. DeviceInfo is built for EVERY platform, so an
        # unguarded vehicle["model"] fails device registration everywhere, not
        # merely in the two entity comprehensions. A device must also always have
        # a name; None is not one, hence the fall through to the VIN.
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
        """Return the availability of the entity."""
        field = getattr(self.entity_description, "field", None)
        if field and self._get_value(field) is None:
            return False
        return self._available

    def _get_value(self, key: str) -> Any | None:
        """Get a data value from the coordinator."""
        return self.coordinator.get(key)


class RivianVehicleControlEntity(RivianVehicleEntity):
    """Base class for Rivian vehicle control entities."""

    def __init__(
        self,
        coordinator: VehicleCoordinator,
        config_entry: ConfigEntry,
        description: EntityDescription,
        vehicle: dict[str, Any],
    ) -> None:
        """Construct a Rivian vehicle control entity."""
        super().__init__(coordinator, config_entry, description, vehicle)
        self._command_in_progress: str | None = None
        self._current_command_id: str | None = None
        self._last_command_id: str | None = None
        self._last_command_status: dict[str, Any] = {}

    @property
    def available(self) -> bool:
        """Return the availability of the entity."""
        # A vehicle that is asleep is not "online", and every control is gated on
        # that -- including the wake button, whose entire job is to bring it back.
        # So from Home Assistant there was no way to wake a sleeping vehicle: the
        # one control that would work was the one guaranteed to be unavailable.
        # Descriptions that set available_offline opt out of this check; they must
        # be commands the cloud accepts while the vehicle sleeps, which WAKE_VEHICLE
        # demonstrably is.
        if not self.coordinator.is_online() and not getattr(
            self.entity_description, "available_offline", False
        ):
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
        """Return entity specific state attributes."""
        # Seeded so both codes are readable before any command. Appending them
        # inside the _last_command_status block leaves them absent until the
        # first send, which is the state f7 has to inspect.
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
        # _last_command_id, NOT _current_command_id: the `finally` of
        # _execute_command clears the latter, and the values below only exist
        # AFTER the call has returned. Gating on _current_command_id makes
        # every one of them permanently read its seed.
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
        timeout: int = 30,
        *,
        _clock=None,
        _sleep=None,
    ) -> dict[str, Any] | None:
        """Execute a vehicle command with state tracking.

        Args:
            command: The VehicleCommand to execute
            params: Optional command parameters
            timeout: Timeout in seconds to wait for the first well-formed frame
            _clock, _sleep: test seams; default to the loop clock and asyncio.sleep

        Returns:
            Command state dict of the first well-formed frame, None on timeout
        """
        import asyncio

        from homeassistant.util import dt as dt_util

        clock = _clock or asyncio.get_event_loop().time
        sleep = _sleep or asyncio.sleep

        # Set executing state
        self._command_in_progress = command.value
        self.async_write_ha_state()

        try:
            # Send command and get ID
            command_id = await self.coordinator.send_vehicle_command(command, params)

            if not command_id:
                _LOGGER.error(
                    "Failed to send command %s, no command ID returned", command
                )
                return None

            self._current_command_id = command_id
            self._last_command_id = command_id

            # Return on the first well-formed frame. _process_command_state
            # refuses to write a record on a malformed payload or a null state,
            # so presence in _command_states is the arrival of a real answer.
            # Terminality is tracked on the coordinator, in the background.
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

            # Timeout reached -- zero well-formed frames
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

        except Exception as ex:  # noqa: BLE001 -- command boundary: failures are surfaced to the caller as None, not raised
            _LOGGER.error("Error executing command %s: %s", command, ex)
            return None
        finally:
            # Clear executing state
            self._command_in_progress = None
            self._current_command_id = None
            self.async_write_ha_state()

    def _handle_driver_update(self) -> None:
        """Handle driver update."""
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
        """When entity is added to hass."""
        self._handle_driver_update()
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.drivers_coordinator.async_add_listener(
                self._handle_driver_update
            )
        )


class RivianChargingEntity(RivianEntity[ChargingCoordinator]):
    """Base class for Rivian charging entities."""

    def __init__(
        self,
        coordinator: ChargingCoordinator,
        description: EntityDescription,
        vin: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self.vin = vin
        self._attr_unique_id = f"{vin}-{description.key}"

        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, vin)})


class RivianWallboxEntity(RivianEntity[WallboxCoordinator]):
    """Base class for Rivian wallbox entities."""

    def __init__(
        self,
        coordinator: WallboxCoordinator,
        description: EntityDescription,
        wallbox: dict[str, Any],
    ) -> None:
        """Construct a Rivian wallbox entity."""
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
        """Handle updated data from the coordinator."""
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
