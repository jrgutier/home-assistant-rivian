from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder, _fields
from .proto import energy_pb2

_BATTERY_CELL_TYPE_MAP: Final[dict[int, str]] = {
    1: "50g",
    2: "53g",
    3: "g124",
    4: "lg_4695",
}

_LOW_VOLTAGE_HEALTH_MAP: Final[dict[int, str]] = {
    1: "normal",
    2: "low",
}


@RVMDecoder.register(energy_pb2.BatteryState, "energy.high_voltage.battery_state")
def decode_battery_state(m: energy_pb2.BatteryState) -> dict[str, Any]:
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
    return _fields(m, {"cell_type": ("batteryCellType", _BATTERY_CELL_TYPE_MAP)})


@RVMDecoder.register(
    energy_pb2.LowVoltageBatteryState,
    "energy.low_voltage.battery_state",
)
def decode_low_voltage_battery(m: energy_pb2.LowVoltageBatteryState) -> dict[str, Any]:
    return _fields(m, {"health": ("twelveVoltBatteryHealth", _LOW_VOLTAGE_HEALTH_MAP)})
