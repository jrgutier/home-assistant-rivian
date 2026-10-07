"""APK M2V data-channel commands (Gear Guard live).

PeerCommunicationManager.switchCameraViaDataChannel encodes
M2V.command (ef9) with uuid, commandName=SWITCH_CAMERA (1), camera enum.
Wrapped as e1n field 1 (COMMAND). Binary DataChannel send.
"""

from __future__ import annotations

from .rivian_client.proto.vehicle_operation import (
    encode_length_delimited,
    encode_varint,
)

GGVS_CAMERA: dict[str, int] = {
    "front": 1,
    "rear": 2,
    "left": 3,
    "right": 4,
    "bed": 5,
    "interior": 6,
}

M2V_COMMAND_NAME_SWITCH_CAMERA = 1


def encode_switch_camera(camera: str, command_uuid: str) -> bytes:
    """Return the APK SWITCH_CAMERA data-channel payload."""
    cam = GGVS_CAMERA.get(camera)
    if cam is None:
        raise ValueError(f"unknown Gear Guard camera: {camera}")
    inner = (
        encode_length_delimited(1, command_uuid.encode("utf-8"))
        + b"\x10"
        + encode_varint(M2V_COMMAND_NAME_SWITCH_CAMERA)
        + b"\x18"
        + encode_varint(cam)
    )
    return encode_length_delimited(1, inner)
