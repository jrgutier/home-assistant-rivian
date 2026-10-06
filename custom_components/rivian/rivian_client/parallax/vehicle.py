"""Decoders for `vehicle.*` topics: power state, wheels, network."""

from __future__ import annotations

from typing import Any, Final

from google.protobuf.message import Message
from google.protobuf.unknown_fields import UnknownFieldSet

from .core import RVMDecoder, _name
from .proto import vehicle_pb2

# The app's VEHICLE_POWER_MODE (`qqf`, 3.16.0). 0 UNDEFINED is left out, so it
# takes decode_power_state's "standby" fallback like any unknown value.
POWER_STATE_MAP = {
    1: "sleep",
    2: "standby",
    3: "ready",
    4: "go",
    5: "vehicle_reset",
    6: "ota_update",
    7: "shutdown",
}

# --- vehicle.network.state ---------------------------------------------------
#
# The one decoder here NOT backed by a topic-to-message binding, taken on the
# owner's decision and flagged as such rather than blended in with the others.
#
# `opl` is parsed in the app (`ipf`), but its parser `ipf.e` has NO CALLER
# anywhere in the 32,941 files, so nothing in the decompilation says which topic
# feeds it. What makes the identification strong enough to act on is that its
# field names land one-to-one on the gateway schema f4 rebuilt from the app's own
# documents:
#
#     opl.wifi.ssid            -> wifiSsid            opl.cellular.carrier  -> cellularCarrier
#     opl.wifi.signal_quality  -> wifiAntennaBars     opl.cellular.network  -> cellularMode
#     opl.wifi.link_speed      -> wifiLinkSpeed       opl.cellular.signal_* -> cellular*
#     opl.wifi.frequency       -> wifiFreq
#
# Twelve names, all present in `type VehicleState`, matching a topic literally
# called vehicle.network.state. That is corroboration from a second independent
# source, not just a plausible-sounding name.
#
# The blast radius if it is still wrong: every field below except wifiSignal is
# DECLARED but NOT SUBSCRIBED, so a bad decode mis-fills sensors that do not exist
# yet rather than corrupting a working one. wifiSignal is subscribed, and the
# gap-fill rule means the subscription keeps it -- this decoder cannot touch it.
_CONNECTIVITY_LEVEL_MAP: Final[dict[int, str]] = {
    1: "level_0",
    2: "level_1",
    3: "level_2",
    4: "level_3",
    5: "level_4",
}
_WPA_STATUS_MAP: Final[dict[int, str]] = {
    1: "not_connected",
    2: "connected",
    3: "scanning",
    4: "connecting",
    5: "disconnecting",
}
_WIFI_SECURITY_MAP: Final[dict[int, str]] = {
    1: "open",
    2: "wpa_personal",
    3: "wpa_enterprise",
    4: "wpa2_personal",
    5: "wpa2_enterprise",
}

_WIFI_SPEC: Final[dict[int, tuple[str, dict[int, str] | None]]] = {
    1: ("wifiWpaStatus", _WPA_STATUS_MAP),
    3: ("wifiSsid", None),
    7: ("wifiAntennaBars", _CONNECTIVITY_LEVEL_MAP),
    8: ("wifiSignal", None),
    9: ("wifiLinkSpeed", None),
    10: ("wifiFreq", None),
    12: ("wifiSecureStatus", _WIFI_SECURITY_MAP),
}

_CELLULAR_SPEC: Final[dict[int, tuple[str, dict[int, str] | None]]] = {
    1: ("cellularCarrier", None),
    2: ("cellularMode", None),
    3: ("cellularAntennaBars", _CONNECTIVITY_LEVEL_MAP),
    4: ("cellularSignalStrength", None),
}


def _network_part(
    part: Message, spec: dict[int, tuple[str, dict[int, str] | None]]
) -> dict[str, Any]:
    """Decode one of NetworkState's submessages against `spec`.

    Unlike every other decoder here, this one does not trust the schema's
    types. The binding of this topic to its message is an inference (see
    above), so a field's declared type is a guess too, and the decoder this
    replaced reported a spec'd field whichever way it arrived: text if
    length-delimited, a number if a varint. A field that arrives the other way
    round from its declaration lands in the unknown fields, so those are read
    as well.
    """
    seen: list[tuple[int, Any]] = [
        (number, getattr(part, _name(part, number)))
        for number in spec
        if part.HasField(_name(part, number))
    ]
    seen += [
        (unknown.field_number, unknown.data)
        for unknown in UnknownFieldSet(part)
        if unknown.field_number in spec and unknown.wire_type in (0, 2)
    ]
    out: dict[str, Any] = {}
    for number, value in seen:
        key, mapping = spec[number]
        if isinstance(value, bytes):
            try:
                out[key] = value.decode("utf-8")
            except UnicodeDecodeError:
                continue
        elif mapping is None:
            out[key] = value
        elif value in mapping:
            out[key] = mapping[value]
    return out


@RVMDecoder.register(vehicle_pb2.VehiclePowerState, "vehicle.power.state")
def decode_power_state(m: vehicle_pb2.VehiclePowerState) -> dict[str, Any]:
    """Decode vehicle.power.state.

    Returns dict with keys:
        - powerState: str ("sleep", "standby", "ready", "go")
    """
    if m.HasField("state"):
        return {"powerState": POWER_STATE_MAP.get(m.state, "standby")}
    return {}


@RVMDecoder.register(vehicle_pb2.VehicleWheels, "vehicle.wheels.vehicle_wheels")
def decode_vehicle_wheels(m: vehicle_pb2.VehicleWheels) -> dict[str, Any]:
    """Decode vehicle.wheels.vehicle_wheels.

    Returns dict with keys:
        - wheels: list[dict] -- one entry per wheel, each with wheelPackage,
          tireOdometerMeters, odometerAtLastRotationMeters,
          rotationReminderIntervalMeters, isInstalled, tires
        - wheelsInstalled: int -- how many report is_installed
    """
    # proto3 omits fields at their default, and absent means zero here, so
    # every key is always present.
    wheels: list[dict[str, Any]] = [
        {
            "wheelPackage": wheel.wheel_package,
            "tireOdometerMeters": wheel.tire_odometer,
            "odometerAtLastRotationMeters": wheel.odometer_at_last_rotation,
            "rotationReminderIntervalMeters": wheel.rotation_reminder_interval,
            "isInstalled": wheel.is_installed,
            "tires": wheel.tires,
            "currentOdometerMeters": wheel.current_odometer,
        }
        for wheel in m.wheel
    ]
    if not wheels:
        return {}
    return {
        "wheels": wheels,
        "wheelsInstalled": sum(1 for w in wheels if w.get("isInstalled")),
    }


@RVMDecoder.register(vehicle_pb2.NetworkState, "vehicle.network.state")
def decode_network_state(m: vehicle_pb2.NetworkState) -> dict[str, Any]:
    """Decode vehicle.network.state.

    Returns the wifi* and cellular* fields the gateway schema declares. See the
    block comment above for why this binding is an inference rather than a read
    parse site, and what the cost of being wrong is.
    """
    result: dict[str, Any] = {}
    if m.HasField("wifi"):
        result |= _network_part(m.wifi, _WIFI_SPEC)
    if m.HasField("cellular"):
        result |= _network_part(m.cellular, _CELLULAR_SPEC)
    return result
