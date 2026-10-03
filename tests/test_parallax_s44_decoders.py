"""s44: decoders for the five APK-bound topics that had none.

`PARALLAX_CROSS_CHECK.md` found these bound in the app (s42 schema) and decoded
by bretterer but not here. They are written from the APK schema -- not from
bretterer's, which reads remote_command and several OTA fields differently -- and
pinned, like s43, against the committed APK JSON and the live captures.
"""

from __future__ import annotations

import base64
import json
import pathlib

import pytest

from custom_components.rivian.const import PARALLAX_ONLY_FIELDS, SENSORS
from custom_components.rivian.rivian_client.parallax import (
    _DERATE_STATUS,
    _FAULT_CHIME,
    _OTA_CURRENT_STATUS,
    _OTA_STATUS,
    _START_AVAILABLE,
    RVM_DECODERS,
    decode_charging_notification,
    decode_ota_deployment_state,
    decode_remote_command,
    decode_trip_target,
)

ROOT = pathlib.Path(__file__).parent.parent
FIXTURES = pathlib.Path(__file__).parent / "client" / "fixtures" / "parallax"
BOUND = json.loads(
    (ROOT / "docs/development/apk/schema/apk_parallax_schema_3.16.0.json").read_text()
)

NOTIFICATION = "charging.session.notification"
REMOTE = "charging.session.remote_command"
SOC_SLIDER = "charging.session.soc_slider"
TRIP_TARGET = "charging.session.trip_target"
OTA = "ota.deployment.state"
S44 = (NOTIFICATION, REMOTE, SOC_SLIDER, TRIP_TARGET, OTA)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _capture(topic: str) -> dict:
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    raw = (FIXTURES / manifest[topic]["file"]).read_bytes()
    return RVM_DECODERS[topic](_b64(raw))


def _enum(fields: dict, *path: str) -> dict[int, str]:
    for name in path[:-1]:
        fields = fields[name]["message"]
    return {v: k for k, v in fields[path[-1]]["enum"].items()}


@pytest.mark.parametrize("topic", S44)
def test_registered_and_bound_in_the_app(topic: str) -> None:
    assert topic in RVM_DECODERS
    assert topic in BOUND


class TestMapsAreTheAppsEnums:
    def test_derate_status(self) -> None:
        apk = _enum(BOUND[NOTIFICATION]["fields"], "derate_status")
        assert {n: f"DERATE_STATUS_{v}" for n, v in _DERATE_STATUS.items()} == apk

    def test_fault_chime(self) -> None:
        apk = _enum(BOUND[NOTIFICATION]["fields"], "fault_chime")
        assert {n: f"FAULT_CHIME_{v.upper()}" for n, v in _FAULT_CHIME.items()} == apk

    def test_start_available(self) -> None:
        apk = _enum(BOUND[REMOTE]["fields"], "start_available")
        assert apk[1] == "START_AVAILABILITY_FALSE"
        assert apk[2] == "START_AVAILABILITY_TRUE"
        assert _START_AVAILABLE == {1: 0, 2: 1}

    def test_ota_status_and_current_status(self) -> None:
        progress = ("softwares", "available_ota", "ota_progress")
        fields = BOUND[OTA]["fields"]
        status = _enum(fields, *progress, "ota_status")
        current = _enum(fields, *progress, "ota_current_status")
        assert {n: f"OTA_STATUS_{v}" for n, v in _OTA_STATUS.items()} == {
            n: v for n, v in status.items() if n
        }
        assert {
            n: f"OTA_CURRENT_STATUS_{v}" for n, v in _OTA_CURRENT_STATUS.items()
        } == {n: v for n, v in current.items() if n}

    def test_field_numbers(self) -> None:
        assert BOUND[SOC_SLIDER]["fields"]["user_soc_limit"]["number"] == 1
        assert BOUND[TRIP_TARGET]["fields"]["soc"]["number"] == 1
        softwares = BOUND[OTA]["fields"]["softwares"]
        assert softwares["number"] == 1
        sub = softwares["message"]
        assert sub["version"]["number"] == 2
        assert sub["available_ota"]["number"] == 4
        version = sub["version"]["message"]
        assert {k: version[k]["number"] for k in version} == {
            "version": 1,
            "software_version_id": 2,
            "year": 3,
            "week": 4,
            "number": 5,
            "git_hash": 6,
        }


