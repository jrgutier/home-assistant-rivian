"""s43: the APK is the authority for Parallax decoding.

`docs/development/PARALLAX_CROSS_CHECK.md` compared these decoders with
bretterer/rivian-python-client and with the app's own schema (s42, committed under
`docs/development/apk/schema/`). Where the decoders disagreed with the app, the
app won. This pins each of those decisions twice:

- against the committed APK JSON, so a decoder map cannot drift from the app's
  enum without a test failing, and
- against the committed live capture, so the result is what a real vehicle frame
  actually decodes to.

The APK JSON is derived data (field numbers and enum names), not decompiled
source, so these tests run on a clean checkout.
"""

from __future__ import annotations

import base64
import json
import pathlib

import pytest

from custom_components.rivian.rivian_client.parallax import (
    _GEAR_GUARD_CONSENT,
    _GEAR_GUARD_DAILY_LIMIT,
    DEFROST_DEFOG_MAP,
    POWER_STATE_MAP,
    PRECONDITIONING_STATE_MAP,
    RVM_DECODERS,
    SEAT_DEVICES,
    SEAT_INSTANCES,
    SEAT_LEVELS,
)

ROOT = pathlib.Path(__file__).parent.parent
SCHEMA = ROOT / "docs" / "development" / "apk" / "schema"
FIXTURES = pathlib.Path(__file__).parent / "client" / "fixtures" / "parallax"
VERSION = "3.16.0"


def _json(name: str) -> dict:
    return json.loads((SCHEMA / f"{name}_{VERSION}.json").read_text())


BOUND = _json("apk_parallax_schema")
UNCALLED = _json("uncalled_parse_wrappers")


def _enum(fields: dict, *path: str) -> dict[int, str]:
    """number -> APK enum constant, following `path` through nested messages."""
    for name in path[:-1]:
        fields = fields[name]["message"]
    return {v: k for k, v in fields[path[-1]]["enum"].items()}


def _strip(name: str, prefix: str) -> str:
    assert name.startswith(prefix), name
    return name[len(prefix) :].lower()


def _decode_capture(topic: str) -> dict:
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    raw = (FIXTURES / manifest[topic]["file"]).read_bytes()
    return RVM_DECODERS[topic](base64.b64encode(raw).decode())


class TestMapsAreTheAppsEnums:
    """Each decoder map, value for value, against the app's enum."""

    def test_preconditioning_is_p22(self) -> None:
        apk = _enum(
            BOUND["comfort.cabin.cabin_preconditioning_status"]["fields"], "state"
        )
        expected = {
            n: _strip(name, "CABIN_PRECONDITIONING_STATE_") for n, name in apk.items()
        }
        # Two spellings follow the sensor's existing options, not the app's:
        expected[0] = "undefined"  # UNSPECIFIED; the sensor's "Undefined"
        expected[5] = "timeout_temperature_not_achieved"  # TIMEOUT_TEMP_NOT_ACHIEVED
        assert expected == PRECONDITIONING_STATE_MAP

    def test_time_estimation_is_o9k(self) -> None:
        fields = BOUND["charging.session.time_estimation"]["fields"]
        assert fields["validity_flag"]["number"] == 1
        assert fields["remaining_minutes"]["number"] == 2

    def test_seat_conditioning_is_c1i(self) -> None:
        levels = BOUND["comfort.cabin.seat_conditioning_status"]["fields"]["levels"]
        assert levels["number"] == 1
        sub = levels["message"]
        assert [sub[k]["number"] for k in ("instance", "device", "level")] == [1, 2, 3]

        instance = _enum(sub, "instance")
        for number, prefix in SEAT_INSTANCES.items():
            assert number in instance, prefix
        assert instance[1] == "CABIN_SURFACE_INSTANCE_STEERING_WHEEL"
        assert instance[5] == "CABIN_SURFACE_INSTANCE_ROW_1_LEFT_SEAT"
        assert instance[13] == "CABIN_SURFACE_INSTANCE_ROW_3_RIGHT_SEAT"

        device = _enum(sub, "device")
        assert {n: device[n] for n in SEAT_DEVICES} == {
            1: "CABIN_SURFACE_DEVICE_HEAT",
            2: "CABIN_SURFACE_DEVICE_VENT",
        }

        level = _enum(sub, "level")
        assert level[0] == "CABIN_SURFACE_LEVEL_UNSPECIFIED"
        assert {n: level[n] for n in (1, 2, 3)} == {
            1: "CABIN_SURFACE_LEVEL_LEVEL1",
            2: "CABIN_SURFACE_LEVEL_LEVEL2",
            3: "CABIN_SURFACE_LEVEL_LEVEL3",
        }
        assert set(SEAT_LEVELS) == set(level)

    def test_defrost_is_lv5(self) -> None:
        apk = _enum(UNCALLED["lv5"], "current_level")
        assert {
            n: _strip(apk[n], "CABIN_DEFROST_DEFOG_LEVEL_") for n in DEFROST_DEFOG_MAP
        } == {n: v.lower() for n, v in DEFROST_DEFOG_MAP.items()}
        assert set(DEFROST_DEFOG_MAP) == set(apk) - {0}

    def test_power_state_is_qqf(self) -> None:
        apk = _enum(UNCALLED["qqf"], "power_mode")
        assert {
            n: _strip(apk[n], "VEHICLE_POWER_MODE_") for n in POWER_STATE_MAP
        } == POWER_STATE_MAP
        assert set(POWER_STATE_MAP) == set(apk) - {0}

    def test_gear_guard_consent_is_vpl(self) -> None:
        apk = _enum(UNCALLED["vpl"], "user_consent")
        assert {n: name.lower() for n, name in apk.items()} == _GEAR_GUARD_CONSENT

    def test_gear_guard_daily_limit_is_uc5(self) -> None:
        apk = _enum(UNCALLED["uc5"], "daily_limit")
        assert {
            n: name.lower().removeprefix("daily_limit_") for n, name in apk.items()
        } == _GEAR_GUARD_DAILY_LIMIT

    def test_charge_session_breakdown_is_nl2(self) -> None:
        nl2 = UNCALLED["nl2"]
        assert nl2["range_added_kms"]["number"] == 8
        assert nl2["current_power"]["number"] == 9
        assert nl2["current_range_per_hour"]["number"] == 10


