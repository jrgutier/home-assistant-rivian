"""Decoders for `security.*` topics: alarm, Gear Guard video, access faults."""

from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder, _fields
from .proto import security_pb2

# security.alarm.state -- SoundAlarmStatus
_ALARM_SOUND_MAP: Final[dict[int, str]] = {
    1: "false",
    2: "true",
    3: "signal_not_available",
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

# security.access.immobilizer_state -- SecureImmoStatus. Note 0 is a REAL value
# here ("not assigned"), not the usual UNSPECIFIED sentinel.
_IMMOBILIZER_MAP: Final[dict[int, str]] = {
    0: "not_assigned",
    1: "not_authorized",
    2: "authorized_to_drive",
}


@RVMDecoder.register(security_pb2.AlarmState, "security.alarm.state")
def decode_alarm_state(m: security_pb2.AlarmState) -> dict[str, Any]:
    """Decode security.alarm.state.

    Returns dict with keys:
        - alarmSoundStatus: str ("true" / "false" / "signal_not_available")

    The strings are the subscription's own vocabulary, which the sensor's
    value_lambda turns into Active/Inactive. signal_not_available is in
    INVALID_SENSOR_STATES, so it reports as unknown rather than as Inactive.
    """
    return _fields(
        m,
        {
            "sound_alarm": ("alarmSoundStatus", _ALARM_SOUND_MAP),
            "consecutive_alarm_disabled_notification": (
                "consecutiveAlarmDisabledNotification",
                None,
            ),
        },
    )


@RVMDecoder.register(
    security_pb2.VideoMonitoringState,
    "security.video_monitoring.state",
)
def decode_video_monitoring(m: security_pb2.VideoMonitoringState) -> dict[str, Any]:
    """Decode security.video_monitoring.state.

    Returns dict with keys:
        - gearGuardVideoStatus: str
        - gearGuardVideoMode: str
        - gearGuardVideoTermsAccepted: str
    """
    return _fields(
        m,
        {
            "status": ("gearGuardVideoStatus", _VIDEO_MONITORING_STATUS_MAP),
            "mode": ("gearGuardVideoMode", _VIDEO_MODE_MAP),
            "terms_accepted": ("gearGuardVideoTermsAccepted", _TOS_ACCEPTANCE_MAP),
        },
    )


@RVMDecoder.register(security_pb2.Btm, "security.access.btm")
def decode_btm_diagnosis(m: security_pb2.Btm) -> dict[str, Any]:
    """Decode security.access.btm.

    Returns dict with keys:
        - btmFfHardwareFailureStatus, btmIcHardwareFailureStatus,
          btmLfdHardwareFailureStatus, btmRfHardwareFailureStatus,
          btmRfdHardwareFailureStatus, btmOcHardwareFailureStatus: str

    Six of the ten fields share one enum. Fields 7-10 are separate error counters
    with no enum of their own, are not in the spec below, and so are dropped.
    """
    return _fields(
        m,
        {
            "ff": ("btmFfHardwareFailureStatus", _HARDWARE_FAILURE_MAP),
            "ic": ("btmIcHardwareFailureStatus", _HARDWARE_FAILURE_MAP),
            "lfd": ("btmLfdHardwareFailureStatus", _HARDWARE_FAILURE_MAP),
            "rf": ("btmRfHardwareFailureStatus", _HARDWARE_FAILURE_MAP),
            "rfd": ("btmRfdHardwareFailureStatus", _HARDWARE_FAILURE_MAP),
            "oc": ("btmOcHardwareFailureStatus", _HARDWARE_FAILURE_MAP),
        },
    )


@RVMDecoder.register(security_pb2.VasFault, "security.access.vas_fault")
def decode_vas_fault(m: security_pb2.VasFault) -> dict[str, Any]:
    """Decode security.access.vas_fault.

    Returns dict with keys:
        - vasSecureElementFaulted: str
        - vasAccessCanFaulted: str

    Both are declared in the gateway schema and neither is subscribed, so this
    topic is the only source for them.
    """
    return _fields(
        m,
        {
            "secure_element": ("vasSecureElementFaulted", _SECURE_ELEMENT_FAULTED_MAP),
            "access_can": ("vasAccessCanFaulted", _ACCESS_CAN_FAULTED_MAP),
        },
    )


@RVMDecoder.register(
    security_pb2.PassiveEntryDebug,
    "security.access.passive_entry_debug",
)
def decode_passive_entry_debug(m: security_pb2.PassiveEntryDebug) -> dict[str, Any]:
    """Decode security.access.passive_entry_debug.

    Returns dict with keys:
        - passiveEntryUnlockFailReason: str
    """
    return _fields(
        m, {"reason": ("passiveEntryUnlockFailReason", _PASSIVE_ENTRY_FAIL_MAP)}
    )


@RVMDecoder.register(
    security_pb2.ImmobilizerState,
    "security.access.immobilizer_state",
)
def decode_immobilizer_state(m: security_pb2.ImmobilizerState) -> dict[str, Any]:
    """Decode security.access.immobilizer_state.

    Returns dict with keys:
        - secureImmobilizerStatus: str

    No gateway field carries this, so it backs no entity yet -- it is decoded so
    the topic stops being an unknown one, and so an entity can be added against
    observed values rather than against a guess.
    """
    return _fields(m, {"status": ("secureImmobilizerStatus", _IMMOBILIZER_MAP)})
