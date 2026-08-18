"""Diagnostics support for Rivian."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import ATTR_COORDINATOR, ATTR_USER, ATTR_VEHICLE, ATTR_WALLBOX, DOMAIN
from .coordinator import UserCoordinator, VehicleCoordinator, WallboxCoordinator
from .helpers import redact
from .rivian_client.parallax import CHARGING_RVMS, PARALLAX_RVMS, RVM_DECODERS


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinators = hass.data[DOMAIN][entry.entry_id][ATTR_COORDINATOR]
    user_coordinator: UserCoordinator = coordinators[ATTR_USER]
    vehicle_coordinators: dict[str, VehicleCoordinator] = coordinators[ATTR_VEHICLE]
    wallbox_coordinator: WallboxCoordinator = coordinators[ATTR_WALLBOX]
    # Parallax now feeds the vehicle and charging coordinators directly rather
    # than a store of its own, so its DATA already appears below. What is not
    # otherwise visible -- and what every diagnosis in this area has needed -- is
    # whether the subscription is actually live and which topics it asked for.
    # The gateway allows one active subscription per user session, so "connected
    # but receiving nothing" is a real and non-obvious state.
    parallax = {
        vehicle_id: {
            "subscribed": coor._unsub_parallax is not None,
            "rvms_requested": sorted({*PARALLAX_RVMS, *CHARGING_RVMS}),
            "rvms_decodable": sorted(RVM_DECODERS),
        }
        for vehicle_id, coor in vehicle_coordinators.items()
    }

    data = {
        "parallax": parallax,
        "user": user_coordinator.data,
        "vehicle": [coor.data for coor in vehicle_coordinators.values()],
        "charging": [
            coor.charging_coordinator.data for coor in vehicle_coordinators.values()
        ],
        "drivers": [
            coor.drivers_coordinator.data for coor in vehicle_coordinators.values()
        ],
        "wallbox": wallbox_coordinator.data,
    }
    return redact(data)
