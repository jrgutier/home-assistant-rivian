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
import logging
import struct
import sys
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Protocol

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from backports.strenum import StrEnum

from .proto.vehicle_operation import _encode_varint_field

_LOGGER = logging.getLogger(__name__)

CLOSURE_MAP = {
    1: "doorFrontLeftClosed",
    2: "doorFrontRightClosed",
    3: "doorRearLeftClosed",
    4: "doorRearRightClosed",
    5: "closureFrunkClosed",
    6: "closureSideBinLeftClosed",
    7: "closureLiftgateClosed",
}

LOCK_MAP = {
    1: "doorFrontLeftLocked",
    2: "doorFrontRightLocked",
    3: "doorRearLeftLocked",
    4: "doorRearRightLocked",
    5: "closureFrunkLocked",
    7: "closureLiftgateLocked",
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


RVM_DECODERS: dict[str, Callable[[str], dict[str, Any]]] = {
    "body.closures.states": decode_closures,
    "body.locks.states": decode_locks,
    "charging.session.status": decode_charging_session_status,
    "charging.session.time_estimation": decode_time_estimation,
    "comfort.cabin.cabin_preconditioning_status": decode_preconditioning,
    "comfort.cabin.cabin_temperatures": decode_cabin_temperatures,
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


def decode_parallax_message(
    rvm: str, payload: str, **kwargs: Any
) -> dict[str, Any] | None:
    """Decode a Parallax message payload given its RVM topic.

    Accepts the GraphQL message fields directly (rvm, payload, and optional kwargs/timestamp).
    Returns a dict of decoded fields, or None if no decoder exists for this RVM.
    """
    decoder = RVM_DECODERS.get(rvm)
    if decoder is None:
        _LOGGER.warning("Unknown Parallax RVM topic %s", rvm)
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
