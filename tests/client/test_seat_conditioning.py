"""comfort.cabin.seat_conditioning_status.

The vehicle-state subscription reports seatRearLeftHeat and seatRearRightHeat as
'SNA' on a truck that does have rear seat heaters, so the sensors showed 'SNA' and
the selects showed 'unknown'. Parallax carries the real value on this RVM.

s43: the layout is the app's `c1i` (bound, 3.16.0) -- one repeated field #1, each
entry {#1 instance, #2 device, #3 level}. The decoder used to read fields 7-12,
which belong to a different app message (`mtm`), and returned {} on every real
frame; the committed capture now decodes (see TestTheCapture).
"""

import base64
import json
import pathlib

from custom_components.rivian.rivian_client.parallax import (
    RVM_DECODERS,
    decode_seat_conditioning_status,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "parallax"
TOPIC = "comfort.cabin.seat_conditioning_status"

# CABIN_SURFACE_INSTANCE
STEERING_WHEEL, FRONT_LEFT, FRONT_MIDDLE, FRONT_RIGHT = 1, 5, 6, 7
REAR_LEFT, REAR_RIGHT, THIRD_LEFT, THIRD_RIGHT, REAR_GLASS = 8, 10, 11, 13, 2
# CABIN_SURFACE_DEVICE
HEAT, VENT = 1, 2


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _level(instance: int, device: int, level: int = 0) -> bytes:
    """One `levels` entry under field 1. level 0 is omitted, as proto3 does."""
    inner = b"\x08" + _varint(instance) + b"\x10" + _varint(device)
    if level:
        inner += b"\x18" + _varint(level)
    return b"\x0a" + _varint(len(inner)) + inner


def payload(*parts: bytes) -> str:
    return base64.b64encode(b"".join(parts)).decode()


class TestDecodeSeatConditioning:
    def test_rear_seats_decode(self) -> None:
        """The case that prompted this: rear heat, which GraphQL will not report."""
        out = decode_seat_conditioning_status(
            payload(_level(REAR_LEFT, HEAT, 3), _level(REAR_RIGHT, HEAT, 2))
        )
        assert out == {"seatRearLeftHeat": "Level_3", "seatRearRightHeat": "Level_2"}

    def test_a_listed_surface_with_no_level_is_off(self) -> None:
        """CABIN_SURFACE_LEVEL has no OFF member, so an entry with no level is
        the only way the message can say a present heater is off."""
        assert decode_seat_conditioning_status(payload(_level(REAR_LEFT, HEAT))) == {
            "seatRearLeftHeat": "Off"
        }

    def test_heat_and_vent_on_one_seat_are_separate_entries(self) -> None:
        out = decode_seat_conditioning_status(
            payload(
                _level(FRONT_LEFT, HEAT, 1),
                _level(FRONT_LEFT, VENT, 3),
                _level(FRONT_RIGHT, HEAT),
                _level(FRONT_RIGHT, VENT, 2),
            )
        )
        assert out == {
            "seatFrontLeftHeat": "Level_1",
            "seatFrontLeftVent": "Level_3",
            "seatFrontRightHeat": "Off",
            "seatFrontRightVent": "Level_2",
        }

    def test_steering_wheel_and_third_row(self) -> None:
        out = decode_seat_conditioning_status(
            payload(
                _level(STEERING_WHEEL, HEAT, 2),
                _level(THIRD_LEFT, HEAT, 1),
                _level(THIRD_RIGHT, HEAT),
            )
        )
        assert out == {
            "steeringWheelHeat": "Level_2",
            "seatThirdRowLeftHeat": "Level_1",
            "seatThirdRowRightHeat": "Off",
        }

    def test_surfaces_with_no_gateway_field_are_dropped(self) -> None:
        """Rear glass, the middle seats and rear vents have no field to fill."""
        out = decode_seat_conditioning_status(
            payload(
                _level(REAR_GLASS, HEAT, 1),
                _level(FRONT_MIDDLE, HEAT, 1),
                _level(REAR_LEFT, VENT, 1),
                _level(REAR_LEFT, HEAT, 1),
            )
        )
        assert out == {"seatRearLeftHeat": "Level_1"}

    def test_an_unknown_level_is_dropped(self) -> None:
        """A level past LEVEL3 is new firmware, not something to guess at."""
        assert (
            decode_seat_conditioning_status(payload(_level(REAR_LEFT, HEAT, 4))) == {}
        )

    def test_empty_and_garbage_are_safe(self) -> None:
        assert decode_seat_conditioning_status("") == {}
        assert decode_seat_conditioning_status("!!!not-base64!!!") == {}

    def test_the_values_are_ones_the_entities_accept(self) -> None:
        """The decoder is useless if it emits a vocabulary the select rejects --
        that is exactly the 'unknown' state this fixes."""
        from custom_components.rivian.select import LEVELS

        out = decode_seat_conditioning_status(
            payload(*(_level(REAR_LEFT, HEAT, n) for n in range(4)))
        )
        for value in out.values():
            assert value in LEVELS

    def test_it_is_registered(self) -> None:
        assert RVM_DECODERS[TOPIC] is decode_seat_conditioning_status


class TestTheCapture:
    """The committed live frame: nine entries, every surface listed, none on."""

    def test_the_live_frame_decodes_to_nine_surfaces_all_off(self) -> None:
        manifest = json.loads((FIXTURES / "manifest.json").read_text())
        raw = (FIXTURES / manifest[TOPIC]["file"]).read_bytes()

        out = decode_seat_conditioning_status(base64.b64encode(raw).decode())

        assert out == {
            "steeringWheelHeat": "Off",
            "seatFrontLeftHeat": "Off",
            "seatFrontLeftVent": "Off",
            "seatFrontRightHeat": "Off",
            "seatFrontRightVent": "Off",
            "seatRearLeftHeat": "Off",
            "seatRearRightHeat": "Off",
            "seatThirdRowLeftHeat": "Off",
            "seatThirdRowRightHeat": "Off",
        }
