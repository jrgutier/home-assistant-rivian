"""Asynchronous Python client for the Rivian API."""

# Vendored from jrgutier/rivian-python-client @ 3cec320254f9.
# Upstream generates __version__.py with Hatchling and gitignores it; there is
# no build step here, so the version is static and records the source commit.
__version__ = "vendored+3cec320254f9"
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
