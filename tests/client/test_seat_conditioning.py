"""comfort.cabin.seat_conditioning_status.

The vehicle-state subscription reports seatRearLeftHeat and seatRearRightHeat as
'SNA' on a truck that does have rear seat heaters, so the sensors showed 'SNA' and
the selects showed 'unknown'. Parallax carries the real value on this RVM, which
nothing was decoding -- the app defines 71 RVM topics and we decoded 17.

Field numbers and the level enum are transcribed from
com.rivian.android.consumer 3.15.0; the payloads below are built to that spec.
"""

import base64

from custom_components.rivian.rivian_client.parallax import (
    RVM_DECODERS,
    decode_seat_conditioning_status,
)


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _seat(field_num: int, level: int) -> bytes:
    """One SeatStatus submessage: field `field_num`, containing val=level.

    The tag is varint-encoded, not a single byte: field 18's tag is 146, which
    does not fit in seven bits. Writing it as one byte produced a payload the
    decoder read as a different field entirely.
    """
    inner = _varint(1 << 3 | 0) + _varint(level)  # field 1, varint
    return _varint(field_num << 3 | 2) + _varint(len(inner)) + inner


def payload(*parts: bytes) -> str:
    return base64.b64encode(b"".join(parts)).decode()


class TestDecodeSeatConditioning:
    def test_rear_seats_decode(self) -> None:
        """The case that prompted this: rear heat, which GraphQL will not report."""
        out = decode_seat_conditioning_status(payload(_seat(9, 3), _seat(10, 2)))
        assert out["seatRearLeftHeat"] == "Level_2"
        assert out["seatRearRightHeat"] == "Level_1"

    def test_level_0_is_off(self) -> None:
        """LEVEL_0 (enum value 1) is off, not 'Level_0'. The GraphQL vocabulary
        the entities already accept says "Off"."""
        assert decode_seat_conditioning_status(payload(_seat(9, 1))) == {
            "seatRearLeftHeat": "Off"
        }

    def test_unspecified_is_omitted_not_reported_as_off(self) -> None:
        """LEVEL_UNSPECIFIED means the vehicle is not saying. Reporting that as
        "Off" would claim the heater is off when it is unknown."""
        assert decode_seat_conditioning_status(payload(_seat(9, 0))) == {}

    def test_front_seats_and_vents(self) -> None:
        out = decode_seat_conditioning_status(
            payload(_seat(7, 4), _seat(8, 1), _seat(11, 2), _seat(12, 1))
        )
        assert out == {
            "seatFrontLeftHeat": "Level_3",
            "seatFrontRightHeat": "Off",
            "seatFrontLeftVent": "Level_1",
            "seatFrontRightVent": "Off",
        }

    def test_unknown_fields_are_ignored(self) -> None:
        """Third row (18/19) has no entity; it must not crash or leak in."""
        out = decode_seat_conditioning_status(payload(_seat(18, 2), _seat(9, 2)))
        assert out == {"seatRearLeftHeat": "Level_1"}

    def test_empty_and_garbage_are_safe(self) -> None:
        assert decode_seat_conditioning_status("") == {}
        assert decode_seat_conditioning_status("!!!not-base64!!!") == {}

    def test_the_values_are_ones_the_entities_accept(self) -> None:
        """The decoder is useless if it emits a vocabulary the select rejects --
        that is exactly the 'unknown' state this fixes."""
        from custom_components.rivian.select import LEVELS

        out = decode_seat_conditioning_status(payload(_seat(9, 1), _seat(10, 2)))
        for value in out.values():
            assert value in LEVELS

    def test_it_is_registered(self) -> None:
        assert (
            RVM_DECODERS["comfort.cabin.seat_conditioning_status"]
            is decode_seat_conditioning_status
        )
