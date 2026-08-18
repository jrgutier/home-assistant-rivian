"""Wire-format message types for the Parallax protocol.

Everything here is hand-rolled. The package carries no protobuf runtime: the
integration encodes exactly ONE message (ClimateHoldSetting, a single int32) and
one envelope, which did not justify a dependency Home Assistant pins separately
and whose generated code refuses to load when its gencode is newer than the
runtime -- a failure that took the whole integration down during vendoring.

The .proto files in this directory REMAIN as the source of truth for the wire
formats, reverse-engineered from com.rivian.android.consumer. They are
documentation and a regeneration input, not shipped code. scripts/regen_proto.sh
regenerates the classes into a temporary directory and re-asserts the golden bytes
in tests/fixtures/golden/, so the .proto files cannot drift from what is actually
encoded.
"""

from .vehicle_operation import (
    Metadata,
    Operation,
    PhoneInfo,
    Timestamp,
    VehicleOperationRequest,
)

__all__ = [
    "Metadata",
    "Operation",
    "PhoneInfo",
    "Timestamp",
    "VehicleOperationRequest",
]
