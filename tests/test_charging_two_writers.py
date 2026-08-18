"""ChargingCoordinator.data has two writers; they must not fight.

The s05 merge left the coordinator fed from two sources at once:

  update_from_parallax   (upstream)  -- Parallax push, MERGES
  _process_new_data      (ours)      -- getLiveSessionData subscription

Dropping either is not an option. Four sensors -- price, powerKW, timeRemaining,
isFreeSession -- have no Parallax source at all, and five Parallax-only fields
(displayStatus, evseType, plugConnectionStatus, currentPrice, currentCurrency)
have no subscription source. Both are needed, so both must compose.

These tests pin the composition, and they are written from the user-visible
symptom: sensors must not flap while the car is actually charging.
"""

from unittest.mock import MagicMock

import pytest

from custom_components.rivian.coordinator import ChargingCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


@pytest.fixture
def coordinator(hass: HomeAssistant, mock_config_entry: ConfigEntry):
    coord = ChargingCoordinator(
        hass=hass,
        config_entry=mock_config_entry,
        client=MagicMock(),
        vehicle_id="test_vehicle_123",
    )
    coord.async_set_updated_data = MagicMock(
        side_effect=lambda d: setattr(coord, "data", d)
    )
    return coord


def _subscription(live: dict | list) -> dict:
    """The subscription delivers nested chartData/liveData, and
    _process_charging_data flattens {**chartData, **liveData} -- top-level keys of
    the session object are discarded, so fixtures must nest."""
    session = live if isinstance(live, list) else {"liveData": live}
    return {"payload": {"data": {"chargingSession": session}}}


class TestNeitherWriterErasesTheOther:
    def test_subscription_data_keeps_parallax_only_fields(self, coordinator) -> None:
        # displayStatus/evseType/plugConnectionStatus come ONLY from Parallax.
        # A replacing write drops them and their sensors go unavailable mid-charge.
        coordinator.update_from_parallax(
            {"displayStatus": "charging", "evseType": "CCS", "power": 11}
        )
        coordinator._process_new_data(
            _subscription({"startTime": "T1", "totalChargedEnergy": 5})
        )
        assert coordinator.data["displayStatus"] == "charging"
        assert coordinator.data["evseType"] == "CCS"
        assert coordinator.data["totalChargedEnergy"] == 5

    def test_parallax_data_keeps_subscription_only_fields(self, coordinator) -> None:
        # price/powerKW/timeRemaining/isFreeSession have no Parallax source.
        coordinator._process_new_data(
            _subscription({"startTime": "T1", "price": 0.42, "isFreeSession": False})
        )
        coordinator.update_from_parallax({"power": 11, "startTime": "T1"})
        assert coordinator.data["price"] == 0.42
        assert coordinator.data["isFreeSession"] is False
        assert coordinator.data["power"] == 11


class TestSyntheticStartTimeDoesNotFakeANewSession:
    def test_a_real_start_time_replacing_a_synthetic_one_keeps_metrics(
        self, coordinator
    ) -> None:
        """The flap this guards.

        update_from_parallax invents a startTime when it sees power but none
        stored. When the REAL startTime later arrives it differs from the invented
        one, which looked like a brand-new session and cleared everything the
        session had accumulated.
        """
        coordinator.update_from_parallax({"power": 11})  # invents one
        assert coordinator.data["startTime"]
        coordinator.update_from_parallax(
            {"totalChargedEnergy": 7, "rangeAddedThisSession": 20}
        )
        coordinator.update_from_parallax({"startTime": "2026-08-18T00:00:00.000+0000"})
        assert coordinator.data["startTime"] == "2026-08-18T00:00:00.000+0000"
        assert coordinator.data["totalChargedEnergy"] == 7
        assert coordinator.data["rangeAddedThisSession"] == 20

    def test_a_genuinely_new_session_still_clears(self, coordinator) -> None:
        # The clearing behaviour must survive: stale metrics leaking across two
        # real sessions is the bug it was written for.
        coordinator.update_from_parallax({"startTime": "REAL-A"})
        coordinator.update_from_parallax({"totalChargedEnergy": 9})
        coordinator.update_from_parallax({"startTime": "REAL-B"})
        assert coordinator.data["startTime"] == "REAL-B"
        assert "totalChargedEnergy" not in coordinator.data

    def test_the_same_start_time_is_not_a_new_session(self, coordinator) -> None:
        coordinator.update_from_parallax({"startTime": "REAL-A"})
        coordinator.update_from_parallax({"totalChargedEnergy": 9})
        coordinator.update_from_parallax({"startTime": "REAL-A", "power": 11})
        assert coordinator.data["totalChargedEnergy"] == 9


class TestSessionEnd:
    def test_an_empty_session_list_still_ends_the_session(self, coordinator) -> None:
        coordinator._process_new_data(
            _subscription({"startTime": "T1", "totalChargedEnergy": 5})
        )
        coordinator._process_new_data(_subscription([]))
        assert coordinator.data == {}

    def test_a_non_empty_list_takes_the_first_entry(self, coordinator) -> None:
        coordinator._process_new_data(
            _subscription([{"liveData": {"startTime": "T9"}}])
        )
        assert coordinator.data["startTime"] == "T9"
