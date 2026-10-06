"""Decoders for `vehicle_access.*` topics."""

from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder
from .proto import vehicle_access_pb2

# `fre` #2 CCC_PASSIVE_PERMISSION_STATUS (3.16.0)
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
    """Decode vehicle_access.{state.passive_entry,passive_entry.passive_entry}.

    `fre` is BOUND, request-side, to vehicle_access.passive_entry.passive_entry:
    the app builds it and sends it there as a PARALLAX_OPERATION_REQUEST
    (FOLLOWUP_S45.md, wy9.java:2225-2234). It never parses one. Reading the
    vehicle's publication on that topic, and on the .state sibling (a
    name-match), as the same message is the inference here.

    Returns dict with keys:
        - passiveEntryBluetoothInCcc: bool (#1)
        - cccPassivePermissionStatus: str (#2)
    """
    return {
        "passiveEntryBluetoothInCcc": m.allow_bluetooth_while_in_ccc,
        "cccPassivePermissionStatus": _CCC_PASSIVE_PERMISSION.get(
            m.ccc_passive_permission, _CCC_PASSIVE_PERMISSION[0]
        ),
    }
