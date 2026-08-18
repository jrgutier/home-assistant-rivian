"""Validate captured Parallax RVM fixtures. Exit non-zero on any problem.

The previous s08a gate checked existence only, so four `touch`ed empty files
passed it. An empty payload is exactly what the live vehicle returns for an
unconfigured RVM, so "the file is there" proves nothing.
"""

import pathlib
import sys

from google.protobuf.internal import decoder

from rivian.proto.rivian_climate_pb2 import ClimateHoldSetting

D = pathlib.Path(sys.argv[1])

# The one server-verified WRITE: captured by setting a 5-minute hold, so it must
# carry a non-zero duration and survive a re-encode unchanged.
raw = (D / "climate_hold_setting.bin").read_bytes()
setting = ClimateHoldSetting()
setting.ParseFromString(raw)
assert setting.hold_time_duration_seconds > 0, "climate_hold_setting duration is zero"
assert setting.SerializeToString() == raw, "climate_hold_setting re-encode differs"

# The reads only need to be well-formed protobuf; their layouts are decoded in s08b.
for name in ("climate_hold_status", "vehicle_wheels"):
    raw = (D / f"{name}.bin").read_bytes()
    assert raw, f"{name} is empty"
    i = 0
    while i < len(raw):
        key, i = decoder._DecodeVarint(raw, i)
        wire_type = key & 7
        if wire_type == 0:
            _, i = decoder._DecodeVarint(raw, i)
        elif wire_type == 2:
            length, i = decoder._DecodeVarint(raw, i)
            i += length
        elif wire_type == 5:
            i += 4
        elif wire_type == 1:
            i += 8
        else:
            raise SystemExit(f"{name}: unsupported wire type {wire_type}")
    assert i == len(raw), f"{name}: trailing garbage"

print("fixtures OK")
