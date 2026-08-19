"""UserCoordinator and WallboxCoordinator poll on their own schedule.

Both inherited the base's 30-second interval, which is the cadence a *vehicle*
needs. Neither is that. `currentUser` carries the account, its enrolled phones
and the vehicle capability list; `getRegisteredWallboxes` carries the home
charger. Both are heavyweight queries whose payloads change on the order of
months, and both were being re-fetched twice a minute.

## The 900-second cap, and why the number chosen makes it moot

`_set_update_interval` (coordinator.py:86-98) computes

    seconds = min(self._update_interval_seconds * 2**self._error_count, 900)

and never reassigns `_update_interval_seconds`. So the *base* is a constant and
the cap applies to the product. Any base **above** 900 is therefore a trap: it is
used verbatim at construction, then collapses to 900 on the first error and never
climbs back, turning a back-off into a one-way ratchet downward. Verified: base
3600 -> 900 after a single error, and 900 again after recovery.

Both coordinators are set to **900 seconds** exactly, which stays at the cap and
makes the trap unreachable. The cost is stated rather than hidden: at exactly the
cap, the back-off is a no-op -- an erroring coordinator keeps retrying every 15
minutes instead of stretching further. That is acceptable, because 900 s is
already the ceiling the old 30 s base reached after five consecutive failures.
The back-off existed to stop a failing API being hammered every 30 seconds, and
starting at the ceiling satisfies that outright.

The assertions below check the **effective** `update_interval` after a simulated
error, not the declared class attribute. A gate that reads only the attribute
passes green while the poll still runs every 15 minutes -- or every 30 seconds.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.coordinator import (
    RivianDataUpdateCoordinator,
    UserCoordinator,
    WallboxCoordinator,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

CAP_SECONDS = 900
EXPECTED_INTERVAL = 900


_built: list[RivianDataUpdateCoordinator] = []


def _build(cls, hass: HomeAssistant, entry: ConfigEntry) -> RivianDataUpdateCoordinator:
    client = MagicMock()
    client.get_user_information = AsyncMock()
    client.get_registered_wallboxes = AsyncMock()
    coordinator = cls(hass=hass, config_entry=entry, client=client)
    _built.append(coordinator)
    return coordinator


@pytest.fixture(autouse=True)
def _cancel_scheduled_refreshes():
    """`_set_update_interval` reschedules, which leaves a live timer behind.

    pytest-homeassistant-custom-component fails any test that leaves one, and it
    reports as an ERROR at teardown rather than beside the assertion that caused
    it -- so without this the failures point at the wrong place.
    """
    _built.clear()
    yield
    for coordinator in _built:
        coordinator._unschedule_refresh()
    _built.clear()


@pytest.mark.parametrize("cls", [UserCoordinator, WallboxCoordinator])
class TestDeclaredInterval:
    def test_declares_its_own_interval(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry, cls
    ) -> None:
        """Its own, not the base's."""
        assert "_update_interval_seconds" in vars(cls), (
            f"{cls.__name__} still inherits the base's interval"
        )
        assert cls._update_interval_seconds == EXPECTED_INTERVAL

    def test_it_is_not_the_thirty_second_vehicle_cadence(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry, cls
    ) -> None:
        assert cls._update_interval_seconds != 30
        assert (
            cls._update_interval_seconds
            > RivianDataUpdateCoordinator._update_interval_seconds
        )

    def test_the_base_is_at_or_below_the_cap(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry, cls
    ) -> None:
        """Above the cap the back-off inverts into a permanent downgrade."""
        assert cls._update_interval_seconds <= CAP_SECONDS

    def test_the_constructed_interval_matches(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry, cls
    ) -> None:
        coordinator = _build(cls, hass, mock_config_entry)
        assert coordinator.update_interval == timedelta(seconds=EXPECTED_INTERVAL)


