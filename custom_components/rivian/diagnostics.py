"""Diagnostics support for Rivian."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import ATTR_COORDINATOR, ATTR_USER, ATTR_VEHICLE, ATTR_WALLBOX, DOMAIN
from .coordinator import UserCoordinator, VehicleCoordinator, WallboxCoordinator
from .helpers import redact
from .rivian_client.parallax import CHARGING_RVMS, PARALLAX_RVMS, RVM_DECODERS


def _command_outcomes(coordinator: VehicleCoordinator) -> list[dict[str, Any]]:
    """The in-memory command-state records, for the first bug report.

    TIMEOUT with frames_seen 0 is subscription silence. A malformed payload
    never writes a record and is distinguished by the two log lines in
    _process_command_state. is_lifecycle may be None: an unrecognised frame,
    not a guess at terminality.
    """
    states = getattr(coordinator, "_command_states", None)
    if not isinstance(states, dict):
        return []
    return [
        {
            "command_id": command_id,
            "command": rec.get("command"),
            "first_state": rec.get("first_state"),
            "state": rec.get("state"),
            "frames_seen": rec.get("frames_seen", 0),
            "is_lifecycle": rec.get("is_lifecycle"),
            "terminal_reached": rec.get("terminal_reached", False),
            "time_to_first_frame": rec.get("time_to_first_frame"),
            "time_to_terminal": rec.get("time_to_terminal"),
        }
        for command_id, rec in states.items()
        if isinstance(rec, dict)
    ]


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
        # Per-topic Parallax arrival counts. A topic absent from this map has
        # never delivered, which is what distinguishes "the field was zero and
        # proto3 omitted it" from "the decoder never fired".
        "parallax_rvm_arrivals": {
            vehicle_id: coordinator.rvm_arrivals
            for vehicle_id, coordinator in vehicle_coordinators.items()
        },
        "command_outcomes": {
            vehicle_id: _command_outcomes(coordinator)
            for vehicle_id, coordinator in vehicle_coordinators.items()
        },
    }
    return redact(data)
