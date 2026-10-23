from __future__ import annotations

from enum import Enum


class ConnectivityState(Enum):
    ONLINE = "online"
    SLEEPING = "sleeping"
    OFFLINE = "offline"


def derive_connectivity_state(
    is_online: bool | None, power_state: str | None
) -> ConnectivityState:
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
