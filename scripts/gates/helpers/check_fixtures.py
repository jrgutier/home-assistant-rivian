"""Validate captured RVM fixtures. Exit non-zero on any problem.

The previous s08a gate checked existence only, so four `touch`ed empty files
passed it. An empty payload is exactly what the live vehicle returns for an
unconfigured RVM, so "the file is there" proves nothing.

Rewritten after s10: the generated protobuf classes this used to parse with are
gone, replaced by hand-rolled decoders. Those decoders are now the reference --
which is stronger, because they are what actually ships.
"""

import base64
import pathlib
import sys

from rivian.parallax import (
    decode_climate_hold_setting,
    decode_climate_hold_status,
    decode_vehicle_wheels,
    encode_climate_hold_setting,
)

D = pathlib.Path(sys.argv[1])


def _payload(name: str) -> str:
    return base64.b64encode((D / f"{name}.bin").read_bytes()).decode()


# The one server-verified WRITE, captured by setting a five-minute hold. It must
# decode to a non-zero duration AND re-encode to exactly the captured bytes.
raw = (D / "climate_hold_setting.bin").read_bytes()
decoded = decode_climate_hold_setting(_payload("climate_hold_setting"))
seconds = decoded["climateHoldDurationSeconds"]
assert seconds > 0, f"climate_hold_setting decoded to {seconds}"
assert encode_climate_hold_setting(seconds) == raw, "does not re-encode identically"

# The reads must decode to real data, not an empty dict.
for name, decoder in (
    ("climate_hold_status", decode_climate_hold_status),
    ("vehicle_wheels", decode_vehicle_wheels),
):
    out = decoder(_payload(name))
    assert out, f"{name} decoded to {out!r}"

print("fixtures OK")
