"""Support for Rivian notify platform to send navigation destinations."""

from __future__ import annotations

import logging
from typing import Any

from rivian import Rivian
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_API, ATTR_VEHICLE, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Debug: Log rivian library info
try:
    import rivian

    _LOGGER.warning(
        "Rivian library location: %s | Has send_location_to_vehicle: %s",
        rivian.__file__,
        hasattr(Rivian, "send_location_to_vehicle"),
    )
except Exception as err:
    _LOGGER.error("Could not inspect rivian library: %s", err)

# Service schema for navigation service
NAVIGATION_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("message"): cv.string,
    }
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Rivian notify platform from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client: Rivian = entry_data[ATTR_API]
    vehicles: dict[str, dict[str, Any]] = entry_data[ATTR_VEHICLE]

    # Register a notification service for each vehicle
    for vehicle_id, vehicle in vehicles.items():
        vehicle_name = vehicle.get("name", vehicle.get("model", "unknown"))
        vin_suffix = vehicle.get("vin", "")[-6:]
        # Sanitize name for service ID (lowercase, replace spaces with underscores)
        safe_name = vehicle_name.lower().replace(" ", "_")
        service_name = f"rivian_{safe_name}_{vin_suffix}_navigation"

        _LOGGER.debug(
            "Registering notify service for vehicle %s: notify.%s",
            vehicle_name,
            service_name,
        )

        # Create and register the notification service
        notification_service = RivianNotificationService(
            hass=hass,
            client=client,
            vehicle_id=vehicle_id,
            vehicle=vehicle,
            service_name=service_name,
            config_entry=entry,
        )

        # Register the service with Home Assistant with schema
        hass.services.async_register(
            "notify",
            service_name,
            notification_service.async_send_message,
            schema=NAVIGATION_SERVICE_SCHEMA,
        )

        _LOGGER.info(
            "Registered notify service: notify.%s for vehicle %s",
            service_name,
            vehicle_name,
        )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload notify services for this entry."""
    entry_data = hass.data[DOMAIN].get(entry.entry_id)
    if not entry_data:
        return True

    vehicles: dict[str, dict[str, Any]] = entry_data[ATTR_VEHICLE]

    # Remove each vehicle's notification service
    for vehicle_id, vehicle in vehicles.items():
        vehicle_name = vehicle.get("name", vehicle.get("model", "unknown"))
        vin_suffix = vehicle.get("vin", "")[-6:]
        safe_name = vehicle_name.lower().replace(" ", "_")
        service_name = f"rivian_{safe_name}_{vin_suffix}_navigation"

        if hass.services.has_service("notify", service_name):
            hass.services.async_remove("notify", service_name)
            _LOGGER.info("Removed notify service: notify.%s", service_name)

    return True


class RivianNotificationService:
    """Implementation of Rivian notification service for sending navigation destinations."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: Rivian,
        vehicle_id: str,
        vehicle: dict[str, Any],
        service_name: str,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the service."""
        self.hass = hass
        self._client = client
        self._vehicle_id = vehicle_id
        self._vehicle = vehicle
        self._service_name = service_name
        self._config_entry = config_entry

        vehicle_name = vehicle.get("name", vehicle.get("model", "unknown"))
        vin_suffix = vehicle.get("vin", "")[-6:]

        _LOGGER.debug(
            "Created Rivian notification service for vehicle %s (VIN: ...%s): notify.%s",
            vehicle_name,
            vin_suffix,
            self._service_name,
        )

    async def async_send_message(self, call: ServiceCall) -> None:
        """Send a navigation destination to the Rivian vehicle.

        This is called directly as a Home Assistant service.

        Args:
            call: The service call containing the message parameter

        """
        message = call.data.get("message", "")

        if not message:
            _LOGGER.error("No location provided in message")
            return

        try:
            _LOGGER.debug(
                "Sending navigation destination to vehicle %s: %s",
                self._vehicle_id,
                message,
            )

            # Call the Rivian API to send the location
            result = await self._client.send_location_to_vehicle(
                location_str=message,
                vehicle_id=self._vehicle_id,
            )

            # Check result - 0 indicates success
            result_code = result.get("publishResponse", {}).get("result")
            if result_code == 0:
                _LOGGER.info(
                    "Successfully sent navigation destination '%s' to vehicle %s",
                    message,
                    self._vehicle.get("name", self._vehicle_id),
                )
            else:
                _LOGGER.error(
                    "Failed to send navigation destination to vehicle %s. Result code: %s",
                    self._vehicle.get("name", self._vehicle_id),
                    result_code,
                )

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error(
                "Error sending navigation destination to vehicle %s: %s",
                self._vehicle.get("name", self._vehicle_id),
                err,
                exc_info=True,
            )
