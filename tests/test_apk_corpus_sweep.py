"""Unit tests for the cross-version APK extractor.

These test the extractor's LOGIC, never a decompiled tree. The dumps are
gitignored and live outside the repo, so a test that read one could not run in a
clean checkout -- and a skipped test is worse than an absent one. The
tree-reading half belongs in `scripts/gates/`, exactly as
`tests/test_apk_transcription.py` and `scripts/gates/f1.sh` already divide it.

The `wiperFluidState` case below is the one that earned its own test. That name
is a real `vehicleState` field AND a prefix of the Room column
`wiperFluidStateUpdatedTimestamp`, so a substring match counts 14 where a
whole-word match counts 15. `docs/development/apk/REGENERATION.md` records that
discrepancy, and four earlier flat greps of this app were lossy -- which is why
the shipped data is transcribed rather than grepped. An extractor that
reintroduces substring matching would be the fifth.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import re

import pytest

_MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "scripts" / "apk_corpus_sweep.py"
)
_SPEC = importlib.util.spec_from_file_location("apk_corpus_sweep", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
sweep = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sweep)


class TestWholeWordFieldNames:
    """`wiperFluidState` must not be conflated with its longer neighbour."""

    def test_both_names_survive_as_distinct_fields(self) -> None:
        """A document carrying both yields both, and the short one exactly once."""
        document = """
        query GetVehicleState {
          vehicleState(id: $id) {
            wiperFluidState { value }
            wiperFluidStateUpdatedTimestamp { value }
          }
        }
        """
        fields = sweep.graphql_field_names(document)

        assert fields.count("wiperFluidState") == 1
        assert "wiperFluidStateUpdatedTimestamp" in fields

    def test_the_room_column_alone_does_not_yield_the_short_name(self) -> None:
        """The substring is present; the field is not. Only whole-word sees that."""
        document = """
        query GetVehicleState {
          vehicleState(id: $id) {
            wiperFluidStateUpdatedTimestamp { value }
          }
        }
        """
        fields = sweep.graphql_field_names(document)

        assert "wiperFluidStateUpdatedTimestamp" in fields
        assert "wiperFluidState" not in fields


class TestVersionOrdering:
    """Provenance strings are only useful if versions sort like versions."""

    def test_ten_sorts_after_nine(self) -> None:
        """String sorting puts 1.10.0 before 1.9.0. Numeric sorting does not."""
        ordered = sorted(["1.10.0", "1.9.0", "1.2.1"], key=sweep.version_key)

        assert ordered == ["1.2.1", "1.9.0", "1.10.0"]

    @pytest.mark.parametrize("version", ["2.0.0_beta", "2.5.0_beta"])
    def test_the_beta_spellings_parse(self, version: str) -> None:
        """Both betas are irregular on disk and neither may crash the sort."""
        assert sweep.version_key(version)

    def test_a_beta_sorts_before_its_release(self) -> None:
        """2.0.0_beta precedes 2.2.0; the tiebreak must not invert them."""
        ordered = sorted(["2.2.0", "2.0.0_beta"], key=sweep.version_key)

        assert ordered == ["2.0.0_beta", "2.2.0"]


class TestCorpusAllowlist:
    """The corpus is enumerated, never globbed."""

    def test_the_irregular_directory_names_are_carried_verbatim(self) -> None:
        """One has an underscore, one a SPACE. Normalising either loses the dump."""
        assert sweep.SRC_DUMPS["2.0.0_beta"] == "rivian_2.0.0_beta"
        assert sweep.SRC_DUMPS["2.5.0_beta"] == "rivian_2.5.0 beta"

    def test_the_allowlist_excludes_the_abrp_telemetry_directory(self) -> None:
        """`~/src/rivian-dump/` matches a `rivian*` glob and is not an app dump."""
        assert "rivian-dump" not in sweep.SRC_DUMPS.values()

    def test_every_on_disk_dump_version_is_listed(self) -> None:
        """25 `~/src` dumps plus the trees under `.apk/`, 54 versions in all.

        The `.apk/` trees were all decompiled here with jadx 1.5.6 from APKMirror
        bundles, so unlike cohorts A and B -- whose decompiler was never recorded
        -- that cohort has documented provenance and its counts are comparable to
        each other. 3.15.0 stays its ground truth; 3.16.0 is the frontier build,
        and Google Play serves only current, so nothing can be backfilled from it.
        """
        assert len(sweep.SRC_DUMPS) == 25
        assert len(sweep.REPO_DUMPS) == 29
        assert {"3.15.0", "3.16.0"} <= set(sweep.REPO_DUMPS)

    def test_the_repo_trees_all_share_one_layout(self) -> None:
        """Their root IS jadx/sources, so every one resolves to the `.` cohort."""
        assert all(
            path.name == "sources" and path.parent.name == "jadx"
            for path in sweep.REPO_DUMPS.values()
        )


class TestVehicleStateDepthOneMetric:
    """The sensor mode measures depth 1, not every depth. The two disagree."""

    DOCUMENT = """subscription VehicleState($vehicleID: String!) {
      vehicleState(id: $vehicleID) {
        __typename
        batteryLevel { timeStamp value }
        gnssLocation { latitude longitude }
        ...VehicleStateFields
      }
    }
    fragment VehicleStateFields on VehicleState {
      powerState { timeStamp value }
    }
    """

    def test_nested_names_are_not_counted_as_subscribed_fields(self) -> None:
        """`latitude` is inside `gnssLocation`, so it is not a subscribed name.

        `VEHICLE_STATE_API_FIELDS` is a set of TOP-LEVEL names. Counting nested
        ones inflates the app side and manufactures a deficit that is not real.
        """
        fields = sweep.vehicle_state_field_names(self.DOCUMENT)

        assert "gnssLocation" in fields
        assert "latitude" not in fields
        assert "value" not in fields

    def test_a_fragment_spread_contributes_its_own_depth_one_names(self) -> None:
        """Not resolving spreads drops whole documents -- h9l and lel yield 0."""
        fields = sweep.vehicle_state_field_names(self.DOCUMENT)

        assert "powerState" in fields

    def test_the_two_metrics_diverge_and_that_is_the_point(self) -> None:
        """The tokenizer counts more. Neither is wrong; only one is comparable."""
        depth_one = sweep.vehicle_state_field_names(self.DOCUMENT)
        any_depth = set(sweep.graphql_field_names(self.DOCUMENT))

        assert depth_one < any_depth

    def test_typename_is_not_a_field(self) -> None:
        """Apollo bookkeeping, and subscribing to it would be a name we invented."""
        assert "__typename" not in sweep.vehicle_state_field_names(self.DOCUMENT)


class TestRvmTableExtraction:
    """The enum class name is obfuscated and build-specific; the property is not."""

    def test_the_restored_enum_form_yields_its_rvm_names(self) -> None:
        """jadx emits `NAME("rvm.name"),` when it can restore the enum modifier."""
        source = """public enum iol {
            USER_PASSCODES_DRIVE_AUTH("user_passcodes.passcode_types.drive_auth"),
            PASSIVE_ENTRY_SETTING_V2("security.access.passive_entry");
            private final String rvmName;
        }"""

        assert sweep.extract_rvm_names(source) == {
            "user_passcodes.passcode_types.drive_auth",
            "security.access.passive_entry",
        }

    def test_the_unrestored_enum_form_yields_them_too(self) -> None:
        """When it cannot, it emits constructor calls -- 3.15.0's real l6e.java."""
        source = """public final class l6e {
            private final String rvmName;
            public static final l6e BODY_LOCKS_STATES =
                new l6e("BODY_LOCKS_STATES", 21, "body.locks.states", true, null);
        }"""

        assert sweep.extract_rvm_names(source) == {"body.locks.states"}

    def test_a_file_without_the_marker_yields_nothing(self) -> None:
        """Dotted lowercase literals are everywhere. Only the RVM table counts."""
        source = """public final class Analytics {
            static final String EVENT = "body.locks.states";
        }"""

        assert sweep.extract_rvm_names(source) == set()


