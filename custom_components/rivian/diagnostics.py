"""Diagnostics support for Rivian."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    ATTR_COORDINATOR,
    ATTR_USER,
    ATTR_VEHICLE,
    ATTR_WALLBOX,
    DOMAIN,
    VEHICLE_STATE_SUBSCRIPTION_FIELDS,
)
from .coordinator import UserCoordinator, VehicleCoordinator, WallboxCoordinator
from .helpers import redact
from .rivian_client.parallax import CHARGING_RVMS, PARALLAX_RVMS, RVM_DECODERS

# Every read below is via getattr(..., default) rather than a bare attribute
# access. Diagnostics must never crash the download, and several test
# fixtures are MagicMock(spec=VehicleCoordinator) instances that never run
# __init__ -- a spec'd mock raises AttributeError on the first read of an
# attribute nobody has explicitly set on it yet, which a bare `coor.x` would
# hit immediately.


def _subscription_diagnostics(
    coor: VehicleCoordinator, vehicle_id: str
) -> dict[str, Any]:
    """§G, non-gating half: which vehicleState document is live and what it
    is missing.

    `document` is read from the client via subscription_document(), never
    inferred: None means "never subscribed" and must not collapse into
    "core" -- a never-connected vehicle would otherwise read as merely
    degraded rather than dead (S1).
    """
    document: str | None = None
    if (api := getattr(coor, "api", None)) is not None:
        try:
            document = api.subscription_document(vehicle_id)
        except Exception:  # noqa: BLE001 -- diagnostics must never raise
            document = None

    subscription_keys: set[str] = getattr(coor, "_subscription_keys", None) or set()
    initial = getattr(coor, "_initial", None)
    # Suppressed until the main stream's first frame lands, or every one of
    # the 137 names would be listed as "never delivered" on every boot before
    # the first frame -- indistinguishable from a genuinely dropped field.
    fields_never_delivered = (
        sorted(VEHICLE_STATE_SUBSCRIPTION_FIELDS - subscription_keys)
        if initial is not None and initial.is_set()
        else []
    )
    return {
        "document": document,
        "requested_field_count": len(VEHICLE_STATE_SUBSCRIPTION_FIELDS),
        "accepted": document is not None,
        "last_document_error": getattr(coor, "_last_document_error", None),
        "fields_never_delivered": fields_never_delivered,
    }


def _tire_pressure_diagnostics(coor: VehicleCoordinator) -> dict[str, Any]:
    """The TPMS stream's own liveness (S4) -- separate from the main
    subscription's watchdog block below, because its liveness clock is."""
    last = getattr(coor, "_tpms_last_update_time", None)
    return {
        "subscribed": getattr(coor, "_unsub_tire_pressure", None) is not None,
        "last_frame_age": (
            (datetime.now(timezone.utc) - last).total_seconds() if last else None
        ),
        "frames_seen": getattr(coor, "_tpms_frames_seen", 0),
    }


def _watchdog_diagnostics(coor: VehicleCoordinator) -> dict[str, Any]:
    """The main-stream watchdog's restart history."""
    last_update = getattr(coor, "_last_update_time", None)
    return {
        "last_update_time": last_update.isoformat() if last_update else None,
        "restarts": getattr(coor, "_watchdog_restarts", 0),
        "last_restart_reason": getattr(coor, "_last_restart_reason", None),
    }


def _provenance_diagnostics(coor: VehicleCoordinator) -> dict[str, Any]:
    """Which keys the subscription(s) have claimed vs which Parallax has
    actually filled -- the direct evidence for the gap-fill rule in
    _process_parallax_data."""
    return {
        "subscription_keys": sorted(getattr(coor, "_subscription_keys", None) or set()),
        "parallax_filled_keys": sorted(
            getattr(coor, "_parallax_filled_keys", None) or set()
        ),
    }


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
    # "connected but receiving nothing" is a real and non-obvious state, which
    # is why `subscribed` is reported separately from the data itself.
    # This comment previously justified that with "the gateway allows one active
    # subscription per user session". FALSIFIED 2026-08-20: rivian.py:827 runs a
    # single monitor multiplexing rivian.py:147 `_subscriptions`, and
    # subscribe_for_vehicle_updates, subscribe_for_parallax_messages and
    # subscribe_for_cloud_connection in coordinator.py open three concurrent on
    # one u-sess every day. The diagnostic is still worth reporting; the reason
    # given for it was false. See docs/development/WS_CONTENTION.md, claim C1s.
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
        # §G, non-gating half (release 1): what document is live, whether TPMS
        # is, the watchdog's restart history, and who claimed which field.
        "subscription": {
            vehicle_id: _subscription_diagnostics(coordinator, vehicle_id)
            for vehicle_id, coordinator in vehicle_coordinators.items()
        },
        "tire_pressure": {
            vehicle_id: _tire_pressure_diagnostics(coordinator)
            for vehicle_id, coordinator in vehicle_coordinators.items()
        },
        "watchdog": {
            vehicle_id: _watchdog_diagnostics(coordinator)
            for vehicle_id, coordinator in vehicle_coordinators.items()
        },
        "provenance": {
            vehicle_id: _provenance_diagnostics(coordinator)
            for vehicle_id, coordinator in vehicle_coordinators.items()
        },
    }
    return redact(data)
