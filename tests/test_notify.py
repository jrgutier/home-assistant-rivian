"""Tests for Rivian notify platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.rivian.const import ATTR_API, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.notify import (
    RivianNotificationService,
    async_setup_entry,
    async_unload_entry,
)


@pytest.mark.asyncio
async def test_async_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test notify platform setup."""
    mock_client = MagicMock()
    mock_client.send_location_to_vehicle = AsyncMock()

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
            ATTR_API: mock_client,
            ATTR_VEHICLE: vehicle_data,
        }
    }

    await async_setup_entry(hass, mock_config_entry, lambda entities: None)

    # Service should be registered
    assert hass.services.has_service("notify", "rivian_test_r1t_456789_navigation")


@pytest.mark.asyncio
async def test_async_setup_entry_multiple_vehicles(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test notify platform setup with multiple vehicles."""
    mock_client = MagicMock()

    vehicle_data = {
        "vehicle_1": {
            "id": "vehicle_1",
            "vin": "VIN1234567890",
            "name": "R1T One",
            "model": "R1T",
        },
        "vehicle_2": {
            "id": "vehicle_2",
            "vin": "VIN0987654321",
            "name": "R1S Two",
            "model": "R1S",
        },
    }

    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            ATTR_API: mock_client,
            ATTR_VEHICLE: vehicle_data,
        }
    }

    await async_setup_entry(hass, mock_config_entry, lambda entities: None)

    # Should have registered two notify services
    assert hass.services.has_service("notify", "rivian_r1t_one_567890_navigation")
    assert hass.services.has_service("notify", "rivian_r1s_two_654321_navigation")


@pytest.mark.asyncio
async def test_async_setup_entry_sanitizes_vehicle_name(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test that vehicle names are sanitized for service names."""
    mock_client = MagicMock()

    vehicle_data = {
        "test_vehicle": {
            "id": "test_vehicle",
            "vin": "TEST123456789",
            "name": "My Awesome R1T",  # Has spaces and uppercase
            "model": "R1T",
        }
    }

    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            ATTR_API: mock_client,
            ATTR_VEHICLE: vehicle_data,
        }
    }

    await async_setup_entry(hass, mock_config_entry, lambda entities: None)

    # Service name should be lowercase with underscores
    assert hass.services.has_service(
        "notify", "rivian_my_awesome_r1t_456789_navigation"
    )


@pytest.mark.asyncio
async def test_async_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test notify platform unload."""
    mock_client = MagicMock()

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
            ATTR_API: mock_client,
            ATTR_VEHICLE: vehicle_data,
        }
    }

    # First setup the entry
    await async_setup_entry(hass, mock_config_entry, lambda entities: None)

    # Verify service exists
    assert hass.services.has_service("notify", "rivian_test_r1t_456789_navigation")

    # Now unload
    result = await async_unload_entry(hass, mock_config_entry)

    # Should return True
    assert result is True

    # Service should be removed
    assert not hass.services.has_service("notify", "rivian_test_r1t_456789_navigation")


@pytest.mark.asyncio
async def test_async_unload_entry_no_data(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test notify platform unload when no data exists."""
    hass.data[DOMAIN] = {}

    # Should return True even when no data
    result = await async_unload_entry(hass, mock_config_entry)
    assert result is True


