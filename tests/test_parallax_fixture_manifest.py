"""Every Parallax fixture count comes from the manifest, never from a filename.

This file exists because the "undecoded RVM" count was published wrong five
times in a row: 47, then 8, then 1, then 18, then 15. Four of the five came from
the same mistake in different clothes -- a transform between a dotted topic name
and something else, applied without checking it inverts:

  * `topic.replace(".", "_")` does not invert. `charging.schedule.time_window`
    becomes `charging_schedule_time_window`, and mapping back with
    `replace("_", ".")` yields `charging.schedule.time.window`, which is not a
    topic. Underscores live INSIDE segments.
  * Comparing dotted topics against the dispatch's CONST names by upper-casing
    silently mismatched `comfort.cabin.cabin_preconditioning_status` against
    `COMFORT_CABIN_PRECONDITIONING_STATUS`.
  * Three fixtures predate the naming convention entirely, so a filename-derived
    tally filed decoded topics as undecoded and double-counted the same frame.

The fix is not a better transform. It is to stop deriving topics from filenames:
`manifest.json` records the mapping explicitly, and every count is computed from
it. A count that appears in a document and not here is a claim nobody checks.

The fifth wrong count (47) is a separate lesson: it was *correct* in its own
context -- an app-only column, 80 - 33 -- and a "correction" would have broken
it. Verify a number is wrong before fixing it.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from custom_components.rivian.rivian_client.parallax import RVM_DECODERS

FIXTURES = pathlib.Path(__file__).resolve().parent / "client" / "fixtures" / "parallax"
MANIFEST = FIXTURES / "manifest.json"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text())


class TestManifestIsTheSourceOfTruth:
    """The mapping is recorded, not reconstructed."""

    def test_the_manifest_ships(self, manifest: dict) -> None:
        """Without it every count reverts to a filename guess."""
        assert manifest

    def test_every_fixture_file_is_accounted_for(self, manifest: dict) -> None:
        """No orphans: a `.bin` nobody references is a fixture nobody trusts."""
        referenced = {entry["file"] for entry in manifest.values()}
        referenced |= {e["alias"] for e in manifest.values() if "alias" in e}

        assert {p.name for p in FIXTURES.glob("*.bin")} == referenced

    def test_every_manifest_entry_exists_on_disk(self, manifest: dict) -> None:
        """The reverse direction, which a one-way check would miss."""
        missing = [
            e["file"] for e in manifest.values() if not (FIXTURES / e["file"]).is_file()
        ]

        assert not missing

    def test_topics_are_never_derived_from_filenames(self, manifest: dict) -> None:
        """Three fixtures predate the convention; deriving would mis-map them.

        `climate_hold_setting.bin` is read by name at
        `scripts/gates/helpers/check_fixtures.py:32` and documented at
        `RVM_FIXTURES.md:49`, so it keeps its legacy name and the manifest
        carries the mapping instead.
        """
        legacy = {
            topic
            for topic, entry in manifest.items()
            if entry["file"] != topic.replace(".", "_") + ".bin"
        }

        assert legacy == {
            "comfort.cabin.climate_hold_setting",
            "comfort.cabin.climate_hold_status",
            "vehicle.wheels.vehicle_wheels",
        }


class TestPublishedCountsAreRecomputed:
    """Numbers that appear in docs are asserted here or they are unchecked."""

    def test_fixture_and_decoder_totals(self, manifest: dict) -> None:
        """40 captured topics (41 minus one withheld); 37 decoders after s34."""
        assert len(manifest) == 40
        assert len(RVM_DECODERS) == 37

    def test_the_frame_without_decoder_count(self, manifest: dict) -> None:
        """The number published wrong five times.

        Derived from the manifest's topics, so a rename cannot move it and a
        filename transform cannot inflate it. It legitimately MOVES when a
        decoder ships -- 14 before s34's four, 10 after -- which is the point:
        the count tracks reality instead of a doc someone forgot to edit.
        """
        undecoded = {topic for topic in manifest if topic not in RVM_DECODERS}

        assert len(undecoded) == 10

    def test_seven_decoders_have_no_fixture(self, manifest: dict) -> None:
        """The asymmetry the earlier arithmetic hid.

        `51 publishing - 33 decoded` assumed every decoded topic published. Seven
        did not, which is why subtraction gave 18 where counting gives 15.
        """
        assert len(set(RVM_DECODERS) - set(manifest)) == 7


class TestFixturesCarryNoPersonalData:
    """Blocking. A capture already put a school name and a home SSID on disk.

    These are frames from a real vehicle in a public repository. The guard in
    `scripts/capture_rvm_frames.py` refuses to WRITE identifier-shaped payloads;
    this refuses to SHIP them, because the guard was added after the first leak
    and the fixtures predating it were never subject to it.
    """

    FORBIDDEN = (
        # substrings that would each indicate a specific real leak class
        (b"Elementary", "a saved-place name"),
        (b"School", "a saved-place name"),
        (b"seatsinc", "a home wifi SSID"),
    )

    @staticmethod
    def _longitude_magnitudes(raw: bytes) -> list[float]:
        """f64 values only a longitude would plausibly hold.

        Latitude alone is indistinguishable from a temperature or a percentage,
        so it is not the signal. Nor is magnitude alone: this check first flagged
        `energy_high_voltage_battery_state`, whose 45.6 and 124.695 are state of
        charge and range -- confirmed against a live probe reading
        `batteryLevel = 45.600002`.

        What no reading here is: NEGATIVE with a magnitude above 90. Tyre
        pressure, charge, kWh and range are all positive; a western-hemisphere
        longitude is not. That is the discriminator.

        It misses eastern-hemisphere longitudes, which are positive. It is a
        floor, not a proof, and the withheld-by-default rule in
        `capture_rvm_frames.py` remains the primary control.
        """
        import struct

        out = []
        for i in range(max(0, len(raw) - 8)):
            value = struct.unpack("<d", raw[i : i + 8])[0]
            if -180.0 <= value < -90.0 and abs(value - round(value)) > 1e-6:
                out.append(round(value, 5))
        return out

    def test_the_coordinate_guard_catches_the_frame_that_leaked(self) -> None:
        """Proof the check works, using the bytes that actually shipped.

        `charging.schedule.time_window` carried 35.5566 / -97.6779 as two f64
        doubles nested inside a WindowData submessage. No `strings` scan could
        see them, and the fixture reached a pushed commit before this existed.
        """
        leaked = bytes.fromhex(
            "0801122308e40a10e80218a403203"
            "02a1209000000803fc7414011000000"
            "40636b58c030023803"
        )

        assert self._longitude_magnitudes(leaked), (
            "guard would have missed the real leak"
        )

    @pytest.mark.parametrize(
        "path", sorted(FIXTURES.glob("*.bin")), ids=lambda p: p.name
    )
    def test_fixture_carries_no_longitude(self, path: pathlib.Path) -> None:
        found = self._longitude_magnitudes(path.read_bytes())

        assert not found, f"{path.name} carries longitude-shaped values {found}"

    @pytest.mark.parametrize(
        "path", sorted(FIXTURES.glob("*.bin")), ids=lambda p: p.name
    )
    def test_fixture_carries_no_known_identifier(self, path: pathlib.Path) -> None:
        raw = path.read_bytes()
        hits = [why for needle, why in self.FORBIDDEN if needle in raw]

        assert not hits, f"{path.name} carries {hits}"

    @pytest.mark.parametrize(
        "path", sorted(FIXTURES.glob("*.bin")), ids=lambda p: p.name
    )
    def test_fixture_carries_no_mac_or_uuid(self, path: pathlib.Path) -> None:
        """Shape-based, so it catches identifiers nobody has seen yet."""
        import re

        text = path.read_bytes()
        mac = re.search(rb"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", text)
        uuid = re.search(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-", text)

        assert not mac, f"{path.name} carries a MAC address"
        assert not uuid, f"{path.name} carries a UUID"


class TestCaptureRerunIsAdditive:
    """`RVM_FIXTURES.md` told the operator the capture skips existing topics.

    It did not. `capture_rvm_frames.py` wrote `topic.replace(".", "_") + ".bin"`
    unconditionally, so a second run -- the one the doc asks for, while driving
    -- would have overwritten every frame the decoder tests assert against, and
    for the three legacy-named fixtures would have written a SECOND file under
    the derived name, orphaning it.

    These run against the REAL committed manifest, not a synthetic one, because
    the legacy trio is exactly the case a synthetic fixture would omit.
    """

    @staticmethod
    def _capture():
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "capture_rvm_frames",
            pathlib.Path(__file__).resolve().parents[1]
            / "scripts"
            / "capture_rvm_frames.py",
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_every_committed_topic_is_skipped_not_rewritten(
        self, manifest: dict
    ) -> None:
        """The whole guarantee, over all 40, with plausible frame bytes."""
        capture = self._capture()

        for topic in manifest:
            action, detail = capture.write_decision(
                topic, b"\x08\x01", manifest, FIXTURES
            )

            assert action == "already-fixtured", f"{topic} -> {action}"
            assert detail == manifest[topic]["file"]

    def test_the_legacy_trio_already_shows_the_damage(self, manifest: dict) -> None:
        """The duplicate is not hypothetical -- it is committed, and divergent.

        This test was first written claiming the old code *would* orphan a
        derived-name file. It already had: all three legacy topics carry an
        `alias` recording a second .bin under the derived name, written by an
        earlier run. `comfort.cabin.climate_hold_setting` is the one that
        matters -- `alias_identical: False`, so the two files hold DIFFERENT
        frames for the same topic, and which one a reader gets depends on
        whether it went through the manifest or through the filename.

        The skip is what stops a third copy diverging further.
        """
        capture = self._capture()
        legacy = "comfort.cabin.climate_hold_setting"
        entry = manifest[legacy]

        assert capture.fixture_name(legacy) == entry["alias"] != entry["file"]
        assert entry["alias_identical"] is False
        assert (FIXTURES / entry["file"]).read_bytes() != (
            FIXTURES / entry["alias"]
        ).read_bytes()

        for topic in (
            legacy,
            "comfort.cabin.climate_hold_status",
            "vehicle.wheels.vehicle_wheels",
        ):
            action, detail = capture.write_decision(
                topic, b"\x08\x01", manifest, FIXTURES
            )
            assert action == "already-fixtured", topic
            assert detail == manifest[topic]["file"], topic

    def test_a_new_topic_is_written(self, manifest: dict) -> None:
        """The skip must not be a blanket refusal -- the run has to add frames."""
        capture = self._capture()

        action, detail = capture.write_decision(
            "navigation.navigation_service.trip_info", b"\x08\x01", manifest, FIXTURES
        )

        assert action == "write"
        assert detail == "navigation_navigation_service_trip_info.bin"

    def test_an_untracked_bin_is_refused_rather_than_clobbered(
        self, manifest: dict, tmp_path: pathlib.Path
    ) -> None:
        """Manifest and disk disagreeing is evidence; overwriting destroys it."""
        capture = self._capture()
        # A topic genuinely absent from the manifest -- `ota.deployment.state`
        # is IN it, and short-circuits on the skip before reaching this branch.
        topic = "navigation.navigation_service.trip_progress"
        assert topic not in manifest
        (tmp_path / capture.fixture_name(topic)).write_bytes(b"\x08\x02")

        action, detail = capture.write_decision(topic, b"\x08\x01", manifest, tmp_path)

        assert action == "refused"
        assert detail == capture.fixture_name(topic)

    def test_identifier_bearing_frames_are_still_withheld(
        self, manifest: dict, tmp_path: pathlib.Path
    ) -> None:
        """The skip logic must not have displaced the privacy guard."""
        capture = self._capture()

        action, detail = capture.write_decision(
            "vehicle.setting.network", b"\x12\x08seatsinc", manifest, tmp_path
        )

        assert action == "withheld"
        assert "seatsinc" in detail

    def test_a_written_entry_matches_the_committed_entry_shape(
        self, manifest: dict
    ) -> None:
        """Recompute a real fixture's entry; it must equal what is on disk.

        Catches the two ways a writer drifts from 40 hand-made entries: a
        different hash length (`sha256_12` holds sixteen hex chars, not twelve)
        or a different key set.
        """
        capture = self._capture()
        topic = "body.closures.states"
        raw = (FIXTURES / manifest[topic]["file"]).read_bytes()

        assert capture.manifest_entry(raw, manifest[topic]["file"]) == manifest[topic]
