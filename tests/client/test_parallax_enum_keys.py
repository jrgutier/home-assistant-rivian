"""Each Parallax lookup table pairs the proto enum member it was written for.

The tables are keyed by the generated enum constants, so a renumbered or
reordered `.proto` shows up here as a member mapped to the wrong field.
"""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.rivian.rivian_client.parallax import body, charging, comfort
from custom_components.rivian.rivian_client.parallax.proto import (
    body_pb2,
    charging_pb2,
    comfort_pb2,
)

CASES: list[tuple[str, Any, Any, dict[str, Any]]] = [
    (
        "CLOSURE_MAP",
        body.CLOSURE_MAP,
        body_pb2.ClosureId,
        {
            "DOOR_FRONT_LEFT": "doorFrontLeftClosed",
            "DOOR_FRONT_RIGHT": "doorFrontRightClosed",
            "DOOR_REAR_LEFT": "doorRearLeftClosed",
            "DOOR_REAR_RIGHT": "doorRearRightClosed",
            "FRUNK": "closureFrunkClosed",
            "TAILGATE": "closureTailgateClosed",
            "LIFTGATE": "closureLiftgateClosed",
            "SIDE_BIN_LEFT": "closureSideBinLeftClosed",
            "SIDE_BIN_RIGHT": "closureSideBinRightClosed",
            "TONNEAU": "closureTonneauClosed",
            "WINDOW_FRONT_LEFT": "windowFrontLeftClosed",
            "WINDOW_FRONT_RIGHT": "windowFrontRightClosed",
            "WINDOW_REAR_LEFT": "windowRearLeftClosed",
            "WINDOW_REAR_RIGHT": "windowRearRightClosed",
        },
    ),
    (
        "LOCK_MAP",
        body.LOCK_MAP,
        body_pb2.LockId,
        {
            "LOCK_DOOR_FRONT_LEFT": "doorFrontLeftLocked",
            "LOCK_DOOR_FRONT_RIGHT": "doorFrontRightLocked",
            "LOCK_DOOR_REAR_LEFT": "doorRearLeftLocked",
            "LOCK_DOOR_REAR_RIGHT": "doorRearRightLocked",
            "LOCK_FRUNK": "closureFrunkLocked",
            "LOCK_TAILGATE": "closureTailgateLocked",
            "LOCK_LIFTGATE": "closureLiftgateLocked",
            "LOCK_SIDE_BIN_LEFT": "closureSideBinLeftLocked",
            "LOCK_SIDE_BIN_RIGHT": "closureSideBinRightLocked",
            "LOCK_TONNEAU": "closureTonneauLocked",
        },
    ),
    (
        "_TRAILER_PRESENCE_MAP",
        body._TRAILER_PRESENCE_MAP,
        body_pb2.TrailerPresence,
        {
            "TRAILER_NOT_PRESENT": "trailer_not_present",
            "TRAILER_PRESENT": "trailer_present",
            "TRAILER_PRESENT_WITH_BRAKES": "trailer_present_with_brakes",
            "TRAILER_INVALID": "trailer_invalid",
        },
    ),
    (
        "_WINDOW_CALIBRATION_FIELDS",
        body._WINDOW_CALIBRATION_FIELDS,
        body_pb2.WindowInstance,
        {
            "WINDOW_INSTANCE_FRONT_LEFT": "windowFrontLeftCalibrated",
            "WINDOW_INSTANCE_FRONT_RIGHT": "windowFrontRightCalibrated",
            "WINDOW_INSTANCE_REAR_LEFT": "windowRearLeftCalibrated",
            "WINDOW_INSTANCE_REAR_RIGHT": "windowRearRightCalibrated",
        },
    ),
    (
        "_WINDOW_CALIBRATION",
        body._WINDOW_CALIBRATION,
        body_pb2.CalibrationStatus,
        {
            "CALIBRATION_STATUS_CALIBRATED": "Calibrated",
            "CALIBRATION_STATUS_NOT_CALIBRATED": "Not_Calibrated",
        },
    ),
    (
        "SEAT_INSTANCES",
        comfort.SEAT_INSTANCES,
        comfort_pb2.CabinSurface,
        {
            "STEERING_WHEEL": "steeringWheel",
            "SEAT_ROW_1_LEFT": "seatFrontLeft",
            "SEAT_ROW_1_RIGHT": "seatFrontRight",
            "SEAT_ROW_2_LEFT": "seatRearLeft",
            "SEAT_ROW_2_RIGHT": "seatRearRight",
            "SEAT_ROW_3_LEFT": "seatThirdRowLeft",
            "SEAT_ROW_3_RIGHT": "seatThirdRowRight",
        },
    ),
    (
        "SEAT_DEVICES",
        comfort.SEAT_DEVICES,
        comfort_pb2.ConditioningType,
        {"CONDITIONING_HEAT": "Heat", "CONDITIONING_VENT": "Vent"},
    ),
    (
        "SEAT_LEVELS",
        comfort.SEAT_LEVELS,
        comfort_pb2.ConditioningLevel,
        {
            "CONDITIONING_LEVEL_UNSPECIFIED": "Off",
            "CONDITIONING_LEVEL_1": "Level_1",
            "CONDITIONING_LEVEL_2": "Level_2",
            "CONDITIONING_LEVEL_3": "Level_3",
        },
    ),
]


@pytest.mark.parametrize(
    ("table", "enum_type", "expected"),
    [case[1:] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_table_keys_name_their_enum_members(
    table: dict[int, str], enum_type: Any, expected: dict[str, str]
) -> None:
    assert {enum_type.Name(k): v for k, v in table.items()} == expected


def test_time_estimate_invalid_names_the_invalid_validities() -> None:
    assert {
        charging_pb2.TimeEstimationValidity.Name(v)
        for v in charging._TIME_ESTIMATE_INVALID
    } == {
        "TIME_ESTIMATION_VALIDITY_INVALID",
        "TIME_ESTIMATION_VALIDITY_PACK_DISCHARGING",
    }
