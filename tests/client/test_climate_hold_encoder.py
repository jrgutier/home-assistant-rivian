"""The hand-rolled ClimateHoldSetting encoder must match protobuf byte for byte.

This is the ONLY payload the integration ever encodes -- a single int32 field --
so carrying the protobuf runtime for it was never proportionate. The generated
class is going away, and these golden bytes are what stops the replacement from
drifting.

Captured FROM the generated class before deleting it
(tests/fixtures/golden/climate_hold_setting.json), and independently corroborated
twice: 08ac02 is what the real vehicle returned after a 5-minute hold was written,
and 08a038 (7200s) is recorded in SENDVEHICLEOPERATION_TEST_RESULTS.md.

A round-trip test is not available here -- there is no write-side decoder -- so
golden bytes are the whole safety net.
"""

import json
import pathlib

import pytest

from custom_components.rivian.rivian_client.parallax import encode_climate_hold_setting

GOLDEN = json.loads(
    (
        pathlib.Path(__file__).parent / "fixtures/golden/climate_hold_setting.json"
    ).read_text()
)["ClimateHoldSetting.hold_time_duration_seconds"]


@pytest.mark.parametrize(
    ("seconds", "expected_hex"), sorted(GOLDEN.items(), key=lambda kv: int(kv[0]))
)
def test_matches_protobuf_byte_for_byte(seconds: str, expected_hex: str) -> None:
    assert encode_climate_hold_setting(int(seconds)).hex() == expected_hex


def test_the_documented_two_hour_value() -> None:
    # Recorded independently in SENDVEHICLEOPERATION_TEST_RESULTS.md.
    assert encode_climate_hold_setting(7200).hex() == "08a038"


def test_the_live_captured_value() -> None:
    # What the vehicle actually returned after writing a 5-minute hold.
    captured = (
        pathlib.Path(__file__).parent / "fixtures/parallax/climate_hold_setting.bin"
    ).read_bytes()
    assert encode_climate_hold_setting(300) == captured


def test_zero_encodes_to_nothing() -> None:
    """proto3 omits a field at its default, and the vehicle treats an empty
    payload as 'no hold configured' -- verified live across three sessions."""
    assert encode_climate_hold_setting(0) == b""


def test_the_multi_byte_varint_boundary() -> None:
    # 127 fits in one byte, 128 needs two. Getting this wrong is the classic
    # varint bug and would silently corrupt any duration above ~2 minutes.
    assert encode_climate_hold_setting(127).hex() == "087f"
    assert encode_climate_hold_setting(128).hex() == "088001"


def test_a_negative_duration_is_rejected() -> None:
    with pytest.raises(ValueError):
        encode_climate_hold_setting(-1)


class TestHandRolledTimestamp:
    """google.protobuf.Timestamp, replaced by ~20 lines.

    Golden values captured from timestamp_pb2 before it was deleted. Two edge
    cases matter: the epoch encodes to NOTHING (proto3 omits defaults, so an
    unset timestamp is an empty message, not eight zero bytes), and sub-second
    precision must reach the nanos field.
    """

    @pytest.mark.parametrize(
        ("iso", "expected_hex"),
        [
            ("2026-08-18T12:00:00+00:00", "08c09291d406"),
            ("1970-01-01T00:00:00+00:00", ""),
            ("2038-01-19T03:14:07+00:00", "08ffffffff07"),
            ("2026-08-18T12:00:00.500000+00:00", "08c09291d4061080cab5ee01"),
        ],
    )
    def test_matches_protobuf(self, iso: str, expected_hex: str) -> None:
        from datetime import datetime

        from custom_components.rivian.rivian_client.proto.vehicle_operation import (
            Timestamp,
        )

        assert (
            Timestamp.from_datetime(datetime.fromisoformat(iso))
            .SerializeToString()
            .hex()
            == expected_hex
        )

    def test_round_trips_through_to_datetime(self) -> None:
        from datetime import datetime, timezone

        from custom_components.rivian.rivian_client.proto.vehicle_operation import (
            Timestamp,
        )

        moment = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
        assert Timestamp.from_datetime(moment).ToDatetime() == moment
