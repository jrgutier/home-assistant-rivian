"""The closure and lock id maps, against the ids the Rivian app itself uses.

CLOSURE_MAP mapped id 6 to closureSideBinLeftClosed. The app's
CLOSURE_INSTANCE enum (com.rivian.android.consumer 3.15.0) says 6 is TAILGATE and
8 is SIDE_BIN_LEFT, so the left gear tunnel binary sensor was reporting the
tailgate's state -- and the real side bins, tonneau and charge port were dropped
entirely because nothing mapped their ids.

The values below are transcribed from the decompiled enums and are the ground
truth these maps must match:

    CLOSURE_INSTANCE            LOCK_INSTANCE
    0  UNSPECIFIED              0  UNSPECIFIED
    1  DOOR_ROW_1_LEFT          1  DOOR_FRONT_LEFT
    2  DOOR_ROW_1_RIGHT         2  DOOR_FRONT_RIGHT
    3  DOOR_ROW_2_LEFT          3  DOOR_BACK_LEFT
    4  DOOR_ROW_2_RIGHT         4  DOOR_BACK_RIGHT
    5  FRUNK                    5  FRUNK
    6  TAILGATE                 6  TAILGATE
    7  LIFTGATE                 7  LIFTGATE
    8  SIDE_BIN_LEFT            8  SIDE_BIN_LEFT
    9  SIDE_BIN_RIGHT           9  SIDE_BIN_RIGHT
    10 CHARGE_PORT              10 CHARGE_PORT
    11 TONNEAU                  11 TRUNK_SECURITY
    12 WINDOW_FRONT_LEFT        12 CENTER_CONSOLE
    13 WINDOW_FRONT_RIGHT       13 GLOVE_BOX
    14 WINDOW_BACK_LEFT         14 GEAR_GUARD
    15 WINDOW_BACK_RIGHT        15 TONNEAU
    16 WINDOW_REAR
    10000 GROUP_WINDOWS
"""

from custom_components.rivian.rivian_client.parallax import CLOSURE_MAP, LOCK_MAP

# id -> the substring the mapped field name must contain, per the app's enum.
CLOSURE_TRUTH = {
    1: "doorFrontLeft",
    2: "doorFrontRight",
    3: "doorRearLeft",
    4: "doorRearRight",
    5: "Frunk",
    6: "Tailgate",
    7: "Liftgate",
    8: "SideBinLeft",
    9: "SideBinRight",
    11: "Tonneau",
    12: "windowFrontLeft",
    13: "windowFrontRight",
    14: "windowRearLeft",
    15: "windowRearRight",
}
LOCK_TRUTH = {
    1: "doorFrontLeft",
    2: "doorFrontRight",
    3: "doorRearLeft",
    4: "doorRearRight",
    5: "Frunk",
    6: "Tailgate",
    7: "Liftgate",
    8: "SideBinLeft",
    9: "SideBinRight",
    15: "Tonneau",
}


class TestClosureIds:
    def test_id_six_is_the_tailgate_not_a_side_bin(self) -> None:
        """The specific defect: a truck's left gear tunnel showed tailgate state."""
        assert "Tailgate" in CLOSURE_MAP[6]
        assert "SideBin" not in CLOSURE_MAP[6]

    def test_the_side_bins_have_their_own_ids(self) -> None:
        assert "SideBinLeft" in CLOSURE_MAP[8]
        assert "SideBinRight" in CLOSURE_MAP[9]

    def test_every_mapped_id_matches_the_app(self) -> None:
        for cid, expected in CLOSURE_TRUTH.items():
            assert cid in CLOSURE_MAP, f"closure id {cid} ({expected}) is unmapped"
            assert expected.lower() in CLOSURE_MAP[cid].lower(), (
                f"closure id {cid} maps to {CLOSURE_MAP[cid]!r}, "
                f"but the app calls it {expected}"
            )

    def test_no_id_is_mapped_twice(self) -> None:
        """Two ids sharing a field means one closure silently overwrites another."""
        fields = list(CLOSURE_MAP.values())
        assert len(fields) == len(set(fields)), f"duplicate targets in {fields}"


class TestLockIds:
    def test_the_tailgate_lock_is_mapped(self) -> None:
        assert 6 in LOCK_MAP and "Tailgate" in LOCK_MAP[6]

    def test_every_mapped_id_matches_the_app(self) -> None:
        for lid, expected in LOCK_TRUTH.items():
            assert lid in LOCK_MAP, f"lock id {lid} ({expected}) is unmapped"
            assert expected.lower() in LOCK_MAP[lid].lower(), (
                f"lock id {lid} maps to {LOCK_MAP[lid]!r}, "
                f"but the app calls it {expected}"
            )

    def test_no_id_is_mapped_twice(self) -> None:
        fields = list(LOCK_MAP.values())
        assert len(fields) == len(set(fields)), f"duplicate targets in {fields}"
