"""Parallax protocol: telemetry decoding and vehicle-operation commands.

Two halves that meet here.

READ -- decodes base64 protobuf payloads from the Parallax WebSocket subscription
into structured dicts. Hand-rolled varint parsing, no protobuf dependency.
Reference: https://github.com/kaedenbrinkman/rivian-api (RivDocs)

WRITE -- builds outbound Parallax operations: the RVMType catalogue reverse
engineered from the Android app (EnumC6207c.java) and the build_* helpers that
produce payloads for send_vehicle_operation.

The two were developed independently -- upstream is read-only, this fork added
the write path -- and share no symbols, which is why they simply sit side by
side. Only one RVM overlaps them at all
(energy_edge_compute.graphs.charging_graph_global).

Note the asymmetry: every RVM here can be *read*, but Rivian currently accepts
only one as a *write* (comfort.cabin.climate_hold_setting). The other builders
are retained until the entities that call them are removed.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import datetime, timezone
import logging
import struct
import sys
from typing import Any, Final, Protocol
import uuid

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from backports.strenum import StrEnum

from .proto.vehicle_operation import _encode_varint_field

_LOGGER = logging.getLogger(__name__)

# Ids from the Rivian Android app's own CLOSURE_INSTANCE enum
# (com.rivian.android.consumer 3.15.0). Transcribed, not inferred.
#
# Id 6 was previously mapped to closureSideBinLeftClosed. It is the TAILGATE; the
# left side bin is 8. On an R1T that made the left gear tunnel sensor report the
# tailgate's state, while the real side bins, tonneau and charge port were
# discarded because nothing mapped their ids.
#
# Ids present in the enum but deliberately unmapped: 0 UNSPECIFIED, 10 CHARGE_PORT
# and 16 WINDOW_REAR (no corresponding entity field), and 10000 GROUP_WINDOWS,
# which is an aggregate rather than a physical closure.
CLOSURE_MAP = {
    1: "doorFrontLeftClosed",  # DOOR_ROW_1_LEFT
    2: "doorFrontRightClosed",  # DOOR_ROW_1_RIGHT
    3: "doorRearLeftClosed",  # DOOR_ROW_2_LEFT
    4: "doorRearRightClosed",  # DOOR_ROW_2_RIGHT
    5: "closureFrunkClosed",  # FRUNK
    6: "closureTailgateClosed",  # TAILGATE   (was: side bin left)
    7: "closureLiftgateClosed",  # LIFTGATE
    8: "closureSideBinLeftClosed",  # SIDE_BIN_LEFT
    9: "closureSideBinRightClosed",  # SIDE_BIN_RIGHT
    11: "closureTonneauClosed",  # TONNEAU
    12: "windowFrontLeftClosed",  # WINDOW_FRONT_LEFT
    13: "windowFrontRightClosed",  # WINDOW_FRONT_RIGHT
    14: "windowRearLeftClosed",  # WINDOW_BACK_LEFT
    15: "windowRearRightClosed",  # WINDOW_BACK_RIGHT
}

# Ids from the app's LOCK_INSTANCE enum. Note it is NOT the same numbering as
# CLOSURE_INSTANCE past id 10: tonneau is 15 here and 11 there.
#
# Unmapped: 0 UNSPECIFIED, 10 CHARGE_PORT, 11 TRUNK_SECURITY, 12 CENTER_CONSOLE,
# 13 GLOVE_BOX and 14 GEAR_GUARD -- no entity reads them.
LOCK_MAP = {
    1: "doorFrontLeftLocked",  # DOOR_FRONT_LEFT
    2: "doorFrontRightLocked",  # DOOR_FRONT_RIGHT
    3: "doorRearLeftLocked",  # DOOR_BACK_LEFT
    4: "doorRearRightLocked",  # DOOR_BACK_RIGHT
    5: "closureFrunkLocked",  # FRUNK
    6: "closureTailgateLocked",  # TAILGATE
    7: "closureLiftgateLocked",  # LIFTGATE
    8: "closureSideBinLeftLocked",  # SIDE_BIN_LEFT
    9: "closureSideBinRightLocked",  # SIDE_BIN_RIGHT
    15: "closureTonneauLocked",  # TONNEAU
}

POWER_STATE_MAP = {
    1: "sleep",
    2: "standby",
    3: "ready",
    4: "go",
}

TIRE_POSITION_MAP = {
    1: "FrontLeft",
    2: "FrontRight",
    3: "RearLeft",
    4: "RearRight",
}


def _decode_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Decode a protobuf varint, return (value, new_offset)."""
    result = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        result |= (byte & 0x7F) << shift
        shift += 7
        offset += 1
        if not (byte & 0x80):
            break
    return result, offset


def _decode_protobuf_fields(data: bytes) -> list[tuple[int, int, Any]]:
    """Decode raw protobuf bytes into a list of (field_number, wire_type, value) tuples."""
    fields = []
    i = 0
    while i < len(data):
        tag, i = _decode_varint(data, i)
        field_num = tag >> 3
        wire_type = tag & 0x07
        value: Any

        if wire_type == 0:  # Varint
            value, i = _decode_varint(data, i)
            fields.append((field_num, wire_type, value))
        elif wire_type == 1:  # 64-bit float
            if i + 8 <= len(data):
                value = struct.unpack("<d", data[i : i + 8])[0]
                i += 8
                fields.append((field_num, wire_type, value))
            else:
                break
        elif wire_type == 2:  # Length-delimited
            length, i = _decode_varint(data, i)
            if i + length <= len(data):
                value = data[i : i + length]
                i += length
                fields.append((field_num, wire_type, value))
            else:
                break
        elif wire_type == 5:  # 32-bit float
            if i + 4 <= len(data):
                value = struct.unpack("<f", data[i : i + 4])[0]
                i += 4
                fields.append((field_num, wire_type, value))
            else:
                break
        else:
            _LOGGER.debug("Unknown wire type %d for field %d", wire_type, field_num)
            break

    return fields


