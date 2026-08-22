"""Tests for SupportedFeaturesCoordinator.

Two accessors, two different filters:
  available_features()   -- AVAILABLE only, the gating-safe subset a future
                             story might read.
  features_by_status()   -- every status, including UPDATE_FIRMWARE, which
                             diagnostics reads so that status is visible
                             instead of silently dropped.

Neither is wired to gate anything here (s19 scope); see
SupportedFeaturesCoordinator's own docstring.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.rivian.coordinator import (
    RivianDataUpdateCoordinator,
    SupportedFeaturesCoordinator,
    UserCoordinator,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

RAW_PAYLOAD = {
    "vehicles": [
        {
            "id": "v1",
            "vehicle": {
                "vehicleState": {
                    "supportedFeatures": [
                        {"name": "CHARG_NTW_EA", "status": "AVAILABLE"},
                        {"name": "TESLA_NACS", "status": "UPDATE_FIRMWARE"},
                    ]
                }
            },
        },
        {
            "id": "v2",
            "vehicle": {"vehicleState": {"supportedFeatures": []}},
        },
    ]
}


@pytest.fixture
def coordinator(hass: HomeAssistant, mock_config_entry: ConfigEntry):
    return SupportedFeaturesCoordinator(
        hass=hass, config_entry=mock_config_entry, client=MagicMock()
    )


class TestAvailableFeatures:
    def test_filters_to_available_only(self, coordinator) -> None:
        coordinator.data = RAW_PAYLOAD
        assert coordinator.available_features() == {
            "v1": frozenset({"CHARG_NTW_EA"}),
            "v2": frozenset(),
        }

    def test_update_firmware_is_excluded(self, coordinator) -> None:
        coordinator.data = RAW_PAYLOAD
        assert "TESLA_NACS" not in coordinator.available_features()["v1"]

    def test_no_data_returns_empty_dict(self, coordinator) -> None:
        coordinator.data = None
        assert coordinator.available_features() == {}


class TestFeaturesByStatus:
    def test_update_firmware_survives(self, coordinator) -> None:
        coordinator.data = RAW_PAYLOAD
        assert coordinator.features_by_status()["v1"]["TESLA_NACS"] == "UPDATE_FIRMWARE"

    def test_available_also_survives(self, coordinator) -> None:
        coordinator.data = RAW_PAYLOAD
        assert coordinator.features_by_status()["v1"]["CHARG_NTW_EA"] == "AVAILABLE"

    def test_every_vehicle_present_even_with_no_features(self, coordinator) -> None:
        coordinator.data = RAW_PAYLOAD
        assert coordinator.features_by_status()["v2"] == {}

    def test_no_data_returns_empty_dict(self, coordinator) -> None:
        coordinator.data = None
        assert coordinator.features_by_status() == {}


class TestFitsTheBase:
    def test_key_is_currentUser(self) -> None:
        assert SupportedFeaturesCoordinator.key == "currentUser"

    def test_interval_matches_user_coordinator(self) -> None:
        """Per the task: 'user-level update interval (match UserCoordinator's)'."""
        assert (
            SupportedFeaturesCoordinator._update_interval_seconds
            == UserCoordinator._update_interval_seconds
        )

    def test_it_is_not_the_thirty_second_vehicle_cadence(self) -> None:
        assert (
            SupportedFeaturesCoordinator._update_interval_seconds
            != RivianDataUpdateCoordinator._update_interval_seconds
        )

    async def test_fetch_data_calls_the_client_method(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        from unittest.mock import AsyncMock

        client = MagicMock()
        client.get_supported_features = AsyncMock()
        coordinator = SupportedFeaturesCoordinator(
            hass=hass, config_entry=mock_config_entry, client=client
        )
        await coordinator._fetch_data()
        client.get_supported_features.assert_called_once_with()
