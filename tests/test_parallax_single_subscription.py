"""VehicleCoordinator owns exactly one Parallax subscription, with an explicit list.

Two defects are pinned here, both of which shipped at some point:

* TWO subscriptions. The s05 merge left ours (on the now-dissolved
  ParallaxCoordinator) alongside upstream's, so every message was delivered and
  protobuf-decoded twice and _resubscribe_all reopened both on each reconnect.

* rvms=None. That asks the client for `PARALLAX_RVMS`, which omits the charging
  topics entirely. Naively concatenating the two lists is not the fix either:
  they overlap by five topics, so 25 subscriptions would cover 20 unique ones and
  the overlap would arrive twice.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.rivian_client.parallax import CHARGING_RVMS, PARALLAX_RVMS
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


@pytest.fixture
def api() -> MagicMock:
    client = MagicMock()
    client.subscribe_for_vehicle_updates = AsyncMock(return_value=AsyncMock())
    client.subscribe_for_tire_pressure_updates = AsyncMock(return_value=AsyncMock())
    client.subscribe_for_cloud_connection = AsyncMock(return_value=AsyncMock())
    client.subscribe_for_parallax_messages = AsyncMock(return_value=AsyncMock())
    schedule = MagicMock()
    schedule.json = AsyncMock(
        return_value={"data": {"getVehicle": {"chargingSchedules": []}}}
    )
    client.get_charging_schedules = AsyncMock(return_value=schedule)
    return client


@pytest.fixture
def coordinator(hass: HomeAssistant, mock_config_entry: ConfigEntry, api: MagicMock):
    c = VehicleCoordinator(
        hass=hass,
        config_entry=mock_config_entry,
        client=api,
        vehicle_id="test_vehicle_123",
    )
    c._initial.set()  # skip the initial-data wait; it is startup timing, not the invariant
    return c


async def test_exactly_one_parallax_subscription(coordinator, api) -> None:
    await coordinator._async_update_data()
    assert api.subscribe_for_parallax_messages.await_count == 1
    coordinator._stop_watchdog()


async def test_the_rvm_list_is_explicit_never_none(coordinator, api) -> None:
    await coordinator._async_update_data()
    rvms = api.subscribe_for_parallax_messages.await_args.kwargs["rvms"]
    assert rvms is not None, "rvms=None silently drops the charging topics"
    coordinator._stop_watchdog()


async def test_the_rvm_list_is_deduped(coordinator, api) -> None:
    await coordinator._async_update_data()
    rvms = api.subscribe_for_parallax_messages.await_args.kwargs["rvms"]
    assert len(rvms) == len(set(rvms)), f"duplicate topics requested: {rvms}"
    coordinator._stop_watchdog()


async def test_the_rvm_list_covers_both_sources(coordinator, api) -> None:
    """Telemetry AND charging. Either list alone leaves entities unavailable.

    Scoped to the topics we can decode: three of CHARGING_RVMS have no decoder and
    are now filtered out, because subscribing to them only produced an "Unknown
    Parallax RVM topic" warning on every push. The guard this test exists for --
    that neither source is dropped wholesale -- is unchanged.
    """
    from custom_components.rivian.rivian_client.parallax import RVM_DECODERS

    await coordinator._async_update_data()
    rvms = set(api.subscribe_for_parallax_messages.await_args.kwargs["rvms"])
    assert set(PARALLAX_RVMS) & set(RVM_DECODERS) <= rvms
    assert set(CHARGING_RVMS) & set(RVM_DECODERS) <= rvms
    assert rvms == (set(PARALLAX_RVMS) | set(CHARGING_RVMS)) & set(RVM_DECODERS)
    # Charging telemetry specifically must survive the filter.
    assert "charging.session.status" in rvms
    coordinator._stop_watchdog()


async def test_the_subscription_is_torn_down(coordinator, api) -> None:
    await coordinator._async_update_data()
    unsub = coordinator._unsub_parallax
    assert unsub is not None
    coordinator._stop_watchdog()
    await coordinator._unsubscribe()
    unsub.assert_awaited()
    assert coordinator._unsub_parallax is None


class TestWeOnlySubscribeToWhatWeCanDecode:
    """Asking for a topic with no decoder buys nothing and costs a warning.

    CHARGING_RVMS (upstream's list) names three topics that RVM_DECODERS does not
    cover: charging.session.notification, .remote_command and .soc_slider. The
    vehicle pushes them, decode_parallax_message returns None, and the client logs

        WARNING Unknown Parallax RVM topic charging.session.soc_slider

    for each, every push -- observed roughly every three minutes on a live
    instance. The payload is discarded either way, so the subscription is pure
    noise and bandwidth.

    Filtered here rather than by editing CHARGING_RVMS, because that list is
    upstream's and vendored; narrowing it locally would diverge a file we merge.
    The intersection is also self-maintaining: adding a decoder subscribes its
    topic automatically.
    """

    def test_every_subscribed_topic_has_a_decoder(self) -> None:
        from custom_components.rivian.coordinator import SUBSCRIBED_RVMS
        from custom_components.rivian.rivian_client.parallax import RVM_DECODERS

        undecodable = sorted(set(SUBSCRIBED_RVMS) - set(RVM_DECODERS))
        assert not undecodable, (
            f"{undecodable} would be subscribed but cannot be decoded; each push "
            "logs a warning and the payload is thrown away"
        )

    def test_it_still_covers_everything_we_can_decode(self) -> None:
        """The filter must not silently shrink coverage -- that would trade log
        noise for missing telemetry."""
        from custom_components.rivian.coordinator import SUBSCRIBED_RVMS
        from custom_components.rivian.rivian_client.parallax import (
            CHARGING_RVMS,
            PARALLAX_RVMS,
            RVM_DECODERS,
        )

        wanted = {*PARALLAX_RVMS, *CHARGING_RVMS} & set(RVM_DECODERS)
        assert set(SUBSCRIBED_RVMS) == wanted
        assert len(SUBSCRIBED_RVMS) == len(set(SUBSCRIBED_RVMS)), "deduped"
        assert SUBSCRIBED_RVMS == sorted(SUBSCRIBED_RVMS), "stable order"
