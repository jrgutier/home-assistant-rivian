from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder, _fields
from .proto import charging_pb2

_TIME_ESTIMATE_INVALID = frozenset(
    {
        charging_pb2.TIME_ESTIMATION_VALIDITY_INVALID,
        charging_pb2.TIME_ESTIMATION_VALIDITY_PACK_DISCHARGING,
    }
)

_START_AVAILABLE: Final[dict[int, int]] = {1: 0, 2: 1}

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

_TRIP_TARGET_SOC_RANGE: Final = range(1, 101)


@RVMDecoder.register(charging_pb2.SessionStatus, "charging.session.status")
def decode_charging_session_status(m: charging_pb2.SessionStatus) -> dict[str, Any]:
    return _fields(
        m,
        {
            "connection_state": ("plugConnectionStatus", None),
            "charging_state": ("displayStatus", None),
            "evse_type": ("evseType", None),
        },
    )


@RVMDecoder.register(
    charging_pb2.TimeEstimation,
    "charging.session.time_estimation",
)
def decode_time_estimation(m: charging_pb2.TimeEstimation) -> dict[str, Any]:
    if m.validity in _TIME_ESTIMATE_INVALID:
        return {}
    return {"timeToEndOfCharge": m.estimated_time_remaining}


@RVMDecoder.register(charging_pb2.SocSlider, "charging.session.soc_slider")
def decode_soc_slider(m: charging_pb2.SocSlider) -> dict[str, Any]:
    return {"batteryLimit": m.soc_limit} if m.HasField("soc_limit") else {}


@RVMDecoder.register(
    charging_pb2.SessionRemoteCommand,
    "charging.session.remote_command",
)
def decode_remote_command(m: charging_pb2.SessionRemoteCommand) -> dict[str, Any]:
    if m.start_available in _START_AVAILABLE:
        return {"remoteChargingAvailable": _START_AVAILABLE[m.start_available]}
    return {}


@RVMDecoder.register(
    charging_pb2.SessionNotification,
    "charging.session.notification",
    empty_payload=True,
)
def decode_charging_notification(m: charging_pb2.SessionNotification) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if m.derate_status in _DERATE_STATUS:
        result["chargerDerateStatus"] = _DERATE_STATUS[m.derate_status]
    if m.fault_chime in _FAULT_CHIME:
        result["chargingFaultChime"] = _FAULT_CHIME[m.fault_chime]
    return result


@RVMDecoder.register(charging_pb2.TripTarget, "charging.session.trip_target")
def decode_trip_target(m: charging_pb2.TripTarget) -> dict[str, Any]:
    if m.soc not in _TRIP_TARGET_SOC_RANGE:
        return {}
    result: dict[str, Any] = {"tripTargetSoc": m.soc}
    if m.HasField("time_estimate"):
        result["tripTargetMinutesRemaining"] = m.time_estimate
    return result


@RVMDecoder.register(
    charging_pb2.ScheduleTimeWindow,
    "charging.schedule.time_window",
    skip_empty_message=True,
)
def decode_charging_schedule_time_window(
    m: charging_pb2.ScheduleTimeWindow,
) -> dict[str, Any]:
    result: dict[str, Any] = {"chargeScheduleValid": m.enabled}
    if not m.enabled:
        return result
    window = _fields(
        m.window,
        {
            "start_time": ("chargeScheduleStartMinute", None),
            "end_time": ("chargeScheduleEndMinute", None),
            "duration": ("chargeScheduleDurationMinute", None),
            "amps": ("chargeScheduleAmps", None),
            "start_day": ("chargeScheduleStartDay", None),
            "end_day": ("chargeScheduleEndDay", None),
        },
    )
    result.update(window)
    start, end = (
        window.get("chargeScheduleStartMinute"),
        window.get("chargeScheduleEndMinute"),
    )
    if start is not None and end is not None:
        result["chargeScheduleWindow"] = (
            f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"
        )
    return result
