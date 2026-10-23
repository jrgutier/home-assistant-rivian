from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder, _fields
from .proto import user_passcodes_pb2

_DRIVE_AUTH_SETTING_MAP: Final[dict[int, str]] = {
    1: "none",
    2: "mobile_notif",
}


@RVMDecoder.register(
    user_passcodes_pb2.DriveAuthPasscode,
    "user_passcodes.passcode_types.drive_auth",
)
def decode_drive_auth(m: user_passcodes_pb2.DriveAuthPasscode) -> dict[str, Any]:
    return _fields(m, {"state": ("driveAuthSetting", _DRIVE_AUTH_SETTING_MAP)})
