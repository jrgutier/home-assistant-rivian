"""Tests for the next-action-state enums.

These enums mirror the Android app's NextActionState values and decide whether a
closure reads as open, closed, moving, faulted or obstructed. Getting a member
into the wrong bucket is silent: the entity simply reports the wrong state.

The tests are therefore written as **invariants over every member of every enum**
rather than as a list of hand-picked examples. A hand-picked test passes forever
once written; an invariant fails the moment someone adds a new `*_FAULTED` member
and forgets to add it to the `is_faulted()` tuple — which is the actual failure
mode this module has.
"""

from __future__ import annotations

from enum import Enum

import pytest

from custom_components.rivian.next_action_states import (
    ChargePortDoorNextActionState,
    FrunkNextActionState,
    LiftgateNextActionState,
    SideBinNextActionState,
    TailgateNextActionState,
    WindowsNextActionState,
)

ALL_STATE_ENUMS: list[type[Enum]] = [
    FrunkNextActionState,
    LiftgateNextActionState,
    TailgateNextActionState,
    ChargePortDoorNextActionState,
    WindowsNextActionState,
    SideBinNextActionState,
]

# (enum class, member) for every member of every enum — 77 cases.
ALL_MEMBERS = [(cls, member) for cls in ALL_STATE_ENUMS for member in cls]


def _members_with(predicate: str) -> list[tuple[type[Enum], Enum]]:
    """Members exposing `predicate`.

    Parametrising over these rather than skipping inside the test keeps the run
    skip-free: a skipped test and an absent test look identical in a summary, and
    the coverage gate treats skips as a smell.
    """
    return [case for case in ALL_MEMBERS if hasattr(case[1], predicate)]


OBSTRUCTABLE = _members_with("is_obstructed")
TRAILER_AWARE = _members_with("has_trailer_detected")
OBSTACLE_AWARE = _members_with("has_obstacle_detected")
CALIBRATABLE = _members_with("needs_calibration")
ANGLE_AWARE = _members_with("needs_vehicle_angle_confirmation")

# Members that are legitimately neither open nor closed: no signal, mid-travel, or
# still resolving. Anything NOT in here must be classified, or the entity reports
# nothing at all. Kept as an explicit allow-list so adding a new unclassified member
# is a deliberate act rather than an oversight.
NEITHER_OPEN_NOR_CLOSED = {
    "SNA",
    "OPENING_PAUSE_NOT_ALLOWED",
    "CLOSING_PAUSE_NOT_ALLOWED",
    "PROCESSING",
}


def _member_id(case: tuple[type[Enum], Enum]) -> str:
    cls, member = case
    return f"{cls.__name__}.{member.name}"


@pytest.mark.parametrize("case", ALL_MEMBERS, ids=_member_id)
class TestMemberInvariants:
    """Invariants that must hold for every member of every state enum."""

    def test_round_trips_through_from_api_value(
        self, case: tuple[type[Enum], Enum]
    ) -> None:
        """The API value maps back to exactly the member it came from.

        Guards against duplicate values, which Enum silently aliases.
        """
        cls, member = case
        assert cls.from_api_value(member.value) is member

    def test_from_api_value_is_case_insensitive(
        self, case: tuple[type[Enum], Enum]
    ) -> None:
        """Rivian has shipped mixed casing; parsing must not care."""
        cls, member = case
        assert cls.from_api_value(member.value.upper()) is member
        assert cls.from_api_value(member.value.title()) is member

    def test_open_and_closed_are_mutually_exclusive(
        self, case: tuple[type[Enum], Enum]
    ) -> None:
        """A closure is never simultaneously open and closed.

        Both predicates are hand-maintained tuples, so a member added to both is
        an easy and completely silent mistake.
        """
        _cls, member = case
        assert not (member.is_open() and member.is_closed())

    def test_faulted_matches_the_member_name(
        self, case: tuple[type[Enum], Enum]
    ) -> None:
        """`is_faulted()` is true for exactly the `*_FAULTED` members."""
        _cls, member = case
        assert member.is_faulted() is ("FAULTED" in member.name)

    def test_every_predicate_returns_a_real_bool(
        self, case: tuple[type[Enum], Enum]
    ) -> None:
        """Predicates return `bool`, not a truthy tuple or None.

        `self in (...)` returns bool, but `self.X` typos return a member, which is
        always truthy — so a mistyped predicate would report the closure open.
        """
        _cls, member = case
        predicates = [
            name
            for name in dir(member)
            if name.startswith(("is_", "has_", "needs_"))
            and callable(getattr(member, name))
        ]
        assert predicates, "member exposes no predicates"
        for name in predicates:
            assert isinstance(getattr(member, name)(), bool), (
                f"{name} returned non-bool"
            )


@pytest.mark.parametrize("case", OBSTRUCTABLE, ids=_member_id)
def test_obstructed_matches_the_member_name(case: tuple[type[Enum], Enum]) -> None:
    """`is_obstructed()` is true for exactly the `OBSTRUCTED_*` members."""
    _cls, member = case
    assert member.is_obstructed() is ("OBSTRUCTED" in member.name)


@pytest.mark.parametrize("case", TRAILER_AWARE, ids=_member_id)
def test_trailer_detection_matches_the_member_name(
    case: tuple[type[Enum], Enum],
) -> None:
    """`has_trailer_detected()` is true for exactly the `*_TRAILER_*` members."""
    _cls, member = case
    assert member.has_trailer_detected() is ("TRAILER" in member.name)


