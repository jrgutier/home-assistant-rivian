"""Decoders for `comfort.*` topics: cabin climate, seats, user modes."""

from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder, _fields, _name
from .proto import comfort_pb2

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

# `uql` #1 in_service and #2 car_wash: MODE_STATUS 0 UNSPECIFIED, 1 ON. The
# enum has no OFF member, so 0 -- which proto3 omits -- is how "not on" is
# encoded. Emitted as the gateway's serviceMode / carWashMode ("on" / "off").
# #3-#7 (pet_mode, camp_mode, transport_mode, climate_keep, factory_mode) use
# enums the s42 extraction could not attribute and are not decoded.
_USER_MODE_FIELDS: Final[dict[int, str]] = {1: "serviceMode", 2: "carWashMode"}


@RVMDecoder.register(
    comfort_pb2.CabinTemperatures,
    "comfort.cabin.cabin_temperatures",
)
def decode_cabin_temperatures(m: comfort_pb2.CabinTemperatures) -> dict[str, Any]:
    """Decode comfort.cabin.cabin_temperatures.

    Returns dict with keys:
        - cabinClimateInteriorTemperature: float (Celsius)
        - cabinClimateDriverTemperature: float (Celsius)
    """
    result: dict[str, Any] = {}
    if m.HasField("interior_temperature"):
        result["cabinClimateInteriorTemperature"] = round(m.interior_temperature, 1)
    if m.HasField("driver_set_point"):
        result["cabinClimateDriverTemperature"] = round(m.driver_set_point, 1)
    return result


@RVMDecoder.register(
    comfort_pb2.DefrostDefogStatus,
    "comfort.cabin.defrost_defog_status",
)
def decode_defrost(m: comfort_pb2.DefrostDefogStatus) -> dict[str, Any]:
    """Decode comfort.cabin.defrost_defog_status.

    Returns dict with keys:
        - defrostDefogStatus: str ("Defog", "Defrost", "Defog_Defrost", "Off")

    Previously only 2 was recognised and every other value read as "Off", so
    defog alone, or defog with defrost, showed the system as off.
    """
    if m.status in DEFROST_DEFOG_MAP:
        return {"defrostDefogStatus": DEFROST_DEFOG_MAP[m.status]}
    return {}


@RVMDecoder.register(
    comfort_pb2.CabinPreconditioningStatus,
    "comfort.cabin.cabin_preconditioning_status",
    empty_payload=True,
)
def decode_preconditioning(m: comfort_pb2.CabinPreconditioningStatus) -> dict[str, Any]:
    """Decode comfort.cabin.cabin_preconditioning_status.

    Field 1 is the app's CABIN_PRECONDITIONING_STATE (`p22`); see
    PRECONDITIONING_STATE_MAP. An empty payload is the proto3 encoding of 0,
    UNSPECIFIED, which the sensor already renders as "Undefined".

    Previously 2 read as "initiate" (it is ACTIVE) and everything outside 1, 2
    and 4 read as "off", including a running hold with a warning (3).

    Returns dict with keys:
        - cabinPreconditioningStatus: str
    """
    if m.status not in PRECONDITIONING_STATE_MAP:
        return {}
    return {"cabinPreconditioningStatus": PRECONDITIONING_STATE_MAP[m.status]}


@RVMDecoder.register(
    comfort_pb2.ClimateHoldStatus,
    "comfort.cabin.climate_hold_status",
)
def decode_climate_hold_status(m: comfort_pb2.ClimateHoldStatus) -> dict[str, Any]:
    """Decode comfort.cabin.climate_hold_status.

    Returns dict with keys:
        - climateHoldStatus: str  (off | on | unavailable | fault | unspecified)
        - climateHoldAvailability: str
        - climateHoldUnavailabilityReason: str (only when not "unspecified")
        - climateHoldEndTime: int (epoch seconds, only when a hold is running)
    """
    result: dict[str, Any] = {}
    if m.HasField("status"):
        result["climateHoldStatus"] = _CLIMATE_HOLD_STATUS.get(m.status, "unspecified")
    if m.HasField("availability"):
        result["climateHoldAvailability"] = _CLIMATE_HOLD_AVAILABILITY.get(
            m.availability, "unspecified"
        )
    reason = _CLIMATE_HOLD_UNAVAILABILITY_REASON.get(
        m.unavailability_reason, "unspecified"
    )
    if reason != "unspecified":
        result["climateHoldUnavailabilityReason"] = reason
    # An empty end_time message means "no hold".
    if m.end_time.HasField("seconds"):
        result["climateHoldEndTime"] = m.end_time.seconds
    return result


