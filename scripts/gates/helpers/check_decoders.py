"""Every shipped RVM must decode its captured fixture into real data.

A name-only gate is satisfied by three functions that return {}, which would
leave every entity unavailable -- the exact defect S8b exists to fix.
"""

import base64
import pathlib
import sys

from rivian.parallax import RVM_DECODERS, decode_parallax_message

FIXTURES = pathlib.Path("tests/fixtures/parallax")
SHIPPED = {
    "climate_hold_status": "comfort.cabin.climate_hold_status",
    "climate_hold_setting": "comfort.cabin.climate_hold_setting",
    "vehicle_wheels": "vehicle.wheels.vehicle_wheels",
}

failures = []
for name, rvm in SHIPPED.items():
    if rvm not in RVM_DECODERS:
        failures.append(f"{rvm} not registered")
        continue
    raw = (FIXTURES / f"{name}.bin").read_bytes()
    decoded = decode_parallax_message(
        rvm=rvm, payload=base64.b64encode(raw).decode(), timestamp="t"
    )
    if not decoded:
        failures.append(f"{rvm} decoded to {decoded!r}")
    elif set(decoded) <= {"raw"}:
        failures.append(f"{rvm} decoded to a raw passthrough: {decoded!r}")

if failures:
    sys.exit("; ".join(failures))
print("all shipped RVMs decode to real data")
