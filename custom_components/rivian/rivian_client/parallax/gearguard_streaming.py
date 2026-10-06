"""Decoders for `gearguard_streaming.privacy.*` topics."""

from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder
from .proto import gearguard_streaming_pb2

# CORRECTION (s43): the two enums below are NOT the ones in
# the legacy rivian_security.proto. That file's numbering came from the 3.6.0 transcription
# and is offset from the wire. The app's own classes -- `vpl` (user_consent) and
# `uc5` (daily_limit, next_reset_time_unix_sec), 3.16.0 uncalled parse wrappers
# whose field names match these topics -- give the numbers used here. The live
# consent capture is 2, which the old map read as not_consented. The APK is the
# authority, and proto/gearguard_streaming.proto matches it.
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
    """Decode gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent.

    Schema: `proto/gearguard_streaming.proto`.

    Returns dict with keys:
        - gearGuardStreamingConsent: str
          (consented | not_consented | not_applicable | unknown | unrecognized)
    """
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
    """Decode gearguard_streaming.privacy.gearguard_streaming_daily_limit.

    Schema: `proto/gearguard_streaming.proto`.

    The reset timestamp is emitted verbatim. The observed fixture carries a value
    in the past relative to its capture date, which is recorded rather than
    corrected -- interpreting it as anything but "what the vehicle said" would be
    a guess about semantics this frame does not establish.

    Returns dict with keys:
        - gearGuardStreamingDailyLimit: str
          (not_hit | hit | undefined | unrecognized)
        - gearGuardStreamingLimitResetTime: int (epoch seconds), when sent
    """
    result: dict[str, Any] = {}
    if m.HasField("limit"):
        result["gearGuardStreamingDailyLimit"] = _GEAR_GUARD_DAILY_LIMIT.get(
            m.limit, "unrecognized"
        )
    if m.HasField("limit_reset_time"):
        result["gearGuardStreamingLimitResetTime"] = m.limit_reset_time
    return result