@RVMDecoder.register(
    comfort_pb2.ClimateHoldSetting,
    "comfort.cabin.climate_hold_setting",
    empty_payload=True,
)
def decode_climate_hold_setting(m: comfort_pb2.ClimateHoldSetting) -> dict[str, Any]:
    """Decode comfort.cabin.climate_hold_setting.

    Returns dict with keys:
        - climateHoldDurationSeconds: int  (0 or absent when no hold is set)

    An EMPTY payload is the vehicle's way of saying "no hold configured"; it is
    reported as 0 rather than {} so the entity reads as off rather than
    unavailable.
    """
    return {"climateHoldDurationSeconds": m.hold_time_duration_seconds}


@RVMDecoder.register(
    comfort_pb2.SeatConditioningStatus,
    "comfort.cabin.seat_conditioning_status",
)
def decode_seat_conditioning_status(
    m: comfort_pb2.SeatConditioningStatus,
) -> dict[str, Any]:
    """Decode comfort.cabin.seat_conditioning_status.

    Returns dict with keys, for each surface the vehicle lists:
        - seatFrontLeftHeat, seatFrontRightHeat, seatRearLeftHeat,
          seatRearRightHeat, seatThirdRowLeftHeat, seatThirdRowRightHeat,
          seatFrontLeftVent, seatFrontRightVent, steeringWheelHeat
          ("Off" / "Level_1" / "Level_2" / "Level_3")
    """
    result: dict[str, Any] = {}
    for surface in m.surface:
        if surface.id not in SEAT_INSTANCES or surface.type not in SEAT_DEVICES:
            continue
        key = SEAT_INSTANCES[surface.id] + SEAT_DEVICES[surface.type]
        if key in SEAT_FIELDS and surface.state in SEAT_LEVELS:
            result[key] = SEAT_LEVELS[surface.state]
    return result


@RVMDecoder.register(comfort_pb2.PetModeStatus, "comfort.cabin.pet_mode_status")
def decode_pet_mode_status(m: comfort_pb2.PetModeStatus) -> dict[str, Any]:
    """Decode comfort.cabin.pet_mode_status.

    Returns dict with keys:
        - petModeStatus: str
        - petModeTemperatureStatus: str
    """
    return _fields(
        m,
        {
            "status": ("petModeStatus", _PET_MODE_STATE_MAP),
            "temperature_status": (
                "petModeTemperatureStatus",
                _PET_MODE_TEMPERATURE_MAP,
            ),
        },
    )


@RVMDecoder.register(
    comfort_pb2.CabinVentilationSetting,
    "comfort.cabin.cabin_ventilation_setting",
)
def decode_cabin_ventilation_setting(
    m: comfort_pb2.CabinVentilationSetting,
) -> dict[str, Any]:
    """Decode comfort.cabin.cabin_ventilation_setting.

    Schema: `proto/comfort.proto`. `REMAINING_APK_GAPS.md` lists this RVM as
    undecoded and wanted; the WRITE path is separately recorded as ISE, so this
    reads state that cannot currently be set from here.

    Returns dict with keys:
        - cabinVentilationEnabled: bool
        - cabinVentilationMode: str ("AUTO" | "MANUAL" | "OFF"), when sent
        - cabinVentilationWindowsOpenPercent: int, when sent
        - cabinVentilationSunroofOpenPercent: int, when sent
        - cabinVentilationDurationMinutes: int, when sent
    """
    return _fields(
        m,
        {
            "auto_cabin_ventilation_enabled": ("cabinVentilationEnabled", None),
            "mode": ("cabinVentilationMode", None),
            "windows_open_percent": ("cabinVentilationWindowsOpenPercent", None),
            "sunroof_open_percent": ("cabinVentilationSunroofOpenPercent", None),
            "duration_minutes": ("cabinVentilationDurationMinutes", None),
        },
    )


@RVMDecoder.register(
    comfort_pb2.HvacSettingsStatus,
    "comfort.cabin.hvac_settings_status",
)
def decode_hvac_settings_status(m: comfort_pb2.HvacSettingsStatus) -> dict[str, Any]:
    """Decode comfort.cabin.hvac_settings_status (name-match: `e9a`).

    #1 set_temperature_celsius, float. The capture (`0d0000a841`) is 21.0.

    Returns dict with keys:
        - hvacSetTemperature: float (Celsius)
    """
    if m.HasField("target_temperature"):
        return {"hvacSetTemperature": round(m.target_temperature, 1)}
    return {}


@RVMDecoder.register(
    comfort_pb2.UserModesState,
    "comfort.user_modes.state",
    empty_payload=True,
)
def decode_user_modes(m: comfort_pb2.UserModesState) -> dict[str, Any]:
    """Decode comfort.user_modes.state (name-match: `uql`).

    Returns dict with keys:
        - serviceMode, carWashMode: str ("on" / "off")
    """
    return {
        key: "on" if getattr(m, _name(m, number)) == 1 else "off"
        for number, key in _USER_MODE_FIELDS.items()
    }
