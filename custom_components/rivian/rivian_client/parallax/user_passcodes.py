"""Decoders for `user_passcodes.*` topics."""

from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder, _fields
from .proto import user_passcodes_pb2

# Drive-auth vocabulary, transcribed from the 3.17.0 app's protobuf-lite field-info
# descriptor (defpackage/q97.java) and its enum class p97. 0 is SNA and is dropped.
_DRIVE_AUTH_SETTING_MAP: Final[dict[int, str]] = {
    1: "none",
    2: "mobile_notif",
}


@RVMDecoder.register(
    user_passcodes_pb2.DriveAuthPasscode,
    "user_passcodes.passcode_types.drive_auth",
)
def decode_drive_auth(m: user_passcodes_pb2.DriveAuthPasscode) -> dict[str, Any]:
    """Decode user_passcodes.passcode_types.drive_auth -> `q97`.

    Single field: #1 driveAuthSetting (enum p97: 0 SNA, 1 NONE, 2 MOBILE_NOTIF).
    0 (SNA) is dropped like every other invalid state.
    """
    return _fields(m, {"state": ("driveAuthSetting", _DRIVE_AUTH_SETTING_MAP)})
