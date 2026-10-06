"""The sendVehicleOperation envelope classes.

This package used to hold the reverse-engineered `.proto` files as documentation
and a hand-rolled encoder beside them, and its docstring said the client carried
no protobuf runtime. Since s49 it does: the schemas live in `../parallax/proto/`,
are compiled by scripts/regen_proto.sh, and are what both the decoders and this
encoder run on. See docs/development/PARALLAX_SCHEMAS.md.

What stays here is `vehicle_operation.py`, at the import path the client and its
tests have always used.
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
