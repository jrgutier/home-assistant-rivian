"""Tests for Rivian image platform."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from custom_components.rivian.const import (
    ATTR_COORDINATOR,
    ATTR_USER,
    ATTR_VEHICLE,
    CONF_VEHICLE_IMAGE_STYLE,
    DOMAIN,
    IMAGE_STYLE_CEL,
    IMAGE_STYLE_NONE,
    IMAGE_STYLE_PHOTO,
)
from custom_components.rivian.coordinator import (
    UserCoordinator,
    VehicleImageCoordinator,
)
from custom_components.rivian.image import RivianVehicleImageEntity, async_setup_entry
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant


@pytest.mark.asyncio
async def test_async_setup_entry_cel_style(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
    monkeypatch,
) -> None:
    """Test image platform setup with CEL style."""
    user_coordinator = MagicMock(spec=UserCoordinator)
    user_coordinator.api = MagicMock()

    vehicle_data = {
        "vehicle_1": {
            "id": "vehicle_1",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }
    }

    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            ATTR_VEHICLE: vehicle_data,
            ATTR_COORDINATOR: {
                ATTR_USER: user_coordinator,
            },
        }
    }

    # Mock config entry options
    monkeypatch.setattr(
        type(mock_config_entry),
        "options",
        PropertyMock(return_value={CONF_VEHICLE_IMAGE_STYLE: IMAGE_STYLE_CEL}),
        raising=False,
    )

    # Mock VehicleImageCoordinator
    with patch(
        "custom_components.rivian.image.VehicleImageCoordinator"
    ) as mock_coordinator_class:
        mock_coordinator = MagicMock(spec=VehicleImageCoordinator)
        mock_coordinator.hass = hass
        mock_coordinator.data = [
            {
                "vehicleId": "vehicle_1",
                "url": "https://example.com/image_large.png",
                "placement": "front",
                "design": "r1t",
                "size": "large",
            },
            {
                "vehicleId": "vehicle_1",
                "url": "https://example.com/image_small.png",
                "placement": "front",
                "design": "r1t",
                "size": "small",
            },
        ]
        mock_coordinator.async_config_entry_first_refresh = AsyncMock()
        mock_coordinator_class.return_value = mock_coordinator

        entities_added = []

        def mock_add_entities(entities):
            entities_added.extend(entities)

        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should create coordinator with version "3" for CEL style
        mock_coordinator_class.assert_called_once()
        call_kwargs = mock_coordinator_class.call_args[1]
        assert call_kwargs["version"] == "3"

        # Should only create entity for "large" size
        assert len(entities_added) == 1
        assert isinstance(entities_added[0], RivianVehicleImageEntity)


@pytest.mark.asyncio
async def test_async_setup_entry_photo_style(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
    monkeypatch,
) -> None:
    """Test image platform setup with photo style."""
    user_coordinator = MagicMock(spec=UserCoordinator)
    user_coordinator.api = MagicMock()

    vehicle_data = {
        "vehicle_1": {
            "id": "vehicle_1",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }
    }

    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            ATTR_VEHICLE: vehicle_data,
            ATTR_COORDINATOR: {
                ATTR_USER: user_coordinator,
            },
        }
    }

    # Mock config entry options
    monkeypatch.setattr(
        type(mock_config_entry),
        "options",
        PropertyMock(return_value={CONF_VEHICLE_IMAGE_STYLE: IMAGE_STYLE_PHOTO}),
        raising=False,
    )

    # Mock VehicleImageCoordinator
    with patch(
        "custom_components.rivian.image.VehicleImageCoordinator"
    ) as mock_coordinator_class:
        mock_coordinator = MagicMock(spec=VehicleImageCoordinator)
        mock_coordinator.hass = hass
        mock_coordinator.data = [
            {
                "vehicleId": "vehicle_1",
                "url": "https://example.com/image.png",
                "placement": "front",
                "design": "r1t",
                "size": "large",
            }
        ]
        mock_coordinator.async_config_entry_first_refresh = AsyncMock()
        mock_coordinator_class.return_value = mock_coordinator

        entities_added = []

        def mock_add_entities(entities):
            entities_added.extend(entities)

        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should create coordinator with version "2" for photo style
        mock_coordinator_class.assert_called_once()
        call_kwargs = mock_coordinator_class.call_args[1]
        assert call_kwargs["version"] == "2"


@pytest.mark.asyncio
async def test_async_setup_entry_none_style(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
    monkeypatch,
) -> None:
    """Test image platform setup with NONE style (disabled)."""
    user_coordinator = MagicMock(spec=UserCoordinator)
    user_coordinator.api = MagicMock()

    vehicle_data = {
        "vehicle_1": {
            "id": "vehicle_1",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }
    }

    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            ATTR_VEHICLE: vehicle_data,
            ATTR_COORDINATOR: {
                ATTR_USER: user_coordinator,
            },
        }
    }

    # Mock config entry options
    monkeypatch.setattr(
        type(mock_config_entry),
        "options",
        PropertyMock(return_value={CONF_VEHICLE_IMAGE_STYLE: IMAGE_STYLE_NONE}),
        raising=False,
    )

    entities_added = []

    def mock_add_entities(entities):
        entities_added.extend(entities)

    await async_setup_entry(hass, mock_config_entry, mock_add_entities)

    # Should not create any entities when style is NONE
    assert len(entities_added) == 0


class TestRivianVehicleImageEntity:
    """Test RivianVehicleImageEntity class."""

    def test_initialization(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test entity initialization."""
        coordinator = MagicMock(spec=VehicleImageCoordinator)
        coordinator.hass = hass

        data = {
            "url": "https://example.com/image.png",
            "placement": "front",
            "design": "r1t",
            "size": "large",
        }

        entity = RivianVehicleImageEntity(
            coordinator=coordinator,
            vin="TEST123456789",
            data=data,
        )

        assert entity._attr_image_url == "https://example.com/image.png"
        assert entity._attr_name == "Front r1t"
        assert entity._attr_unique_id == "TEST123456789-r1t-front"
        assert entity._attr_content_type == "image/png"
        assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC

    def test_initialization_rear_placement(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test entity initialization with rear placement."""
        coordinator = MagicMock(spec=VehicleImageCoordinator)
        coordinator.hass = hass

        data = {
            "url": "https://example.com/image_rear.png",
            "placement": "rear",
            "design": "r1s",
            "size": "large",
        }

        entity = RivianVehicleImageEntity(
            coordinator=coordinator,
            vin="VIN123456789",
            data=data,
        )

        assert entity._attr_image_url == "https://example.com/image_rear.png"
        assert entity._attr_name == "Rear r1s"
        assert entity._attr_unique_id == "VIN123456789-r1s-rear"

    def test_image_last_updated(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test image_last_updated property."""
        coordinator = MagicMock(spec=VehicleImageCoordinator)
        coordinator.hass = hass
        last_updated = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        coordinator.last_updated = last_updated

        data = {
            "url": "https://example.com/image.png",
            "placement": "front",
            "design": "r1t",
            "size": "large",
        }

        entity = RivianVehicleImageEntity(
            coordinator=coordinator,
            vin="TEST123456789",
            data=data,
        )

        assert entity.image_last_updated == last_updated

    def test_device_info(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test device_info is set correctly."""
        coordinator = MagicMock(spec=VehicleImageCoordinator)
        coordinator.hass = hass

        data = {
            "url": "https://example.com/image.png",
            "placement": "front",
            "design": "r1t",
            "size": "large",
        }

        entity = RivianVehicleImageEntity(
            coordinator=coordinator,
            vin="TEST123456789",
            data=data,
        )

        assert entity._attr_device_info["identifiers"] == {(DOMAIN, "TEST123456789")}
