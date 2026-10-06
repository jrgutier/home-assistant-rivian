"""Decoders for `charging.*` topics."""

from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder, _fields
from .proto import charging_pb2

# charging.session.time_estimation -- the app's VALIDITY_FLAG (`o9k` field 1).
# NONE (0) is what the live capture carries alongside a real estimate, so only
# the two values that say the estimate is meaningless suppress it.
_TIME_ESTIMATE_INVALID = frozenset({2, 3})  # INVALID, PACK_DISCHARGING

# `dsg` #1 start_available: 0 SNA, 1 FALSE, 2 TRUE. The gateway's
# remoteChargingAvailable is an int, 1 = available (switch.py reads `== 1`).
_START_AVAILABLE: Final[dict[int, int]] = {1: 0, 2: 1}

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

# The app's own rule (FOLLOWUP_S47.md): a trip target exists only when its SOC
# is 1-100 -- every reader (np4.java:81, y13.java:397, j23.java:1146) tests
# `soc > 0 && soc <= 100` and hides the whole indicator otherwise, minutes
# included. The app has no sentinel for the minutes themselves; s46's frame
# (`10ffff03`, #2 = 65535, no #1) is hidden by the SOC test, not by its value.
_TRIP_TARGET_SOC_RANGE: Final = range(1, 101)


@RVMDecoder.register(charging_pb2.SessionStatus, "charging.session.status")
def decode_charging_session_status(m: charging_pb2.SessionStatus) -> dict[str, Any]:
    """Decode charging.session.status.

    Returns dict with keys:
        - plugConnectionStatus: int (enum)
        - displayStatus: int (enum)
        - evseType: int (enum)
    """
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
    """Decode charging.session.time_estimation.

    The app's `o9k` (bound, 3.16.0): #1 validity_flag enum, #2
    remaining_minutes uint32. Field 1 used to be read as the remaining time,
    which never matched a real frame -- the capture is `1040`, field 2 = 64 --
    so this returned {} on every one.

    Returns dict with keys:
        - timeToEndOfCharge: int (minutes, the sensor's own unit)
    """
    if m.validity in _TIME_ESTIMATE_INVALID:
        return {}
    return {"timeToEndOfCharge": m.estimated_time_remaining}


@RVMDecoder.register(charging_pb2.SocSlider, "charging.session.soc_slider")
def decode_soc_slider(m: charging_pb2.SocSlider) -> dict[str, Any]:
    """Decode charging.session.soc_slider -- `hgh` #1 user_soc_limit (%).

    Returns dict with keys:
        - batteryLimit: int (percent)
    """
    return {"batteryLimit": m.soc_limit} if m.HasField("soc_limit") else {}


@RVMDecoder.register(
    charging_pb2.SessionRemoteCommand,
    "charging.session.remote_command",
)
def decode_remote_command(m: charging_pb2.SessionRemoteCommand) -> dict[str, Any]:
    """Decode charging.session.remote_command.

    Despite the topic name this is not a command: it says whether a remote
    charge start is available. SNA (0, or an empty payload) emits nothing.

    Returns dict with keys:
        - remoteChargingAvailable: int (0 / 1)
    """
    if m.start_available in _START_AVAILABLE:
        return {"remoteChargingAvailable": _START_AVAILABLE[m.start_available]}
    return {}


@RVMDecoder.register(
    charging_pb2.SessionNotification,
    "charging.session.notification",
    empty_payload=True,
)
def decode_charging_notification(m: charging_pb2.SessionNotification) -> dict[str, Any]:
    """Decode charging.session.notification.

    proto3 omits a zero, so a frame without #2 or #3 is saying NONE for it --
    the live capture (`0801`) carries only #1. An empty payload says NONE for
    both.

    Returns dict with keys:
        - chargerDerateStatus: str ("NONE", "BATTERY_HEATING", ...)
        - chargingFaultChime: str ("none", "charging_disabled_dc", ...)
    """
    result: dict[str, Any] = {}
    if m.derate_status in _DERATE_STATUS:
        result["chargerDerateStatus"] = _DERATE_STATUS[m.derate_status]
    if m.fault_chime in _FAULT_CHIME:
        result["chargingFaultChime"] = _FAULT_CHIME[m.fault_chime]
    return result


