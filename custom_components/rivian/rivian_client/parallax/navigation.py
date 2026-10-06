"""Decoders for `navigation.*` topics."""

from __future__ import annotations

from typing import Any

from .core import RVMDecoder
from .proto import navigation_pb2


@RVMDecoder.register(
    navigation_pb2.TripProgress,
    "navigation.navigation_service.trip_progress",
)
def decode_trip_progress(m: navigation_pb2.TripProgress) -> dict[str, Any]:
    """Decode navigation.navigation_service.trip_progress (name-match: `u3l`).

    #1 legetautc and #2 tripetautc (Timestamps), #3 nextstopindex (not
    emitted; nothing reads it), #4 legremainingdistancemeters and #5 legremainingdurationseconds (doubles,
    units in the app's own field names). #6, the vehicle's GPS fix, is not
    emitted: dynamics.vehicle.gnss already supplies the location.

    Returns dict with keys, when sent:
        - navLegEta, navTripEta: int (epoch seconds)
        - navLegRemainingDistance: float (m), navLegRemainingDuration: float (s)
    """
    result: dict[str, Any] = {}
    if m.next_waypoint.HasField("seconds"):
        result["navLegEta"] = m.next_waypoint.seconds
    if m.final_destination.HasField("seconds"):
        result["navTripEta"] = m.final_destination.seconds
    if m.HasField("distance_remaining"):
        result["navLegRemainingDistance"] = round(m.distance_remaining, 1)
    if m.HasField("duration_remaining"):
        result["navLegRemainingDuration"] = round(m.duration_remaining, 1)
    return result
