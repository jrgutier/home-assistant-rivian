"""The four s34 decoders, each asserted against its captured frame.

Every decoder here was written from a NAMED schema in `rivian_client/proto/`,
bound to its topic by a `// RVM:` comment. None required signature-matching
against obfuscated classes: `PARALLAX_DECODERS.md` closed that search over all
32,941 files, and every dispatch-bound topic was already decoded.

These assert VALUES, not "parses without raising". Every decoder in this module
swallows exceptions so a bad frame cannot take the subscription down, which
means a broken decoder returns `{}` silently. That is exactly what happened
while writing `decode_parked_energy_distributions`: it re-packed an
already-unpacked float and returned empty, and nothing surfaced it until a real
fixture was decoded. A test that only checked for no-raise would have passed.

Two topics with named schemas are deliberately absent:

  * `charging.schedule.time_window` -- its frame carries a GPS coordinate in a
    nested `WindowData.location` field, the fixture was withheld, and a decoder
    with nothing to verify against does not ship.
  * `holiday_celebration…halloween_celebration_settings` -- `HalloweenCostumeTheme`
    is a message rather than an enum, so there is no vocabulary to map, and
    `REMAINING_APK_GAPS.md` already dispositions the HLWN_25 family as ISE with
    its entities removed. Decoding it would add a live subscription for a feature
    the repo decided against.
"""

from __future__ import annotations

import base64
import json
import pathlib

import pytest

from custom_components.rivian.rivian_client.parallax import RVM_DECODERS

FIXTURES = pathlib.Path(__file__).resolve().parent / "client" / "fixtures" / "parallax"


def frame(topic: str) -> str:
    """The captured frame for `topic`, base64 as the decoders expect it."""
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    return base64.b64encode((FIXTURES / manifest[topic]["file"]).read_bytes()).decode()


class TestCabinVentilationSetting:
    """`REMAINING_APK_GAPS.md` lists this RVM as undecoded and wanted."""

    TOPIC = "comfort.cabin.cabin_ventilation_setting"

    def test_decodes_the_captured_frame(self) -> None:
        """A 2-byte frame: field 1 set, every optional field absent."""
        assert RVM_DECODERS[self.TOPIC](frame(self.TOPIC)) == {
            "cabinVentilationEnabled": True
        }

    def test_absent_optional_fields_are_omitted_not_defaulted(self) -> None:
        """protobuf omits defaults, so a missing field is unknown, not zero.

        Emitting `windowsOpenPercent: 0` for an absent field would render a
        confident "windows closed" from a frame that said nothing at all.
        """
        decoded = RVM_DECODERS[self.TOPIC](frame(self.TOPIC))

        assert "cabinVentilationWindowsOpenPercent" not in decoded
        assert "cabinVentilationMode" not in decoded


class TestGearGuardStreaming:
    """Two clean enum vocabularies from `rivian_security.proto`."""

    CONSENT = "gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent"
    LIMIT = "gearguard_streaming.privacy.gearguard_streaming_daily_limit"

    def test_consent_maps_the_enum_not_the_integer(self) -> None:
        """Value 2 is GEAR_GUARD_NOT_CONSENTED, emitted prefix-stripped."""
        assert RVM_DECODERS[self.CONSENT](frame(self.CONSENT)) == {
            "gearGuardStreamingConsent": "not_consented"
        }

    def test_daily_limit_maps_status_and_reset_time(self) -> None:
        """Value 2 is …DAILY_LIMIT_NOT_HIT; field 2 is epoch seconds."""
        decoded = RVM_DECODERS[self.LIMIT](frame(self.LIMIT))

        assert decoded["gearGuardStreamingDailyLimit"] == "not_hit"
        assert decoded["gearGuardStreamingLimitResetTime"] == 1767852000

    def test_the_reset_timestamp_is_emitted_verbatim(self) -> None:
        """It is in the past relative to capture, and that is left alone.

        Recorded rather than corrected: treating it as stale, or rebasing it to
        "next midnight", would assert semantics this frame does not establish.
        """
        decoded = RVM_DECODERS[self.LIMIT](frame(self.LIMIT))

        assert decoded["gearGuardStreamingLimitResetTime"] < 1770000000


class TestParkedEnergyDistributions:
    """Three windows of the same ten measurements (`rivian_energy.proto:23`)."""

    TOPIC = "energy_edge_compute.graphs.parked_energy_distributions"

    def test_all_three_windows_decode(self) -> None:
        decoded = RVM_DECODERS[self.TOPIC](frame(self.TOPIC))

        assert set(decoded) == {
            "parkedEnergyLast24Hours",
            "parkedEnergyLast8Hours",
            "parkedEnergyLastParkSession",
        }

    def test_components_sum_to_the_total(self) -> None:
        """The strongest evidence the field mapping is right, not just parseable.

        If `thermal`, `outlets` and `system` were mapped to the wrong field
        numbers they would still decode as floats -- and would not add up.
        """
        window = RVM_DECODERS[self.TOPIC](frame(self.TOPIC))["parkedEnergyLast24Hours"]
        parts = window["thermalKwh"] + window["outletsKwh"] + window["systemKwh"]

        assert parts == pytest.approx(window["totalKwh"], abs=0.05)

    def test_range_scales_consistently_with_energy(self) -> None:
        """~3.61 range units per kWh in every window, independently.

        A shuffled mapping would not hold this ratio across three windows whose
        absolute values differ by an order of magnitude.
        """
        decoded = RVM_DECODERS[self.TOPIC](frame(self.TOPIC))
        ratios = [
            w["totalRange"] / w["totalKwh"]
            for w in decoded.values()
            if w.get("totalKwh")
        ]

        assert len(ratios) == 3
        assert all(r == pytest.approx(ratios[0], rel=0.01) for r in ratios)

    def test_a_window_omits_measurements_the_frame_did_not_send(self) -> None:
        """The park-session window carries no outlets figure; none is invented."""
        session = RVM_DECODERS[self.TOPIC](frame(self.TOPIC))[
            "parkedEnergyLastParkSession"
        ]

        assert "outletsKwh" not in session


class TestDecodersAreRegisteredAndVerifiable:
    """Every s34 decoder is reachable and backed by a committed frame."""

    S34 = (
        "comfort.cabin.cabin_ventilation_setting",
        "gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent",
        "gearguard_streaming.privacy.gearguard_streaming_daily_limit",
        "energy_edge_compute.graphs.parked_energy_distributions",
    )

    @pytest.mark.parametrize("topic", S34)
    def test_registered(self, topic: str) -> None:
        assert topic in RVM_DECODERS

    @pytest.mark.parametrize("topic", S34)
    def test_has_a_committed_fixture(self, topic: str) -> None:
        """No decoder ships without a frame to verify it."""
        manifest = json.loads((FIXTURES / "manifest.json").read_text())

        assert topic in manifest
        assert (FIXTURES / manifest[topic]["file"]).is_file()

    def test_the_withheld_topic_has_no_decoder(self) -> None:
        """`charging.schedule.time_window` carried a coordinate; both are absent."""
        assert "charging.schedule.time_window" not in RVM_DECODERS
        assert not (FIXTURES / "charging_schedule_time_window.bin").exists()
