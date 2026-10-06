"""charging.schedule.time_window: the decoder s34 withheld for its GPS field.

s34 left this topic undecoded because its only frame carried the owner's home
coordinate and the fixture was withheld, so there was nothing to verify a decoder
against. A 3.17.0 app capture supplied a frame; its location submessage is zeroed
in the committed fixture (see TestNoCoordinateLeaks) and the decoder never emits
latitude/longitude. Decode is pinned against that fixture here.

Times are MINUTES, confirmed against the app UI ("Daily 11pm-6am") and by
internal consistency: 23:00 + 7h = 06:00 only reconciles in minutes. The .proto
comment that read "seconds" is corrected alongside this.
"""

from __future__ import annotations

import base64
import json
import pathlib

from custom_components.rivian.const import BINARY_SENSORS, PARALLAX_ONLY_FIELDS, SENSORS
from custom_components.rivian.rivian_client.parallax import (
    RVM_DECODERS,
    decode_charging_schedule_time_window,
)

TOPIC = "charging.schedule.time_window"
FIXTURES = pathlib.Path(__file__).parent / "client" / "fixtures" / "parallax"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())


def _payload() -> str:
    raw = (FIXTURES / MANIFEST[TOPIC]["file"]).read_bytes()
    return base64.b64encode(raw).decode()


class TestChargeScheduleDecoder:
    def test_registered(self) -> None:
        assert RVM_DECODERS[TOPIC] is decode_charging_schedule_time_window

    def test_decodes_the_committed_frame(self) -> None:
        assert decode_charging_schedule_time_window(_payload()) == {
            "chargeScheduleValid": True,
            "chargeScheduleStartMinute": 1380,
            "chargeScheduleEndMinute": 360,
            "chargeScheduleDurationMinute": 420,
            "chargeScheduleAmps": 48,
            "chargeScheduleStartDay": 3,
            "chargeScheduleEndDay": 4,
            "chargeScheduleWindow": "23:00-06:00",
        }

    def test_window_reconciles_only_in_minutes(self) -> None:
        d = decode_charging_schedule_time_window(_payload())
        start, end, dur = (
            d["chargeScheduleStartMinute"],
            d["chargeScheduleEndMinute"],
            d["chargeScheduleDurationMinute"],
        )
        assert (start + dur) % 1440 == end  # 23:00 + 7h == 06:00

    def test_empty_payload_is_empty(self) -> None:
        assert decode_charging_schedule_time_window("") == {}

    def test_inactive_schedule_reports_false_and_hides_the_window(self) -> None:
        """proto3 omits a false is_valid, so field #1 is absent on an inactive
        schedule. A non-empty frame with no field #1 is is_valid=False, and the
        window/amps are withheld so the "active" sensor cannot latch on beside a
        stale window.
        """
        # window_data (#2) present, field #1 (is_valid) omitted, location zeroed
        raw = bytes.fromhex(
            "122308e40a10e80218a40320302a12"
            + "09"
            + "00" * 8
            + "11"
            + "00" * 8
            + "30033804"
        )
        out = decode_charging_schedule_time_window(base64.b64encode(raw).decode())
        assert out == {"chargeScheduleValid": False}


class TestNoCoordinateLeaks:
    """The reason s34 withheld this: the raw frame carried a home coordinate."""

    def test_decoder_emits_no_latitude_or_longitude(self) -> None:
        out = decode_charging_schedule_time_window(_payload())
        assert not any("atitude" in k or "ongitude" in k.lower() for k in out)

    def test_committed_fixture_location_is_zeroed(self) -> None:
        raw = (FIXTURES / MANIFEST[TOPIC]["file"]).read_bytes()
        # The Location submessage (window_data #5) is present but its two doubles
        # are zero bytes -- the 1.0f exponent byte of the real latitude is gone.
        assert b"\x00\x00\x80?" not in raw
        assert b"\x2a\x12" + b"\x09" + b"\x00" * 8 + b"\x11" + b"\x00" * 8 in raw


class TestEntitiesExist:
    def test_fields_back_entities(self) -> None:
        fields = {d.field for d in SENSORS}
        fields |= {d.field for d in BINARY_SENSORS if isinstance(d.field, str)}
        # chargeScheduleValid is decoded but intentionally NOT an entity: the
        # vehicle goes silent when the schedule is disabled (hardware-verified),
        # so an "active" sensor could never read off. Only window/amps surface.
        for field in ("chargeScheduleWindow", "chargeScheduleAmps"):
            assert field in fields
            assert field in PARALLAX_ONLY_FIELDS