def decode_battery_state(payload: str) -> dict[str, Any]:
    """Decode energy.high_voltage.battery_state.

    Returns dict with keys:
        - soc: float (percentage, 0-100)
        - packEnergyKwh: float
        - rangeKm: float (if present)
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 2:
                # Nested charge_state message
                inner_fields = _decode_protobuf_fields(value)
                for inner_num, inner_wt, inner_val in inner_fields:
                    if inner_num == 1 and inner_wt == 1:  # soc (float)
                        result["soc"] = round(inner_val, 2)
                    elif inner_num == 2 and inner_wt == 1:  # packEnergyKwh (float)
                        result["packEnergyKwh"] = round(inner_val, 2)
                    elif inner_num == 3 and inner_wt == 5:  # rangeKm (float)
                        result["rangeKm"] = round(inner_val, 1)

        return result
    except Exception:
        _LOGGER.debug("Failed to decode battery_state payload", exc_info=True)
        return {}


def decode_cabin_temperatures(payload: str) -> dict[str, Any]:
    """Decode comfort.cabin.cabin_temperatures.

    Returns dict with keys:
        - cabinClimateInteriorTemperature: float (Celsius)
        - cabinClimateDriverTemperature: float (Celsius)
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 3 and wire_type == 5:  # interior temp (float, Celsius)
                result["cabinClimateInteriorTemperature"] = round(value, 1)
            if field_num == 4 and wire_type == 5:  # interior temp (float, Celsius)
                result["cabinClimateDriverTemperature"] = round(value, 1)

        return result
    except Exception:
        _LOGGER.debug("Failed to decode cabin temperatures payload", exc_info=True)
        return {}


def decode_charge_session_breakdown(payload: str) -> dict[str, Any]:
    """Decode energy_edge_compute.graphs.charge_session_breakdown.

    Returns dict with keys matching legacy getLiveSessionData field names:
        - totalChargedEnergy: float (kWh total)
        - power: float (kW, current charge rate)
        - timeElapsed: int (seconds, estimated)
        - rangeAddedThisSession: float (km, estimated from energy)
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        total_kwh = 0.0

        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 5:  # totalKwh (float)
                total_kwh = round(value, 4)
                result["totalChargedEnergy"] = total_kwh
            elif field_num == 9 and wire_type == 5:  # currentPower (float, kW)
                result["power"] = round(value, 2)
            elif field_num == 7 and wire_type == 0:  # timeRemainingMins or elapsed secs
                result["_time_field_7"] = value
            elif field_num == 10 and wire_type == 0:  # charge power integer (kW)
                if "power" not in result:
                    result["power"] = float(value)
            elif field_num == 13 and wire_type == 0:  # chargingState enum
                result["_charging_state"] = value

        # Estimate range added: ~3.5 km/kWh (~2.17 mi/kWh) is a typical Rivian average
        if total_kwh > 0:
            result["rangeAddedThisSession"] = round(total_kwh * 3.5, 1)

        # Derive charge rate (km/h) from current power (kW)
        if "power" in result:
            p = result["power"]
            result["kilometersChargedPerHour"] = round(p * 3.5, 1) if p > 0 else 0.0

        return result
    except Exception:
        _LOGGER.debug(
            "Failed to decode charge_session_breakdown payload", exc_info=True
        )
        return {}


def decode_charging_graph_global(payload: str) -> dict[str, Any]:
    """Decode energy_edge_compute.graphs.charging_graph_global.

    Returns dict with keys:
        - startTime: str (ISO format timestamp of session start)
        - timeElapsed: int (seconds elapsed since session start)
        - power: float (kW, latest segment power)
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        outer = _decode_protobuf_fields(data)
        segments = []
        for field_num, wire_type, value in outer:
            if field_num == 1 and wire_type == 2:
                inner = _decode_protobuf_fields(value)
                seg: dict[str, Any] = {}
                for in_num, in_wt, in_val in inner:
                    if in_num == 1 and in_wt == 0:
                        seg["soc"] = in_val
                    elif in_num == 2 and in_wt == 5:
                        seg["power"] = round(in_val, 2)
                    elif in_num == 3 and in_wt == 0:
                        seg["start_ms"] = in_val
                    elif in_num == 4 and in_wt == 0:
                        seg["end_ms"] = in_val
                    elif in_num == 6 and in_wt == 0:
                        seg["state"] = in_val
                segments.append(seg)

        if not segments:
            return {}

        active_segments = [
            s for s in segments if s.get("power", 0) > 0 or s.get("state") == 3
        ]

        first_seg = active_segments[0] if active_segments else segments[0]
        result: dict[str, Any] = {}

        if "start_ms" in first_seg:
            st = datetime.fromtimestamp(first_seg["start_ms"] / 1000, timezone.utc)
            result["startTime"] = st.strftime("%Y-%m-%dT%H:%M:%S.%f%z")

        if active_segments:
            result["timeElapsed"] = sum(
                max(0, int((s["end_ms"] - s["start_ms"]) / 1000))
                for s in active_segments
                if "end_ms" in s and "start_ms" in s
            )
        else:
            result["timeElapsed"] = 0

        latest_segment = segments[-1]
        if (
            "power" in latest_segment
            and latest_segment.get("power", 0) > 0
            and latest_segment.get("state") != 8
        ):
            result["power"] = latest_segment["power"]
            result["kilometersChargedPerHour"] = round(result["power"] * 3.5, 1)
        else:
            result["power"] = 0.0
            result["kilometersChargedPerHour"] = 0.0

        return result
    except Exception:
        _LOGGER.debug("Failed to decode charging_graph_global payload", exc_info=True)
        return {}


def decode_charging_session_status(payload: str) -> dict[str, Any]:
    """Decode charging.session.status.

    Returns dict with keys:
        - plugConnectionStatus: int (enum)
        - displayStatus: int (enum)
        - evseType: int (enum)
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 0:
                result["plugConnectionStatus"] = value
            elif field_num == 2 and wire_type == 0:
                result["displayStatus"] = value
            elif field_num == 3 and wire_type == 0:
                result["evseType"] = value

        return result
    except Exception:
        _LOGGER.debug("Failed to decode charging.session.status payload", exc_info=True)
        return {}


def decode_closures(payload: str) -> dict[str, Any]:
    """Decode body.closures.states.

    Returns dict with keys:
        - doorFrontLeftClosed, doorFrontRightClosed, closureFrunkClosed, etc. ("closed" / "open")
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 2:  # Repeated nested closure state
                inner = _decode_protobuf_fields(value)
                cid = None
                state_val = None
                for in_num, in_type, in_val in inner:
                    if in_num == 1 and in_type == 0:
                        cid = in_val
                    elif in_num == 2 and in_type == 0:
                        state_val = in_val

                if cid and cid in CLOSURE_MAP and state_val is not None:
                    # 1 = open, 2 = closed
                    result[CLOSURE_MAP[cid]] = "closed" if state_val == 2 else "open"

        return result
    except Exception:
        _LOGGER.debug("Failed to decode closures payload", exc_info=True)
        return {}