class TestTheCapturesDecodeAsTheAppSays:
    """What each live frame decodes to now, with the bytes that say so."""

    def test_time_estimation_reads_field_2(self) -> None:
        """Frame `1040`: field 2 = 64 minutes. It used to decode to {}."""
        assert _decode_capture("charging.session.time_estimation") == {
            "timeToEndOfCharge": 64
        }

    def test_preconditioning_unavailable(self) -> None:
        """Frame `0808`: 8 is UNAVAILABLE. It used to read as off; bretterer
        reads it as active."""
        assert _decode_capture("comfort.cabin.cabin_preconditioning_status") == {
            "cabinPreconditioningStatus": "unavailable"
        }

    def test_completed_charge_session_has_no_power(self) -> None:
        """#13 = 4 (complete), #9 absent, #10 = 2, #8 = 20. It used to report
        2.0 kW and an estimated 21.7 km."""
        assert _decode_capture(
            "energy_edge_compute.graphs.charge_session_breakdown"
        ) == {
            "totalChargedEnergy": 6.2,
            "power": 0.0,
            "rangeAddedThisSession": 20,
            "kilometersChargedPerHour": 2,
        }

    def test_gear_guard_consent(self) -> None:
        """Frame `0802`: 2 is CONSENTED. It used to read as not_consented."""
        assert _decode_capture(
            "gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent"
        ) == {"gearGuardStreamingConsent": "consented"}

    def test_gear_guard_daily_limit(self) -> None:
        """2 is NOT_HIT under both numberings, which is how the offset hid."""
        out = _decode_capture(
            "gearguard_streaming.privacy.gearguard_streaming_daily_limit"
        )
        assert out["gearGuardStreamingDailyLimit"] == "not_hit"

    def test_defrost_off(self) -> None:
        assert _decode_capture("comfort.cabin.defrost_defog_status") == {
            "defrostDefogStatus": "Off"
        }

    def test_passive_entry_debug_is_correctly_empty(self) -> None:
        """Frame `1002`: only field 2, send_lock_fail_notification = FALSE.
        No fail reason was sent, so none is reported."""
        assert _decode_capture("security.access.passive_entry_debug") == {}

    @pytest.mark.parametrize(
        "topic",
        ["energy.high_voltage.battery_state"],
    )
    def test_no_phantom_range_key(self, topic: str) -> None:
        """`bc1.charge_state` has two fields; there is no rangeKm."""
        assert "rangeKm" not in _decode_capture(topic)
