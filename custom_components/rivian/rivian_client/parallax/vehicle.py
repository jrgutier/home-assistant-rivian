from __future__ import annotations

from typing import Any, Final

from google.protobuf.message import Message
from google.protobuf.unknown_fields import UnknownFieldSet

from .core import RVMDecoder, _name
from .proto import vehicle_pb2

POWER_STATE_MAP = {
    1: "sleep",
    2: "standby",
    3: "ready",
    4: "go",
    5: "vehicle_reset",
    6: "ota_update",
    7: "shutdown",
}

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
    if m.HasField("state"):
        return {"powerState": POWER_STATE_MAP.get(m.state, "standby")}
    return {}


@RVMDecoder.register(vehicle_pb2.VehicleWheels, "vehicle.wheels.vehicle_wheels")
def decode_vehicle_wheels(m: vehicle_pb2.VehicleWheels) -> dict[str, Any]:
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
    result: dict[str, Any] = {}
    if m.HasField("wifi"):
        result |= _network_part(m.wifi, _WIFI_SPEC)
    if m.HasField("cellular"):
        result |= _network_part(m.cellular, _CELLULAR_SPEC)
    return result