class TestRivianNotificationService:
    """Test RivianNotificationService class."""

    async def test_initialization(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test service initialization."""
        mock_client = MagicMock()
        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        service = RivianNotificationService(
            hass=hass,
            client=mock_client,
            vehicle_id="test_vehicle_123",
            vehicle=vehicle_data,
            service_name="rivian_test_r1t_456789_navigation",
            config_entry=mock_config_entry,
        )

        assert service._vehicle_id == "test_vehicle_123"
        assert service._service_name == "rivian_test_r1t_456789_navigation"
        assert service._client == mock_client

    async def test_async_send_message_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test sending a navigation destination successfully."""
        mock_client = MagicMock()
        mock_client.send_location_to_vehicle = AsyncMock(
            return_value={"publishResponse": {"result": 0}}
        )

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        service = RivianNotificationService(
            hass=hass,
            client=mock_client,
            vehicle_id="test_vehicle_123",
            vehicle=vehicle_data,
            service_name="test_service",
            config_entry=mock_config_entry,
        )

        # Create service call with MagicMock
        call = MagicMock()
        call.data = {"message": "123 Main Street, Anytown, CA 12345"}

        await service.async_send_message(call)

        # Should have called send_location_to_vehicle
        mock_client.send_location_to_vehicle.assert_called_once_with(
            location_str="123 Main Street, Anytown, CA 12345",
            vehicle_id="test_vehicle_123",
        )

    async def test_async_send_message_with_coordinates(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test sending coordinates as navigation destination."""
        mock_client = MagicMock()
        mock_client.send_location_to_vehicle = AsyncMock(
            return_value={"publishResponse": {"result": 0}}
        )

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
        }

        service = RivianNotificationService(
            hass=hass,
            client=mock_client,
            vehicle_id="test_vehicle_123",
            vehicle=vehicle_data,
            service_name="test_service",
            config_entry=mock_config_entry,
        )

        call = MagicMock()
        call.data = {"message": "37.7749,-122.4194"}

        await service.async_send_message(call)

        mock_client.send_location_to_vehicle.assert_called_once_with(
            location_str="37.7749,-122.4194",
            vehicle_id="test_vehicle_123",
        )

    async def test_async_send_message_empty_message(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test handling of empty message."""
        mock_client = MagicMock()
        mock_client.send_location_to_vehicle = AsyncMock()

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
        }

        service = RivianNotificationService(
            hass=hass,
            client=mock_client,
            vehicle_id="test_vehicle_123",
            vehicle=vehicle_data,
            service_name="test_service",
            config_entry=mock_config_entry,
        )

        call = MagicMock()
        call.data = {"message": ""}

        await service.async_send_message(call)

        # Should not call API with empty message
        mock_client.send_location_to_vehicle.assert_not_called()

    async def test_async_send_message_no_message_key(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test handling when message key is missing."""
        mock_client = MagicMock()
        mock_client.send_location_to_vehicle = AsyncMock()

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
        }

        service = RivianNotificationService(
            hass=hass,
            client=mock_client,
            vehicle_id="test_vehicle_123",
            vehicle=vehicle_data,
            service_name="test_service",
            config_entry=mock_config_entry,
        )

        call = MagicMock()
        call.data = {}

        await service.async_send_message(call)

        # Should not call API when message key is missing
        mock_client.send_location_to_vehicle.assert_not_called()

    async def test_async_send_message_api_failure(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test handling of API failure with non-zero result code."""
        mock_client = MagicMock()
        mock_client.send_location_to_vehicle = AsyncMock(
            return_value={"publishResponse": {"result": 1}}  # Non-zero = failure
        )

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
        }

        service = RivianNotificationService(
            hass=hass,
            client=mock_client,
            vehicle_id="test_vehicle_123",
            vehicle=vehicle_data,
            service_name="test_service",
            config_entry=mock_config_entry,
        )

        call = MagicMock()
        call.data = {"message": "San Francisco, CA"}

        # Should not raise exception, just log error
        await service.async_send_message(call)

        # API should still have been called
        mock_client.send_location_to_vehicle.assert_called_once()

    async def test_async_send_message_exception(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test handling of exception during API call."""
        mock_client = MagicMock()
        mock_client.send_location_to_vehicle = AsyncMock(
            side_effect=Exception("API Error")
        )

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
        }

        service = RivianNotificationService(
            hass=hass,
            client=mock_client,
            vehicle_id="test_vehicle_123",
            vehicle=vehicle_data,
            service_name="test_service",
            config_entry=mock_config_entry,
        )

        call = MagicMock()
        call.data = {"message": "123 Main St"}

        # Should not raise exception, just log error
        await service.async_send_message(call)

        # API should have been called
        mock_client.send_location_to_vehicle.assert_called_once()

    async def test_async_send_message_vehicle_without_name(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test sending message when vehicle has no name."""
        mock_client = MagicMock()
        mock_client.send_location_to_vehicle = AsyncMock(
            return_value={"publishResponse": {"result": 0}}
        )

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "model": "R1T",
            # No name field
        }

        service = RivianNotificationService(
            hass=hass,
            client=mock_client,
            vehicle_id="test_vehicle_123",
            vehicle=vehicle_data,
            service_name="test_service",
            config_entry=mock_config_entry,
        )

        call = MagicMock()
        call.data = {"message": "123 Main St"}

        # Should still work without vehicle name
        await service.async_send_message(call)

        mock_client.send_location_to_vehicle.assert_called_once()
