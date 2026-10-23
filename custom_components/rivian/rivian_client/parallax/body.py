from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder, _fields
from .proto import body_pb2

CLOSURE_MAP = {
    body_pb2.DOOR_FRONT_LEFT: "doorFrontLeftClosed",
    body_pb2.DOOR_FRONT_RIGHT: "doorFrontRightClosed",
    body_pb2.DOOR_REAR_LEFT: "doorRearLeftClosed",
    body_pb2.DOOR_REAR_RIGHT: "doorRearRightClosed",
    body_pb2.FRUNK: "closureFrunkClosed",
    body_pb2.TAILGATE: "closureTailgateClosed",
    body_pb2.LIFTGATE: "closureLiftgateClosed",
    body_pb2.SIDE_BIN_LEFT: "closureSideBinLeftClosed",
    body_pb2.SIDE_BIN_RIGHT: "closureSideBinRightClosed",
    body_pb2.TONNEAU: "closureTonneauClosed",
    body_pb2.WINDOW_FRONT_LEFT: "windowFrontLeftClosed",
    body_pb2.WINDOW_FRONT_RIGHT: "windowFrontRightClosed",
    body_pb2.WINDOW_REAR_LEFT: "windowRearLeftClosed",
    body_pb2.WINDOW_REAR_RIGHT: "windowRearRightClosed",
}

LOCK_MAP = {
    body_pb2.LOCK_DOOR_FRONT_LEFT: "doorFrontLeftLocked",
    body_pb2.LOCK_DOOR_FRONT_RIGHT: "doorFrontRightLocked",
    body_pb2.LOCK_DOOR_REAR_LEFT: "doorRearLeftLocked",
    body_pb2.LOCK_DOOR_REAR_RIGHT: "doorRearRightLocked",
    body_pb2.LOCK_FRUNK: "closureFrunkLocked",
    body_pb2.LOCK_TAILGATE: "closureTailgateLocked",
    body_pb2.LOCK_LIFTGATE: "closureLiftgateLocked",
    body_pb2.LOCK_SIDE_BIN_LEFT: "closureSideBinLeftLocked",
    body_pb2.LOCK_SIDE_BIN_RIGHT: "closureSideBinRightLocked",
    body_pb2.LOCK_TONNEAU: "closureTonneauLocked",
}

_TRAILER_PRESENCE_MAP: Final[dict[int, str]] = {
    body_pb2.TRAILER_NOT_PRESENT: "trailer_not_present",
    body_pb2.TRAILER_PRESENT: "trailer_present",
    body_pb2.TRAILER_PRESENT_WITH_BRAKES: "trailer_present_with_brakes",
    body_pb2.TRAILER_INVALID: "trailer_invalid",
}

_WINDOW_CALIBRATION_FIELDS: Final[dict[int, str]] = {
    body_pb2.WINDOW_INSTANCE_FRONT_LEFT: "windowFrontLeftCalibrated",
    body_pb2.WINDOW_INSTANCE_FRONT_RIGHT: "windowFrontRightCalibrated",
    body_pb2.WINDOW_INSTANCE_REAR_LEFT: "windowRearLeftCalibrated",
    body_pb2.WINDOW_INSTANCE_REAR_RIGHT: "windowRearRightCalibrated",
}
_WINDOW_CALIBRATION: Final[dict[int, str]] = {
    body_pb2.CALIBRATION_STATUS_CALIBRATED: "Calibrated",
    body_pb2.CALIBRATION_STATUS_NOT_CALIBRATED: "Not_Calibrated",
}


@RVMDecoder.register(body_pb2.ClosuresState, "body.closures.states")
def decode_closures(m: body_pb2.ClosuresState) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for closure in m.closure:
        if closure.id in CLOSURE_MAP and closure.HasField("state"):
            result[CLOSURE_MAP[closure.id]] = (
                "closed" if closure.state == body_pb2.CLOSURE_STATE_CLOSED else "open"
            )
    return result


@RVMDecoder.register(body_pb2.LocksState, "body.locks.states")
def decode_locks(m: body_pb2.LocksState) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for lock in m.lock:
        if lock.id in LOCK_MAP and lock.HasField("state"):
            result[LOCK_MAP[lock.id]] = (
                "locked" if lock.state == body_pb2.LOCK_STATE_LOCKED else "unlocked"
            )
    return result


@RVMDecoder.register(body_pb2.WindowsState, "body.windows.states")
def decode_window_states(m: body_pb2.WindowsState) -> dict[str, Any]:
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
    return _fields(m, {"presence": ("trailerStatus", _TRAILER_PRESENCE_MAP)})
