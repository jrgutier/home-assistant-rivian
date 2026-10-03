"""s45: decoders for topics the app subscribes to but never parses.

Each uses the app's own message class whose field names match the topic -- an
uncalled parse wrapper in `docs/development/apk/schema/uncalled_parse_wrappers_
3.16.0.json`. That is a name-match, not a dispatch binding; the owner chose to
decode them anyway (PARALLAX_CROSS_CHECK.md). Pinned against the APK JSON so a
decoder cannot drift from its class, and against the captures where one exists.
"""

from __future__ import annotations

import base64
import json
import pathlib

import pytest

from custom_components.rivian.rivian_client.parallax import (
    _CCC_PASSIVE_PERMISSION,
    _GEOFENCE_TYPE,
    _PET_SNAPSHOT_FILE_TYPE,
    _USER_MODE_FIELDS,
    _WINDOW_CALIBRATION,
    _WINDOW_CALIBRATION_FIELDS,
    RVM_DECODERS,
    decode_favorite_geofences,
    decode_ota_config,
    decode_passive_entry_state,
    decode_pet_snapshot,
    decode_trip_progress,
    decode_vehicle_ota_state,
    decode_window_states,
)

ROOT = pathlib.Path(__file__).parent.parent
FIXTURES = pathlib.Path(__file__).parent / "client" / "fixtures" / "parallax"
UNCALLED = json.loads(
    (
        ROOT / "docs/development/apk/schema/uncalled_parse_wrappers_3.16.0.json"
    ).read_text()
)

# topic -> the app class its decoder is written from
CLASS = {
    "body.windows.states": "zzn",
    "comfort.cabin.hvac_settings_status": "e9a",
    "comfort.user_modes.state": "uql",
    "energy_edge_compute.graphs.cold_weather_soc": "jx3",
    "geofence.geofence_service.favoriteGeofences": "wq7",
    "navigation.navigation_service.trip_progress": "u3l",
    "ota.ota_state.vehicle_ota_state": "ugm",
    "ota.user_schedule.ota_config": "rfe",
    "secure_file_transfer.pet_snapshot.secure_file": "g2i",
    "vehicle_access.state.passive_entry": "fre",
    # Request-side BINDING, not a name-match: the app sends `fre` to this
    # topic (FOLLOWUP_S45.md, wy9.java:2225-2234).
    "vehicle_access.passive_entry.passive_entry": "fre",
}


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _msg(field: int, body: bytes) -> bytes:
    return bytes([field << 3 | 2, len(body)]) + body


def _ts(seconds: int) -> bytes:
    out, n = bytearray(), seconds
    while True:
        b, n = n & 0x7F, n >> 7
        out.append(b | (0x80 if n else 0))
        if not n:
            break
    return b"\x08" + bytes(out)


def _capture(topic: str) -> dict:
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    raw = (FIXTURES / manifest[topic]["file"]).read_bytes()
    return RVM_DECODERS[topic](_b64(raw))


def _numbers(cls: str, *path: str) -> dict[str, int]:
    fields = UNCALLED[cls]
    for name in path:
        fields = fields[name]["message"]
    return {name: f["number"] for name, f in fields.items()}


def _enum(cls: str, *path: str) -> dict[int, str]:
    fields = UNCALLED[cls]
    for name in path[:-1]:
        fields = fields[name]["message"]
    return {v: k for k, v in fields[path[-1]]["enum"].items()}


@pytest.mark.parametrize(("topic", "cls"), sorted(CLASS.items()))
def test_registered_and_its_class_exists(topic: str, cls: str) -> None:
    assert topic in RVM_DECODERS
    assert cls in UNCALLED


class TestFieldNumbersAreTheClasses:
    def test_windows(self) -> None:
        assert _numbers("zzn") == {"states": 1}
        assert _numbers("zzn", "states") == {
            "window_instance": 1,
            "calibration_status": 2,
        }
        instance = _enum("zzn", "states", "window_instance")
        assert {n: instance[n] for n in _WINDOW_CALIBRATION_FIELDS} == {
            1: "WINDOW_INSTANCE_FRONT_LEFT",
            2: "WINDOW_INSTANCE_FRONT_RIGHT",
            3: "WINDOW_INSTANCE_REAR_LEFT",
            4: "WINDOW_INSTANCE_REAR_RIGHT",
        }
        status = _enum("zzn", "states", "calibration_status")
        assert {n: status[n] for n in _WINDOW_CALIBRATION} == {
            1: "CALIBRATION_STATUS_CALIBRATED",
            2: "CALIBRATION_STATUS_NOT_CALIBRATED",
        }

    def test_cold_weather_soc(self) -> None:
        assert _numbers("jx3") == {
            "soc_perc_green": 1,
            "soc_perc_blue": 2,
            "cold_range_impact_km": 3,
        }

    def test_hvac(self) -> None:
        assert _numbers("e9a") == {"set_temperature_celsius": 1}

    def test_user_modes(self) -> None:
        numbers = _numbers("uql")
        assert {numbers["in_service"], numbers["car_wash"]} == set(_USER_MODE_FIELDS)
        assert _enum("uql", "in_service") == {
            0: "MODE_STATUS_UNSPECIFIED",
            1: "MODE_STATUS_ON",
        }

    def test_passive_entry_state(self) -> None:
        assert _numbers("fre") == {
            "allowpassiveentryviabluetoothwhileinccc": 1,
            "cccpassivepermissionstatus": 2,
        }
        apk = _enum("fre", "cccpassivepermissionstatus")
        assert {
            n: v.removeprefix("CCC_PASSIVE_PERMISSION_STATUS_").lower()
            for n, v in apk.items()
        } == _CCC_PASSIVE_PERMISSION

    def test_geofences(self) -> None:
        assert _numbers("wq7", "favorites") == {"type": 1, "name": 2}
        assert {n: v.lower() for n, v in _enum("wq7", "favorites", "type").items()} == (
            _GEOFENCE_TYPE
        )

    def test_ota_state_and_config(self) -> None:
        assert _numbers("ugm") == {"id": 1, "install_time_epoch": 2}
        assert _numbers("rfe", "schedules") == {
            "id": 1,
            "isenabled": 2,
            "repeatsdaily": 3,
            "singleoccurrence": 4,
        }
        assert _numbers("rfe", "schedules", "repeatsdaily")["startsatmin"] == 1
        assert _numbers("rfe", "schedules", "singleoccurrence") == {"startsatutc": 1}

    def test_pet_snapshot_metadata(self) -> None:
        assert _numbers("g2i")["metadata"] == 4
        assert _numbers("g2i", "metadata") == {
            "filename": 1,
            "file_type": 2,
            "file_size": 3,
            "created_at": 4,
        }
        apk = _enum("g2i", "metadata", "file_type")
        assert {n: apk[n] for n in _PET_SNAPSHOT_FILE_TYPE} == {
            1: "FILE_TYPE_IMAGE_PNG",
            2: "FILE_TYPE_IMAGE_JPEG",
            3: "FILE_TYPE_IMAGE_WEBP",
        }

    def test_trip_progress(self) -> None:
        numbers = _numbers("u3l")
        assert numbers["legetautc"] == 1
        assert numbers["tripetautc"] == 2
        assert numbers["legremainingdistancemeters"] == 4
        assert numbers["legremainingdurationseconds"] == 5