def decode_defrost(payload: str) -> dict[str, Any]:
    """Decode comfort.cabin.defrost_defog_status.

    Returns dict with keys:
        - defrostDefogStatus: str ("Defrost", "Off")
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}
        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 0:
                result["defrostDefogStatus"] = "Defrost" if value == 2 else "Off"
        return result
    except Exception:
        _LOGGER.debug("Failed to decode defrost payload", exc_info=True)
        return {}


def decode_gnss(payload: str) -> dict[str, Any]:
    """Decode dynamics.vehicle.gnss.

    Returns dict with keys:
        - gnssLocation: {"latitude": float, "longitude": float, "timeStamp": str}
        - gnssAltitude: float (meters)
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        lat = None
        lon = None
        alt = None
        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 1:  # latitude (float)
                lat = round(value, 6)
            elif field_num == 2 and wire_type == 1:  # longitude (float)
                lon = round(value, 6)
            elif field_num == 3 and wire_type == 1:  # altitude (float)
                alt = round(value, 1)

        result: dict[str, Any] = {}
        if lat is not None and lon is not None:
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f%z")
            result["gnssLocation"] = {
                "latitude": lat,
                "longitude": lon,
                "timeStamp": now_iso,
            }
        if alt is not None:
            result["gnssAltitude"] = alt
        return result
    except Exception:
        _LOGGER.debug("Failed to decode dynamics.vehicle.gnss payload", exc_info=True)
        return {}


def decode_locks(payload: str) -> dict[str, Any]:
    """Decode body.locks.states.

    Returns dict with keys:
        - doorFrontLeftLocked, closureFrunkLocked, etc. ("locked" / "unlocked")
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 2:  # Repeated nested lock state
                inner = _decode_protobuf_fields(value)
                lid = None
                state_val = None
                for in_num, in_type, in_val in inner:
                    if in_num == 1 and in_type == 0:
                        lid = in_val
                    elif in_num == 2 and in_type == 0:
                        state_val = in_val

                if lid and lid in LOCK_MAP and state_val is not None:
                    # 1 = locked, 2 = unlocked
                    result[LOCK_MAP[lid]] = "locked" if state_val == 1 else "unlocked"

        return result
    except Exception:
        _LOGGER.debug("Failed to decode locks payload", exc_info=True)
        return {}


def decode_odometer(payload: str) -> dict[str, Any]:
    """Decode dynamics.vehicle.odometer.

    Returns dict with keys:
        - vehicleMileage: float (meters)
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 0:
                # Value is distance in km; HA expects meters
                result["vehicleMileage"] = value * 1000

        return result
    except Exception:
        _LOGGER.debug("Failed to decode odometer payload", exc_info=True)
        return {}


def decode_power_state(payload: str) -> dict[str, Any]:
    """Decode vehicle.power.state.

    Returns dict with keys:
        - powerState: str ("sleep", "standby", "ready", "go")
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 0:
                result["powerState"] = POWER_STATE_MAP.get(value, "standby")

        return result
    except Exception:
        _LOGGER.debug("Failed to decode power state payload", exc_info=True)
        return {}


def decode_preconditioning(payload: str) -> dict[str, Any]:
    """Decode comfort.cabin.cabin_preconditioning_status.

    Returns dict with keys:
        - cabinPreconditioningStatus: str ("active", "initiate", "off")
    """
    if not payload:
        return {"cabinPreconditioningStatus": "off"}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        status_val = None
        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 0:
                status_val = value

        if status_val == 4:
            return {"cabinPreconditioningStatus": "active"}
        elif status_val in (1, 2):
            return {"cabinPreconditioningStatus": "initiate"}
        return {"cabinPreconditioningStatus": "off"}
    except Exception:
        _LOGGER.debug("Failed to decode preconditioning payload", exc_info=True)
        return {}


def decode_time_estimation(payload: str) -> dict[str, Any]:
    """Decode charging.session.time_estimation.

    Returns dict with keys:
        - timeToEndOfCharge: int (seconds remaining)
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 0:
                result["timeToEndOfCharge"] = value

        return result
    except Exception:
        _LOGGER.debug("Failed to decode time_estimation payload", exc_info=True)
        return {}


