"""Decoders for `body.*` topics: closures, locks, windows, trailer."""

from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder, _fields
from .proto import body_pb2

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

# body.trailer.state -- TrailerPresenceStatus
_TRAILER_PRESENCE_MAP: Final[dict[int, str]] = {
    1: "trailer_not_present",
    2: "trailer_present",
    3: "trailer_present_with_brakes",
    4: "trailer_invalid",
}

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


@RVMDecoder.register(body_pb2.ClosuresState, "body.closures.states")
def decode_closures(m: body_pb2.ClosuresState) -> dict[str, Any]:
    """Decode body.closures.states.

    Returns dict with keys:
        - doorFrontLeftClosed, doorFrontRightClosed, closureFrunkClosed, etc. ("closed" / "open")
    """
    result: dict[str, Any] = {}
    for closure in m.closure:
        if closure.id in CLOSURE_MAP and closure.HasField("state"):
            # 1 = open, 2 = closed
            result[CLOSURE_MAP[closure.id]] = "closed" if closure.state == 2 else "open"
    return result


@RVMDecoder.register(body_pb2.LocksState, "body.locks.states")
def decode_locks(m: body_pb2.LocksState) -> dict[str, Any]:
    """Decode body.locks.states.

    Returns dict with keys:
        - doorFrontLeftLocked, closureFrunkLocked, etc. ("locked" / "unlocked")
    """
    result: dict[str, Any] = {}
    for lock in m.lock:
        if lock.id in LOCK_MAP and lock.HasField("state"):
            # 1 = locked, 2 = unlocked
            result[LOCK_MAP[lock.id]] = "locked" if lock.state == 1 else "unlocked"
    return result


@RVMDecoder.register(body_pb2.WindowsState, "body.windows.states")
def decode_window_states(m: body_pb2.WindowsState) -> dict[str, Any]:
    """Decode body.windows.states (name-match: `zzn`).

    Returns dict with keys window{FrontLeft,FrontRight,RearLeft,RearRight}Calibrated.
    """
    result: dict[str, Any] = {}
    for window in m.window:
        if (
            window.instance in _WINDOW_CALIBRATION_FIELDS
            and window.calibration_status in _WINDOW_CALIBRATION
        ):
            result[_WINDOW_CALIBRATION_FIELDS[window.instance]] = _WINDOW_CALIBRATION[
                window.calibration_status
            ]
    return result


@RVMDecoder.register(body_pb2.TrailerState, "body.trailer.state")
def decode_trailer_state(m: body_pb2.TrailerState) -> dict[str, Any]:
    """Decode body.trailer.state.

    Returns dict with keys:
        - trailerStatus: str
    """
    return _fields(m, {"presence": ("trailerStatus", _TRAILER_PRESENCE_MAP)})