class TestTheCaptures:
    def test_hvac_set_temperature(self) -> None:
        """`0d0000a841`: 21.0 degC."""
        assert _capture("comfort.cabin.hvac_settings_status") == {
            "hvacSetTemperature": 21.0
        }

    def test_user_modes(self) -> None:
        """`20023804`: only #4 and #7, so in_service and car_wash are off."""
        assert _capture("comfort.user_modes.state") == {
            "serviceMode": "off",
            "carWashMode": "off",
        }

    def test_cold_weather_soc(self) -> None:
        """`082e`: green 46; blue and impact omitted, so 0."""
        assert _capture("energy_edge_compute.graphs.cold_weather_soc") == {
            "coldWeatherSocGreen": 46,
            "coldWeatherSocBlue": 0,
            "coldRangeImpact": 0,
        }

    def test_vehicle_ota_state_has_no_install_time(self) -> None:
        """Only #1 id = 'VehicleOTAState'."""
        assert _capture("ota.ota_state.vehicle_ota_state") == {}


class TestDecoders:
    def test_windows(self) -> None:
        payload = _msg(1, b"\x08\x01\x10\x01") + _msg(1, b"\x08\x04\x10\x02")
        payload += _msg(1, b"\x08\x05\x10\x01")  # REAR: no gateway field
        assert decode_window_states(_b64(payload)) == {
            "windowFrontLeftCalibrated": "Calibrated",
            "windowRearRightCalibrated": "Not_Calibrated",
        }

    def test_passive_entry_state(self) -> None:
        assert decode_passive_entry_state(_b64(b"\x08\x01\x10\x02")) == {
            "passiveEntryBluetoothInCcc": True,
            "cccPassivePermissionStatus": "enabled",
        }

    def test_geofences(self) -> None:
        payload = _msg(1, b"\x08\x01\x12\x04Home") + _msg(1, b"\x12\x03Gym")
        assert decode_favorite_geofences(_b64(payload)) == {
            "favoriteGeofences": [
                {"type": "home", "name": "Home"},
                {"type": "custom", "name": "Gym"},
            ]
        }

    def test_vehicle_ota_state_install_time(self) -> None:
        payload = b"\x0a\x0fVehicleOTAState" + _msg(2, _ts(1790000000))
        assert decode_vehicle_ota_state(_b64(payload)) == {
            "otaOneTimeInstallTime": 1790000000
        }

    def test_ota_config(self) -> None:
        daily = _msg(1, b"\x10\x01" + _msg(3, b"\x08\xb4\x01"))  # 180 min
        once = _msg(1, _msg(4, _msg(1, _ts(1790000000))))
        assert decode_ota_config(_b64(daily + once)) == {
            "otaInstallSchedules": [
                {"enabled": True, "dailyStartMinute": 180},
                {"enabled": False, "startsAt": 1790000000},
            ]
        }

    def test_pet_snapshot_never_emits_the_payload_or_keys(self) -> None:
        metadata = _msg(4, b"\x0a\x05a.jpg\x10\x02\x18\x80\x08" + _msg(4, _ts(5)))
        payload = (
            b"\x0a\x04s3id"  # 1: s3_id
            + _msg(2, b"\xde\xad\xbe\xef")  # 2: raw_data (encrypted)
            + _msg(3, b"\x0a\x01x")  # 3: wrapped_keys
            + metadata
            + b"\x2a\x03sid"  # 5: session_id
        )
        assert decode_pet_snapshot(_b64(payload)) == {
            "petSnapshot": {"fileType": "image/jpeg", "fileSize": 1024, "createdAt": 5}
        }

    def test_trip_progress(self) -> None:
        import struct

        payload = (
            _msg(1, _ts(1790000100))
            + _msg(2, _ts(1790000900))
            + b"\x18\x02"  # nextstopindex: not emitted
            + b"\x21"
            + struct.pack("<d", 12345.67)
            + b"\x29"
            + struct.pack("<d", 600.0)
        )
        assert decode_trip_progress(_b64(payload)) == {
            "navLegEta": 1790000100,
            "navTripEta": 1790000900,
            "navLegRemainingDistance": 12345.7,
            "navLegRemainingDuration": 600.0,
        }
