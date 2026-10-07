"""Decoders for `energy_edge_compute.graphs.*` topics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Final

from .core import _TIMESTAMP_FORMAT, RVMDecoder, _name
from .proto import energy_edge_compute_pb2

# EnergyDistribution field number -> key suffix (EnergyDistribution in proto/energy_edge_compute.proto).
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
    """Decode energy_edge_compute.graphs.charge_session_breakdown.

    Layout is the app's `nl2` (3.16.0; `uncalled_parse_wrappers`), the only
    message class in either app build whose fields fit the live capture:

        1 total_kwh float          8 range_added_kms uint32
        2 pack_kwh float           9 current_power float
        3 thermal_kwh float       10 current_range_per_hour uint32
        4 outlets_kwh float       11 session_cost message
        5 system_kwh float        12 is_free_session bool
        6 session_duration_mins   13 charging_state enum
        7 time_remaining_mins

    Field 10 was previously read as an integer kW figure, so a completed
    session reported 2.0 kW; it is the range rate. proto3 omits a zero, so a
    non-empty frame without #8, #9 or #10 means zero, not "unknown".

    Returns dict with keys matching legacy getLiveSessionData field names:
        - totalChargedEnergy: float (kWh)
        - power: float (kW)
        - rangeAddedThisSession: int (km)
        - kilometersChargedPerHour: int (km/h)
    """
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
    """Decode energy_edge_compute.graphs.charging_graph_global.

    Returns dict with keys:
        - startTime: str (ISO format timestamp of session start)
        - timeElapsed: int (seconds elapsed since session start)
        - power: float (kW, latest segment power)
    """
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
        st = datetime.fromtimestamp(first_seg["start_ms"] / 1000, timezone.utc)
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
    """Decode energy_edge_compute.graphs.parked_energy_distributions.

    Schema: `proto/energy_edge_compute.proto`, three `EnergyDistribution` submessages.
    Emitted as nested dicts rather than 30 flattened keys, because the three
    windows are the same ten measurements over different periods and flattening
    would invent thirty names for ten concepts.

    Returns dict with keys:
        - parkedEnergyLast24Hours: dict[str, float]
        - parkedEnergyLast8Hours: dict[str, float]
        - parkedEnergyLastParkSession: dict[str, float]
    """
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
    """Decode energy_edge_compute.graphs.cold_weather_soc (name-match: `jx3`).

    #1 soc_perc_green, #2 soc_perc_blue (percent), #3 cold_range_impact_km.
    Units are from the field names only; the app references the class nowhere
    (FOLLOWUP_S45.md). proto3 omits zeros, so absent fields are 0. The capture
    (`082e`) is green = 46.

    Returns dict with keys:
        - coldWeatherSocGreen, coldWeatherSocBlue: int (percent)
        - coldRangeImpact: int (km)
    """
    return {
        "coldWeatherSocGreen": m.soc_perc_green,
        "coldWeatherSocBlue": m.soc_perc_blue,
        "coldRangeImpact": m.cold_range_impact,
    }
