from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder
from .proto import vehicle_access_pb2

_CCC_PASSIVE_PERMISSION: Final[dict[int, str]] = {
    0: "sna",
    1: "disabled",
    2: "enabled",
}


@RVMDecoder.register(
    vehicle_access_pb2.PassiveEntryState,
    "vehicle_access.state.passive_entry",
    "vehicle_access.passive_entry.passive_entry",
    empty_payload=True,
)
def decode_passive_entry_state(
    m: vehicle_access_pb2.PassiveEntryState,
) -> dict[str, Any]:
    return {
        "passiveEntryBluetoothInCcc": m.allow_bluetooth_while_in_ccc,
        "cccPassivePermissionStatus": _CCC_PASSIVE_PERMISSION.get(
            m.ccc_passive_permission, _CCC_PASSIVE_PERMISSION[0]
        ),
    }
