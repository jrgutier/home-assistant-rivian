from __future__ import annotations

from typing import Any, Final

from .data_classes import RivianCameraEntityDescription

DEFAULT_MOTION_CAMERA: Final = "left"
EXTERIOR_CAMERAS: Final = ("left", "right", "front", "rear")
BED_CAMERA: Final = "bed"
INTERIOR_CAMERA: Final = "interior"

CAMERAS: Final[tuple[RivianCameraEntityDescription, ...]] = (
    RivianCameraEntityDescription(
        key="gear_guard_live",
        translation_key="gear_guard_live",
        icon="mdi:cctv",
        feature=("LIVE_CAM", "MOTION_CAM"),
        camera=DEFAULT_MOTION_CAMERA,
    ),
)


def gear_guard_camera_options(vehicle: dict[str, Any]) -> tuple[str, ...]:
    options = list(EXTERIOR_CAMERAS)
    model = str(vehicle.get("model") or "").upper()
    if "R1T" in model:
        options.append(BED_CAMERA)
    features = vehicle.get("supported_features") or []
    if "INTERIOR_CAMERA" in features:
        options.append(INTERIOR_CAMERA)
    return tuple(options)
