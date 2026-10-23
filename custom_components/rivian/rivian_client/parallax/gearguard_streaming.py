from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder
from .proto import gearguard_streaming_pb2

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


@RVMDecoder.register(
    gearguard_streaming_pb2.GearGuardStreamingConsent,
    "gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent",
)
def decode_gear_guard_streaming_consent(
    m: gearguard_streaming_pb2.GearGuardStreamingConsent,
) -> dict[str, Any]:
    if m.HasField("consent"):
        return {
            "gearGuardStreamingConsent": _GEAR_GUARD_CONSENT.get(
                m.consent, "unrecognized"
            )
        }
    return {}


@RVMDecoder.register(
    gearguard_streaming_pb2.GearGuardStreamingDailyLimit,
    "gearguard_streaming.privacy.gearguard_streaming_daily_limit",
)
def decode_gear_guard_streaming_daily_limit(
    m: gearguard_streaming_pb2.GearGuardStreamingDailyLimit,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if m.HasField("limit"):
        result["gearGuardStreamingDailyLimit"] = _GEAR_GUARD_DAILY_LIMIT.get(
            m.limit, "unrecognized"
        )
    if m.HasField("limit_reset_time"):
        result["gearGuardStreamingLimitResetTime"] = m.limit_reset_time
    return result