@pytest.mark.parametrize("case", OBSTACLE_AWARE, ids=_member_id)
def test_obstacle_detection_matches_the_member_name(
    case: tuple[type[Enum], Enum],
) -> None:
    """`has_obstacle_detected()` is true for exactly the `*_OBSTACLE_*` members."""
    _cls, member = case
    assert member.has_obstacle_detected() is ("OBSTACLE" in member.name)


@pytest.mark.parametrize("case", CALIBRATABLE, ids=_member_id)
def test_calibration_matches_the_member_name(case: tuple[type[Enum], Enum]) -> None:
    """`needs_calibration()` is true for exactly the `*_CALIBRAT*` members."""
    _cls, member = case
    assert member.needs_calibration() is ("CALIBRAT" in member.name)


@pytest.mark.parametrize("case", ANGLE_AWARE, ids=_member_id)
def test_angle_confirmation_matches_the_member_name(
    case: tuple[type[Enum], Enum],
) -> None:
    """`needs_vehicle_angle_confirmation()` is true for exactly the `*_ANGLE_*` members."""
    _cls, member = case
    assert member.needs_vehicle_angle_confirmation() is ("ANGLE" in member.name)


@pytest.mark.parametrize("case", ALL_MEMBERS, ids=_member_id)
def test_every_member_is_classified_open_closed_or_explicitly_neither(
    case: tuple[type[Enum], Enum],
) -> None:
    """Totality: no member falls silently through both buckets.

    Mutual exclusivity alone is satisfied *vacuously* by a member in neither tuple,
    which is the likeliest real mistake — add a new open state, forget `is_open()`,
    and the closure silently reports nothing. This closes that gap: a new member
    must be classified, or deliberately added to NEITHER_OPEN_NOR_CLOSED.
    """
    _cls, member = case
    classified = member.is_open() or member.is_closed()
    if member.name in NEITHER_OPEN_NOR_CLOSED:
        assert not classified, (
            f"{member.name} is allow-listed as neither open nor closed, but is classified"
        )
    else:
        assert classified, (
            f"{member.name} is neither open nor closed and is not allow-listed — "
            "add it to is_open()/is_closed(), or to NEITHER_OPEN_NOR_CLOSED on purpose"
        )


@pytest.mark.parametrize("cls", ALL_STATE_ENUMS, ids=lambda c: c.__name__)
class TestFromApiValueRejectsBadInput:
    """`from_api_value` must degrade to None, never raise."""

    def test_none_returns_none(self, cls: type[Enum]) -> None:
        assert cls.from_api_value(None) is None

    def test_empty_string_returns_none(self, cls: type[Enum]) -> None:
        assert cls.from_api_value("") is None

    def test_unknown_value_returns_none(self, cls: type[Enum]) -> None:
        """An unrecognised state must not raise — Rivian adds values over time."""
        assert cls.from_api_value("a_state_rivian_has_not_shipped_yet") is None


@pytest.mark.parametrize("cls", ALL_STATE_ENUMS, ids=lambda c: c.__name__)
def test_sna_is_neither_open_nor_closed(cls: type[Enum]) -> None:
    """SNA means "signal not available" — it must not be reported as a state.

    Classifying SNA as closed would make every closure read closed whenever the
    vehicle stops reporting, which is worse than reporting nothing.
    """
    sna = cls.SNA
    assert not sna.is_open()
    assert not sna.is_closed()
    assert not sna.is_faulted()


class TestSemanticSpotChecks:
    """A few explicit cases, so the invariants above cannot all pass vacuously."""

    def test_frunk_close_allowed_means_it_is_open(self) -> None:
        """ "Close allowed" is the API's way of saying the frunk is currently open."""
        assert FrunkNextActionState.CLOSE_ALLOWED.is_open()
        assert not FrunkNextActionState.CLOSE_ALLOWED.is_closed()

    def test_frunk_open_allowed_means_it_is_closed(self) -> None:
        assert FrunkNextActionState.OPEN_ALLOWED.is_closed()
        assert not FrunkNextActionState.OPEN_ALLOWED.is_open()

    def test_motion_predicates_are_distinct(self) -> None:
        assert FrunkNextActionState.OPENING.is_opening()
        assert not FrunkNextActionState.OPENING.is_closing()
        assert FrunkNextActionState.CLOSING.is_closing()
        assert not FrunkNextActionState.CLOSING.is_opening()

    def test_obstruction_keeps_the_closure_open(self) -> None:
        """An obstructed closure is open — it is physically blocked mid-travel."""
        state = FrunkNextActionState.OBSTRUCTED_WHILE_CLOSING_OPEN_ALLOWED
        assert state.is_obstructed()
        assert state.is_open()

    def test_liftgate_trailer_detected_is_still_a_positional_state(self) -> None:
        """Trailer detection annotates the state; it does not replace it."""
        state = LiftgateNextActionState.CLOSE_ALLOWED_TRAILER_DETECTED
        assert state.has_trailer_detected()
        assert state.is_open()

    def test_liftgate_paused_is_neither_open_nor_closed(self) -> None:
        """A paused liftgate is mid-travel; reporting either extreme would be wrong."""
        for state in (
            LiftgateNextActionState.OPENING_PAUSE_NOT_ALLOWED,
            LiftgateNextActionState.CLOSING_PAUSE_NOT_ALLOWED,
            LiftgateNextActionState.PROCESSING,
        ):
            assert not state.is_open()
            assert not state.is_closed()
