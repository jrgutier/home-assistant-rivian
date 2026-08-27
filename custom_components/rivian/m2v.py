"""APK M2V data-channel commands (Gear Guard live).

PeerCommunicationManager.switchCameraViaDataChannel encodes
M2V.command (ef9) with uuid, commandName=SWITCH_CAMERA (1), camera enum.
Wrapped as e1n field 1 (COMMAND). Binary DataChannel send.
"""

from __future__ import annotations

GGVS_CAMERA: dict[str, int] = {
    "front": 1,
    "rear": 2,
    "left": 3,
    "right": 4,
    "bed": 5,
    "interior": 6,
}

M2V_COMMAND_NAME_SWITCH_CAMERA = 1


def _varint(value: int) -> bytes:
    """Protobuf base-128 varint."""
    if value < 0:
        raise ValueError("varint must be non-negative")
    out = bytearray()
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def encode_switch_camera(camera: str, command_uuid: str) -> bytes:
    """Return the APK SWITCH_CAMERA data-channel payload."""
    cam = GGVS_CAMERA.get(camera)
    if cam is None:
        raise ValueError(f"unknown Gear Guard camera: {camera}")
    uid = command_uuid.encode("utf-8")
    inner = bytearray()
    inner.append(0x0A)
    inner.extend(_varint(len(uid)))
    inner.extend(uid)
    inner.append(0x10)
    inner.extend(_varint(M2V_COMMAND_NAME_SWITCH_CAMERA))
    inner.append(0x18)
    inner.extend(_varint(cam))
    outer = bytearray()
    outer.append(0x0A)
    outer.extend(_varint(len(inner)))
    outer.extend(inner)
    return bytes(outer)