@RVMDecoder.register(charging_pb2.TripTarget, "charging.session.trip_target")
def decode_trip_target(m: charging_pb2.TripTarget) -> dict[str, Any]:
    """Decode charging.session.trip_target -- `d5l`.

    #1 soc and #2 time_estimate, which the app passes unmodified into its
    chargingTripTargetMinsRemaining (FOLLOWUP_S45.md, c97.java:591) -- minutes.
    #3 status has no enum in any app version and is not emitted.

    Emits nothing unless the SOC is 1-100, the app's own test for "there is a
    trip target" (FOLLOWUP_S47.md). Minutes are then passed through as the app
    does, unfiltered.

    Returns dict with keys, when a trip target is set:
        - tripTargetSoc: int (percent)
        - tripTargetMinutesRemaining: int (minutes), when sent
    """
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
    """Decode charging.schedule.time_window -> ChargingScheduleTimeWindow.

    Returns dict with keys:
        - chargeScheduleValid: bool              (is_valid)
        - chargeScheduleStartMinute: int         (minutes since midnight, 0-1439)
        - chargeScheduleEndMinute: int
        - chargeScheduleDurationMinute: int
        - chargeScheduleAmps: int                (charge current limit)
        - chargeScheduleStartDay: int            (0=Sun .. 6=Sat)
        - chargeScheduleEndDay: int
        - chargeScheduleWindow: str              ("HH:MM-HH:MM", when both times present)

    Outer message: #1 is_valid (bool), #2 window_data (WindowData submessage).
    WindowData: #1 start_time, #2 end_time, #3 duration, #4 amps, #5 location
    (google-style Location {#1 lat, #2 lon}, both double), #6 start_day_of_week,
    #7 end_day_of_week.

    Times are MINUTES, not seconds -- the captured 3.17.0 frame reads start 1380 /
    end 360 / duration 420, which is 23:00 / 06:00 / 7h, and 23:00 + 7h = 06:00
    reconciles only in minutes. The app UI confirms "Daily 11pm-6am". The .proto
    comment that said "seconds" was wrong and is corrected alongside this.

    Field #5 (location) is deliberately NOT surfaced: it carries the owner's home
    coordinates, which is the same reason s34 withheld this decoder until a frame
    could be verified. The committed fixture has field #5 zeroed; nothing here
    emits latitude/longitude.

    Validity under proto3: a false `is_valid` is the scalar default and is omitted
    from the wire, so field #1 is simply ABSENT on an inactive schedule, never
    `field1=0`. A non-empty frame with no field #1 decodes as is_valid=False, and
    the window/amps are surfaced ONLY when valid.

    chargeScheduleValid is decoded but NOT surfaced as an entity. Hardware verify
    (2026-10-06, live R1T) settled the open question: when the schedule is disabled
    the vehicle STOPS sending this topic entirely -- it does not send an inactive
    frame -- so no is_valid=False ever arrives to decode. An "active" binary sensor
    could therefore only ever read "on"/stale-on and can't represent "disabled", so
    it was dropped. The valid=False branch stays as a correctness guard, not a live
    path.

    chargeScheduleWindow/Amps are correct when a frame arrives, but this topic is
    EVENT-GATED: hardware verify saw it push promptly on schedule hour/amp edits
    yet send nothing for 20+ min after a disable+re-enable, while the car was awake
    and other topics streamed. So these sensors can lag the app by minutes after a
    change even when the vehicle is online, and they never go "unavailable" -- they
    hold the last received schedule (gap-fill). That is expected, not a fault.
    """
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
