"""The wake is dispatched, never awaited.

`send_vehicle_command` used to fire WAKE_VEHICLE at a sleeping vehicle and then
block on `asyncio.wait_for(self._awake.wait(), 30)` before sending the command the
user actually asked for. That wait had a latent defect on top of its cost: `_awake`
was set only by a `powerState` subscription frame, so after a restart or a dropped
subscription -- exactly when `powerState` is None -- it always burned the full 30 s
and timed out anyway.

The app does not wait. `C2150e.java:212-215` builds the command flow, fires
WakeVehicle, and collects, with no await between them; its accommodation for a
sleeping vehicle is a longer give-up timeout (`C5332Z.java:821`, 120 s vs 60 s), not
a blocking wait. This file pins that ordering and pins the wait staying gone.
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.connectivity import ConnectivityState
from custom_components.rivian.const import (
    ATTR_COORDINATOR,
    ATTR_USER,
    ATTR_VEHICLE,
    DOMAIN,
)
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.rivian_client import VehicleCommand
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


def _coordinator(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
    *,
    is_online: bool | None,
    data: dict | None,
) -> VehicleCoordinator:
    """Build a real coordinator wired to a mock API, with the given raw inputs.

    Deliberately a *real* VehicleCoordinator with real `_is_online` / `data`, not a
    stubbed `connectivity_state`: what these tests are about is the derivation
    driving the dispatch, so short-circuiting it would test nothing.
    """
    coordinator = VehicleCoordinator(
        hass=hass,
        config_entry=mock_config_entry,
        client=MagicMock(),
        vehicle_id="v1",
    )
    coordinator._is_online = is_online
    coordinator.data = data
    coordinator.api.send_vehicle_command = AsyncMock(return_value=None)
    coordinator._subscribe_to_command_state = AsyncMock()

    user = MagicMock()
    user.get_enrolled_phone_data = MagicMock(return_value=("phone-1",))
    hass.data.setdefault(DOMAIN, {})[mock_config_entry.entry_id] = {
        ATTR_VEHICLE: {"v1": {"phone_identity_id": "id-1", "public_key": "pub"}},
        ATTR_COORDINATOR: {ATTR_USER: user},
    }
    return coordinator


def _sent(coordinator: VehicleCoordinator) -> list[VehicleCommand]:
    return [
        call.kwargs["command"]
        for call in coordinator.api.send_vehicle_command.call_args_list
    ]


async def test_a_sleeping_command_dispatches_wake_first(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """A SLEEPING vehicle gets WAKE_VEHICLE, then the requested command, in order.

    Ordering is asserted, not just the call count: the app dispatches the wake before
    collecting the command flow, and a `create_task` shape would make the two arrive
    at the cloud in a nondeterministic order.
    """
    coordinator = _coordinator(
        hass, mock_config_entry, is_online=True, data={"powerState": "sleep"}
    )
    assert coordinator.connectivity_state() is ConnectivityState.SLEEPING

    await coordinator.send_vehicle_command(VehicleCommand.HONK_AND_FLASH_LIGHTS)

    assert _sent(coordinator) == [
        VehicleCommand.WAKE_VEHICLE,
        VehicleCommand.HONK_AND_FLASH_LIGHTS,
    ]


async def test_an_online_command_dispatches_no_wake(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """An awake vehicle is not woken. One command in, one command out."""
    coordinator = _coordinator(
        hass, mock_config_entry, is_online=True, data={"powerState": "ready"}
    )
    assert coordinator.connectivity_state() is ConnectivityState.ONLINE

    await coordinator.send_vehicle_command(VehicleCommand.HONK_AND_FLASH_LIGHTS)

    assert _sent(coordinator) == [VehicleCommand.HONK_AND_FLASH_LIGHTS]


async def test_wake_itself_does_not_recurse(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """WAKE_VEHICLE on a sleeping vehicle sends exactly one wake, not infinitely many.

    `send_vehicle_command` calls itself to dispatch the wake, so the
    `command != VehicleCommand.WAKE_VEHICLE` guard is the only thing standing between
    this path and unbounded recursion. It is retained verbatim across this change.
    """
    coordinator = _coordinator(
        hass, mock_config_entry, is_online=False, data={"powerState": "standby"}
    )
    assert coordinator.connectivity_state() is ConnectivityState.SLEEPING

    await coordinator.send_vehicle_command(VehicleCommand.WAKE_VEHICLE)

    assert _sent(coordinator) == [VehicleCommand.WAKE_VEHICLE]


async def test_a_sleeping_command_does_not_stall(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The worst case for the old code completes promptly instead of burning 30 s.

    This is the exact shape that used to stall: the cached `powerState` is "sleep", so
    the wake dispatches, but no subscription frame is ever delivered -- and a frame was
    the ONLY thing that ever set `_awake`. So the old `wait_for(self._awake.wait(), 30)`
    could not be satisfied and always ran out its full 30 s before the user's command
    was sent. After a restart or a dropped subscription this was the normal case, not
    an edge case.

    Bounded with a real 5 s wall clock rather than a fake one: a reintroduced 30 s
    Event wait fails this in 5 s instead of slowing the suite by 30, and 5 s leaves
    enough margin that a loaded CI box will not flake. 1 s would not.
    """
    coordinator = _coordinator(
        hass, mock_config_entry, is_online=False, data={"powerState": "sleep"}
    )
    assert coordinator.connectivity_state() is ConnectivityState.SLEEPING

    await asyncio.wait_for(
        coordinator.send_vehicle_command(VehicleCommand.HONK_AND_FLASH_LIGHTS), 5
    )

    assert _sent(coordinator) == [
        VehicleCommand.WAKE_VEHICLE,
        VehicleCommand.HONK_AND_FLASH_LIGHTS,
    ]


def test_no_event_wait_remains_in_send_vehicle_command() -> None:
    """The structural guard: neither the wait nor the Event it waited on survives.

    The wall-clock bound above proves the current code does not stall; this proves it
    cannot stall by that mechanism again. `_awake` has no readers left at all, so it
    was deleted outright rather than left as write-only state -- and the reason it was
    write-only is the defect being removed here.
    """
    source = inspect.getsource(VehicleCoordinator.send_vehicle_command)
    assert "wait_for" not in source
    assert "_awake" not in source

    module = inspect.getsource(inspect.getmodule(VehicleCoordinator))
    assert "_awake" not in module


@pytest.mark.parametrize(
    ("is_online", "power_state", "expect_wake"),
    [
        (True, "sleep", True),
        (None, "sleep", True),
        (False, "sleep", True),
        # The widened trigger: `isOnline is False` + `standby` derives to SLEEPING and
        # now wakes, where the old raw `powerState == "sleep"` compare did not. This is
        # the one extra input combination the change adds, and it is intended.
        (False, "standby", True),
        (True, "standby", False),
        (False, "ready", False),
        (True, "ready", False),
        (None, None, False),
    ],
)
async def test_the_wake_trigger_follows_the_derived_state(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
    is_online: bool | None,
    power_state: str | None,
    expect_wake: bool,
) -> None:
    """The dispatch trigger is the derived SLEEPING state, not a raw string compare.

    Pins the supersession explicitly so the widened trigger is a decision on record.
    """
    coordinator = _coordinator(
        hass,
        mock_config_entry,
        is_online=is_online,
        data={"powerState": power_state} if power_state else {},
    )

    await coordinator.send_vehicle_command(VehicleCommand.HONK_AND_FLASH_LIGHTS)

    assert (VehicleCommand.WAKE_VEHICLE in _sent(coordinator)) is expect_wake
