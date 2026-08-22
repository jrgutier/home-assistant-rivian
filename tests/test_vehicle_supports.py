"""s19 SECTION A: `helpers.py`'s `vehicle_supports()` -- gate plumbing, not gating.

INERT by construction: nothing outside this file calls `vehicle_supports()`.
sensor.py, binary_sensor.py, and every other platform still call
`groups_for_model()` directly, which is why `scripts/dump_entity_sets.py
--check` (also exercised below) has to show zero movement -- landing this
predicate must not be observable from any platform's entity set. Switching a
platform's `async_setup_entry` over to this predicate is a later story.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

from custom_components.rivian.data_classes import RivianGateMixin
from custom_components.rivian.helpers import GateEvidence, vehicle_supports

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _vehicle(
    model: str | None = None,
    features: list[str] | None = None,
    option_codes: list[str] | None = None,
) -> dict:
    vehicle: dict = {}
    if model is not None:
        vehicle["model"] = model
    vehicle["supported_features"] = features or []
    vehicle["option_codes"] = option_codes or []
    return vehicle


class TestEmptyGateIsUngated:
    """A description with none of the three gating fields set is unconditional.

    This is NOT the same thing as a description that has gating fields set
    which simply do not match a particular vehicle -- see
    TestTruthTable.test_none_of_the_three_match below for that case, which
    yields the empty frozenset instead.
    """

    @pytest.mark.parametrize("model", ["R1T", "R1S", "R2", None, "", "R3X"])
    def test_no_gating_fields_at_all(self, model: str | None) -> None:
        description = RivianGateMixin()
        assert vehicle_supports(description, _vehicle(model)) == frozenset({"ungated"})

    def test_ungated_is_independent_of_feature_and_option_codes_too(self) -> None:
        """An unset gate ignores the vehicle entirely, not just its model."""
        description = RivianGateMixin()
        vehicle = _vehicle("R1T", features=["ANYTHING"], option_codes=["ANYTHING_TOO"])
        assert vehicle_supports(description, vehicle) == frozenset({"ungated"})


class TestTruthTable:
    """All eight (legacy, feature, option) combinations. UNION, never AND.

    The description below has all three gating fields set. `legacy_group`
    ("LIFTGATE") is granted by groups_for_model() only for "R1S" and "R2"
    (legacy_grants.py), never "R1T" -- so R1T/R2 stand in for
    legacy-absent/legacy-present without needing a fourth model axis.
    """

    DESCRIPTION = RivianGateMixin(
        legacy_group="LIFTGATE", feature="LIFTGATE_CMD", option_code="LFGT"
    )

    @pytest.mark.parametrize(
        ("model", "features", "option_codes", "expected"),
        [
            # no evidence source fires
            ("R1T", [], [], frozenset()),
            # exactly one source
            ("R2", [], [], frozenset({"legacy"})),
            ("R1T", ["LIFTGATE_CMD"], [], frozenset({"feature"})),
            ("R1T", [], ["XLFGTY"], frozenset({"option"})),
            # exactly two sources
            ("R2", ["LIFTGATE_CMD"], [], frozenset({"legacy", "feature"})),
            ("R2", [], ["XLFGTY"], frozenset({"legacy", "option"})),
            ("R1T", ["LIFTGATE_CMD"], ["XLFGTY"], frozenset({"feature", "option"})),
            # all three
            (
                "R2",
                ["LIFTGATE_CMD"],
                ["XLFGTY"],
                frozenset({"legacy", "feature", "option"}),
            ),
        ],
    )
    def test_union_over_all_eight_combinations(
        self,
        model: str,
        features: list[str],
        option_codes: list[str],
        expected: GateEvidence,
    ) -> None:
        vehicle = _vehicle(model, features, option_codes)
        assert vehicle_supports(self.DESCRIPTION, vehicle) == expected, (
            model,
            features,
            option_codes,
        )

    def test_none_of_the_three_match_yields_empty_not_ungated(self) -> None:
        """Gating fields ARE set on the description; they just don't apply here.

        Contrast TestEmptyGateIsUngated, where no gating field is set at all.
        """
        vehicle = _vehicle("R1T", [], [])
        assert vehicle_supports(self.DESCRIPTION, vehicle) == frozenset()


class TestFeatureAcceptsATuple:
    def test_any_one_of_a_tuple_of_features_counts(self) -> None:
        description = RivianGateMixin(feature=("FRUNK_NXT_ACT", "LIFTGATE_CMD"))
        vehicle = _vehicle(features=["LIFTGATE_CMD"])
        assert "feature" in vehicle_supports(description, vehicle)

    def test_none_of_a_tuple_of_features_present(self) -> None:
        description = RivianGateMixin(feature=("FRUNK_NXT_ACT", "LIFTGATE_CMD"))
        vehicle = _vehicle(features=["CHARG_PORT_DOOR_COMMAND"])
        assert "feature" not in vehicle_supports(description, vehicle)


class TestOptionCodeIsContainmentNotEquality:
    """The app itself matches option codes with Kotlin `contains`."""

    def test_option_code_matches_as_a_substring(self) -> None:
        description = RivianGateMixin(option_code="LFGT")
        vehicle = _vehicle(option_codes=["XXLFGTYY"])
        assert "option" in vehicle_supports(description, vehicle)

    def test_option_code_matches_a_full_equal_entry_too(self) -> None:
        description = RivianGateMixin(option_code="LFGT")
        vehicle = _vehicle(option_codes=["LFGT"])
        assert "option" in vehicle_supports(description, vehicle)

    def test_a_partial_prefix_is_not_a_match(self) -> None:
        """Containment of the OPTION CODE in an entry, not the other way round."""
        description = RivianGateMixin(option_code="LFGT")
        vehicle = _vehicle(option_codes=["LF"])
        assert "option" not in vehicle_supports(description, vehicle)

    def test_no_option_codes_reported_is_no_match(self) -> None:
        description = RivianGateMixin(option_code="LFGT")
        assert "option" not in vehicle_supports(description, _vehicle())


class TestNoBoolComparisonLint:
    """`GateEvidence` is `frozenset[str]`, a plain alias -- mypy will not flag
    `vehicle_supports(...) is True`. Runtime backstop until a real call site
    exists to wire this predicate in: scans the integration source (not this
    test file, and not the vendored rivian_client/) for the comparison this
    function's docstring warns against.
    """

    BOOL_COMPARISON = re.compile(
        r"vehicle_supports\([^)]*\)\s*(?:is|==)\s*(?:True|False)\b"
    )

    def test_no_call_site_compares_the_result_to_a_bool(self) -> None:
        integration_root = REPO_ROOT / "custom_components" / "rivian"
        offenders = []
        for path in integration_root.rglob("*.py"):
            if "rivian_client" in path.parts:
                continue  # vendored, not this integration's code
            text = path.read_text(encoding="utf-8")
            if self.BOOL_COMPARISON.search(text):
                offenders.append(str(path.relative_to(REPO_ROOT)))
        assert not offenders, offenders

    def test_the_lint_pattern_actually_catches_the_mistake(self) -> None:
        """The regression guard for the guard: prove BOOL_COMPARISON fires."""
        assert self.BOOL_COMPARISON.search("if vehicle_supports(d, v) is True:")
        assert self.BOOL_COMPARISON.search("vehicle_supports(d, v) == False")
        assert not self.BOOL_COMPARISON.search("if vehicle_supports(d, v):")
        assert not self.BOOL_COMPARISON.search("if not vehicle_supports(d, v):")


class TestEntitySetsUnmovedByThisPlumbing:
    """The proof this section is inert: dump_entity_sets.py --check.

    That script derives entity sets from `groups_for_model()` and
    `SENSORS`/`BINARY_SENSORS` only -- it does not import `vehicle_supports`
    at all -- so a passing --check here is direct evidence that adding
    RivianGateMixin to every description class and adding this predicate
    changed no vehicle's entity set, run from inside the test suite rather
    than trusted as something a human ran once before committing.
    """

    def test_dump_entity_sets_check_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/dump_entity_sets.py", "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
