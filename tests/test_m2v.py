"""APK SWITCH_CAMERA data-channel payload."""

from __future__ import annotations

import pytest

from custom_components.rivian.m2v import GGVS_CAMERA, encode_switch_camera


def test_switch_camera_left_is_command_field_one() -> None:
    """e1n COMMAND is field 1 wrapping ef9 uuid + SWITCH_CAMERA + CAMERA_LEFT."""
    uid = "00000000-0000-0000-0000-000000000001"
    payload = encode_switch_camera("left", uid)
    assert payload[0] == 0x0A
    inner = payload[2:]
    assert inner[0] == 0x0A
    assert inner[1] == len(uid)
    assert inner[2 : 2 + len(uid)] == uid.encode()
    rest = inner[2 + len(uid) :]
    assert rest[0] == 0x10
    assert rest[1] == 1
    assert rest[2] == 0x18
    assert rest[3] == GGVS_CAMERA["left"]


def test_long_uuid_uses_multi_byte_varint() -> None:
    """Protobuf length fields are varints; a 200-byte uuid is not a single byte."""
    uid = "x" * 200
    payload = encode_switch_camera("left", uid)
    assert payload[0] == 0x0A
    assert payload[1] != 200


def test_unknown_camera_is_rejected() -> None:
    """A typo must not encode a default camera — the vehicle would switch wrong."""
    with pytest.raises(ValueError, match="unknown Gear Guard camera"):
        encode_switch_camera("side", "00000000-0000-0000-0000-000000000001")


def test_ggvs_enum_matches_apk_cf9() -> None:
    """cf9.java: CAMERA_FRONT=1 … CAMERA_INTERIOR=6."""
    assert GGVS_CAMERA == {
        "front": 1,
        "rear": 2,
        "left": 3,
        "right": 4,
        "bed": 5,
        "interior": 6,
    }
