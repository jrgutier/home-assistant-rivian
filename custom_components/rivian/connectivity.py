"""Connectivity state derived from the cloud flag and the vehicle power state.

Mirrors the Rivian Android app's derivation at
`java_src/p116Eg/C1611c.java:141-158`, including its two asymmetries:
  * `isOnline` null is treated as ONLINE, not OFFLINE;
  * `standby` counts as sleeping ONLY when `isOnline` is False.
"""

from __future__ import annotations

from enum import Enum


class ConnectivityState(Enum):
    """Three-state vehicle connectivity, per the app's C1329b/C1330c/C1328a."""

    ONLINE = "online"
    SLEEPING = "sleeping"
    OFFLINE = "offline"


def derive_connectivity_state(
    is_online: bool | None, power_state: str | None
) -> ConnectivityState:
    """Return the connectivity state. Total over both nullable inputs."""
    if is_online is None or is_online:
        return (
            ConnectivityState.SLEEPING
            if power_state == "sleep"
            else ConnectivityState.ONLINE
        )
    return (
        ConnectivityState.SLEEPING
        if power_state in ("sleep", "standby")
        else ConnectivityState.OFFLINE
    )
