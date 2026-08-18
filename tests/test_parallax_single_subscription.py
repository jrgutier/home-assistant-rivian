"""The Parallax stream must be subscribed exactly ONCE per vehicle.

Merging upstream 1.5.3b5 produced two independent
`subscribe_for_parallax_messages` calls for the same vehicle: ours on
ParallaxCoordinator (feeding _rvm_data, diagnostics and the PARALLAX_* entities)
and upstream's on VehicleCoordinator (routing decoded fields to the charging and
vehicle coordinators).

Each PARENT had exactly one. Two is a merge regression, not a feature: both
default to the same RVM set, ws_monitor assigns a fresh uuid4 per subscription
with no payload dedupe, and _resubscribe_all reopens both on every reconnect --
so every message is delivered and protobuf-decoded twice.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.coordinator import VehicleCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


def _ready(coordinator: VehicleCoordinator) -> VehicleCoordinator:
    """Skip the 5s initial-data waits; they are startup timing, not the invariant
    under test, and two of them exceed pytest-timeout."""
    coordinator._initial.set()
    coordinator.parallax_coordinator._initial.set()
    return coordinator


@pytest.fixture
def api() -> MagicMock:
    client = MagicMock()
    client.subscribe_for_vehicle_updates = AsyncMock(return_value=AsyncMock())
    client.subscribe_for_cloud_connection = AsyncMock(return_value=AsyncMock())
    client.subscribe_for_parallax_messages = AsyncMock(return_value=AsyncMock())
    schedule = MagicMock()
    schedule.json = AsyncMock(
        return_value={"data": {"getVehicle": {"chargingSchedules": []}}}
    )
    client.get_charging_schedules = AsyncMock(return_value=schedule)
    return client


async def test_only_one_parallax_subscription_across_both_coordinators(
    hass: HomeAssistant, mock_config_entry: ConfigEntry, api: MagicMock
) -> None:
    """Run BOTH update cycles; exactly one subscription must exist between them."""
    coordinator = _ready(
        VehicleCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=api,
            vehicle_id="test_vehicle_123",
        )
    )
    await coordinator._async_update_data()
    await coordinator.parallax_coordinator._async_update_data()
    assert api.subscribe_for_parallax_messages.await_count == 1
    coordinator.parallax_coordinator._stop_watchdog()
    coordinator._stop_watchdog()


async def test_the_parallax_coordinator_is_the_owner(
    hass: HomeAssistant, mock_config_entry: ConfigEntry, api: MagicMock
) -> None:
    """ParallaxCoordinator holds it, because its _rvm_data store feeds
    diagnostics and the PARALLAX_* entity registries."""
    coordinator = _ready(
        VehicleCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=api,
            vehicle_id="test_vehicle_123",
        )
    )
    await coordinator._async_update_data()
    assert api.subscribe_for_parallax_messages.await_count == 0, (
        "VehicleCoordinator must not open a Parallax subscription of its own"
    )
    await coordinator.parallax_coordinator._async_update_data()
    assert api.subscribe_for_parallax_messages.await_count == 1
    assert coordinator.parallax_coordinator._unsub_handler is not None
    coordinator.parallax_coordinator._stop_watchdog()
    coordinator._stop_watchdog()


def test_the_router_is_wired_to_the_owner(
    hass: HomeAssistant, mock_config_entry: ConfigEntry, api: MagicMock
) -> None:
    """Collapsing to one subscription must not lose upstream's routing."""
    coordinator = _ready(
        VehicleCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=api,
            vehicle_id="test_vehicle_123",
        )
    )
    assert (
        coordinator.parallax_coordinator.on_message
        == coordinator._process_parallax_data
    )


def test_every_message_reaches_the_router(
    hass: HomeAssistant, mock_config_entry: ConfigEntry, api: MagicMock
) -> None:
    """A message on the owner's callback must still be handed to the router, or
    the charging and vehicle coordinators stop receiving Parallax fields."""
    coordinator = _ready(
        VehicleCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=api,
            vehicle_id="test_vehicle_123",
        )
    )
    routed = MagicMock()
    coordinator.parallax_coordinator.on_message = routed
    message = {
        "payload": {
            "data": {
                "parallaxMessages": {
                    "rvm": "comfort.cabin.climate_hold_status",
                    "payload": "CAIQARgBIgA=",
                    "timestamp": "2026-08-18T00:00:00Z",
                }
            }
        }
    }
    coordinator.parallax_coordinator._process_new_data(message)
    routed.assert_called_once_with(message)
