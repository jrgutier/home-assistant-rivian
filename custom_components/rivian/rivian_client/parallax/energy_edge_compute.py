from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

from .core import _TIMESTAMP_FORMAT, RVMDecoder, _name
from .proto import energy_edge_compute_pb2

_ENERGY_DISTRIBUTION: Final[dict[int, str]] = {
    1: "totalKwh",
    2: "thermalKwh",
    3: "outletsKwh",
    4: "systemKwh",
    5: "gearGuardKwh",
    6: "totalRange",
    7: "thermalRange",
    8: "outletsRange",
    9: "systemRange",
    10: "gearGuardRange",
}


@RVMDecoder.register(
    energy_edge_compute_pb2.ChargeSessionBreakdown,
    "energy_edge_compute.graphs.charge_session_breakdown",
    skip_empty_message=True,
)
def decode_charge_session_breakdown(
    m: energy_edge_compute_pb2.ChargeSessionBreakdown,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "power": round(m.power, 2),
        "rangeAddedThisSession": m.range_added,
        "kilometersChargedPerHour": m.range_rate,
    }
    if m.HasField("total_energy"):
        result["totalChargedEnergy"] = round(m.total_energy, 4)
    return result


@RVMDecoder.register(
    energy_edge_compute_pb2.ChargingGraphGlobal,
    "energy_edge_compute.graphs.charging_graph_global",
)
def decode_charging_graph_global(
    m: energy_edge_compute_pb2.ChargingGraphGlobal,
) -> dict[str, Any]:
    segments = []
    for segment in m.segment:
        seg: dict[str, Any] = {}
        if segment.HasField("power"):
            seg["power"] = round(segment.power, 2)
        if segment.HasField("start_time"):
            seg["start_ms"] = segment.start_time
        if segment.HasField("end_time"):
            seg["end_ms"] = segment.end_time
        if segment.HasField("state"):
            seg["state"] = segment.state
        segments.append(seg)

    if not segments:
        return {}

    active_segments = [
        s for s in segments if s.get("power", 0) > 0 or s.get("state") == 3
    ]

    first_seg = active_segments[0] if active_segments else segments[0]
    result: dict[str, Any] = {}

    if "start_ms" in first_seg:
        st = datetime.fromtimestamp(first_seg["start_ms"] / 1000, UTC)
        result["startTime"] = st.strftime(_TIMESTAMP_FORMAT)

    result["timeElapsed"] = sum(
        max(0, int((s["end_ms"] - s["start_ms"]) / 1000))
        for s in active_segments
        if "end_ms" in s and "start_ms" in s
    )

    latest_segment = segments[-1]
    if latest_segment.get("power", 0) > 0 and latest_segment.get("state") != 8:
        result["power"] = latest_segment["power"]
        result["kilometersChargedPerHour"] = round(result["power"] * 3.5, 1)
    else:
        result["power"] = 0.0
        result["kilometersChargedPerHour"] = 0.0

    return result


@RVMDecoder.register(
    energy_edge_compute_pb2.ParkedEnergyDistributions,
    "energy_edge_compute.graphs.parked_energy_distributions",
)
def decode_parked_energy_distributions(
    m: energy_edge_compute_pb2.ParkedEnergyDistributions,
) -> dict[str, Any]:
    windows = {
        "last_24_hours": "parkedEnergyLast24Hours",
        "last_8_hours": "parkedEnergyLast8Hours",
        "last_park_session": "parkedEnergyLastParkSession",
    }
    result: dict[str, Any] = {}
    for field, key in windows.items():
        distribution = getattr(m, field)
        window: dict[str, float] = {
            suffix: round(getattr(distribution, name), 4)
            for number, suffix in _ENERGY_DISTRIBUTION.items()
            if distribution.HasField(name := _name(distribution, number))
        }
        if window:
            result[key] = window
    return result


@RVMDecoder.register(
    energy_edge_compute_pb2.ColdWeatherSoc,
    "energy_edge_compute.graphs.cold_weather_soc",
    empty_payload=True,
)
def decode_cold_weather_soc(
    m: energy_edge_compute_pb2.ColdWeatherSoc,
) -> dict[str, Any]:
    return {
        "coldWeatherSocGreen": m.soc_perc_green,
        "coldWeatherSocBlue": m.soc_perc_blue,
        "coldRangeImpact": m.cold_range_impact,
    }
