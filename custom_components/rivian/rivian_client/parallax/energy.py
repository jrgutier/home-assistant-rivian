"""Decoders for `energy.*` topics: the high- and low-voltage batteries."""

from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder, _fields
from .proto import energy_pb2

# energy.high_voltage.battery_characteristics -- BatteryCellType
_BATTERY_CELL_TYPE_MAP: Final[dict[int, str]] = {
    1: "50g",
    2: "53g",
    3: "g124",
    4: "lg_4695",
}

# energy.low_voltage.battery_state -- LowVoltageBatteryHealthStatus
_LOW_VOLTAGE_HEALTH_MAP: Final[dict[int, str]] = {
    1: "normal",
    2: "low",
}


@RVMDecoder.register(energy_pb2.BatteryState, "energy.high_voltage.battery_state")
def decode_battery_state(m: energy_pb2.BatteryState) -> dict[str, Any]:
    """Decode energy.high_voltage.battery_state.

    Returns dict with keys:
        - soc: float (percentage, 0-100)
        - packEnergyKwh: float

    `charge_state` has two fields in the app (`bc1`, 3.16.0): #1
    charge_percentage and #2 charge_kwh, both double. An earlier #3 "rangeKm"
    read here does not exist in either app build or in any capture.
    """
    result: dict[str, Any] = {}
    if m.charge_state.HasField("soc"):
        result["soc"] = round(m.charge_state.soc, 2)
    if m.charge_state.HasField("pack_energy"):
        result["packEnergyKwh"] = round(m.charge_state.pack_energy, 2)
    return result


@RVMDecoder.register(
    energy_pb2.BatteryCharacteristics,
    "energy.high_voltage.battery_characteristics",
)
def decode_battery_characteristics(
    m: energy_pb2.BatteryCharacteristics,
) -> dict[str, Any]:
    """Decode energy.high_voltage.battery_characteristics.

    Returns dict with keys:
        - batteryCellType: str

    Fields 5 and 6 (user_total_kwh, user_max_kwh) are floats and would map to
    batteryCapacity, but they are fixed32 (wire type 5) and _decode_enum_fields
    reads varints only. Left undecoded rather than misdecoded: the
    subscription already carries batteryCapacity, and a wrong kWh figure on the
    energy sensor is worse than no second source for it.
    """
    return _fields(m, {"cell_type": ("batteryCellType", _BATTERY_CELL_TYPE_MAP)})


@RVMDecoder.register(
    energy_pb2.LowVoltageBatteryState,
    "energy.low_voltage.battery_state",
)
def decode_low_voltage_battery(m: energy_pb2.LowVoltageBatteryState) -> dict[str, Any]:
    """Decode energy.low_voltage.battery_state.

    Returns dict with keys:
        - twelveVoltBatteryHealth: str
    """
    return _fields(m, {"health": ("twelveVoltBatteryHealth", _LOW_VOLTAGE_HEALTH_MAP)})
