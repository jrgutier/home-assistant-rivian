from __future__ import annotations

from typing import Any

from .core import RVMDecoder
from .proto import navigation_pb2


@RVMDecoder.register(
    navigation_pb2.TripProgress,
    "navigation.navigation_service.trip_progress",
)
def decode_trip_progress(m: navigation_pb2.TripProgress) -> dict[str, Any]:
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
