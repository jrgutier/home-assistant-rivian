"""Asynchronous Python client for the Rivian API."""

# Vendored from jrgutier/rivian-python-client @ 5a1205e39d1d.
# Upstream generates __version__.py with Hatchling at build time and gitignores
# it; there is no build step here, so the version is static and records the
# commit this copy came from. Edited in place -- no external package to bump.
__version__ = "vendored+5a1205e39d1d"
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
