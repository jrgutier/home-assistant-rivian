"""vehicle_supports() truth table and dump wiring.

Dump MUST import vehicle_supports. groups_for_model is gone; vehicle_supports
is the sensor / binary-sensor / SELECTS creation predicate.
"""

from __future__ import annotations

import pathlib
import re

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
    """A description with none of the two gating fields set is unconditional.

    This is NOT the same thing as a description that has gating fields set
    which simply do not match a particular vehicle -- see
    TestTruthTable.test_none_match_yields_empty_not_ungated below for that
    case, which yields the empty frozenset instead.
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
    """Feature and option combinations. UNION, never AND. No legacy_group."""

    FEATURE_ONLY = RivianGateMixin(feature="LIFTGATE_CMD")
    OPTION_ONLY = RivianGateMixin(option_code="TON-P01")
    BOTH = RivianGateMixin(feature="LIFTGATE_CMD", option_code="TON-P01")

    @pytest.mark.parametrize(
        ("which", "features", "option_codes", "expected"),
        [
            ("feature", ["LIFTGATE_CMD"], [], frozenset({"feature"})),
            ("feature", [], [], frozenset()),
            ("option", [], ["TON-P01"], frozenset({"option"})),
            ("option", [], [], frozenset()),
            ("both", ["LIFTGATE_CMD"], ["TON-P01"], frozenset({"feature", "option"})),
            ("both", ["LIFTGATE_CMD"], [], frozenset({"feature"})),
            ("both", [], ["TON-P01"], frozenset({"option"})),
            ("both", [], [], frozenset()),
        ],
        ids=[
            "feature-only-match",
            "feature-only-miss",
            "option-only-match",
            "option-only-miss",
            "both-match",
            "both-only-feature",
            "both-only-option",
            "none-match",
        ],
    )
    def test_union_over_feature_and_option(
        self,
        which: str,
        features: list[str],
        option_codes: list[str],
        expected: GateEvidence,
    ) -> None:
        description = {
            "feature": self.FEATURE_ONLY,
            "option": self.OPTION_ONLY,
            "both": self.BOTH,
        }[which]
        vehicle = _vehicle("R1T", features, option_codes)
        assert vehicle_supports(description, vehicle) == expected, (
            which,
            features,
            option_codes,
        )

    def test_none_match_yields_empty_not_ungated(self) -> None:
        """Gating fields ARE set on the description; they just don't apply here.

        Contrast TestEmptyGateIsUngated, where no gating field is set at all.
        """
        vehicle = _vehicle("R1T", [], [])
        assert vehicle_supports(self.BOTH, vehicle) == frozenset()


class TestFeatureAcceptsATuple:
    def test_any_one_of_a_tuple_of_features_counts(self) -> None:
        description = RivianGateMixin(feature=("FRUNK_NXT_ACT", "LIFTGATE_CMD"))
        vehicle = _vehicle(features=["LIFTGATE_CMD"])
        assert "feature" in vehicle_supports(description, vehicle)

    def test_none_of_a_tuple_of_features_present(self) -> None:
        description = RivianGateMixin(feature=("FRUNK_NXT_ACT", "LIFTGATE_CMD"))
        vehicle = _vehicle(features=["CHARG_PORT_DOOR_COMMAND"])
        assert "feature" not in vehicle_supports(description, vehicle)


class TestOptionCodeIsListMembershipNotEquality:
    """`coordinator.py`'s `_extract_option_codes()` (landed alongside this
    section) flattens `mobileConfiguration` into a list of ATOMIC optionId
    strings -- e.g. `["TON-P01", "WHL-A01"]`, confirmed against
    `test_coordinator_base.py`'s own `"TON-P01" in option_codes` assertion.
    So the check here is Python `in` on that list (membership: is this ONE
    of the vehicle's codes), not substring search within a longer string,
    and not comparing the whole `option_codes` field against a fixed value.
    """

    def test_option_code_present_in_the_list_matches(self) -> None:
        description = RivianGateMixin(option_code="TON-P01")
        vehicle = _vehicle(option_codes=["TON-P01", "WHL-A01"])
        assert "option" in vehicle_supports(description, vehicle)

    def test_option_code_absent_from_the_list_does_not_match(self) -> None:
        description = RivianGateMixin(option_code="TON-P01")
        vehicle = _vehicle(option_codes=["WHL-A01"])
        assert "option" not in vehicle_supports(description, vehicle)

    def test_a_substring_of_a_list_entry_is_not_a_match(self) -> None:
        """List MEMBERSHIP, not substring-within-an-entry.

        This is the one place this predicate's semantics deliberately part
        ways with the Rivian app's own Kotlin `.contains()` (a substring
        check on a single optionId field): `_extract_option_codes()` already
        flattened that field into a list of atomic codes, so containment at
        THIS layer means "is this code one of the list's elements", not
        "is this code a substring of one of them".
        """
        description = RivianGateMixin(option_code="TON-P0")
        vehicle = _vehicle(option_codes=["TON-P01"])
        assert "option" not in vehicle_supports(description, vehicle)

    def test_no_option_codes_reported_is_no_match(self) -> None:
        """`option_codes` absent entirely -- `vehicle.get(...)` reads `None`."""
        description = RivianGateMixin(option_code="TON-P01")
        assert "option" not in vehicle_supports(description, _vehicle())

    def test_option_codes_accepted_but_empty_is_also_no_match(self) -> None:
        """Distinct from the case above (fragment rejected vs. accepted-empty
        -- coordinator.py's `_extract_option_codes()` docstring), but both
        mean no evidence for this predicate."""
        description = RivianGateMixin(option_code="TON-P01")
        vehicle = _vehicle(option_codes=[])
        assert "option" not in vehicle_supports(description, vehicle)


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
    """Dump MUST import vehicle_supports. groups_for_model is gone from dump."""

    def test_dump_imports_vehicle_supports(self) -> None:
        source = (REPO_ROOT / "scripts" / "dump_entity_sets.py").read_text(
            encoding="utf-8"
        )
        assert "from custom_components.rivian.helpers import vehicle_supports" in source
        assert "from custom_components.rivian.helpers import groups_for_model" not in (
            source
        )
        assert "groups_for_model(" not in source
