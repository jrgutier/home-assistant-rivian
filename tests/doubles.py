"""A VehicleCoordinator double carrying the attributes its `__init__` sets.

`MagicMock(spec=VehicleCoordinator)` only knows class attributes, so every
instance attribute production reads directly has to be seeded here or the read
raises AttributeError.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.rivian_client import Rivian


def vehicle_coordinator_double(**overrides: Any) -> MagicMock:
    api = MagicMock(spec=Rivian)
    api.subscription_document.return_value = None
    attributes: dict[str, Any] = {
        "api": api,
        "vehicle_id": "veh-1",
        "data": {},
        "rvm_arrivals": {},
        "charging_coordinator": MagicMock(data={}),
        "drivers_coordinator": MagicMock(data={}),
        "async_set_updated_data": MagicMock(),
        "_note_unusable": MagicMock(),
        "_unsub_parallax": None,
        "_rvm_arrivals": {},
        "_subscription_keys": set(),
        "_initial": asyncio.Event(),
        "_last_document_error": None,
        "_tpms_last_update_time": None,
        "_unsub_tire_pressure": None,
        "_tpms_frames_seen": 0,
        "_last_update_time": None,
        "_watchdog_restarts": 0,
        "_last_restart_reason": None,
        "_parallax_filled_keys": set(),
        "_command_states": {},
    } | overrides
    double = MagicMock(spec=VehicleCoordinator)
    for name, value in attributes.items():
        setattr(double, name, value)
    return double
