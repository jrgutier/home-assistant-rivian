"""Tests for the three-state connectivity derivation.

`derive_connectivity_state` mirrors the Rivian Android app's derivation at
`java_src/p116Eg/C1611c.java:141-158`. It is a total function of two nullable
scalars, so the table below is the whole specification: 3 values of `isOnline`
x 5 values of `powerState` = **15** cells, every one asserted.

Two of those cells are counter-intuitive and each has its own named test, because
a future reader will otherwise "fix" them:

  * `isOnline is None` derives to ONLINE, not OFFLINE. The app treats an absent
    answer as "we have no reason to believe it is unreachable", and this change
    exists precisely so a vehicle we have not heard from keeps its controls.
  * `standby` counts as sleeping ONLY when the cloud has actually said offline.
    An awake vehicle in `standby` is ONLINE.
"""

from __future__ import annotations

import pytest

from custom_components.rivian.connectivity import (
    ConnectivityState,
    derive_connectivity_state,
)

ONLINE = ConnectivityState.ONLINE
SLEEPING = ConnectivityState.SLEEPING
OFFLINE = ConnectivityState.OFFLINE

# The full cross product of the app's two inputs. `PowerState` vocabulary is
# SLEEP, STANDBY, READY, GO (plus UNKNOWN) per
# `java_src/com/rivian/android/consumer/data/model/PowerState.java`; `None` stands
# for "no powerState frame has arrived yet", which is the post-restart state.
TRUTH_TABLE: list[tuple[bool | None, str | None, ConnectivityState]] = [
    # isOnline is None -> the app's null branch: only `sleep` sleeps.
    (None, "sleep", SLEEPING),
    (None, "standby", ONLINE),
    (None, "ready", ONLINE),
    (None, "go", ONLINE),
    (None, None, ONLINE),
    # isOnline is True -> same branch as null.
    (True, "sleep", SLEEPING),
    (True, "standby", ONLINE),
    (True, "ready", ONLINE),
    (True, "go", ONLINE),
    (True, None, ONLINE),
    # isOnline is False -> `standby` joins `sleep`; everything else is OFFLINE.
    (False, "sleep", SLEEPING),
    (False, "standby", SLEEPING),
    (False, "ready", OFFLINE),
    (False, "go", OFFLINE),
    (False, None, OFFLINE),
]


@pytest.mark.parametrize(("is_online", "power_state", "expected"), TRUTH_TABLE)
def test_the_truth_table(
    is_online: bool | None, power_state: str | None, expected: ConnectivityState
) -> None:
    """Every cell of C1611c.java:141-158, one assert per cell.

    Fifteen cells, not ten: the derivation is total over both nullable inputs, so
    leaving five untested would leave the post-restart path (`powerState is None`)
    unpinned -- and that is the exact path this change was written for.
    """
    assert derive_connectivity_state(is_online, power_state) is expected


def test_null_is_online_is_treated_as_online() -> None:
    """`isOnline is None` means unknown, and unknown means ONLINE.

    This is the app's rule (`C1611c.java:141-158`: `isOnline == null || isOnline ==
    TRUE` share a branch), and it reads backwards to anyone who assumes "we have not
    heard from it" implies "it is unreachable". It is deliberate: the cost of
    offering a control on an unreachable vehicle is one confusing cloud error, while
    the cost of hiding a control on a reachable one is that the user cannot drive
    their car from Home Assistant until a frame happens to arrive.
    """
    assert derive_connectivity_state(None, None) is ONLINE
    assert derive_connectivity_state(None, "ready") is ONLINE
    # ...and the null branch still sleeps on `sleep`, so "unknown" is not a blanket
    # override -- it only decides *which* of the app's two branches applies.
    assert derive_connectivity_state(None, "sleep") is SLEEPING


def test_standby_only_sleeps_when_the_cloud_says_offline() -> None:
    """`standby` is the app's second asymmetry and is easy to over-generalise.

    `standby` maps to SLEEPING only in the `isOnline is False` branch. When the
    cloud says the vehicle is reachable (or says nothing), a `standby` power state
    is ONLINE. Collapsing the two branches into a single `power_state in ("sleep",
    "standby")` test would dispatch a wake at every `standby` frame on a vehicle
    that is already answering.
    """
    assert derive_connectivity_state(False, "standby") is SLEEPING
    assert derive_connectivity_state(True, "standby") is ONLINE
    assert derive_connectivity_state(None, "standby") is ONLINE


def test_an_unknown_power_state_string_is_not_special_cased() -> None:
    """Only the four known power states matter; anything else falls through.

    Recorded by contrast with the client's `decode_power_state`, which falls back to
    `"standby"` for an unrecognised Parallax value (`rivian_client/parallax.py:536`).
    That fallback means an undecodable power state on an offline vehicle derives to
    SLEEPING -- controls stay available -- while a *string* we simply do not know
    derives to OFFLINE. The bias is on the record as a decision, not an accident.
    """
    assert derive_connectivity_state(False, "banana") is OFFLINE
    assert derive_connectivity_state(True, "banana") is ONLINE


def test_the_enum_has_exactly_three_members() -> None:
    """Three states, lowercase string values, matching next_action_states.py's style.

    The app models these as three sealed classes (C1329b/C1330c/C1328a); we have no
    payload to carry, so a plain Enum is the whole shape. A fourth member would mean
    the derivation no longer mirrors C1611c.java.
    """
    assert [m.value for m in ConnectivityState] == ["online", "sleeping", "offline"]