@pytest.mark.parametrize("cls", [UserCoordinator, WallboxCoordinator])
@pytest.mark.parametrize("errors", [1, 2, 5, 10])
async def test_effective_interval_after_an_error_is_still_the_long_one(
    hass: HomeAssistant, mock_config_entry: ConfigEntry, cls, errors: int
) -> None:
    """The assertion that actually binds.

    Reading the class attribute proves nothing about what is scheduled. This
    drives the same code path an error does and reads `update_interval`.
    """
    coordinator = _build(cls, hass, mock_config_entry)
    coordinator._error_count = errors
    coordinator._set_update_interval()
    assert coordinator.update_interval == timedelta(seconds=EXPECTED_INTERVAL)


@pytest.mark.parametrize("cls", [UserCoordinator, WallboxCoordinator])
async def test_recovery_does_not_leave_it_faster_than_intended(
    hass: HomeAssistant, mock_config_entry: ConfigEntry, cls
) -> None:
    """After errors clear, it must not snap back to a 30-second poll."""
    coordinator = _build(cls, hass, mock_config_entry)
    coordinator._error_count = 3
    coordinator._set_update_interval()
    coordinator._error_count = 0
    coordinator._set_update_interval()
    assert coordinator.update_interval == timedelta(seconds=EXPECTED_INTERVAL)


async def test_a_base_above_the_cap_would_be_a_one_way_ratchet(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The trap, demonstrated on a synthetic subclass rather than asserted in prose.

    This is why the chosen number is 900 and not 3600. It is a characterisation
    test of the base class: if someone later raises the cap or makes
    `_set_update_interval` reassign the base, this goes red and the comment above
    needs rewriting.
    """

    class _TooSlow(WallboxCoordinator):
        _update_interval_seconds = 3600

    coordinator = _build(_TooSlow, hass, mock_config_entry)
    assert coordinator.update_interval == timedelta(seconds=3600)

    coordinator._error_count = 1
    coordinator._set_update_interval()
    assert coordinator.update_interval == timedelta(seconds=CAP_SECONDS)

    # And it never climbs back, because the base is never reassigned.
    coordinator._error_count = 0
    coordinator._set_update_interval()
    assert coordinator.update_interval == timedelta(seconds=CAP_SECONDS)


async def test_the_vehicle_coordinator_cadence_is_untouched(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Scope guard: this story is about two coordinators, not the base."""
    from custom_components.rivian.coordinator import (
        ChargingCoordinator,
        DriverKeyCoordinator,
        VehicleCoordinator,
    )

    assert RivianDataUpdateCoordinator._update_interval_seconds == 30
    assert VehicleCoordinator._update_interval_seconds == 15 * 60
    assert DriverKeyCoordinator._update_interval_seconds == 15 * 60
    assert ChargingCoordinator._update_interval_seconds == 0


async def test_capabilities_still_propagate_on_reload(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """A 15-minute poll must not mean 15 minutes of stale capabilities.

    `async_setup_entry` constructs a fresh UserCoordinator and awaits
    `async_config_entry_first_refresh()` before anything else
    (__init__.py:75-78), so reloading the entry re-fetches `currentUser`
    immediately. This asserts that path exists rather than trusting the interval
    change was harmless.
    """
    import inspect

    from custom_components.rivian import async_setup_entry

    source = inspect.getsource(async_setup_entry)
    assert "UserCoordinator(" in source
    assert "async_config_entry_first_refresh()" in source

    # And a refresh really does repopulate, so the longer interval only changes
    # the *schedule*, not whether a reload picks up new capabilities.
    # async_refresh rather than async_config_entry_first_refresh: the latter
    # asserts the entry is SETUP_IN_PROGRESS, which is a harness state, not the
    # behaviour under test.
    coordinator = _build(UserCoordinator, hass, mock_config_entry)
    coordinator._async_update_data = AsyncMock(return_value={"id": "u1"})
    await coordinator.async_refresh()
    assert coordinator.data == {"id": "u1"}
