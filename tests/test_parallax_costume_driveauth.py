"""Decoders for the 3.17.0-new RVM topics: holiday_celebration.car_costume.{state,
settings} and user_passcodes.passcode_types.drive_auth.

Transcribed from the 3.17.0 app's protobuf-lite field-info descriptors
(defpackage/{vg2,sg2,q97}.java) and enum classes (hg2/re5/me5/ycc/pe5/p97), each
verified against a captured frame. The DTO field ORDER (tg2/wg2) disagrees with the
wire numbers and is deliberately NOT used: the state frame's field 6 is
activeCostumeEffect, which the DTO ordering would mislabel as a trailing timestamp.

These topics are named by the 3.17.0 RVM table (zff), not the 3.15.0 l6e
transcription, so their grounding lives in RVM_NAMES_317.
"""

from __future__ import annotations

import base64
import json
import pathlib

from custom_components.rivian.rivian_client.parallax import (
    RVM_DECODERS,
    decode_car_costume_settings,
    decode_car_costume_state,
    decode_drive_auth,
)

FIXTURES = pathlib.Path(__file__).parent / "client" / "fixtures" / "parallax"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())


def _payload(topic: str) -> str:
    return base64.b64encode((FIXTURES / MANIFEST[topic]["file"]).read_bytes()).decode()


class TestCarCostumeState:
    TOPIC = "holiday_celebration.car_costume.state"

    def test_registered(self) -> None:
        assert RVM_DECODERS[self.TOPIC] is decode_car_costume_state

    def test_decodes_the_committed_frame(self) -> None:
        assert decode_car_costume_state(_payload(self.TOPIC)) == {
            "carCostumeAvailability": "unavailable",
            "costumeTheme": "none",
            "costumeMotionTriggered": False,
            "activeCostumeEffect": "none",
        }

    def test_field_six_is_effect_not_timestamp(self) -> None:
        """The DTO-order trap: wire field 6 is activeCostumeEffect, an enum, not a
        trailing timestamp. A 1 here is 'none', never an epoch second."""
        out = decode_car_costume_state(_payload(self.TOPIC))
        assert "timestamp" not in out
        assert out["activeCostumeEffect"] == "none"

    def test_unmapped_enum_is_dropped(self) -> None:
        # field 2 (costumeTheme) = 9, not in re5 -> dropped, not invented
        raw = base64.b64encode(bytes.fromhex("1009")).decode()
        assert "costumeTheme" not in decode_car_costume_state(raw)

    def test_empty(self) -> None:
        assert decode_car_costume_state("") == {}


class TestCarCostumeSettings:
    TOPIC = "holiday_celebration.car_costume.settings"

    def test_registered(self) -> None:
        assert RVM_DECODERS[self.TOPIC] is decode_car_costume_settings

    def test_decodes_the_committed_frame(self) -> None:
        assert decode_car_costume_settings(_payload(self.TOPIC)) == {
            "costumeCelebrationVolume": 0,
            "costumeInteriorMusicEnabled": False,
            "costumeInteriorMusicType": 0,
            "costumeInteriorLightShowEnabled": False,
            "costumeInteriorOverheadLightsEnabled": False,
            "costumeLightsColor": "none",
            "costumeEffect": "none",
            "costumeEffectTrigger": "manual",
        }

    def test_empty(self) -> None:
        assert decode_car_costume_settings("") == {}


class TestDriveAuth:
    TOPIC = "user_passcodes.passcode_types.drive_auth"

    def test_registered(self) -> None:
        assert RVM_DECODERS[self.TOPIC] is decode_drive_auth

    def test_decodes_the_committed_frame(self) -> None:
        assert decode_drive_auth(_payload(self.TOPIC)) == {"driveAuthSetting": "none"}

    def test_sna_zero_is_dropped(self) -> None:
        # field 1 = 0 (SNA) -> dropped, not surfaced as an invalid state
        raw = base64.b64encode(bytes.fromhex("0800")).decode()
        assert decode_drive_auth(raw) == {}

    def test_empty(self) -> None:
        assert decode_drive_auth("") == {}
