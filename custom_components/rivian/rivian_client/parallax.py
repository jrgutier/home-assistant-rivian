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

# The app's CABIN_DEFROST_DEFOG_LEVEL (`lv5`, 3.16.0). Emitted in the casing the
# defrost sensor and climate.py already compare against.
DEFROST_DEFOG_MAP = {
    1: "Defog",
    2: "Defrost",
    3: "Defog_Defrost",
    4: "Off",
}

# The app's CABIN_PRECONDITIONING_STATE (`p22`, bound, 3.16.0), prefix-stripped
# and lowercased. 5 is TIMEOUT_TEMP_NOT_ACHIEVED in the app; it is spelled out
# here to land on the sensor's existing "Timeout Temperature Not Achieved".
PRECONDITIONING_STATE_MAP = {
    0: "undefined",
    1: "initiate",
    2: "active",
    3: "active_warning",
    4: "complete_maintain",
    5: "timeout_temperature_not_achieved",
    6: "error_soc_low",
    7: "error_system_fault",
    8: "unavailable",
    9: "timeout_complete",
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

    `charge_state` has two fields in the app (`bc1`, 3.16.0): #1
    charge_percentage and #2 charge_kwh, both double. An earlier #3 "rangeKm"
    read here does not exist in either app build or in any capture.
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

    Layout is the app's `nl2` (3.16.0; `uncalled_parse_wrappers`), the only
    message class in either app build whose fields fit the live capture:

        1 total_kwh float          8 range_added_kms uint32
        2 pack_kwh float           9 current_power float
        3 thermal_kwh float       10 current_range_per_hour uint32
        4 outlets_kwh float       11 session_cost message
        5 system_kwh float        12 is_free_session bool
        6 session_duration_mins   13 charging_state enum
        7 time_remaining_mins

    Field 10 was previously read as an integer kW figure, so a completed
    session reported 2.0 kW; it is the range rate. proto3 omits a zero, so a
    non-empty frame without #8, #9 or #10 means zero, not "unknown".

    Returns dict with keys matching legacy getLiveSessionData field names:
        - totalChargedEnergy: float (kWh)
        - power: float (kW)
        - rangeAddedThisSession: int (km)
        - kilometersChargedPerHour: int (km/h)
    """
    if not payload:
        return {}
    try:
        fields = _decode_protobuf_fields(base64.b64decode(payload))
        if not fields:
            return {}
        result: dict[str, Any] = {
            "power": 0.0,
            "rangeAddedThisSession": 0,
            "kilometersChargedPerHour": 0,
        }
        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 5:
                result["totalChargedEnergy"] = round(value, 4)
            elif field_num == 8 and wire_type == 0:
                result["rangeAddedThisSession"] = value
            elif field_num == 9 and wire_type == 5:
                result["power"] = round(value, 2)
            elif field_num == 10 and wire_type == 0:
                result["kilometersChargedPerHour"] = value
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
        - defrostDefogStatus: str ("Defog", "Defrost", "Defog_Defrost", "Off")

    Previously only 2 was recognised and every other value read as "Off", so
    defog alone, or defog with defrost, showed the system as off.
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}
        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 0 and value in DEFROST_DEFOG_MAP:
                result["defrostDefogStatus"] = DEFROST_DEFOG_MAP[value]
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

    Field 1 is the app's CABIN_PRECONDITIONING_STATE (`p22`); see
    PRECONDITIONING_STATE_MAP. An empty payload is the proto3 encoding of 0,
    UNSPECIFIED, which the sensor already renders as "Undefined".

    Previously 2 read as "initiate" (it is ACTIVE) and everything outside 1, 2
    and 4 read as "off", including a running hold with a warning (3).

    Returns dict with keys:
        - cabinPreconditioningStatus: str
    """
    if not payload:
        return {"cabinPreconditioningStatus": PRECONDITIONING_STATE_MAP[0]}
    try:
        status_val = 0
        for field_num, wire_type, value in _decode_protobuf_fields(
            base64.b64decode(payload)
        ):
            if field_num == 1 and wire_type == 0:
                status_val = value
        if status_val not in PRECONDITIONING_STATE_MAP:
            return {}
        return {"cabinPreconditioningStatus": PRECONDITIONING_STATE_MAP[status_val]}
    except Exception:
        _LOGGER.debug("Failed to decode preconditioning payload", exc_info=True)
        return {}


# charging.session.time_estimation -- the app's VALIDITY_FLAG (`o9k` field 1).
# NONE (0) is what the live capture carries alongside a real estimate, so only
# the two values that say the estimate is meaningless suppress it.
_TIME_ESTIMATE_INVALID = frozenset({2, 3})  # INVALID, PACK_DISCHARGING


def decode_time_estimation(payload: str) -> dict[str, Any]:
    """Decode charging.session.time_estimation.

    The app's `o9k` (bound, 3.16.0): #1 validity_flag enum, #2
    remaining_minutes uint32. Field 1 used to be read as the remaining time,
    which never matched a real frame -- the capture is `1040`, field 2 = 64 --
    so this returned {} on every one.

    Returns dict with keys:
        - timeToEndOfCharge: int (minutes, the sensor's own unit)
    """
    if not payload:
        return {}
    try:
        validity = 0
        minutes = 0
        for field_num, wire_type, value in _decode_protobuf_fields(
            base64.b64decode(payload)
        ):
            if field_num == 1 and wire_type == 0:
                validity = value
            elif field_num == 2 and wire_type == 0:
                minutes = value
        if validity in _TIME_ESTIMATE_INVALID:
            return {}
        return {"timeToEndOfCharge": minutes}
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


# comfort.cabin.seat_conditioning_status -- the app's `c1i` (bound, 3.16.0):
# one repeated field #1 `levels`, each {#1 instance, #2 device, #3 level}.
#
# This decoder used to read fields 7-12 as one submessage per seat. Those are
# the field numbers of `mtm`, the app's vehicle-state *preconditioning* blob
# (`seat_heat_status_front_left = 7` ...), not of this topic's message, so it
# returned {} on every real frame.
#
# CABIN_SURFACE_INSTANCE -> the gateway field prefix. Glass, mirrors, wiper area
# and the middle seats have no gateway field and are dropped.
SEAT_INSTANCES = {
    1: "steeringWheel",  # STEERING_WHEEL
    5: "seatFrontLeft",  # ROW_1_LEFT_SEAT
    7: "seatFrontRight",  # ROW_1_RIGHT_SEAT
    8: "seatRearLeft",  # ROW_2_LEFT_SEAT
    10: "seatRearRight",  # ROW_2_RIGHT_SEAT
    11: "seatThirdRowLeft",  # ROW_3_LEFT_SEAT
    13: "seatThirdRowRight",  # ROW_3_RIGHT_SEAT
}
SEAT_DEVICES = {1: "Heat", 2: "Vent"}  # CABIN_SURFACE_DEVICE
# Only names the gateway schema declares are emitted.
SEAT_FIELDS = frozenset(
    {
        "steeringWheelHeat",
        "seatFrontLeftHeat",
        "seatFrontLeftVent",
        "seatFrontRightHeat",
        "seatFrontRightVent",
        "seatRearLeftHeat",
        "seatRearRightHeat",
        "seatThirdRowLeftHeat",
        "seatThirdRowRightHeat",
    }
)
# CABIN_SURFACE_LEVEL has no OFF member: 0 is UNSPECIFIED and 1-3 are LEVEL1-3.
# An entry naming a surface with no level is therefore how "present, not on" is
# encoded -- the live capture lists all nine heaters and vents that way on a
# parked truck. Strings match the GraphQL vocabulary ("Off", "Level_1", ...).
SEAT_LEVELS = {0: "Off", 1: "Level_1", 2: "Level_2", 3: "Level_3"}


def decode_seat_conditioning_status(payload: str) -> dict[str, Any]:
    """Decode comfort.cabin.seat_conditioning_status.

    Returns dict with keys, for each surface the vehicle lists:
        - seatFrontLeftHeat, seatFrontRightHeat, seatRearLeftHeat,
          seatRearRightHeat, seatThirdRowLeftHeat, seatThirdRowRightHeat,
          seatFrontLeftVent, seatFrontRightVent, steeringWheelHeat
          ("Off" / "Level_1" / "Level_2" / "Level_3")
    """
    if not payload:
        return {}
    try:
        result: dict[str, Any] = {}
        for field_num, wire_type, value in _decode_protobuf_fields(
            base64.b64decode(payload)
        ):
            if field_num != 1 or wire_type != 2:
                continue
            instance = device = level = 0
            for in_num, in_type, in_val in _decode_protobuf_fields(value):
                if in_type != 0:
                    continue
                if in_num == 1:
                    instance = in_val
                elif in_num == 2:
                    device = in_val
                elif in_num == 3:
                    level = in_val
            if instance not in SEAT_INSTANCES or device not in SEAT_DEVICES:
                continue
            key = SEAT_INSTANCES[instance] + SEAT_DEVICES[device]
            if key in SEAT_FIELDS and level in SEAT_LEVELS:
                result[key] = SEAT_LEVELS[level]
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
    batteryCapacity, but they are fixed32 (wire type 5) and _decode_enum_fields
    reads varints only. Left undecoded rather than misdecoded: the
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
    with no enum of their own, are not in the spec below, and so are dropped.
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


def _submessage(
    data: bytes, spec: dict[int, tuple[str, dict[int, str] | None]]
) -> dict[str, Any]:
    """Decode a nested message's varint and string fields against `spec`."""
    out: dict[str, Any] = {}
    for num, wire, value in _decode_protobuf_fields(data):
        if num not in spec:
            continue
        key, mapping = spec[num]
        if wire == 2 and isinstance(value, bytes):
            try:
                out[key] = value.decode("utf-8")
            except UnicodeDecodeError:
                continue
        elif wire == 0:
            if mapping is None:
                out[key] = value
            elif value in mapping:
                out[key] = mapping[value]
    return out


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


def decode_network_state(payload: str) -> dict[str, Any]:
    """Decode vehicle.network.state.

    Returns the wifi* and cellular* fields the gateway schema declares. See the
    block comment above for why this binding is an inference rather than a read
    parse site, and what the cost of being wrong is.
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        result: dict[str, Any] = {}
        for field_num, wire_type, value in _decode_protobuf_fields(data):
            if wire_type != 2 or not isinstance(value, bytes):
                continue
            if field_num == 4:
                result |= _submessage(value, _WIFI_SPEC)
            elif field_num == 5:
                result |= _submessage(value, _CELLULAR_SPEC)
        return result
    except Exception:
        _LOGGER.debug("Failed to decode network state payload", exc_info=True)
        return {}


# --- s34 decoders -----------------------------------------------------------
#
# Written from the NAMED schemas in `rivian_client/proto/*.proto`, which carry
# field names, types and enum vocabularies and are bound to topics by `// RVM:`
# comment. No signature-matching against obfuscated classes was needed:
# `PARALLAX_DECODERS.md` closed that search over all 32,941 files, and every
# dispatch-bound topic was already decoded.
#
# Value vocabularies follow the existing convention -- the enum name with its
# common prefix stripped and lowercased -- so these feed the same strings the
# GraphQL path already emits.

# CORRECTION (s43): the two enums below are NOT the ones in
# rivian_security.proto. That file's numbering came from the 3.6.0 transcription
# and is offset from the wire. The app's own classes -- `vpl` (user_consent) and
# `uc5` (daily_limit, next_reset_time_unix_sec), 3.16.0 uncalled parse wrappers
# whose field names match these topics -- give the numbers used here. The live
# consent capture is 2, which the old map read as not_consented. The APK is the
# authority, and the proto file has been corrected to match.
_GEAR_GUARD_CONSENT: Final[dict[int, str]] = {
    0: "unknown",
    1: "not_applicable",
    2: "consented",
    3: "not_consented",
}

_GEAR_GUARD_DAILY_LIMIT: Final[dict[int, str]] = {
    0: "undefined",
    1: "hit",
    2: "not_hit",
}

# EnergyDistribution field number -> key suffix (rivian_energy.proto:7-17).
_ENERGY_DISTRIBUTION: Final[dict[int, str]] = {
    1: "totalKwh",
    2: "thermalKwh",
    3: "outletsKwh",
    4: "systemKwh",
    5: "gearGuardKwh",
    6: "totalRange",
    7: "thermalRange",
    8: "outletsRange",
    9: "systemRange",
    10: "gearGuardRange",
}


def decode_cabin_ventilation_setting(payload: str) -> dict[str, Any]:
    """Decode comfort.cabin.cabin_ventilation_setting.

    Schema: `rivian_climate.proto:49`. `REMAINING_APK_GAPS.md` lists this RVM as
    undecoded and wanted; the WRITE path is separately recorded as ISE, so this
    reads state that cannot currently be set from here.

    Returns dict with keys:
        - cabinVentilationEnabled: bool
        - cabinVentilationMode: str ("AUTO" | "MANUAL" | "OFF"), when sent
        - cabinVentilationWindowsOpenPercent: int, when sent
        - cabinVentilationSunroofOpenPercent: int, when sent
        - cabinVentilationDurationMinutes: int, when sent
    """
    if not payload:
        return {}
    try:
        result: dict[str, Any] = {}
        for field_num, wire_type, value in _decode_protobuf_fields(
            base64.b64decode(payload)
        ):
            if field_num == 1 and wire_type == 0:
                result["cabinVentilationEnabled"] = bool(value)
            elif field_num == 2 and wire_type == 2:
                result["cabinVentilationMode"] = value.decode("utf-8", "replace")
            elif field_num == 3 and wire_type == 0:
                result["cabinVentilationWindowsOpenPercent"] = value
            elif field_num == 4 and wire_type == 0:
                result["cabinVentilationSunroofOpenPercent"] = value
            elif field_num == 5 and wire_type == 0:
                result["cabinVentilationDurationMinutes"] = value
        return result
    except Exception:  # noqa: BLE001 -- a bad frame must not take the subscription down
        return {}


def decode_gear_guard_streaming_consent(payload: str) -> dict[str, Any]:
    """Decode gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent.

    Schema: `rivian_security.proto:38`.

    Returns dict with keys:
        - gearGuardStreamingConsent: str
          (consented | not_consented | not_applicable | unknown | unrecognized)
    """
    if not payload:
        return {}
    try:
        result: dict[str, Any] = {}
        for field_num, wire_type, value in _decode_protobuf_fields(
            base64.b64decode(payload)
        ):
            if field_num == 1 and wire_type == 0:
                result["gearGuardStreamingConsent"] = _GEAR_GUARD_CONSENT.get(
                    value, "unrecognized"
                )
        return result
    except Exception:  # noqa: BLE001
        return {}


def decode_gear_guard_streaming_daily_limit(payload: str) -> dict[str, Any]:
    """Decode gearguard_streaming.privacy.gearguard_streaming_daily_limit.

    Schema: `rivian_security.proto:53`.

    The reset timestamp is emitted verbatim. The observed fixture carries a value
    in the past relative to its capture date, which is recorded rather than
    corrected -- interpreting it as anything but "what the vehicle said" would be
    a guess about semantics this frame does not establish.

    Returns dict with keys:
        - gearGuardStreamingDailyLimit: str
          (not_hit | hit | undefined | unrecognized)
        - gearGuardStreamingLimitResetTime: int (epoch seconds), when sent
    """
    if not payload:
        return {}
    try:
        result: dict[str, Any] = {}
        for field_num, wire_type, value in _decode_protobuf_fields(
            base64.b64decode(payload)
        ):
            if field_num == 1 and wire_type == 0:
                result["gearGuardStreamingDailyLimit"] = _GEAR_GUARD_DAILY_LIMIT.get(
                    value, "unrecognized"
                )
            elif field_num == 2 and wire_type == 0:
                result["gearGuardStreamingLimitResetTime"] = value
        return result
    except Exception:  # noqa: BLE001
        return {}


def decode_parked_energy_distributions(payload: str) -> dict[str, Any]:
    """Decode energy_edge_compute.graphs.parked_energy_distributions.

    Schema: `rivian_energy.proto:23`, three `EnergyDistribution` submessages.
    Emitted as nested dicts rather than 30 flattened keys, because the three
    windows are the same ten measurements over different periods and flattening
    would invent thirty names for ten concepts.

    Returns dict with keys:
        - parkedEnergyLast24Hours: dict[str, float]
        - parkedEnergyLast8Hours: dict[str, float]
        - parkedEnergyLastParkSession: dict[str, float]
    """
    if not payload:
        return {}
    windows = {
        1: "parkedEnergyLast24Hours",
        2: "parkedEnergyLast8Hours",
        3: "parkedEnergyLastParkSession",
    }
    try:
        result: dict[str, Any] = {}
        for field_num, wire_type, value in _decode_protobuf_fields(
            base64.b64decode(payload)
        ):
            if field_num not in windows or wire_type != 2:
                continue
            window: dict[str, float] = {}
            for sub_num, sub_wt, sub_val in _decode_protobuf_fields(value):
                # `_decode_protobuf_fields` already unpacks wire type 5 as a
                # float, so no reinterpretation is needed. Re-packing it as an
                # int here raised, and the broad except below swallowed it into
                # an empty result -- silent, and only caught by decoding a real
                # fixture rather than trusting the code path.
                if sub_wt == 5 and sub_num in _ENERGY_DISTRIBUTION:
                    window[_ENERGY_DISTRIBUTION[sub_num]] = round(sub_val, 4)
            if window:
                result[windows[field_num]] = window
        return result
    except Exception:  # noqa: BLE001
        return {}


# --- s44: the five APK-bound topics that had no decoder ----------------------
#
# Each is bound in the app (`apk_parallax_schema_<ver>.json`, s42) and four have
# a live capture. Where the gateway already names the value -- batteryLimit,
# remoteChargingAvailable, chargerDerateStatus, the ota* family -- these emit that
# name in the GraphQL casing, so they feed the existing entities and the gap-fill
# rule keeps the subscription in charge wherever it delivers. Only the fault
# chime and the trip-target SOC are new keys (PARALLAX_ONLY_FIELDS).


def _gql_case(name: str) -> str:
    """READY_TO_INSTALL -> Ready_To_Install, the GraphQL path's casing."""
    return "_".join(word.capitalize() for word in name.lower().split("_"))


def decode_soc_slider(payload: str) -> dict[str, Any]:
    """Decode charging.session.soc_slider -- `hgh` #1 user_soc_limit (%).

    Returns dict with keys:
        - batteryLimit: int (percent)
    """
    if not payload:
        return {}
    try:
        for field_num, wire_type, value in _decode_protobuf_fields(
            base64.b64decode(payload)
        ):
            if field_num == 1 and wire_type == 0:
                return {"batteryLimit": value}
        return {}
    except Exception:
        _LOGGER.debug("Failed to decode soc_slider payload", exc_info=True)
        return {}


# `dsg` #1 start_available: 0 SNA, 1 FALSE, 2 TRUE. The gateway's
# remoteChargingAvailable is an int, 1 = available (switch.py reads `== 1`).
_START_AVAILABLE: Final[dict[int, int]] = {1: 0, 2: 1}


def decode_remote_command(payload: str) -> dict[str, Any]:
    """Decode charging.session.remote_command.

    Despite the topic name this is not a command: it says whether a remote
    charge start is available. SNA (0, or an empty payload) emits nothing.

    Returns dict with keys:
        - remoteChargingAvailable: int (0 / 1)
    """
    if not payload:
        return {}
    try:
        for field_num, wire_type, value in _decode_protobuf_fields(
            base64.b64decode(payload)
        ):
            if field_num == 1 and wire_type == 0 and value in _START_AVAILABLE:
                return {"remoteChargingAvailable": _START_AVAILABLE[value]}
        return {}
    except Exception:
        _LOGGER.debug("Failed to decode remote_command payload", exc_info=True)
        return {}


# `wwd` #2 DERATE_STATUS and #3 FAULT_CHIME (3.16.0), prefix-stripped.
#
# Derate follows what the APP does with it (FOLLOWUP_S45.md, c97.java:296-333):
# it maps exactly seven members onto chargerDerateStatus and, for the other
# eleven, keeps the previous value. So do we -- an unmapped member emits
# nothing. Upper-case because that is the gateway's chargerDerateStatus
# vocabulary ("NONE" in every community capture). #1 unexpected_stop_reason has
# no enum in any of 54 app versions, so it is not decoded.
_DERATE_STATUS: Final[dict[int, str]] = {
    0: "NONE",
    4: "EVSE_DERATING",
    5: "NEARING_TOC",
    6: "NEAR_TOC_LFP_BATT_CALIBRATING",
    8: "BATTERY_HEATING",
    9: "BATTERY_COOLING",
    3: "AC_WARM_PLUG",
}
_FAULT_CHIME: Final[dict[int, str]] = {
    0: "none",
    1: "charging_disabled_all",
    2: "charging_disabled_dc",
    3: "charging_disabled_pin_temp_dc",
    4: "charging_disabled_pin_temp_gradient_dc",
    5: "charging_degraded_dc",
    6: "charging_disabled_ac",
    7: "charging_disabled_pin_temp_ac",
    8: "charging_degraded_ac",
    9: "charging_disabled_partial_connection",
    10: "charging_disabled_not_parked",
}


def decode_charging_notification(payload: str) -> dict[str, Any]:
    """Decode charging.session.notification.

    proto3 omits a zero, so a frame without #2 or #3 is saying NONE for it --
    the live capture (`0801`) carries only #1. An empty payload says NONE for
    both.

    Returns dict with keys:
        - chargerDerateStatus: str ("NONE", "BATTERY_HEATING", ...)
        - chargingFaultChime: str ("none", "charging_disabled_dc", ...)
    """
    try:
        derate = chime = 0
        for field_num, wire_type, value in _decode_protobuf_fields(
            base64.b64decode(payload or "")
        ):
            if field_num == 2 and wire_type == 0:
                derate = value
            elif field_num == 3 and wire_type == 0:
                chime = value
        result: dict[str, Any] = {}
        if derate in _DERATE_STATUS:
            result["chargerDerateStatus"] = _DERATE_STATUS[derate]
        if chime in _FAULT_CHIME:
            result["chargingFaultChime"] = _FAULT_CHIME[chime]
        return result
    except Exception:
        _LOGGER.debug("Failed to decode charging notification payload", exc_info=True)
        return {}


# 0xFFFF in trip_target #2 is the no-estimate sentinel: the only live frame
# (`10ffff03`, s46) carries it with no #1 SOC, i.e. no trip target is set. The
# app passes #2 through unmodified, so where it filters this is not traced;
# suppressing it is an inference, but 65535 minutes rendered as 45 days is not.
_TRIP_TARGET_NO_ESTIMATE: Final = 0xFFFF


def decode_trip_target(payload: str) -> dict[str, Any]:
    """Decode charging.session.trip_target -- `d5l`.

    #1 soc and #2 time_estimate, which the app passes unmodified into its
    chargingTripTargetMinsRemaining (FOLLOWUP_S45.md, c97.java:591) -- minutes.
    #3 status has no enum in any app version and is not emitted.

    Returns dict with keys, when sent:
        - tripTargetSoc: int (percent)
        - tripTargetMinutesRemaining: int (minutes)
    """
    if not payload:
        return {}
    try:
        result: dict[str, Any] = {}
        for field_num, wire_type, value in _decode_protobuf_fields(
            base64.b64decode(payload)
        ):
            if field_num == 1 and wire_type == 0:
                result["tripTargetSoc"] = value
            elif (
                field_num == 2 and wire_type == 0 and value != _TRIP_TARGET_NO_ESTIMATE
            ):
                result["tripTargetMinutesRemaining"] = value
        return result
    except Exception:
        _LOGGER.debug("Failed to decode trip_target payload", exc_info=True)
        return {}


_OTA_SOFTWARE_CATEGORY_FIRMWARE: Final = 1
_OTA_STATUS: Final[dict[int, str]] = {
    1: "IDLE",
    2: "READY_TO_DOWNLOAD",
    3: "FAULT",
    4: "CONNECTION_LOST",
    5: "INSTALL_COUNTDOWN",
    6: "PREPARING",
    7: "DOWNLOADING",
    8: "READY_TO_INSTALL",
    9: "SCHEDULED_TO_INSTALL",
    10: "AWAITING_INSTALL",
    11: "INSTALLING",
    12: "INSTALL_SUCCESS",
    13: "DOWNLOAD_FAILED",
    14: "INSTALL_FAILED",
}
_OTA_CURRENT_STATUS: Final[dict[int, str]] = {
    1: "INSTALL_SUCCESS",
    2: "INSTALL_FAILED",
    3: "INSTALL_UNABLE_TO_START",
}


def _ota_version(data: bytes, prefix: str) -> dict[str, Any]:
    """The app's software version message: 1 version, 3 year, 4 week,
    5 number, 6 git_hash (2 software_version_id has no gateway field)."""
    names = {1: "", 3: "Year", 4: "Week", 5: "Number", 6: "GitHash"}
    out: dict[str, Any] = {}
    for num, wt, val in _decode_protobuf_fields(data):
        if num not in names:
            continue
        if num in (1, 6) and wt == 2:
            out[prefix + names[num]] = val.decode("utf-8", "replace")
        elif num in (3, 4, 5) and wt == 0:
            out[prefix + names[num]] = val
    return out


def _ota_progress(data: bytes) -> dict[str, Any]:
    """`ota_progress`: 1 ota_status, 2 ota_current_status, 3 download and
    4 install progress, each with progress_percent on #2 (a oneof member, so
    serialised even at 0), and 7 install_ready.

    install_ready is a bool the app turns into the gateway's own strings,
    "ota_available" / "ota_not_available" (FOLLOWUP_S45.md, uf7.java:1778).
    proto3 omits False, so a progress message without #7 is not ready.
    """
    out: dict[str, Any] = {"otaInstallReady": "ota_not_available"}
    for num, wt, val in _decode_protobuf_fields(data):
        if num == 1 and wt == 0 and val in _OTA_STATUS:
            out["otaStatus"] = _gql_case(_OTA_STATUS[val])
        elif num == 2 and wt == 0 and val in _OTA_CURRENT_STATUS:
            out["otaCurrentStatus"] = _gql_case(_OTA_CURRENT_STATUS[val])
        elif num == 7 and wt == 0:
            out["otaInstallReady"] = "ota_available" if val else "ota_not_available"
        elif num in (3, 4) and wt == 2:
            key = "otaDownloadProgress" if num == 3 else "otaInstallProgress"
            for p_num, p_wt, p_val in _decode_protobuf_fields(val):
                if p_num == 2 and p_wt == 0:
                    out[key] = p_val
    return out


def decode_ota_deployment_state(payload: str) -> dict[str, Any]:
    """Decode ota.deployment.state -- `r1e` (bound, 3.16.0).

    Repeated #1 `softwares`, one per category; only FIRMWARE feeds the ota*
    fields (HD maps and vehicle config have none). Within it: #2 the installed
    version, #4 `available_ota` with its own #2 version and #5 progress.

    Values use the gateway's casing (`Ready_To_Install`), which update.py
    compares against. Fields the app has no unit or vocabulary for -- install
    time, duration, OTA type -- are not emitted.

    Returns dict with keys, each only when sent:
        - otaCurrentVersion, otaCurrentVersionYear/Week/Number/GitHash
        - otaAvailableVersion, otaAvailableVersionYear/Week/Number/GitHash
        - otaStatus, otaCurrentStatus, otaDownloadProgress, otaInstallProgress,
          otaInstallReady ("ota_available" / "ota_not_available")
    """
    if not payload:
        return {}
    try:
        for field_num, wire_type, value in _decode_protobuf_fields(
            base64.b64decode(payload)
        ):
            if field_num != 1 or wire_type != 2:
                continue
            sub = _decode_protobuf_fields(value)
            category = next((v for n, w, v in sub if n == 1 and w == 0), 0)
            if category != _OTA_SOFTWARE_CATEGORY_FIRMWARE:
                continue
            result: dict[str, Any] = {}
            for num, wt, val in sub:
                if num == 2 and wt == 2:
                    result |= _ota_version(val, "otaCurrentVersion")
                elif num == 4 and wt == 2:
                    for a_num, a_wt, a_val in _decode_protobuf_fields(val):
                        if a_num == 2 and a_wt == 2:
                            result |= _ota_version(a_val, "otaAvailableVersion")
                        elif a_num == 5 and a_wt == 2:
                            result |= _ota_progress(a_val)
            return result
        return {}
    except Exception:
        _LOGGER.debug("Failed to decode ota.deployment.state payload", exc_info=True)
        return {}


# --- s45: name-matched topics --------------------------------------------------
#
# Owner decision: decode the topics the app subscribes to but never parses,
# using the app's own message class whose field names match the topic -- an
# uncalled parse wrapper in `apk/schema/uncalled_parse_wrappers_<ver>.json`.
# That is a NAME-MATCH, not a binding read off a dispatch site, the same class
# of inference vehicle.network.state already is. Each decoder names its class.
# Key material, encrypted payloads and storage ids are never emitted.


def _fields(payload: str) -> list[tuple[int, int, Any]]:
    return _decode_protobuf_fields(base64.b64decode(payload))


def _timestamp_seconds(data: bytes) -> int | None:
    """google.protobuf.Timestamp -> epoch seconds (nanos dropped)."""
    for num, wt, val in _decode_protobuf_fields(data):
        if num == 1 and wt == 0:
            return val
    return None


# `zzn` (3.16.0): repeated #1 states {#1 window_instance, #2 calibration_status}.
_WINDOW_CALIBRATION_FIELDS: Final[dict[int, str]] = {
    1: "windowFrontLeftCalibrated",
    2: "windowFrontRightCalibrated",
    3: "windowRearLeftCalibrated",
    4: "windowRearRightCalibrated",
    # 5 WINDOW_INSTANCE_REAR has no gateway field
}
# CALIBRATION_STATUS, in the gateway's casing ("Calibrated" in every capture)
_WINDOW_CALIBRATION: Final[dict[int, str]] = {1: "Calibrated", 2: "Not_Calibrated"}


def decode_window_states(payload: str) -> dict[str, Any]:
    """Decode body.windows.states (name-match: `zzn`).

    Returns dict with keys window{FrontLeft,FrontRight,RearLeft,RearRight}Calibrated.
    """
    if not payload:
        return {}
    try:
        result: dict[str, Any] = {}
        for num, wt, val in _fields(payload):
            if num != 1 or wt != 2:
                continue
            instance = status = 0
            for in_num, in_wt, in_val in _decode_protobuf_fields(val):
                if in_wt == 0 and in_num == 1:
                    instance = in_val
                elif in_wt == 0 and in_num == 2:
                    status = in_val
            if instance in _WINDOW_CALIBRATION_FIELDS and status in _WINDOW_CALIBRATION:
                result[_WINDOW_CALIBRATION_FIELDS[instance]] = _WINDOW_CALIBRATION[
                    status
                ]
        return result
    except Exception:
        _LOGGER.debug("Failed to decode body.windows.states payload", exc_info=True)
        return {}


def decode_hvac_settings_status(payload: str) -> dict[str, Any]:
    """Decode comfort.cabin.hvac_settings_status (name-match: `e9a`).

    #1 set_temperature_celsius, float. The capture (`0d0000a841`) is 21.0.

    Returns dict with keys:
        - hvacSetTemperature: float (Celsius)
    """
    if not payload:
        return {}
    try:
        for num, wt, val in _fields(payload):
            if num == 1 and wt == 5:
                return {"hvacSetTemperature": round(val, 1)}
        return {}
    except Exception:
        _LOGGER.debug("Failed to decode hvac_settings_status payload", exc_info=True)
        return {}


# `uql` #1 in_service and #2 car_wash: MODE_STATUS 0 UNSPECIFIED, 1 ON. The
# enum has no OFF member, so 0 -- which proto3 omits -- is how "not on" is
# encoded. Emitted as the gateway's serviceMode / carWashMode ("on" / "off").
# #3-#7 (pet_mode, camp_mode, transport_mode, climate_keep, factory_mode) use
# enums the s42 extraction could not attribute and are not decoded.
_USER_MODE_FIELDS: Final[dict[int, str]] = {1: "serviceMode", 2: "carWashMode"}


def decode_user_modes(payload: str) -> dict[str, Any]:
    """Decode comfort.user_modes.state (name-match: `uql`).

    Returns dict with keys:
        - serviceMode, carWashMode: str ("on" / "off")
    """
    try:
        result = dict.fromkeys(_USER_MODE_FIELDS.values(), "off")
        for num, wt, val in _fields(payload or ""):
            if num in _USER_MODE_FIELDS and wt == 0 and val == 1:
                result[_USER_MODE_FIELDS[num]] = "on"
        return result
    except Exception:
        _LOGGER.debug("Failed to decode user_modes payload", exc_info=True)
        return {}


# `fre` #2 CCC_PASSIVE_PERMISSION_STATUS (3.16.0)
_CCC_PASSIVE_PERMISSION: Final[dict[int, str]] = {
    0: "sna",
    1: "disabled",
    2: "enabled",
}


def decode_passive_entry_state(payload: str) -> dict[str, Any]:
    """Decode vehicle_access.{state.passive_entry,passive_entry.passive_entry}.

    `fre` is BOUND, request-side, to vehicle_access.passive_entry.passive_entry:
    the app builds it and sends it there as a PARALLAX_OPERATION_REQUEST
    (FOLLOWUP_S45.md, wy9.java:2225-2234). It never parses one. Reading the
    vehicle's publication on that topic, and on the .state sibling (a
    name-match), as the same message is the inference here.

    Returns dict with keys:
        - passiveEntryBluetoothInCcc: bool (#1)
        - cccPassivePermissionStatus: str (#2)
    """
    try:
        result: dict[str, Any] = {
            "passiveEntryBluetoothInCcc": False,
            "cccPassivePermissionStatus": _CCC_PASSIVE_PERMISSION[0],
        }
        for num, wt, val in _fields(payload or ""):
            if num == 1 and wt == 0:
                result["passiveEntryBluetoothInCcc"] = bool(val)
            elif num == 2 and wt == 0 and val in _CCC_PASSIVE_PERMISSION:
                result["cccPassivePermissionStatus"] = _CCC_PASSIVE_PERMISSION[val]
        return result
    except Exception:
        _LOGGER.debug("Failed to decode passive_entry state payload", exc_info=True)
        return {}


_GEOFENCE_TYPE: Final[dict[int, str]] = {0: "custom", 1: "home", 2: "work"}


def decode_favorite_geofences(payload: str) -> dict[str, Any]:
    """Decode geofence.geofence_service.favoriteGeofences (name-match: `wq7`).

    Repeated #1 favorites {#1 type (0 CUSTOM, 1 HOME, 2 WORK), #2 name}.

    Returns dict with keys:
        - favoriteGeofences: list[{"type": str, "name": str}]
    """
    try:
        favorites: list[dict[str, str]] = []
        for num, wt, val in _fields(payload or ""):
            if num != 1 or wt != 2:
                continue
            entry = {"type": _GEOFENCE_TYPE[0], "name": ""}
            for in_num, in_wt, in_val in _decode_protobuf_fields(val):
                if in_num == 1 and in_wt == 0:
                    entry["type"] = _GEOFENCE_TYPE.get(in_val, "unknown")
                elif in_num == 2 and in_wt == 2:
                    entry["name"] = in_val.decode("utf-8", "replace")
            favorites.append(entry)
        return {"favoriteGeofences": favorites}
    except Exception:
        _LOGGER.debug("Failed to decode favoriteGeofences payload", exc_info=True)
        return {}


def decode_vehicle_ota_state(payload: str) -> dict[str, Any]:
    """Decode ota.ota_state.vehicle_ota_state (name-match: `ugm`).

    #1 id (string), #2 install_time_epoch (Timestamp). The capture carries only
    the id, the literal "VehicleOTAState", so it decodes to {}.

    Returns dict with keys:
        - otaOneTimeInstallTime: int (epoch seconds), when sent
    """
    if not payload:
        return {}
    try:
        for num, wt, val in _fields(payload):
            if num == 2 and wt == 2 and (ts := _timestamp_seconds(val)) is not None:
                return {"otaOneTimeInstallTime": ts}
        return {}
    except Exception:
        _LOGGER.debug("Failed to decode vehicle_ota_state payload", exc_info=True)
        return {}


def decode_ota_config(payload: str) -> dict[str, Any]:
    """Decode ota.user_schedule.ota_config (name-match: `rfe`).

    Repeated #1 schedules {#1 id, #2 isenabled, #3 repeatsdaily {#1 startsatmin,
    #2 geofence {#1 location}}, #4 singleoccurrence {#1 startsatutc}}.

    Returns dict with keys:
        - otaInstallSchedules: list[dict] -- enabled, and either
          dailyStartMinute (minutes after midnight) or startsAt (epoch seconds)
    """
    try:
        schedules: list[dict[str, Any]] = []
        for num, wt, val in _fields(payload or ""):
            if num != 1 or wt != 2:
                continue
            entry: dict[str, Any] = {"enabled": False}
            for in_num, in_wt, in_val in _decode_protobuf_fields(val):
                if in_num == 2 and in_wt == 0:
                    entry["enabled"] = bool(in_val)
                elif in_num == 3 and in_wt == 2:
                    entry["dailyStartMinute"] = 0
                    for d_num, d_wt, d_val in _decode_protobuf_fields(in_val):
                        if d_num == 1 and d_wt == 0:
                            entry["dailyStartMinute"] = d_val
                elif in_num == 4 and in_wt == 2:
                    for o_num, o_wt, o_val in _decode_protobuf_fields(in_val):
                        if o_num == 1 and o_wt == 2:
                            entry["startsAt"] = _timestamp_seconds(o_val)
            schedules.append(entry)
        return {"otaInstallSchedules": schedules}
    except Exception:
        _LOGGER.debug("Failed to decode ota_config payload", exc_info=True)
        return {}


_PET_SNAPSHOT_FILE_TYPE: Final[dict[int, str]] = {
    1: "image/png",
    2: "image/jpeg",
    3: "image/webp",
}


def decode_pet_snapshot(payload: str) -> dict[str, Any]:
    """Decode secure_file_transfer.pet_snapshot.secure_file (name-match: `g2i`).

    METADATA ONLY. #2 raw_data is the encrypted image and #3 wrapped_keys its
    key material; neither is decodable here and neither is emitted. #1 s3_id
    and #5 session_id are storage/session identifiers and are not emitted
    either. #4 metadata {#1 filename, #2 file_type, #3 file_size, #4 created_at}.

    Returns dict with keys, when metadata is sent:
        - petSnapshot: {"createdAt": int (epoch s), "fileType": str,
          "fileSize": int} -- each inner key only when sent
    """
    if not payload:
        return {}
    try:
        snapshot: dict[str, Any] = {}
        for num, wt, val in _fields(payload):
            if num != 4 or wt != 2:
                continue
            for m_num, m_wt, m_val in _decode_protobuf_fields(val):
                if m_num == 2 and m_wt == 0 and m_val in _PET_SNAPSHOT_FILE_TYPE:
                    snapshot["fileType"] = _PET_SNAPSHOT_FILE_TYPE[m_val]
                elif m_num == 3 and m_wt == 0:
                    snapshot["fileSize"] = m_val
                elif (
                    m_num == 4
                    and m_wt == 2
                    and (ts := _timestamp_seconds(m_val)) is not None
                ):
                    snapshot["createdAt"] = ts
        return {"petSnapshot": snapshot} if snapshot else {}
    except Exception:
        _LOGGER.debug("Failed to decode pet_snapshot payload", exc_info=True)
        return {}


def decode_cold_weather_soc(payload: str) -> dict[str, Any]:
    """Decode energy_edge_compute.graphs.cold_weather_soc (name-match: `jx3`).

    #1 soc_perc_green, #2 soc_perc_blue (percent), #3 cold_range_impact_km.
    Units are from the field names only; the app references the class nowhere
    (FOLLOWUP_S45.md). proto3 omits zeros, so absent fields are 0. The capture
    (`082e`) is green = 46.

    Returns dict with keys:
        - coldWeatherSocGreen, coldWeatherSocBlue: int (percent)
        - coldRangeImpact: int (km)
    """
    try:
        result = {
            "coldWeatherSocGreen": 0,
            "coldWeatherSocBlue": 0,
            "coldRangeImpact": 0,
        }
        keys = {1: "coldWeatherSocGreen", 2: "coldWeatherSocBlue", 3: "coldRangeImpact"}
        for num, wt, val in _fields(payload or ""):
            if num in keys and wt == 0:
                result[keys[num]] = val
        return result
    except Exception:
        _LOGGER.debug("Failed to decode cold_weather_soc payload", exc_info=True)
        return {}


def decode_trip_progress(payload: str) -> dict[str, Any]:
    """Decode navigation.navigation_service.trip_progress (name-match: `u3l`).

    #1 legetautc and #2 tripetautc (Timestamps), #3 nextstopindex (not
    emitted; nothing reads it), #4 legremainingdistancemeters and #5 legremainingdurationseconds (doubles,
    units in the app's own field names). #6, the vehicle's GPS fix, is not
    emitted: dynamics.vehicle.gnss already supplies the location.

    Returns dict with keys, when sent:
        - navLegEta, navTripEta: int (epoch seconds)
        - navLegRemainingDistance: float (m), navLegRemainingDuration: float (s)
    """
    if not payload:
        return {}
    try:
        result: dict[str, Any] = {}
        for num, wt, val in _fields(payload):
            if num in (1, 2) and wt == 2:
                if (ts := _timestamp_seconds(val)) is not None:
                    result["navLegEta" if num == 1 else "navTripEta"] = ts
            elif num == 4 and wt == 1:
                result["navLegRemainingDistance"] = round(val, 1)
            elif num == 5 and wt == 1:
                result["navLegRemainingDuration"] = round(val, 1)
        return result
    except Exception:
        _LOGGER.debug("Failed to decode trip_progress payload", exc_info=True)
        return {}


RVM_DECODERS: dict[str, Callable[[str], dict[str, Any]]] = {
    "body.closures.states": decode_closures,
    "body.locks.states": decode_locks,
    "charging.session.status": decode_charging_session_status,
    # s44: APK-bound, previously undecoded
    "charging.session.notification": decode_charging_notification,
    "charging.session.remote_command": decode_remote_command,
    "charging.session.soc_slider": decode_soc_slider,
    "charging.session.trip_target": decode_trip_target,
    "ota.deployment.state": decode_ota_deployment_state,
    # s45: name-matched (uncalled parse wrapper), not dispatch-bound
    "body.windows.states": decode_window_states,
    "comfort.cabin.hvac_settings_status": decode_hvac_settings_status,
    "comfort.user_modes.state": decode_user_modes,
    "energy_edge_compute.graphs.cold_weather_soc": decode_cold_weather_soc,
    "geofence.geofence_service.favoriteGeofences": decode_favorite_geofences,
    "navigation.navigation_service.trip_progress": decode_trip_progress,
    "ota.ota_state.vehicle_ota_state": decode_vehicle_ota_state,
    "ota.user_schedule.ota_config": decode_ota_config,
    "secure_file_transfer.pet_snapshot.secure_file": decode_pet_snapshot,
    "vehicle_access.state.passive_entry": decode_passive_entry_state,
    "vehicle_access.passive_entry.passive_entry": decode_passive_entry_state,
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
    # s34: written from the named .proto schemas, each verified against a
    # captured frame. charging.schedule.time_window is deliberately absent --
    # its frame carries a GPS coordinate and the fixture was withheld, so the
    # decoder has nothing to verify against.
    "comfort.cabin.cabin_ventilation_setting": decode_cabin_ventilation_setting,
    "gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent": (
        decode_gear_guard_streaming_consent
    ),
    "gearguard_streaming.privacy.gearguard_streaming_daily_limit": (
        decode_gear_guard_streaming_daily_limit
    ),
    "energy_edge_compute.graphs.parked_energy_distributions": (
        decode_parked_energy_distributions
    ),
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
    # Inference, not a read binding -- see the block comment on
    # decode_network_state. Owner decision.
    "vehicle.network.state": decode_network_state,
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