class TestChargingSurfaceScoping:
    """The charging surface is the operations the INTEGRATION sends, not all of them."""

    def test_a_wallbox_query_yields_its_fields(self) -> None:
        document = (
            "query getRegisteredWallboxes { getRegisteredWallboxes "
            "{ wallboxId chargingStatus maxAmps } }"
        )

        assert sweep.charging_field_names(document) >= {
            "wallboxId",
            "chargingStatus",
            "maxAmps",
        }

    def test_an_unrelated_operation_yields_nothing(self) -> None:
        """Charging-network browsing is not a surface this integration implements."""
        document = "query chargingSites { chargingSites { id name } }"

        assert sweep.charging_field_names(document) == set()

    def test_a_string_that_is_not_an_operation_yields_nothing(self) -> None:
        """Every Java string literal is offered to this; most are not GraphQL."""
        assert sweep.charging_field_names("failed to load getWallboxStatus") == set()


class TestIntegrationSetsAreParsedNotImported:
    """`const.py` cannot be imported without Home Assistant. It is parsed."""

    def test_union_and_difference_both_evaluate(self) -> None:
        """`VEHICLE_STATE_API_FIELDS` is built from `|` and `-` over four names."""
        module = ast.parse(
            "A = frozenset({'a', 'b'})\n"
            "B: Final[frozenset[str]] = frozenset({'c'})\n"
            "C = {'b'}\n"
            "D = (A | B) - C\n"
        )
        env: dict[str, set[str]] = {}
        for statement in module.body:
            target = (
                statement.target
                if isinstance(statement, ast.AnnAssign)
                else statement.targets[0]
            )
            resolved = sweep._eval_set_expr(statement.value, env)
            if resolved is not None:
                env[target.id] = resolved

        assert env["D"] == {"a", "c"}

    def test_an_expression_it_cannot_evaluate_is_skipped_not_guessed(self) -> None:
        """A silent wrong answer here would move every delta by an unknown amount."""
        node = ast.parse("X = sorted(other)").body[0].value

        assert sweep._eval_set_expr(node, {}) is None

    def test_the_real_symbols_all_resolve(self) -> None:
        """A rename in the integration must fail loudly here, not shrink a delta."""
        root = sweep.REPO_ROOT

        assert len(sweep.integration_vehicle_state_fields(root)) == 149
        assert len(sweep.integration_rvm_names(root)) == 33
        assert len(sweep.integration_feature_pairs(root)) == 64
        assert sweep.integration_charging_fields(root)