def decode_tires(payload: str) -> dict[str, Any]:
    """Decode dynamics.tires.state.

    Returns dict with keys:
        - tirePressureFrontLeft, tirePressureFrontRight, etc. (bar)
        - tirePressureStatusFrontLeft, etc. ("OK")
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 2 and wire_type == 2:  # Repeated nested tire state
                inner = _decode_protobuf_fields(value)
                pos = None
                status = None
                pressure = None
                for in_num, in_type, in_val in inner:
                    if in_num == 1 and in_type == 0:
                        pos = in_val
                    elif in_num == 2 and in_type == 0:
                        status = "OK" if in_val == 1 else "Warning"
                    elif in_num == 3 and in_type == 1:  # 64-bit float (bar)
                        pressure = round(in_val, 2)

                if pos and pos in TIRE_POSITION_MAP:
                    suffix = TIRE_POSITION_MAP[pos]
                    if pressure is not None:
                        result[f"tirePressure{suffix}"] = pressure
                    if status is not None:
                        result[f"tirePressureStatus{suffix}"] = status

        return result
    except Exception:
        _LOGGER.debug("Failed to decode tires payload", exc_info=True)
        return {}


# Map of RVM topic -> decoder function
# --- Decoders for the RVMs this fork ships -----------------------------------
#
# Upstream's table covers 14 telemetry topics and none of these, so
# decode_parallax_message returned None for every one of them -- the entities
# would have read as unavailable forever. Layouts come from the .proto files
# reverse-engineered from com.rivian.android.consumer, and each decoder is
# asserted against a payload captured from a real vehicle
# (tests/fixtures/parallax/, see docs/development/RVM_FIXTURES.md in the
# integration repo).
#
# Written hand-rolled like the rest of this module rather than with the generated
# _pb2 classes, so they survive the removal of the protobuf dependency.

_CLIMATE_HOLD_STATUS = {
    0: "unspecified",
    1: "unavailable",
    2: "off",
    3: "on",
    4: "fault",
}
_CLIMATE_HOLD_AVAILABILITY = {
    0: "unspecified",
    1: "available",
    2: "controllable",
    3: "unavailable",
}
_CLIMATE_HOLD_UNAVAILABILITY_REASON = {
    0: "unspecified",
    1: "unknown",
    2: "low_soc",
}


def decode_climate_hold_status(payload: str) -> dict[str, Any]:
    """Decode comfort.cabin.climate_hold_status.

    Returns dict with keys:
        - climateHoldStatus: str  (off | on | unavailable | fault | unspecified)
        - climateHoldAvailability: str
        - climateHoldUnavailabilityReason: str (only when not "unspecified")
        - climateHoldEndTime: int (epoch seconds, only when a hold is running)
    """
    if not payload:
        return {}
    try:
        result: dict[str, Any] = {}
        for field_num, wire_type, value in _decode_protobuf_fields(
            base64.b64decode(payload)
        ):
            if field_num == 1 and wire_type == 0:
                result["climateHoldStatus"] = _CLIMATE_HOLD_STATUS.get(
                    value, "unspecified"
                )
            elif field_num == 2 and wire_type == 0:
                result["climateHoldAvailability"] = _CLIMATE_HOLD_AVAILABILITY.get(
                    value, "unspecified"
                )
            elif field_num == 3 and wire_type == 0:
                reason = _CLIMATE_HOLD_UNAVAILABILITY_REASON.get(value, "unspecified")
                if reason != "unspecified":
                    result["climateHoldUnavailabilityReason"] = reason
            elif field_num == 4 and wire_type == 2:
                # google.protobuf.Timestamp; an empty message means "no hold"
                for ts_num, ts_wt, ts_val in _decode_protobuf_fields(value):
                    if ts_num == 1 and ts_wt == 0:
                        result["climateHoldEndTime"] = ts_val
        return result
    except Exception:  # pylint: disable=broad-except
        _LOGGER.debug("Failed to decode climate_hold_status", exc_info=True)
        return {}


def decode_climate_hold_setting(payload: str) -> dict[str, Any]:
    """Decode comfort.cabin.climate_hold_setting.

    Returns dict with keys:
        - climateHoldDurationSeconds: int  (0 or absent when no hold is set)

    An EMPTY payload is the vehicle's way of saying "no hold configured"; it is
    reported as 0 rather than {} so the entity reads as off rather than
    unavailable.
    """
    if not payload:
        return {"climateHoldDurationSeconds": 0}
    try:
        result: dict[str, Any] = {"climateHoldDurationSeconds": 0}
        for field_num, wire_type, value in _decode_protobuf_fields(
            base64.b64decode(payload)
        ):
            if field_num == 1 and wire_type == 0:
                result["climateHoldDurationSeconds"] = value
        return result
    except Exception:  # pylint: disable=broad-except
        _LOGGER.debug("Failed to decode climate_hold_setting", exc_info=True)
        return {}


def decode_vehicle_wheels(payload: str) -> dict[str, Any]:
    """Decode vehicle.wheels.vehicle_wheels.

    Returns dict with keys:
        - wheels: list[dict] -- one entry per wheel, each with wheelPackage,
          tireOdometerMeters, odometerAtLastRotationMeters,
          rotationReminderIntervalMeters, isInstalled, tires
        - wheelsInstalled: int -- how many report is_installed
    """
    if not payload:
        return {}
    try:
        wheels: list[dict[str, Any]] = []
        for field_num, wire_type, value in _decode_protobuf_fields(
            base64.b64decode(payload)
        ):
            if field_num != 1 or wire_type != 2:
                continue
            # proto3 omits fields at their default, so seed the defaults rather
            # than emitting a ragged dict -- consumers would otherwise have to
            # distinguish "absent" from "zero", and the two mean the same here.
            wheel: dict[str, Any] = {
                "wheelPackage": 0,
                "tireOdometerMeters": 0,
                "odometerAtLastRotationMeters": 0,
                "rotationReminderIntervalMeters": 0,
                "isInstalled": False,
                "tires": 0,
                "currentOdometerMeters": 0,
            }
            for num, wt, val in _decode_protobuf_fields(value):
                if wt != 0:
                    continue
                if num == 1:
                    wheel["wheelPackage"] = val
                elif num == 2:
                    wheel["tireOdometerMeters"] = val
                elif num == 4:
                    wheel["odometerAtLastRotationMeters"] = val
                elif num == 6:
                    wheel["rotationReminderIntervalMeters"] = val
                elif num == 7:
                    wheel["isInstalled"] = bool(val)
                elif num == 9:
                    wheel["tires"] = val
                elif num == 10:
                    wheel["currentOdometerMeters"] = val
            wheels.append(wheel)
        if not wheels:
            return {}
        return {
            "wheels": wheels,
            "wheelsInstalled": sum(1 for w in wheels if w.get("isInstalled")),
        }
    except Exception:  # pylint: disable=broad-except
        _LOGGER.debug("Failed to decode vehicle_wheels", exc_info=True)
        return {}


# comfort.cabin.seat_conditioning_status. Field numbers and the level enum are
# transcribed from com.rivian.android.consumer 3.15.0:
#
#   SEAT_HEAT_STATUS_FRONT_LEFT   = 7    SEAT_VENT_STATUS_FRONT_LEFT  = 11
#   SEAT_HEAT_STATUS_FRONT_RIGHT  = 8    SEAT_VENT_STATUS_FRONT_RIGHT = 12
#   SEAT_HEAT_STATUS_REAR_LEFT    = 9
#   SEAT_HEAT_STATUS_REAR_RIGHT   = 10
#
# Each is a submessage with one varint field `val` holding a Level:
#   0 UNSPECIFIED, 1 LEVEL_0, 2 LEVEL_1, 3 LEVEL_2, 4 LEVEL_3, 5 LEVEL_4
#
# Why this exists: the vehicle-state subscription reports seatRearLeftHeat and
# seatRearRightHeat as 'SNA' on a truck that does have rear heaters, so those
# entities showed SNA (sensor) and unknown (select). Parallax carries the real
# value. The strings emitted here match the GraphQL vocabulary exactly -- "Off",
# "Level_1".. -- so the existing entities consume them unchanged.
SEAT_STATUS_FIELDS = {
    7: "seatFrontLeftHeat",
    8: "seatFrontRightHeat",
    9: "seatRearLeftHeat",
    10: "seatRearRightHeat",
    11: "seatFrontLeftVent",
    12: "seatFrontRightVent",
}
SEAT_LEVELS = {1: "Off", 2: "Level_1", 3: "Level_2", 4: "Level_3", 5: "Level_4"}


def decode_seat_conditioning_status(payload: str) -> dict[str, Any]:
    """Decode comfort.cabin.seat_conditioning_status.

    Returns dict with keys:
        - seatFrontLeftHeat, seatFrontRightHeat, seatRearLeftHeat,
          seatRearRightHeat, seatFrontLeftVent, seatFrontRightVent
          ("Off" / "Level_1" / "Level_2" / "Level_3")
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        result: dict[str, Any] = {}
        for field_num, wire_type, value in _decode_protobuf_fields(data):
            if wire_type != 2 or field_num not in SEAT_STATUS_FIELDS:
                continue
            for in_num, in_type, in_val in _decode_protobuf_fields(value):
                # LEVEL_UNSPECIFIED (0) means the vehicle is not saying, which is
                # not the same as off -- leave the field out entirely.
                if in_num == 1 and in_type == 0 and in_val in SEAT_LEVELS:
                    result[SEAT_STATUS_FIELDS[field_num]] = SEAT_LEVELS[in_val]
        return result
    except Exception:
        _LOGGER.debug("Failed to decode seat conditioning payload", exc_info=True)
        return {}


