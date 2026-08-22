"""Fixtures for Rivian integration tests."""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rivian.const import DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    yield


@pytest.fixture
def mock_config_entry() -> ConfigEntry:
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Rivian",
        data={
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "test_password",
        },
        options={
            "public_key": "test_public_key",
            "private_key": "test_private_key",
        },
        entry_id="test_entry_id",
    )


@pytest.fixture
def mock_rivian_client() -> Generator[MagicMock, None, None]:
    """Return a mocked Rivian client."""
    with patch("custom_components.rivian.coordinator.Rivian") as mock_client:
        client = MagicMock()
        client.subscribe_for_vehicle_updates = AsyncMock()
        client.subscribe_for_tire_pressure_updates = AsyncMock()
        client.subscribe_for_cloud_connection = AsyncMock()
        client.subscribe_for_charging_session = AsyncMock()
        client.subscribe_for_parallax_messages = AsyncMock()
        client.close = AsyncMock()
        mock_client.return_value = client
        yield client


@pytest.fixture
def mock_vehicle_data() -> dict[str, Any]:
    """Return mock vehicle state data."""
    return {
        "powerState": {"value": "go", "timeStamp": "2024-01-01T00:00:00Z"},
        "chargerState": {
            "value": "chg_station_disconnected",
            "timeStamp": "2024-01-01T00:00:00Z",
        },
        "batteryLevel": {"value": 80.5, "timeStamp": "2024-01-01T00:00:00Z"},
    }


@pytest.fixture
def mock_charging_data() -> dict[str, Any]:
    """Return mock charging session data."""
    return {
        "payload": {
            "data": {
                "chargingSession": {
                    "liveData": {
                        "power": 11.0,
                        "rangeAddedThisSession": 50,
                    },
                    "chartData": {
                        "sessionId": "test_session_123",
                    },
                }
            }
        }
    }


@pytest.fixture
def mock_vehicle_update() -> dict[str, Any]:
    """Return mock vehicle update from subscription."""
    return {
        "payload": {
            "data": {
                "vehicleState": {
                    "powerState": {
                        "value": "go",
                        "timeStamp": "2024-01-01T00:00:00Z",
                    },
                    "batteryLevel": {
                        "value": 80.5,
                        "timeStamp": "2024-01-01T00:00:00Z",
                    },
                }
            }
        }
    }


@pytest.fixture
def mock_user_data() -> dict[str, Any]:
    """Return mock user data."""
    return {
        "currentUser": {
            "vehicles": [
                {
                    "id": "test_vehicle_id_123",
                    "name": "Test R1T",
                    "vehicle": {
                        "vin": "TEST123456789",
                        "modelYear": "2024",
                        "vehicleState": {
                            "supportedFeatures": [
                                {"name": "FEATURE_1", "status": "AVAILABLE"}
                            ]
                        },
                    },
                    "vas": {
                        "vasVehicleId": "test_vas_id",
                        "vehiclePublicKey": "test_vehicle_public_key",
                    },
                }
            ],
            "enrolledPhones": [
                {
                    "vas": {
                        "publicKey": "test_public_key",
                        "vasPhoneId": "test_phone_id",
                    },
                    "enrolled": [
                        {
                            "vehicleId": "test_vehicle_id_123",
                            "identityId": "test_identity_id",
                        }
                    ],
                }
            ],
        }
    }


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
    mock_rivian_client: MagicMock,
) -> ConfigEntry:
    """Set up the integration for testing."""
    mock_config_entry.add_to_hass(hass)
    return mock_config_entry


@pytest.fixture
def mock_vehicle_coordinator_with_parallax() -> MagicMock:
    """Return a mocked VehicleCoordinator with Parallax/Halloween support (paired vehicle).

    This fixture creates a mock coordinator where send_parallax_command() uses
    the real implementation pattern: it gets the method from api and calls it
    with vehicle_id plus any additional kwargs.
    """
    coordinator = MagicMock()
    coordinator.vehicle_id = "test_vehicle_id_123"
    coordinator.vehicle_name = "Test R1T"
    coordinator.vin = "TEST123456789"
    coordinator.data = {
        "powerState": {"value": "go", "timeStamp": "2024-01-01T00:00:00Z"},
        "gearStatus": {"value": "park", "timeStamp": "2024-01-01T00:00:00Z"},
    }

    # Mock API with parallax methods
    coordinator.api = MagicMock()
    coordinator.api.set_halloween_settings = AsyncMock(
        return_value={"success": True, "sequenceNumber": 1, "payload": ""}
    )

    # Mock pairing data (vehicle is paired for Parallax controls)
    coordinator.get_pairing_data = MagicMock(
        return_value={
            "vas_id": "test_vas_id",
            "vehicle_public_key": "test_vehicle_public_key",
            "identity_id": "test_identity_id",
        }
    )

    # Mock parallax_coordinator
    coordinator.parallax_coordinator = MagicMock()
    coordinator.parallax_coordinator.get = MagicMock(return_value=None)

    # Implement send_parallax_command to use real pattern (calls API method)
    async def _send_parallax_command(method_name: str, **kwargs):
        method = getattr(coordinator.api, method_name)
        return await method(vehicle_id=coordinator.vehicle_id, **kwargs)

    coordinator.send_parallax_command = _send_parallax_command

    return coordinator


@pytest.fixture
def mock_vehicle_coordinator_without_pairing() -> MagicMock:
    """Return a mocked VehicleCoordinator without pairing (no Parallax support)."""
    coordinator = MagicMock()
    coordinator.vehicle_id = "test_vehicle_id_123"
    coordinator.vehicle_name = "Test R1T"
    coordinator.vin = "TEST123456789"
    coordinator.data = {
        "powerState": {"value": "go", "timeStamp": "2024-01-01T00:00:00Z"},
    }

    # Mock API
    coordinator.api = MagicMock()

    # No pairing data (vehicle is not paired)
    coordinator.get_pairing_data = MagicMock(return_value=None)

    return coordinator
