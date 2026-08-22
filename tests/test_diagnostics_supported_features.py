"""Diagnostics for the SupportedFeatures feed (s19).

Covers the three-way `feature_source` split -- "feed", "static_fallback",
"none" -- and that UPDATE_FIRMWARE survives into `features_by_status`
instead of being silently dropped by the AVAILABLE-only filter every other
consumer of supportedFeatures uses.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.rivian.const import (
    ATTR_COORDINATOR,
    ATTR_SUPPORTED_FEATURES,
    ATTR_USER,
    ATTR_VEHICLE,
    ATTR_WALLBOX,
    DOMAIN,
)
from custom_components.rivian.coordinator import (
    SupportedFeaturesCoordinator,
    UserCoordinator,
    VehicleCoordinator,
    WallboxCoordinator,
)
from custom_components.rivian.diagnostics import async_get_config_entry_diagnostics
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


def _base_entry_data(features_coordinator, static_vehicles: dict | None = None) -> dict:
    user_coordinator = MagicMock(spec=UserCoordinator)
    user_coordinator.data = {"userId": "user_123"}

    vehicle_coordinator = MagicMock(spec=VehicleCoordinator, rvm_arrivals={})
    vehicle_coordinator._unsub_parallax = None
    vehicle_coordinator.data = {"vin": "VIN1"}
    vehicle_coordinator.charging_coordinator = MagicMock()
    vehicle_coordinator.charging_coordinator.data = {}
    vehicle_coordinator.drivers_coordinator = MagicMock()
    vehicle_coordinator.drivers_coordinator.data = {}

    wallbox_coordinator = MagicMock(spec=WallboxCoordinator)
    wallbox_coordinator.data = {}

    coordinators = {
        ATTR_USER: user_coordinator,
        ATTR_VEHICLE: {"v1": vehicle_coordinator},
        ATTR_WALLBOX: wallbox_coordinator,
    }
    if features_coordinator is not None:
        coordinators[ATTR_SUPPORTED_FEATURES] = features_coordinator

    entry_data = {ATTR_COORDINATOR: coordinators}
    if static_vehicles is not None:
        entry_data[ATTR_VEHICLE] = static_vehicles
    return entry_data


@pytest.mark.asyncio
async def test_feature_source_is_feed_when_the_feed_has_data(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    features_coordinator = MagicMock(spec=SupportedFeaturesCoordinator)
    features_coordinator.features_by_status.return_value = {
        "v1": {"CHARG_NTW_EA": "AVAILABLE", "TESLA_NACS": "UPDATE_FIRMWARE"}
    }

    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: _base_entry_data(
            features_coordinator, static_vehicles={"v1": {"supported_features": []}}
        )
    }

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert diagnostics["supported_features"]["v1"]["feature_source"] == "feed"
    assert diagnostics["supported_features"]["v1"]["features_available"] == [
        "CHARG_NTW_EA"
    ]
    # UPDATE_FIRMWARE must be visible, not dropped.
    assert (
        diagnostics["supported_features"]["v1"]["features_by_status"]["TESLA_NACS"]
        == "UPDATE_FIRMWARE"
    )


@pytest.mark.asyncio
async def test_static_fallback_engages_when_the_feed_has_nothing(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """No SupportedFeaturesCoordinator entry at all -- the feed never ran
    or failed before ever producing data -- so the embedded getUserInfo
    fallback (UserCoordinator.get_vehicles()'s "supported_features" list)
    must answer instead.
    """
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: _base_entry_data(
            features_coordinator=None,
            static_vehicles={"v1": {"supported_features": ["CHARG_NTW_EA"]}},
        )
    }

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert (
        diagnostics["supported_features"]["v1"]["feature_source"] == "static_fallback"
    )
    assert diagnostics["supported_features"]["v1"]["features_available"] == [
        "CHARG_NTW_EA"
    ]
    assert diagnostics["supported_features"]["v1"]["features_by_status"] == {
        "CHARG_NTW_EA": "AVAILABLE"
    }


@pytest.mark.asyncio
async def test_static_fallback_also_engages_when_the_feed_ran_but_this_vehicle_is_absent(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The feed coordinator exists and has data, but not for THIS vehicle
    id (e.g. it failed before ever getting data) -- membership, not
    truthiness, decides the source (a vehicle can legitimately have an
    empty feed-sourced feature list and that must still read as "feed")."""
    features_coordinator = MagicMock(spec=SupportedFeaturesCoordinator)
    features_coordinator.features_by_status.return_value = {}

    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: _base_entry_data(
            features_coordinator,
            static_vehicles={"v1": {"supported_features": ["CHARG_NTW_EA"]}},
        )
    }

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert (
        diagnostics["supported_features"]["v1"]["feature_source"] == "static_fallback"
    )


@pytest.mark.asyncio
async def test_feature_source_is_none_when_neither_source_has_anything(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: _base_entry_data(
            features_coordinator=None, static_vehicles={"v1": {}}
        )
    }

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert diagnostics["supported_features"]["v1"] == {
        "feature_source": "none",
        "features_available": [],
        "features_by_status": {},
    }


@pytest.mark.asyncio
async def test_missing_top_level_vehicle_key_does_not_crash(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Diagnostics must never crash the download: an entry_data dict
    lacking the top-level ATTR_VEHICLE key entirely (e.g. an older test
    fixture, or a config entry set up before this story shipped) still
    produces a "none" answer rather than a KeyError.
    """
    entry_data = _base_entry_data(features_coordinator=None)
    assert ATTR_VEHICLE not in entry_data
    hass.data[DOMAIN] = {mock_config_entry.entry_id: entry_data}

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert diagnostics["supported_features"]["v1"]["feature_source"] == "none"
