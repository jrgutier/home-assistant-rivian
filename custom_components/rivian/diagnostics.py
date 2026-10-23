from __future__ import annotations

from datetime import UTC, datetime
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


def _subscription_diagnostics(
    coor: VehicleCoordinator, vehicle_id: str
) -> dict[str, Any]:
    document = coor.api.subscription_document(vehicle_id)
    fields_never_delivered = (
        sorted(VEHICLE_STATE_SUBSCRIPTION_FIELDS - coor._subscription_keys)
        if coor._initial.is_set()
        else []
    )
    return {
        "document": document,
        "requested_field_count": len(VEHICLE_STATE_SUBSCRIPTION_FIELDS),
        "accepted": document is not None,
        "last_document_error": coor._last_document_error,
        "fields_never_delivered": fields_never_delivered,
    }


def _tire_pressure_diagnostics(coor: VehicleCoordinator) -> dict[str, Any]:
    last = coor._tpms_last_update_time
    return {
        "subscribed": coor._unsub_tire_pressure is not None,
        "last_frame_age": (
            (datetime.now(UTC) - last).total_seconds() if last else None
        ),
        "frames_seen": coor._tpms_frames_seen,
    }


def _watchdog_diagnostics(coor: VehicleCoordinator) -> dict[str, Any]:
    last_update = coor._last_update_time
    return {
        "last_update_time": last_update.isoformat() if last_update else None,
        "restarts": coor._watchdog_restarts,
        "last_restart_reason": coor._last_restart_reason,
    }


def _provenance_diagnostics(coor: VehicleCoordinator) -> dict[str, Any]:
    return {
        "subscription_keys": sorted(coor._subscription_keys),
        "parallax_filled_keys": sorted(coor._parallax_filled_keys),
    }


def _option_codes_diagnostics(coor: UserCoordinator) -> dict[str, Any]:
    try:
        vehicles = coor.get_vehicles()
    except (AttributeError, KeyError, TypeError):
        return {}
    return {
        vehicle_id: vehicle.get("option_codes")
        for vehicle_id, vehicle in vehicles.items()
    }


def _command_outcomes(coordinator: VehicleCoordinator) -> list[dict[str, Any]]:
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
        for command_id, rec in coordinator._command_states.items()
    ]


def _feature_diagnostics(
    features_coordinator: SupportedFeaturesCoordinator | None,
    static_vehicles: dict[str, dict[str, Any]],
    vehicle_id: str,
) -> dict[str, Any]:
    feed_status: dict[str, str] | None = None
    if features_coordinator is not None:
        try:
            feed_status = features_coordinator.features_by_status().get(vehicle_id)
        except (AttributeError, KeyError, TypeError):
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
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinators = entry_data[ATTR_COORDINATOR]
    user_coordinator: UserCoordinator = coordinators[ATTR_USER]
    vehicle_coordinators: dict[str, VehicleCoordinator] = coordinators[ATTR_VEHICLE]
    wallbox_coordinator: WallboxCoordinator = coordinators[ATTR_WALLBOX]
    features_coordinator: SupportedFeaturesCoordinator | None = coordinators.get(
        ATTR_SUPPORTED_FEATURES
    )
    static_vehicles: dict[str, dict[str, Any]] = entry_data.get(ATTR_VEHICLE, {})
    rvms_requested = sorted({*PARALLAX_RVMS, *CHARGING_RVMS})
    rvms_decodable = sorted(RVM_DECODERS)
    parallax = {
        vehicle_id: {
            "subscribed": coor._unsub_parallax is not None,
            "rvms_requested": rvms_requested,
            "rvms_decodable": rvms_decodable,
        }
        for vehicle_id, coor in vehicle_coordinators.items()
    }

    data = {
        "parallax": parallax,
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
        "option_codes": _option_codes_diagnostics(user_coordinator),
        "parallax_rvm_arrivals": {
            vehicle_id: coordinator.rvm_arrivals
            for vehicle_id, coordinator in vehicle_coordinators.items()
        },
        "command_outcomes": {
            vehicle_id: _command_outcomes(coordinator)
            for vehicle_id, coordinator in vehicle_coordinators.items()
        },
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
        "supported_features": {
            vehicle_id: _feature_diagnostics(
                features_coordinator, static_vehicles, vehicle_id
            )
            for vehicle_id in vehicle_coordinators
        },
    }
    return redact(data)
