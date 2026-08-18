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

        name = vehicle["name"]
        model = vehicle["model"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vin), (DOMAIN, vehicle["id"])},
            name=name if name else model,
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
        self._last_command_status: dict[str, Any] = {}

    @property
    def available(self) -> bool:
        """Return the availability of the entity."""
        # Check cloud connection first
        if not self.coordinator.is_online():
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
        attrs = {}
        if self._command_in_progress:
            attrs["current_command"] = self._command_in_progress
        if self._last_command_status:
            attrs.update(
                {
                    "last_command": self._last_command_status.get("command"),
                    "last_command_state": self._last_command_status.get("state"),
                    "last_command_time": self._last_command_status.get("timestamp"),
                }
            )
        return attrs

    async def _execute_command(
        self, command, params: dict[str, Any] | None = None, timeout: int = 30
    ) -> dict[str, Any] | None:
        """Execute a vehicle command with state tracking.

        Args:
            command: The VehicleCommand to execute
            params: Optional command parameters
            timeout: Timeout in seconds to wait for command completion

        Returns:
            Command state dict if successful, None otherwise
        """
        import asyncio

        from homeassistant.util import dt as dt_util

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

            # Wait for command completion with timeout
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                # Check command state
                if cmd_state := self.coordinator.get_command_state(command_id):
                    state = cmd_state.get("state")
                    if state in ["COMPLETED_SUCCESS", "COMPLETED_ERROR", "FAILED"]:
                        # Command completed
                        self._last_command_status = {
                            "command": command.value,
                            "state": state,
                            "timestamp": dt_util.utcnow().isoformat(),
                            "response_code": cmd_state.get("responseCode"),
                            "status_code": cmd_state.get("statusCode"),
                        }
                        return cmd_state

                # Wait a bit before checking again
                await asyncio.sleep(0.5)

            # Timeout reached
            _LOGGER.warning(
                "Command %s (ID: %s) timed out after %s seconds",
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
