"""Asynchronous Python client for the Rivian API."""

# Vendored from jrgutier/rivian-python-client @ ef8230d11af3.
# Upstream generates __version__.py with Hatchling at build time and gitignores
# it; there is no build step here, so the version is static and records the
# commit this copy came from. Edited in place -- no external package to bump.
__version__ = "vendored+ef8230d11af3"
from .const import VehicleCommand
from .parallax import ParallaxCommand, RVMType
from .rivian import Rivian

__all__ = [
    "ParallaxCommand",
    "RVMType",
    "Rivian",
    "VehicleCommand",
    "__version__",
]
