"""Decoders for `geofence.*` topics."""

from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder
from .proto import geofence_pb2

_GEOFENCE_TYPE: Final[dict[int, str]] = {0: "custom", 1: "home", 2: "work"}


@RVMDecoder.register(
    geofence_pb2.FavoriteGeofences,
    "geofence.geofence_service.favoriteGeofences",
    empty_payload=True,
)
def decode_favorite_geofences(m: geofence_pb2.FavoriteGeofences) -> dict[str, Any]:
    """Decode geofence.geofence_service.favoriteGeofences (name-match: `wq7`).

    Repeated #1 favorites {#1 type (0 CUSTOM, 1 HOME, 2 WORK), #2 name}.

    Returns dict with keys:
        - favoriteGeofences: list[{"type": str, "name": str}]
    """
    return {
        "favoriteGeofences": [
            {
                "type": _GEOFENCE_TYPE.get(geofence.type, "unknown"),
                "name": geofence.name,
            }
            for geofence in m.geofence
        ]
    }