def _result(version: str, sensors: dict, commands: list | None = None) -> dict:
    return {
        "version": version,
        "layout": ".",
        "commands": commands or [],
        "errors": [],
        "sensors": sensors,
    }


_EMPTY_SENSORS = {
    "vehicle_state_fields": [],
    "rvm_names": [],
    "parallax_attributes": False,
    "feature_pairs": [],
    "charging_fields": [],
    "charging_documents": 0,
}


class TestSurfaceFloors:
    """A shrinking union reads like progress. It is the extractor breaking."""

    def test_a_union_below_the_floor_is_an_error_on_every_surface(self) -> None:
        """Four floors, not one: the four surfaces fail independently."""
        report = sweep.sensor_surfaces(
            [_result("3.15.0", _EMPTY_SENSORS)], sweep.REPO_ROOT
        )

        assert len(report["errors"]) == len(sweep.SURFACE_FLOORS)
        assert all(s["below_floor"] for s in report["surfaces"].values())

    def test_a_partial_sweep_reports_the_delta_without_claiming_the_floor(self) -> None:
        """`--only 3.15.0` cannot meet a whole-corpus floor and must not pretend to."""
        report = sweep.sensor_surfaces(
            [_result("3.15.0", _EMPTY_SENSORS)], sweep.REPO_ROOT, enforce_floor=False
        )

        assert report["errors"] == []
        assert report["floor_enforced"] is False

    def test_every_surface_carries_a_nonzero_floor(self) -> None:
        """A floor of zero is not a floor; it is an assertion that never fires."""
        assert set(sweep.SURFACE_FLOORS) == set(sweep.SURFACE_TITLES)
        assert all(floor > 0 for floor in sweep.SURFACE_FLOORS.values())


class TestBleOnlyCommandsAreAnAppendix:
    """A BLE-only command is not a field the integration failed to read."""

    def test_it_lands_in_the_appendix_and_in_no_surface(self) -> None:
        """WINCH_IN is BLE-only across 1.0.3-1.4.1 and belongs nowhere else."""
        command = {
            "name": "WINCH_IN",
            "class": "WinchIn",
            "cloud": False,
            "ble": True,
            "cloud_invalid": False,
        }
        report = sweep.sensor_surfaces(
            [_result("1.0.3", _EMPTY_SENSORS, [command])],
            sweep.REPO_ROOT,
            enforce_floor=False,
        )

        assert [row["name"] for row in report["ble_only_commands"]] == ["WINCH_IN"]
        for surface in report["surfaces"].values():
            assert "WINCH_IN" not in surface["app"]

    def test_a_cloud_command_is_not_in_the_appendix(self) -> None:
        """The appendix is BLE-ONLY; a cloud-sendable command is a different thing."""
        command = {
            "name": "WAKE_VEHICLE",
            "class": "WakeVehicle",
            "cloud": True,
            "ble": True,
            "cloud_invalid": False,
        }
        report = sweep.sensor_surfaces(
            [_result("1.0.3", _EMPTY_SENSORS, [command])],
            sweep.REPO_ROOT,
            enforce_floor=False,
        )

        assert report["ble_only_commands"] == []