# ======================================================================
# Decoders transcribed from the app's protobuf classes (f5)
# ======================================================================
#
# How these were recovered, because it is not obvious and the first attempt
# concluded the schema was absent:
#
# R8 renames `GeneratedMessageLite` to `com.google.protobuf.e` and renames every
# message class to two or three letters (`hk8`, `gxf`, `xq`), so grepping the
# decompilation for "GeneratedMessageLite" or "ProtoAdapter" finds nothing and
# the app looks as though it carries no protobuf schema at all. It carries 326
# message classes. What R8 leaves alone is exactly what is needed:
#
#   * `<FIELD>_FIELD_NUMBER` constants, with their original names and numbers
#   * the `<field>_` instance members, with their Java types
#   * protobuf enum constants, with their original names and numbers
#
# The topic -> message binding comes from the app's own decoder dispatch
# (`b7h.java` and ten sibling files): each decoder guards on `l6e.<TOPIC>` and
# parses `<MessageClass>.<method>(Base64.decode(payload, 0))` in the same method
# body, so the pair can be read off mechanically rather than guessed.
#
# The VALUE vocabulary is the app's enum name with its common prefix stripped and
# lowercased -- `GEAR_PARK` -> `park`, `DRIVE_MODE_OFF_ROAD_AUTO` ->
# `off_road_auto`. That is not an inference: it is how GEAR_STATUS_MAP and
# DRIVE_MODE_MAP in the integration's const.py were already built from live
# subscription values. Emitting the same strings is what lets these topics feed
# the EXISTING sensors instead of needing new ones.
#
# Maps are written out rather than derived at runtime. A prefix-stripping helper
# would be shorter and would hide a wrong field number behind plausible output.

# security.alarm.state -- SoundAlarmStatus
_ALARM_SOUND_MAP: Final[dict[int, str]] = {
    1: "false",
    2: "true",
    3: "signal_not_available",
}

