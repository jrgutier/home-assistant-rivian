"""Tests for Rivian update platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.rivian_client.exceptions import RivianBadRequestError
from custom_components.rivian.update import RivianUpdateEntity, async_setup_entry
from homeassistant.components.update import UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


class TestRivianUpdateEntity:
    """Test RivianUpdateEntity class."""

    async def test_installed_version(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test installed_version property."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        from homeassistant.components.update import UpdateEntityDescription

        description = UpdateEntityDescription(key="software_ota")

        entity = RivianUpdateEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _get_value
        def mock_get_value(key):
            values = {
                "otaCurrentVersion": "2024.03.0",
                "otaAvailableVersion": "2024.03.0",
                "otaCurrentVersionGitHash": "abc123",
                "otaAvailableVersionGitHash": "abc123",
            }
            return values.get(key, "")

        entity._get_value = MagicMock(side_effect=mock_get_value)
        entity._update_version_info()

        # Should not show hash when versions match
        assert entity.installed_version == "2024.03.0"

    async def test_installed_version_with_hash(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test installed_version shows hash when different from latest."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        from homeassistant.components.update import UpdateEntityDescription

        description = UpdateEntityDescription(key="software_ota")

        entity = RivianUpdateEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _get_value
        def mock_get_value(key):
            values = {
                "otaCurrentVersion": "2024.02.0",
                "otaAvailableVersion": "2024.03.0",
                "otaCurrentVersionGitHash": "abc123",
                "otaAvailableVersionGitHash": "def456",
            }
            return values.get(key, "")

        entity._get_value = MagicMock(side_effect=mock_get_value)
        entity._update_version_info()

        # Should show hash when versions differ
        assert entity.installed_version == "2024.02.0 (abc123)"
        assert entity.latest_version == "2024.03.0 (def456)"

    async def test_latest_version_zero(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test latest_version uses current when available is 0.0.0."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        from homeassistant.components.update import UpdateEntityDescription

        description = UpdateEntityDescription(key="software_ota")

        entity = RivianUpdateEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _get_value
        def mock_get_value(key):
            values = {
                "otaCurrentVersion": "2024.03.0",
                "otaAvailableVersion": "0.0.0",
                "otaCurrentVersionGitHash": "abc123",
                "otaAvailableVersionGitHash": "",
            }
            return values.get(key, "")

        entity._get_value = MagicMock(side_effect=mock_get_value)
        entity._update_version_info()

        # Should use current version when available is 0.0.0
        assert entity.latest_version == "2024.03.0"

    async def test_in_progress_false(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test in_progress returns False when not installing."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        from homeassistant.components.update import UpdateEntityDescription

        description = UpdateEntityDescription(key="software_ota")

        entity = RivianUpdateEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _get_value
        entity._get_value = MagicMock(return_value="Ready_To_Install")

        assert entity.in_progress is False

    async def test_in_progress_percentage(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test in_progress returns percentage when installing."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        from homeassistant.components.update import UpdateEntityDescription

        description = UpdateEntityDescription(key="software_ota")

        entity = RivianUpdateEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _get_value
        def mock_get_value(key):
            if key == "otaStatus":
                return "Installing"
            if key == "otaInstallProgress":
                return 45
            return None

        entity._get_value = MagicMock(side_effect=mock_get_value)

        assert entity.in_progress == 45

    async def test_supported_features_without_install(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test supported_features without install capability."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            # No phone_identity_id
        }

        from homeassistant.components.update import UpdateEntityDescription

        description = UpdateEntityDescription(key="software_ota")

        entity = RivianUpdateEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _get_value
        entity._get_value = MagicMock(return_value="Ready_To_Install")

        # Should not have INSTALL feature
        assert entity.supported_features == (
            UpdateEntityFeature.PROGRESS | UpdateEntityFeature.RELEASE_NOTES
        )

    async def test_supported_features_with_install(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test supported_features with install capability."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        from homeassistant.components.update import UpdateEntityDescription

        description = UpdateEntityDescription(key="software_ota")

        entity = RivianUpdateEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _get_value
        entity._get_value = MagicMock(return_value="Ready_To_Install")

        # Should have INSTALL feature
        assert entity.supported_features == (
            UpdateEntityFeature.PROGRESS
            | UpdateEntityFeature.RELEASE_NOTES
            | UpdateEntityFeature.INSTALL
        )

    async def test_async_install_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_install successfully triggers install."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {}
        coordinator.send_vehicle_command = AsyncMock()

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        from homeassistant.components.update import UpdateEntityDescription

        description = UpdateEntityDescription(key="software_ota")

        entity = RivianUpdateEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _get_value
        entity._get_value = MagicMock(return_value="Ready_To_Install")

        await entity.async_install(version=None, backup=False)

        # Should call send_vehicle_command
        coordinator.send_vehicle_command.assert_called_once_with(
            "OTA_INSTALL_NOW_ACKNOWLEDGE"
        )

    async def test_async_install_no_vehicle_control(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_install raises error when vehicle control not enabled."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            # No phone_identity_id
        }

        from homeassistant.components.update import UpdateEntityDescription

        description = UpdateEntityDescription(key="software_ota")

        entity = RivianUpdateEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        with pytest.raises(RivianBadRequestError):
            await entity.async_install(version=None, backup=False)

    async def test_async_install_not_ready(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_install raises error when update not ready."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        from homeassistant.components.update import UpdateEntityDescription

        description = UpdateEntityDescription(key="software_ota")

        entity = RivianUpdateEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _get_value
        entity._get_value = MagicMock(return_value="Installing")

        with pytest.raises(RivianBadRequestError):
            await entity.async_install(version=None, backup=False)

    async def test_async_release_notes_with_details(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_release_notes fetches from API."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {}
        coordinator.vehicle_id = "test_vehicle_123"

        # Mock API response
        mock_response = MagicMock()
        mock_response.json = AsyncMock(
            return_value={
                "data": {
                    "getVehicle": {
                        "availableOTAUpdateDetails": {
                            "url": "https://rivian.software/2024-03-0/"
                        }
                    }
                }
            }
        )
        coordinator.api = MagicMock()
        coordinator.api.get_vehicle_ota_update_details = AsyncMock(
            return_value=mock_response
        )

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        from homeassistant.components.update import UpdateEntityDescription

        description = UpdateEntityDescription(key="software_ota")

        entity = RivianUpdateEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        notes = await entity.async_release_notes()

        assert (
            notes == "[Read release announcement](https://rivian.software/2024-03-0/)"
        )

    async def test_async_release_notes_fallback(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_release_notes falls back to generated URL."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {}
        coordinator.vehicle_id = "test_vehicle_123"

        # Mock API error
        coordinator.api = MagicMock()
        coordinator.api.get_vehicle_ota_update_details = AsyncMock(
            side_effect=KeyError("test")
        )

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        from homeassistant.components.update import UpdateEntityDescription

        description = UpdateEntityDescription(key="software_ota")

        entity = RivianUpdateEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _get_value for version
        def mock_get_value(key):
            values = {
                "otaCurrentVersion": "2024.03.0",
                "otaAvailableVersion": "2024.04.0",
                "otaCurrentVersionGitHash": "abc123",
                "otaAvailableVersionGitHash": "def456",
            }
            return values.get(key, "")

        entity._get_value = MagicMock(side_effect=mock_get_value)
        entity._update_version_info()

        notes = await entity.async_release_notes()

        assert (
            notes == "[Read release announcement](https://rivian.software/2024-04-0/)"
        )


@pytest.mark.asyncio
async def test_async_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test update platform setup."""
    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator.data = {}

    vehicle_data = {
        "test_vehicle_123": {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }
    }

    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            ATTR_VEHICLE: vehicle_data,
            ATTR_COORDINATOR: {
                ATTR_VEHICLE: {"test_vehicle_123": vehicle_coordinator},
            },
        }
    }

    entities_added = []

    def mock_add_entities(entities):
        entities_added.extend(entities)

    await async_setup_entry(hass, mock_config_entry, mock_add_entities)

    # Should have created one update entity
    assert len(entities_added) == 1
    assert isinstance(entities_added[0], RivianUpdateEntity)
