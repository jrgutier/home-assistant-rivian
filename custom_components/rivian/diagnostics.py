"""Diagnostics support for Rivian."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    ATTR_COORDINATOR,
    ATTR_SUPPORTED_FEATURES,
    ATTR_USER,
    ATTR_VEHICLE,
    ATTR_WALLBOX,
    DOMAIN,
    VEHICLE_STATE_SUBSCRIPTION_FIELDS,
)
from .coordinator import (
    SupportedFeaturesCoordinator,
    UserCoordinator,
    VehicleCoordinator,
    WallboxCoordinator,
)
from .helpers import redact
from .rivian_client.ble_trace import all_traces_as_dict
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


def _option_codes_diagnostics(coor: UserCoordinator) -> dict[str, Any]:
    """S19: `option_codes` per vehicle, keyed by vehicle id.

    None means the `mobileConfiguration` fragment was rejected and
    get_user_information() (rivian_client/rivian.py) retried without it --
    distinguishable from an empty list, which means the fragment was accepted
    and the vehicle simply has no matching options. Built from
    UserCoordinator.get_vehicles() rather than read raw off coor.data so this
    stays in sync with what get_vehicles() actually surfaces to entities.
    """
    try:
        vehicles = coor.get_vehicles()
    except Exception:  # noqa: BLE001 -- diagnostics must never raise
        return {}
    return {
        vehicle_id: vehicle.get("option_codes")
        for vehicle_id, vehicle in vehicles.items()
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


def _feature_diagnostics(
    features_coordinator: SupportedFeaturesCoordinator | None,
    static_vehicles: dict[str, dict[str, Any]],
    vehicle_id: str,
) -> dict[str, Any]:
    """Which source answered for one vehicle's SupportedFeatures, and every
    status it carried -- not just AVAILABLE, so UPDATE_FIRMWARE is visible
    rather than silently dropped by the AVAILABLE-only filter everything
    else (available_features(), get_vehicles()) uses.

    "feed" wins whenever SupportedFeaturesCoordinator has data for this
    vehicle id at all, even an empty features list -- that is a real answer
    from the feed, not a failure. Only when the feed has nothing for this
    vehicle does this fall back to the supportedFeatures fragment already
    embedded in getUserInfo (UserCoordinator.get_vehicles()'s
    "supported_features" list, AVAILABLE-only by construction there).
    """
    feed_status: dict[str, str] | None = None
    if features_coordinator is not None:
        try:
            feed_status = features_coordinator.features_by_status().get(vehicle_id)
        except Exception:  # noqa: BLE001 -- diagnostics must never raise
            feed_status = None

    if feed_status is not None:
        return {
            "feature_source": "feed",
            "features_available": sorted(
                name for name, status in feed_status.items() if status == "AVAILABLE"
            ),
            "features_by_status": feed_status,
        }

    fallback = static_vehicles.get(vehicle_id, {}).get("supported_features") or []
    if fallback:
        return {
            "feature_source": "static_fallback",
            "features_available": sorted(fallback),
            "features_by_status": {name: "AVAILABLE" for name in fallback},
        }

    return {
        "feature_source": "none",
        "features_available": [],
        "features_by_status": {},
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinators = entry_data[ATTR_COORDINATOR]
    user_coordinator: UserCoordinator = coordinators[ATTR_USER]
    vehicle_coordinators: dict[str, VehicleCoordinator] = coordinators[ATTR_VEHICLE]
    wallbox_coordinator: WallboxCoordinator = coordinators[ATTR_WALLBOX]
    # Absent from fixtures/tests that predate the feed and from any config
    # entry set up before this story shipped -- .get() rather than [...], so
    # neither crashes the download (see module docstring above).
    features_coordinator: SupportedFeaturesCoordinator | None = coordinators.get(
        ATTR_SUPPORTED_FEATURES
    )
    # The embedded supportedFeatures fallback: `vehicles` (top-level, static
    # metadata from UserCoordinator.get_vehicles()) is a different dict from
    # `vehicle_coordinators` above despite sharing ATTR_VEHICLE as a key at
    # two different nesting levels -- see __init__.py's hass.data[DOMAIN][...]
    # assembly.
    static_vehicles: dict[str, dict[str, Any]] = entry_data.get(ATTR_VEHICLE, {})
    # Parallax now feeds the vehicle and charging coordinators directly rather
    # than a store of its own, so its DATA already appears below. What is not
    # otherwise visible -- and what every diagnosis in this area has needed -- is
    # whether the subscription is actually live and which topics it asked for.
    # "connected but receiving nothing" is a real and non-obvious state, which
    # is why `subscribed` is reported separately from the data itself.
    # This comment previously justified that with "the gateway allows one active
    # subscription per user session". FALSIFIED 2026-08-20: rivian.py:928 runs a
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
        # Gen 2 BLE pairing trace (beta): what a tester's pairing attempt
        # actually did on the wire, for the UNPROVEN unknowns in
        # GEN2_BLE_DELTA.md that only a real capture can settle. Filtered to
        # this entry's own vehicle_ids -- all_traces_as_dict() reads from a
        # module-level dict that is not scoped to any one config entry, so
        # an unfiltered dump would leak another account's vehicle trace
        # into this download on a multi-entry install. Redacted below like
        # every other key in this payload; see helpers.TO_REDACT for what
        # is masked and why nonce/MAC bytes are deliberately left as hex.
        "ble_trace": {
            vehicle_id: trace
            for vehicle_id, trace in all_traces_as_dict().items()
            if vehicle_id in vehicle_coordinators
        },
        "user": user_coordinator.data,
        "vehicle": [coor.data for coor in vehicle_coordinators.values()],
        "charging": [
            coor.charging_coordinator.data for coor in vehicle_coordinators.values()
        ],
        "drivers": [
            coor.drivers_coordinator.data for coor in vehicle_coordinators.values()
        ],
        "wallbox": wallbox_coordinator.data,
        # S19: factory option codes per vehicle, None when the fragment was
        # rejected -- see _option_codes_diagnostics.
        "option_codes": _option_codes_diagnostics(user_coordinator),
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
        # SupportedFeatures feed (s19): "feed" or "static_fallback" per
        # vehicle, plus every status the winning source carried -- see
        # _feature_diagnostics's docstring for why the fallback is per
        # vehicle rather than all-or-nothing for the whole entry.
        "supported_features": {
            vehicle_id: _feature_diagnostics(
                features_coordinator, static_vehicles, vehicle_id
            )
            for vehicle_id in vehicle_coordinators
        },
    }
    return redact(data)