# body.trailer.state -- TrailerPresenceStatus
_TRAILER_PRESENCE_MAP: Final[dict[int, str]] = {
    1: "trailer_not_present",
    2: "trailer_present",
    3: "trailer_present_with_brakes",
    4: "trailer_invalid",
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

# energy.high_voltage.battery_characteristics -- BatteryCellType
_BATTERY_CELL_TYPE_MAP: Final[dict[int, str]] = {
    1: "50g",
    2: "53g",
    3: "g124",
    4: "lg_4695",
}

# energy.low_voltage.battery_state -- LowVoltageBatteryHealthStatus
_LOW_VOLTAGE_HEALTH_MAP: Final[dict[int, str]] = {
    1: "normal",
    2: "low",
}

# security.video_monitoring.state
_VIDEO_MONITORING_STATUS_MAP: Final[dict[int, str]] = {
    1: "disabled",
    2: "enabled",
    3: "active",
}
_VIDEO_MODE_MAP: Final[dict[int, str]] = {
    0: "none",
    1: "everywhere",
    2: "away_from_home",
}
_TOS_ACCEPTANCE_MAP: Final[dict[int, str]] = {
    1: "not_accepted",
    2: "accepted",
}

# security.access.btm -- HardwareFailureDtcStatus, one enum shared by six fields
_HARDWARE_FAILURE_MAP: Final[dict[int, str]] = {
    0: "unspecified",
    1: "set",
}

# security.access.vas_fault
_SECURE_ELEMENT_FAULTED_MAP: Final[dict[int, str]] = {
    1: "no_failure",
    2: "lost_communication",
    3: "applet_not_programmed",
    4: "not_configured",
    5: "attack_counter",
    6: "ursk_decrypt_failure",
}
_ACCESS_CAN_FAULTED_MAP: Final[dict[int, str]] = {
    1: "no_failure",
    2: "failure",
}

# security.access.passive_entry_debug -- PassiveEntryUnlockFailReason
_PASSIVE_ENTRY_FAIL_MAP: Final[dict[int, str]] = {
    1: "not_in_park",
    2: "at_home_disable",
    3: "passenger_in_seat",
    4: "device_not_enabled",
    5: "transport_mode",
    6: "car_wash_mode",
    7: "camp_mode",
    8: "active_ota",
    9: "show_and_tell_mode",
    10: "rcvd_rssi_pending",
    11: "lock_only_at_home",
    12: "car_costume_mode",
    13: "slept_immediate",
}

# comfort.cabin.pet_mode_status
_PET_MODE_STATE_MAP: Final[dict[int, str]] = {
    0: "off",
    1: "on",
    2: "disabled",
    3: "faulty",
}
_PET_MODE_TEMPERATURE_MAP: Final[dict[int, str]] = {
    0: "default",
    1: "cold",
    2: "hot",
    3: "faulty",
}

# security.access.immobilizer_state -- SecureImmoStatus. Note 0 is a REAL value
# here ("not assigned"), not the usual UNSPECIFIED sentinel.
_IMMOBILIZER_MAP: Final[dict[int, str]] = {
    0: "not_assigned",
    1: "not_authorized",
    2: "authorized_to_drive",
}

# dynamics.vehicle.location -- KnownLocation
_KNOWN_LOCATION_MAP: Final[dict[int, str]] = {
    1: "unknown",
    2: "home",
    3: "work",
}


def _decode_enum_fields(
    payload: str, spec: dict[int, tuple[str, dict[int, str] | None]], what: str
) -> dict[str, Any]:
    """Decode a flat message of varint fields into named values.

    `spec` maps field number -> (output key, value map). A None map passes the
    integer through; a map that has no entry for the value drops the field rather
    than inventing a name -- an unmapped enum value is new firmware, and guessing
    at it is how "SNA" became a valid sensor option once already.
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        result: dict[str, Any] = {}
        for field_num, wire_type, value in _decode_protobuf_fields(data):
            if wire_type != 0 or field_num not in spec:
                continue
            key, mapping = spec[field_num]
            if mapping is None:
                result[key] = value
            elif value in mapping:
                result[key] = mapping[value]
        return result
    except Exception:
        _LOGGER.debug("Failed to decode %s payload", what, exc_info=True)
        return {}


def decode_gear(payload: str) -> dict[str, Any]:
    """Decode dynamics.vehicle.gear.

    Returns dict with keys:
        - gearStatus: str
    """
    return _decode_enum_fields(payload, {1: ("gearStatus", _GEAR_MAP)}, "gear")


def decode_drive_mode(payload: str) -> dict[str, Any]:
    """Decode dynamics.vehicle.drive_mode.

    Returns dict with keys:
        - driveMode: str
        - limitedAccelCold: bool
        - limitedRegenCold: bool

    Fields 8 and 9, not 2 and 3. The message skips 2-7 outright, which is the kind
    of thing a hand-guessed layout gets wrong and a transcription does not.
    """
    return _decode_enum_fields(
        payload,
        {
            1: ("driveMode", _DRIVE_MODE_MAP),
            8: ("limitedAccelCold", None),
            9: ("limitedRegenCold", None),
        },
        "drive mode",
    )


def decode_range(payload: str) -> dict[str, Any]:
    """Decode dynamics.vehicle.range.

    Returns dict with keys:
        - distanceToEmpty: int (km -- the sensor's own unit, so no conversion)
        - rangeThreshold: str
        - coldRangeNotification: str
    """
    return _decode_enum_fields(
        payload,
        {
            1: ("distanceToEmpty", None),
            2: ("rangeThreshold", _RANGE_THRESHOLD_MAP),
            3: ("coldRangeNotification", _TEMPERATURE_IMPACT_MAP),
        },
        "range",
    )


def decode_alarm_state(payload: str) -> dict[str, Any]:
    """Decode security.alarm.state.

    Returns dict with keys:
        - alarmSoundStatus: str ("true" / "false" / "signal_not_available")

    The strings are the subscription's own vocabulary, which the sensor's
    value_lambda turns into Active/Inactive. signal_not_available is in
    INVALID_SENSOR_STATES, so it reports as unknown rather than as Inactive.
    """
    return _decode_enum_fields(
        payload,
        {
            1: ("alarmSoundStatus", _ALARM_SOUND_MAP),
            2: ("consecutiveAlarmDisabledNotification", None),
        },
        "alarm state",
    )


def decode_trailer_state(payload: str) -> dict[str, Any]:
    """Decode body.trailer.state.

    Returns dict with keys:
        - trailerStatus: str
    """
    return _decode_enum_fields(
        payload, {1: ("trailerStatus", _TRAILER_PRESENCE_MAP)}, "trailer state"
    )


def decode_pet_mode_status(payload: str) -> dict[str, Any]:
    """Decode comfort.cabin.pet_mode_status.

    Returns dict with keys:
        - petModeStatus: str
        - petModeTemperatureStatus: str
    """
    return _decode_enum_fields(
        payload,
        {
            1: ("petModeStatus", _PET_MODE_STATE_MAP),
            2: ("petModeTemperatureStatus", _PET_MODE_TEMPERATURE_MAP),
        },
        "pet mode status",
    )


def decode_low_voltage_battery(payload: str) -> dict[str, Any]:
    """Decode energy.low_voltage.battery_state.

    Returns dict with keys:
        - twelveVoltBatteryHealth: str
    """
    return _decode_enum_fields(
        payload,
        {1: ("twelveVoltBatteryHealth", _LOW_VOLTAGE_HEALTH_MAP)},
        "low voltage battery",
    )


def decode_video_monitoring(payload: str) -> dict[str, Any]:
    """Decode security.video_monitoring.state.

    Returns dict with keys:
        - gearGuardVideoStatus: str
        - gearGuardVideoMode: str
        - gearGuardVideoTermsAccepted: str
    """
    return _decode_enum_fields(
        payload,
        {
            1: ("gearGuardVideoStatus", _VIDEO_MONITORING_STATUS_MAP),
            2: ("gearGuardVideoMode", _VIDEO_MODE_MAP),
            3: ("gearGuardVideoTermsAccepted", _TOS_ACCEPTANCE_MAP),
        },
        "video monitoring",
    )


def decode_battery_characteristics(payload: str) -> dict[str, Any]:
    """Decode energy.high_voltage.battery_characteristics.

    Returns dict with keys:
        - batteryCellType: str

    Fields 5 and 6 (user_total_kwh, user_max_kwh) are floats and would map to
    batteryCapacity, but they are fixed32 on the wire and _decode_protobuf_fields
    hands those back as raw bytes. Left undecoded rather than misdecoded: the
    subscription already carries batteryCapacity, and a wrong kWh figure on the
    energy sensor is worse than no second source for it.
    """
    return _decode_enum_fields(
        payload,
        {2: ("batteryCellType", _BATTERY_CELL_TYPE_MAP)},
        "battery characteristics",
    )


def decode_btm_diagnosis(payload: str) -> dict[str, Any]:
    """Decode security.access.btm.

    Returns dict with keys:
        - btmFfHardwareFailureStatus, btmIcHardwareFailureStatus,
          btmLfdHardwareFailureStatus, btmRfHardwareFailureStatus,
          btmRfdHardwareFailureStatus, btmOcHardwareFailureStatus: str

    Six of the ten fields share one enum. Fields 7-10 are separate error counters
    with no enum of their own; passed through as integers.
    """
    return _decode_enum_fields(
        payload,
        {
            1: ("btmFfHardwareFailureStatus", _HARDWARE_FAILURE_MAP),
            2: ("btmIcHardwareFailureStatus", _HARDWARE_FAILURE_MAP),
            3: ("btmLfdHardwareFailureStatus", _HARDWARE_FAILURE_MAP),
            4: ("btmRfHardwareFailureStatus", _HARDWARE_FAILURE_MAP),
            5: ("btmRfdHardwareFailureStatus", _HARDWARE_FAILURE_MAP),
            6: ("btmOcHardwareFailureStatus", _HARDWARE_FAILURE_MAP),
        },
        "btm diagnosis",
    )


def decode_vas_fault(payload: str) -> dict[str, Any]:
    """Decode security.access.vas_fault.

    Returns dict with keys:
        - vasSecureElementFaulted: str
        - vasAccessCanFaulted: str

    Both are declared in the gateway schema and neither is subscribed, so this
    topic is the only source for them.
    """
    return _decode_enum_fields(
        payload,
        {
            1: ("vasSecureElementFaulted", _SECURE_ELEMENT_FAULTED_MAP),
            2: ("vasAccessCanFaulted", _ACCESS_CAN_FAULTED_MAP),
        },
        "vas fault",
    )


def decode_passive_entry_debug(payload: str) -> dict[str, Any]:
    """Decode security.access.passive_entry_debug.

    Returns dict with keys:
        - passiveEntryUnlockFailReason: str
    """
    return _decode_enum_fields(
        payload,
        {1: ("passiveEntryUnlockFailReason", _PASSIVE_ENTRY_FAIL_MAP)},
        "passive entry debug",
    )


def decode_immobilizer_state(payload: str) -> dict[str, Any]:
    """Decode security.access.immobilizer_state.

    Returns dict with keys:
        - secureImmobilizerStatus: str

    No gateway field carries this, so it backs no entity yet -- it is decoded so
    the topic stops being an unknown one, and so an entity can be added against
    observed values rather than against a guess.
    """
    return _decode_enum_fields(
        payload, {1: ("secureImmobilizerStatus", _IMMOBILIZER_MAP)}, "immobilizer state"
    )


def decode_known_location(payload: str) -> dict[str, Any]:
    """Decode dynamics.vehicle.location.

    Returns dict with keys:
        - knownLocation: str ("unknown" / "home" / "work")

    Distinct from dynamics.vehicle.gnss, which carries coordinates. This is the
    vehicle's own coarse classification and backs no gateway field.
    """
    return _decode_enum_fields(
        payload, {1: ("knownLocation", _KNOWN_LOCATION_MAP)}, "known location"
    )


RVM_DECODERS: dict[str, Callable[[str], dict[str, Any]]] = {
    "body.closures.states": decode_closures,
    "body.locks.states": decode_locks,
    "charging.session.status": decode_charging_session_status,
    "charging.session.time_estimation": decode_time_estimation,
    "comfort.cabin.cabin_preconditioning_status": decode_preconditioning,
    "comfort.cabin.cabin_temperatures": decode_cabin_temperatures,
    "comfort.cabin.seat_conditioning_status": decode_seat_conditioning_status,
    "comfort.cabin.defrost_defog_status": decode_defrost,
    "dynamics.tires.state": decode_tires,
    "dynamics.vehicle.gnss": decode_gnss,
    "dynamics.vehicle.odometer": decode_odometer,
    "energy.high_voltage.battery_state": decode_battery_state,
    "energy_edge_compute.graphs.charge_session_breakdown": decode_charge_session_breakdown,
    "energy_edge_compute.graphs.charging_graph_global": decode_charging_graph_global,
    "vehicle.power.state": decode_power_state,
    # This fork's RVMs, captured and verified against a real vehicle.
    "comfort.cabin.climate_hold_setting": decode_climate_hold_setting,
    "comfort.cabin.climate_hold_status": decode_climate_hold_status,
    "vehicle.wheels.vehicle_wheels": decode_vehicle_wheels,
    # Transcribed from the app's protobuf classes (f5). Every one of these feeds a
    # field the gateway schema already declares, so the existing sensors pick them
    # up with no entity changes -- and four of them (btmOcHardwareFailureStatus,
    # vasSecureElementFaulted, vasAccessCanFaulted, passiveEntryUnlockFailReason)
    # are declared but NOT subscribed, so Parallax is their only source.
    "body.trailer.state": decode_trailer_state,
    "comfort.cabin.pet_mode_status": decode_pet_mode_status,
    "dynamics.vehicle.drive_mode": decode_drive_mode,
    "dynamics.vehicle.gear": decode_gear,
    "dynamics.vehicle.location": decode_known_location,
    "dynamics.vehicle.range": decode_range,
    "energy.high_voltage.battery_characteristics": decode_battery_characteristics,
    "energy.low_voltage.battery_state": decode_low_voltage_battery,
    "security.access.btm": decode_btm_diagnosis,
    "security.access.immobilizer_state": decode_immobilizer_state,
    "security.access.passive_entry_debug": decode_passive_entry_debug,
    "security.access.vas_fault": decode_vas_fault,
    "security.alarm.state": decode_alarm_state,
    "security.video_monitoring.state": decode_video_monitoring,
}

# Full list of Parallax RVMs subscribed for vehicle & charging telemetry
PARALLAX_RVMS: list[str] = list(RVM_DECODERS.keys())
CHARGING_RVMS: list[str] = [
    "charging.session.notification",
    "charging.session.remote_command",
    "charging.session.soc_slider",
    "charging.session.status",
    "charging.session.time_estimation",
    "energy.high_voltage.battery_state",
    "energy_edge_compute.graphs.charge_session_breakdown",
    "energy_edge_compute.graphs.charging_graph_global",
]


def encode_climate_hold_setting(hold_time_duration_seconds: int) -> bytes:
    """Encode a ClimateHoldSetting payload without the protobuf runtime.

    This is the ONLY message the integration ever encodes: one int32 field, so
    carrying protobuf for it was never proportionate. The wire format is a single
    varint field, verified byte-for-byte against the generated class across a
    parameter grid (tests/fixtures/golden/climate_hold_setting.json) and twice
    against reality -- 08ac02 came back from a real vehicle after a five-minute
    hold, and 08a038 (7200s) is recorded in SENDVEHICLEOPERATION_TEST_RESULTS.md.

    Zero encodes to NOTHING: proto3 omits a field at its default, and the vehicle
    reports an unconfigured hold as an empty payload.
    """
    if hold_time_duration_seconds < 0:
        raise ValueError(
            f"hold duration must not be negative: {hold_time_duration_seconds}"
        )
    if hold_time_duration_seconds == 0:
        return b""
    return _encode_varint_field(1, hold_time_duration_seconds)


# Topics already reported as undecodable. Module-level rather than per-instance:
# decode_parallax_message is a free function and the set is small and bounded by
# the number of topics the server can push.
_WARNED_UNKNOWN_RVMS: set[str] = set()


def decode_parallax_message(
    rvm: str, payload: str, **kwargs: Any
) -> dict[str, Any] | None:
    """Decode a Parallax message payload given its RVM topic.

    Accepts the GraphQL message fields directly (rvm, payload, and optional kwargs/timestamp).
    Returns a dict of decoded fields, or None if no decoder exists for this RVM.
    """
    decoder = RVM_DECODERS.get(rvm)
    if decoder is None:
        # Once per topic, not once per message. SUBSCRIBED_RVMS only ever asks for
        # topics that have a decoder, so reaching here means the server pushed
        # something unrequested -- which it does repeatedly, at telemetry rates.
        # The warning is worth seeing; a warning per message buries the log.
        if rvm not in _WARNED_UNKNOWN_RVMS:
            _WARNED_UNKNOWN_RVMS.add(rvm)
            _LOGGER.warning(
                "Unknown Parallax RVM topic %s -- no decoder; further messages on "
                "this topic will not be logged",
                rvm,
            )
        return None
    return decoder(payload)


# ======================================================================
# WRITE PATH -- outbound Parallax operations (this fork; not in upstream)
# ======================================================================


class SupportsSerializeToString(Protocol):
    """Anything that can serialise itself to protobuf wire bytes.

    Structural, so from_protobuf keeps working for the generated classes during
    development without the package depending on the protobuf runtime at all.
    """

    def SerializeToString(self) -> bytes: ...


class RVMType(StrEnum):
    """Remote Vehicle Module types this client ships.

    Rivian's Android app (EnumC6207c.java) declares 18. Only four are accepted by
    sendVehicleOperation -- the rest return INTERNAL_SERVER_ERROR in BOTH
    directions, recorded in docs/development/SENDVEHICLEOPERATION_TEST_RESULTS.md
    -- so the other 14 were pruned in s09a along with their builders and entities.
    Re-add one only after a live test shows the server accepts it.
    """

    # The one server-verified WRITE.
    CLIMATE_HOLD_SETTING = "comfort.cabin.climate_hold_setting"
    # Verified reads.
    CLIMATE_HOLD_STATUS = "comfort.cabin.climate_hold_status"
    VEHICLE_WHEELS = "vehicle.wheels.vehicle_wheels"
    # Accepted by the server, but it returns an empty payload unless the owner has
    # configured a schedule, so no entity ships for it (see RVM_FIXTURES.md).
    OTA_SCHEDULE_CONFIGURATION = "ota.user_schedule.ota_config"


class ParallaxCommand:
    """Parallax command wrapper for cloud-based vehicle operations.

    Attributes:
        rvm: Remote Vehicle Module type
        payload_b64: Base64-encoded protobuf payload
        command_id: Unique command identifier
    """

    def __init__(self, rvm: RVMType, payload: bytes, command_id: str | None = None):
        """Initialize ParallaxCommand.

        Args:
            rvm: RVM type identifier
            payload: Protobuf message bytes (operation-specific)
            command_id: Optional command UUID (generated if not provided)
        """
        self.rvm = rvm
        self.payload_b64 = base64.b64encode(payload).decode() if payload else ""
        self.command_id = command_id or str(uuid.uuid4())

    @property
    def name(self) -> str:
        """Get command name for logging/debugging."""
        return f"parallax_{self.rvm}"

    @classmethod
    def from_protobuf(
        cls,
        rvm: RVMType,
        message: SupportsSerializeToString,
        command_id: str | None = None,
    ) -> ParallaxCommand:
        """Create ParallaxCommand from a protobuf message.

        Args:
            rvm: RVM type identifier
            message: Protobuf message instance
            command_id: Optional command UUID

        Returns:
            ParallaxCommand instance with serialized message
        """
        payload = message.SerializeToString()
        return cls(rvm, payload, command_id)


# Helper functions for Phase 1 RVM types


def build_climate_status_query() -> ParallaxCommand:
    """Build a query for climate hold status.

    Returns:
        ParallaxCommand for RVM #14 (CLIMATE_HOLD_STATUS)

    Example:
        >>> cmd = build_climate_status_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Read operations use empty payload
    return ParallaxCommand(RVMType.CLIMATE_HOLD_STATUS, b"")


def build_climate_hold_command(duration_minutes: int = 120) -> ParallaxCommand:
    """Build a climate hold command.

    Args:
        duration_minutes: Hold duration in minutes (converted to seconds)

    Returns:
        ParallaxCommand for RVM #12 (CLIMATE_HOLD_SETTING)

    Note:
        Based on APK analysis, ClimateHoldSetting only has one field:
        hold_time_duration_seconds. Temperature and enabled state are not
        part of the protobuf message - they may be controlled separately
        via GraphQL or other commands.

    Example:
        >>> cmd = build_climate_hold_command(120)  # 2 hours
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Hand-rolled: one varint field, verified byte-for-byte against the generated
    # class before it was deleted (tests/fixtures/golden/climate_hold_setting.json).
    payload = encode_climate_hold_setting(duration_minutes * 60)

    return ParallaxCommand(RVMType.CLIMATE_HOLD_SETTING, payload)


def build_vehicle_wheels_query() -> ParallaxCommand:
    """Build a query for vehicle wheels configuration.

    Returns:
        ParallaxCommand for RVM #10 (VEHICLE_WHEELS)

    Example:
        >>> cmd = build_vehicle_wheels_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Read operations use empty payload
    return ParallaxCommand(RVMType.VEHICLE_WHEELS, b"")


def build_ota_schedule_query() -> ParallaxCommand:
    """Build a query for OTA schedule configuration.

    Returns:
        ParallaxCommand for RVM #5 (OTA_SCHEDULE_CONFIGURATION)

    Example:
        >>> cmd = build_ota_schedule_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Read operations use empty payload
    return ParallaxCommand(RVMType.OTA_SCHEDULE_CONFIGURATION, b"")
