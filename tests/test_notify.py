"""Tests for Rivian notify platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.const import ATTR_API, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.notify import (
    RivianNotificationService,
    async_setup_entry,
    async_unload_entry,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


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


def _service(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
    client: MagicMock,
    *,
    vehicle: dict | None = None,
    service_name: str = "test_service",
) -> RivianNotificationService:
    """Build the per-vehicle navigation service under test.

    The vehicle record is read exactly once, by notify.py's debug log, so one
    shared default stands in for the near-identical records these tests used to
    spell out; the name-less case passes its own record.
    """
    return RivianNotificationService(
        hass=hass,
        client=client,
        vehicle_id="test_vehicle_123",
        vehicle=vehicle
        or {"id": "test_vehicle_123", "vin": "TEST123456789", "name": "Test R1T"},
        service_name=service_name,
        config_entry=mock_config_entry,
    )


def _call(data: dict) -> MagicMock:
    """Return a service call carrying `data`."""
    call = MagicMock()
    call.data = data
    return call


class TestRivianNotificationService:
    """Test RivianNotificationService class."""

    async def test_initialization(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test service initialization."""
        mock_client = MagicMock()

        service = _service(
            hass,
            mock_config_entry,
            mock_client,
            service_name="rivian_test_r1t_456789_navigation",
        )

        assert service._vehicle_id == "test_vehicle_123"
        assert service._service_name == "rivian_test_r1t_456789_navigation"
        assert service._client == mock_client

    @pytest.mark.parametrize(
        "message",
        ["123 Main Street, Anytown, CA 12345", "37.7749,-122.4194"],
    )
    async def test_async_send_message_forwards_the_destination(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        message: str,
    ) -> None:
        """Test sending an address or coordinates as navigation destination."""
        mock_client = MagicMock()
        mock_client.send_location_to_vehicle = AsyncMock(
            return_value={"publishResponse": {"result": 0}}
        )

        service = _service(hass, mock_config_entry, mock_client)

        await service.async_send_message(_call({"message": message}))

        # Should have called send_location_to_vehicle
        mock_client.send_location_to_vehicle.assert_called_once_with(
            location_str=message,
            vehicle_id="test_vehicle_123",
        )

    @pytest.mark.parametrize("data", [{"message": ""}, {}])
    async def test_async_send_message_without_a_message(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        data: dict,
    ) -> None:
        """Test handling of an empty message and of a missing message key."""
        mock_client = MagicMock()
        mock_client.send_location_to_vehicle = AsyncMock()

        service = _service(hass, mock_config_entry, mock_client)

        await service.async_send_message(_call(data))

        # Should not call API without a message
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

        service = _service(hass, mock_config_entry, mock_client)

        # Should not raise exception, just log error
        await service.async_send_message(_call({"message": "San Francisco, CA"}))

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

        service = _service(hass, mock_config_entry, mock_client)

        # Should not raise exception, just log error
        await service.async_send_message(_call({"message": "123 Main St"}))

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

        service = _service(
            hass,
            mock_config_entry,
            mock_client,
            vehicle={
                "id": "test_vehicle_123",
                "vin": "TEST123456789",
                "model": "R1T",
                # No name field
            },
        )

        # Should still work without vehicle name
        await service.async_send_message(_call({"message": "123 Main St"}))

        mock_client.send_location_to_vehicle.assert_called_once()