class TestTheCaptures:
    def test_soc_slider(self) -> None:
        """`0855`: the charge limit is 85%."""
        assert _capture(SOC_SLIDER) == {"batteryLimit": 85}

    def test_remote_command_is_availability_not_a_command(self) -> None:
        """`0801`: START_AVAILABILITY_FALSE. bretterer reads this as "start"."""
        assert _capture(REMOTE) == {"remoteChargingAvailable": 0}

    def test_notification(self) -> None:
        """`0801`: only #1 (stop reason, not decoded); #2 and #3 are NONE."""
        assert _capture(NOTIFICATION) == {
            "chargerDerateStatus": "NONE",
            "chargingFaultChime": "none",
        }

    def test_ota_deployment_state(self) -> None:
        """Firmware 2026.31.0, idle, last install succeeded; no available
        version in this frame, so none is emitted."""
        assert _capture(OTA) == {
            "otaCurrentVersion": "2026.31.0",
            "otaCurrentVersionYear": 2026,
            "otaCurrentVersionWeek": 31,
            "otaCurrentVersionGitHash": "40c3ab6e",
            "otaStatus": "Idle",
            "otaCurrentStatus": "Install_Success",
            "otaDownloadProgress": 0,
            "otaInstallProgress": 0,
        }


class TestDecoders:
    def test_remote_command_true_and_sna(self) -> None:
        assert decode_remote_command(_b64(b"\x08\x02")) == {
            "remoteChargingAvailable": 1
        }
        assert decode_remote_command(_b64(b"\x08\x00")) == {}
        assert decode_remote_command("") == {}

    def test_notification_derate_and_chime(self) -> None:
        assert decode_charging_notification(_b64(b"\x10\x08\x18\x02")) == {
            "chargerDerateStatus": "BATTERY_HEATING",
            "chargingFaultChime": "charging_disabled_dc",
        }

    def test_notification_empty_is_none(self) -> None:
        """An empty payload is proto3's all-defaults message: NONE for both."""
        assert decode_charging_notification("") == {
            "chargerDerateStatus": "NONE",
            "chargingFaultChime": "none",
        }

    def test_trip_target_emits_only_the_soc(self) -> None:
        """#2 has no unit in the app and #3 no enum, so neither is emitted."""
        assert decode_trip_target(_b64(b"\x08\x50\x10\x2d\x18\x01")) == {
            "tripTargetSoc": 80
        }

    def test_ota_available_version_and_ready_to_install(self) -> None:
        version = b"\x0a\x092026.33.1\x18\xea\x0f\x20\x21"  # 2026.33.1, 2026, 33
        progress = b"\x08\x08"  # READY_TO_INSTALL
        available = b"\x12" + bytes([len(version)]) + version
        available += b"\x2a" + bytes([len(progress)]) + progress
        firmware = b"\x08\x01\x22" + bytes([len(available)]) + available
        out = decode_ota_deployment_state(
            _b64(b"\x0a" + bytes([len(firmware)]) + firmware)
        )
        assert out == {
            "otaAvailableVersion": "2026.33.1",
            "otaAvailableVersionYear": 2026,
            "otaAvailableVersionWeek": 33,
            "otaStatus": "Ready_To_Install",
        }

    def test_ota_ignores_non_firmware_categories(self) -> None:
        """HD maps (2) carry a version too; it must not become the firmware's."""
        version = b"\x0a\x04maps"
        hdmaps = b"\x08\x02\x12" + bytes([len(version)]) + version
        assert (
            decode_ota_deployment_state(_b64(b"\x0a" + bytes([len(hdmaps)]) + hdmaps))
            == {}
        )

    def test_ota_status_matches_update_py(self) -> None:
        """update.py compares against the GraphQL casing."""
        from custom_components.rivian.update import INSTALLING_STATUS, READY_FOR_INSTALL

        emitted = {
            "_".join(w.capitalize() for w in v.lower().split("_"))
            for v in _OTA_STATUS.values()
        }
        assert set(INSTALLING_STATUS) <= emitted
        assert set(READY_FOR_INSTALL) <= emitted


class TestEntities:
    @pytest.mark.parametrize("field", ["chargingFaultChime", "tripTargetSoc"])
    def test_new_keys_back_a_sensor_and_stay_off_the_wire(self, field: str) -> None:
        assert any(d.field == field for d in SENSORS)
        assert field in PARALLAX_ONLY_FIELDS

    def test_trip_target_is_disabled_until_a_frame_is_witnessed(self) -> None:
        desc = next(d for d in SENSORS if d.field == "tripTargetSoc")
        assert desc.entity_registry_enabled_default is False

    def test_fault_chime_is_enabled(self) -> None:
        desc = next(d for d in SENSORS if d.field == "chargingFaultChime")
        assert desc.entity_registry_enabled_default is True
