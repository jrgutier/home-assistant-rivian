from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder, _fields, _name
from .proto import comfort_pb2

DEFROST_DEFOG_MAP = {
    1: "Defog",
    2: "Defrost",
    3: "Defog_Defrost",
    4: "Off",
}

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

SEAT_INSTANCES = {
    comfort_pb2.STEERING_WHEEL: "steeringWheel",
    comfort_pb2.SEAT_ROW_1_LEFT: "seatFrontLeft",
    comfort_pb2.SEAT_ROW_1_RIGHT: "seatFrontRight",
    comfort_pb2.SEAT_ROW_2_LEFT: "seatRearLeft",
    comfort_pb2.SEAT_ROW_2_RIGHT: "seatRearRight",
    comfort_pb2.SEAT_ROW_3_LEFT: "seatThirdRowLeft",
    comfort_pb2.SEAT_ROW_3_RIGHT: "seatThirdRowRight",
}
SEAT_DEVICES = {
    comfort_pb2.CONDITIONING_HEAT: "Heat",
    comfort_pb2.CONDITIONING_VENT: "Vent",
}
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
SEAT_LEVELS = {
    comfort_pb2.CONDITIONING_LEVEL_UNSPECIFIED: "Off",
    comfort_pb2.CONDITIONING_LEVEL_1: "Level_1",
    comfort_pb2.CONDITIONING_LEVEL_2: "Level_2",
    comfort_pb2.CONDITIONING_LEVEL_3: "Level_3",
}

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

_USER_MODE_FIELDS: Final[dict[int, str]] = {1: "serviceMode", 2: "carWashMode"}


@RVMDecoder.register(
    comfort_pb2.CabinTemperatures,
    "comfort.cabin.cabin_temperatures",
)
def decode_cabin_temperatures(m: comfort_pb2.CabinTemperatures) -> dict[str, Any]:
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
    if m.status in DEFROST_DEFOG_MAP:
        return {"defrostDefogStatus": DEFROST_DEFOG_MAP[m.status]}
    return {}


@RVMDecoder.register(
    comfort_pb2.CabinPreconditioningStatus,
    "comfort.cabin.cabin_preconditioning_status",
    empty_payload=True,
)
def decode_preconditioning(m: comfort_pb2.CabinPreconditioningStatus) -> dict[str, Any]:
    if m.status not in PRECONDITIONING_STATE_MAP:
        return {}
    return {"cabinPreconditioningStatus": PRECONDITIONING_STATE_MAP[m.status]}


@RVMDecoder.register(
    comfort_pb2.ClimateHoldStatus,
    "comfort.cabin.climate_hold_status",
)
def decode_climate_hold_status(m: comfort_pb2.ClimateHoldStatus) -> dict[str, Any]:
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
    if m.end_time.HasField("seconds"):
        result["climateHoldEndTime"] = m.end_time.seconds
    return result


@RVMDecoder.register(
    comfort_pb2.ClimateHoldSetting,
    "comfort.cabin.climate_hold_setting",
    empty_payload=True,
)
def decode_climate_hold_setting(m: comfort_pb2.ClimateHoldSetting) -> dict[str, Any]:
    return {"climateHoldDurationSeconds": m.hold_time_duration_seconds}


@RVMDecoder.register(
    comfort_pb2.SeatConditioningStatus,
    "comfort.cabin.seat_conditioning_status",
)
def decode_seat_conditioning_status(
    m: comfort_pb2.SeatConditioningStatus,
) -> dict[str, Any]:
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
    if m.HasField("target_temperature"):
        return {"hvacSetTemperature": round(m.target_temperature, 1)}
    return {}


@RVMDecoder.register(
    comfort_pb2.UserModesState,
    "comfort.user_modes.state",
    empty_payload=True,
)
def decode_user_modes(m: comfort_pb2.UserModesState) -> dict[str, Any]:
    return {
        key: "on" if getattr(m, _name(m, number)) == 1 else "off"
        for number, key in _USER_MODE_FIELDS.items()
    }
