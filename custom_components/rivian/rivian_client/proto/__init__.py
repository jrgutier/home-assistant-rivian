"""Protocol Buffer message definitions for Parallax protocol.

This package contains protobuf message classes for Rivian's Parallax protocol,
which is a cloud-based GraphQL/HTTP protocol for vehicle commands and data retrieval.
"""

from .base import SessionCost, TimeOfDay
from .charging import (
    ChargingScheduleTimeWindow,
    ChargingSessionChartData,
    ChargingSessionLiveData,
)
from .climate import CabinVentilationSetting, ClimateHoldSetting, ClimateHoldStatus
from .energy import ParkedEnergyMonitor
from .navigation import TripInfo, TripProgress, Waypoint
from .ota import OTAState
from .security import (
    GearGuardConsents,
    GearGuardDailyLimits,
    GeoFence,
    PassiveEntrySetting,
    PassiveEntryStatus,
    VehicleGeoFences,
)
from .vehicle import HalloweenSettings, VehicleWheels, WheelInfo

__all__ = [
    "CabinVentilationSetting",
    "ChargingScheduleTimeWindow",
    "ChargingSessionChartData",
    "ChargingSessionLiveData",
    "ClimateHoldSetting",
    "ClimateHoldStatus",
    "GearGuardConsents",
    "GearGuardDailyLimits",
    "GeoFence",
    "HalloweenSettings",
    "OTAState",
    "ParkedEnergyMonitor",
    "PassiveEntrySetting",
    "PassiveEntryStatus",
    "SessionCost",
    "TimeOfDay",
    "TripInfo",
    "TripProgress",
    "VehicleGeoFences",
    "VehicleWheels",
    "Waypoint",
    "WheelInfo",
]
