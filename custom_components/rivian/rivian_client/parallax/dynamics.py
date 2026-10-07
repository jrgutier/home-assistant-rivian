"""Decoders for `dynamics.*` topics: gear, drive mode, range, tires, location."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Final

from .core import _TIMESTAMP_FORMAT, RVMDecoder, _fields
from .proto import dynamics_pb2

TIRE_POSITION_MAP = {
    1: "FrontLeft",
    2: "FrontRight",
    3: "RearLeft",
    4: "RearRight",
}

# dynamics.vehicle.gear -- Gear
_GEAR_MAP: Final[dict[int, str]] = {
    0: "not_defined",
    1: "park",
    2: "reverse",
    3: "neutral",
    4: "drive",
}

# dynamics.vehicle.drive_mode -- DriveMode
_DRIVE_MODE_MAP: Final[dict[int, str]] = {
    1: "init_mode",
    2: "everyday",
    3: "off_road_snow_ice",
    4: "off_road_sport_auto",
    5: "off_road_sport_drift",
    6: "sport_launch",
    7: "fault",
    8: "sport",
    9: "distance",
    10: "towing",
    11: "off_road_auto",
    12: "off_road_sand",
    13: "off_road_rocks",
    14: "off_road_mud",
    15: "winter",
}

# dynamics.vehicle.range -- RangeThreshold and TemperatureRangeImpact
_RANGE_THRESHOLD_MAP: Final[dict[int, str]] = {
    1: "normal",
    2: "low",
    3: "red",
    4: "critically_low",
}
_TEMPERATURE_IMPACT_MAP: Final[dict[int, str]] = {
    1: "normal_range",
    2: "cold_may_impact",
    3: "cold_impact",
}

# dynamics.vehicle.location -- KnownLocation
_KNOWN_LOCATION_MAP: Final[dict[int, str]] = {
    1: "unknown",
    2: "home",
    3: "work",
}


@RVMDecoder.register(dynamics_pb2.Gnss, "dynamics.vehicle.gnss")
def decode_gnss(m: dynamics_pb2.Gnss) -> dict[str, Any]:
    """Decode dynamics.vehicle.gnss.

    Returns dict with keys:
        - gnssLocation: {"latitude": float, "longitude": float, "timeStamp": str}
        - gnssAltitude: float (meters)
    """
    result: dict[str, Any] = {}
    if m.HasField("latitude") and m.HasField("longitude"):
        now_iso = datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT)
        result["gnssLocation"] = {
            "latitude": round(m.latitude, 6),
            "longitude": round(m.longitude, 6),
            "timeStamp": now_iso,
        }
    if m.HasField("altitude"):
        result["gnssAltitude"] = round(m.altitude, 1)
    return result


@RVMDecoder.register(dynamics_pb2.Odometer, "dynamics.vehicle.odometer")
def decode_odometer(m: dynamics_pb2.Odometer) -> dict[str, Any]:
    """Decode dynamics.vehicle.odometer.

    Returns dict with keys:
        - vehicleMileage: float (meters)
    """
    # Value is distance in km; HA expects meters
    return {"vehicleMileage": m.distance * 1000} if m.HasField("distance") else {}


@RVMDecoder.register(dynamics_pb2.TiresState, "dynamics.tires.state")
def decode_tires(m: dynamics_pb2.TiresState) -> dict[str, Any]:
    """Decode dynamics.tires.state.

    Returns dict with keys:
        - tirePressureFrontLeft, tirePressureFrontRight, etc. (bar)
        - tirePressureStatusFrontLeft, etc. ("OK")
    """
    result: dict[str, Any] = {}
    for tire in m.tire:
        if tire.pos not in TIRE_POSITION_MAP:
            continue
        suffix = TIRE_POSITION_MAP[tire.pos]
        if tire.HasField("pressure"):
            result[f"tirePressure{suffix}"] = round(tire.pressure, 2)
        if tire.HasField("status"):
            result[f"tirePressureStatus{suffix}"] = (
                "OK" if tire.status == 1 else "Warning"
            )
    return result


@RVMDecoder.register(dynamics_pb2.Gear, "dynamics.vehicle.gear")
def decode_gear(m: dynamics_pb2.Gear) -> dict[str, Any]:
    """Decode dynamics.vehicle.gear.

    Returns dict with keys:
        - gearStatus: str
    """
    return _fields(m, {"gear": ("gearStatus", _GEAR_MAP)})


@RVMDecoder.register(dynamics_pb2.DriveMode, "dynamics.vehicle.drive_mode")
def decode_drive_mode(m: dynamics_pb2.DriveMode) -> dict[str, Any]:
    """Decode dynamics.vehicle.drive_mode.

    Returns dict with keys:
        - driveMode: str
        - limitedAccelCold: bool
        - limitedRegenCold: bool

    Fields 8 and 9, not 2 and 3. The message skips 2-7 outright, which is the kind
    of thing a hand-guessed layout gets wrong and a transcription does not.
    """
    return _fields(
        m,
        {
            "mode": ("driveMode", _DRIVE_MODE_MAP),
            "limited_accel_cold": ("limitedAccelCold", None),
            "limited_regen_cold": ("limitedRegenCold", None),
        },
    )


@RVMDecoder.register(dynamics_pb2.Range, "dynamics.vehicle.range")
def decode_range(m: dynamics_pb2.Range) -> dict[str, Any]:
    """Decode dynamics.vehicle.range.

    Returns dict with keys:
        - distanceToEmpty: int (km -- the sensor's own unit, so no conversion)
        - rangeThreshold: str
        - coldRangeNotification: str
    """
    return _fields(
        m,
        {
            "distance_to_empty": ("distanceToEmpty", None),
            "threshold": ("rangeThreshold", _RANGE_THRESHOLD_MAP),
            "temperature_impact": ("coldRangeNotification", _TEMPERATURE_IMPACT_MAP),
        },
    )


@RVMDecoder.register(dynamics_pb2.KnownLocation, "dynamics.vehicle.location")
def decode_known_location(m: dynamics_pb2.KnownLocation) -> dict[str, Any]:
    """Decode dynamics.vehicle.location.

    Returns dict with keys:
        - knownLocation: str ("unknown" / "home" / "work")

    Distinct from dynamics.vehicle.gnss, which carries coordinates. This is the
    vehicle's own coarse classification and backs no gateway field.
    """
    return _fields(m, {"location": ("knownLocation", _KNOWN_LOCATION_MAP)})
