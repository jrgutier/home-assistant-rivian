from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder, _fields
from .proto import holiday_celebration_pb2

_COSTUME_AVAILABILITY_MAP: Final[dict[int, str]] = {
    1: "available",
    2: "controllable",
    3: "unavailable",
}
_COSTUME_THEME_MAP: Final[dict[int, str]] = {
    1: "none",
    2: "ghostbusters",
    3: "ghostbusters_display",
}
_COSTUME_EFFECT_MAP: Final[dict[int, str]] = {
    1: "none",
    2: "random",
    3: "effect_1",
    4: "effect_2",
    5: "effect_3",
    6: "effect_4",
}
_COSTUME_LIGHTS_COLOR_MAP: Final[dict[int, str]] = {
    1: "none",
    2: "swamp_gas",
    3: "player_piano",
    4: "bayou_blend",
    5: "slimy_spirits",
}
_COSTUME_EFFECT_TRIGGER_MAP: Final[dict[int, str]] = {
    1: "manual",
    2: "motion",
}


@RVMDecoder.register(
    holiday_celebration_pb2.CarCostumeState,
    "holiday_celebration.car_costume.state",
)
def decode_car_costume_state(
    m: holiday_celebration_pb2.CarCostumeState,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if m.car_costume_availability in _COSTUME_AVAILABILITY_MAP:
        result["carCostumeAvailability"] = _COSTUME_AVAILABILITY_MAP[
            m.car_costume_availability
        ]
    if m.costume_theme in _COSTUME_THEME_MAP:
        result["costumeTheme"] = _COSTUME_THEME_MAP[m.costume_theme]
    if m.HasField("motion_trigger_detected"):
        result["costumeMotionTriggered"] = m.motion_trigger_detected
    if m.active_costume_effect in _COSTUME_EFFECT_MAP:
        result["activeCostumeEffect"] = _COSTUME_EFFECT_MAP[m.active_costume_effect]
    return result


@RVMDecoder.register(
    holiday_celebration_pb2.CarCostumeSettings,
    "holiday_celebration.car_costume.settings",
)
def decode_car_costume_settings(
    m: holiday_celebration_pb2.CarCostumeSettings,
) -> dict[str, Any]:
    result = _fields(
        m,
        {
            "celebration_sound_volume": ("costumeCelebrationVolume", None),
            "interior_music_enabled": ("costumeInteriorMusicEnabled", None),
            "interior_music_type": ("costumeInteriorMusicType", None),
            "interior_light_show_enabled": ("costumeInteriorLightShowEnabled", None),
            "interior_overhead_lights_enabled": (
                "costumeInteriorOverheadLightsEnabled",
                None,
            ),
        },
    )
    if m.lights_color in _COSTUME_LIGHTS_COLOR_MAP:
        result["costumeLightsColor"] = _COSTUME_LIGHTS_COLOR_MAP[m.lights_color]
    if m.costume_effect in _COSTUME_EFFECT_MAP:
        result["costumeEffect"] = _COSTUME_EFFECT_MAP[m.costume_effect]
    if m.effect_trigger in _COSTUME_EFFECT_TRIGGER_MAP:
        result["costumeEffectTrigger"] = _COSTUME_EFFECT_TRIGGER_MAP[m.effect_trigger]
    return result