class TestShippedLedgerIsGuarded:
    """The shipped ledger, not the extractor that produced it.

    `scripts/gates/s17.sh` checks that the extractor works across all three tree
    layouts. Nothing checked the artifact it emits -- which is how a row shipped
    claiming 51 version-observations in a 26-version corpus. `roll_up_ledger`
    appended to `versions` unconditionally while deduping `cohorts` two lines
    below, so a command resolved by two classes in one dump counted twice.

    These read only `docs/development/APK_HISTORICAL_SWEEP.md` and the enum, both
    of which ship, so they run in a clean checkout with no corpus present.
    """

    CORPUS_SIZE = 54  # 25 in ~/src, plus 29 decompiled trees in .apk/
    LEDGER = (
        pathlib.Path(__file__).resolve().parents[1]
        / "docs"
        / "development"
        / "APK_HISTORICAL_SWEEP.md"
    )
    ROW = re.compile(
        r"^\|\s*`(?P<name>[A-Z][A-Z0-9_]*)`(?P<mark>[^|]*)\|"
        r"(?P<span>[^|]*)\|\s*(?P<n>\d+)\s*\|"
    )

    @classmethod
    def _rows(cls) -> dict[str, int]:
        """Command name -> version count, from the ledger's own table."""
        rows: dict[str, int] = {}
        for line in cls.LEDGER.read_text().splitlines():
            match = cls.ROW.match(line)
            if match:
                rows.setdefault(match.group("name"), int(match.group("n")))
        return rows

    def test_the_ledger_ships(self) -> None:
        """It is the deliverable; an absent one is not a passing state."""
        assert self.LEDGER.is_file()

    def test_no_row_claims_more_versions_than_the_corpus_holds(self) -> None:
        """26 dumps cannot yield 51 observations of one command.

        The check is deliberately one-sided. An OVERcount is impossible on its
        face and needs no corpus to refute; an UNDERcount is not, and catching it
        would mean re-extracting -- which would make this corpus-dependent and so
        skippable, the very thing that keeps the tree-reading half in
        `scripts/gates/`. The asymmetry is the price of a check that always runs.
        """
        overcounted = {
            name: n for name, n in self._rows().items() if n > self.CORPUS_SIZE
        }

        assert not overcounted, (
            f"rows claiming impossible version counts: {overcounted}"
        )

    def test_the_enum_only_residue_is_exactly_the_two_third_row_seat_heats(
        self,
    ) -> None:
        """US-004's amended criterion, asserted rather than eyeballed.

        A strict superset is impossible: the app is a lower bound, never the
        schema. What IS checkable is the size and identity of the residue, and
        it must not drift silently.
        """
        from custom_components.rivian.rivian_client import VehicleCommand

        ours = {command.value for command in VehicleCommand}

        assert ours - set(self._rows()) == {
            "CABIN_HVAC_THIRD_ROW_LEFT_SEAT_HEAT",
            "CABIN_HVAC_THIRD_ROW_RIGHT_SEAT_HEAT",
        }


class TestTheMetricDoesNotDriftFromTheGateHelper:
    """The depth-1 metric exists twice in this repo. Pin them together.

    `scripts/gates/helpers/apk_vehicle_state_fields.py` owns the canonical
    metric; `apk_corpus_sweep.py` replicates it rather than importing, because
    the helper's public entry point takes a path to one of the nine pre-flight
    classes while the sweep reads 26 whole trees. That is a defensible reason to
    duplicate -- but a comment saying "the metric matches" cannot keep it true.
    If the two drift, `APK_HISTORICAL_SWEEP.md`'s claim to use the helper's
    metric becomes silently false, and the 15-to-2 collapse stops meaning what
    it says.

    These compare the two on synthetic input, so they exercise the shared string
    logic without needing the gitignored classes and never skip.
    """

    BODY = (
        "batteryLevel { timeStamp value } "
        "gnssLocation { latitude longitude } "
        "...VehicleStateFields "
        "powerState { value }"
    )
    FRAGMENTS = {"VehicleStateFields": "driveMode { value } chargerState { value }"}

    @staticmethod
    def _helper():
        path = (
            pathlib.Path(__file__).resolve().parents[1]
            / "scripts"
            / "gates"
            / "helpers"
            / "apk_vehicle_state_fields.py"
        )
        spec = importlib.util.spec_from_file_location("apk_vehicle_state_fields", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_top_level_splitting_agrees(self) -> None:
        """Same depth-1 tokens, including the fragment spread."""
        assert self._helper()._split_top_level(self.BODY) == sweep.split_top_level(
            self.BODY
        )

    def test_selection_names_agree_including_resolved_fragments(self) -> None:
        """Both resolve the spread; neither counts nested leaves."""
        theirs = self._helper()._selection_names(self.BODY, self.FRAGMENTS)
        ours = sweep.selection_names(self.BODY, self.FRAGMENTS)

        assert theirs == ours
        assert "latitude" not in ours
        assert "driveMode" in ours
