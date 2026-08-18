"""Tests for Rivian diagnostics."""

from unittest.mock import MagicMock

import pytest

from custom_components.rivian.const import (
    ATTR_COORDINATOR,
    ATTR_USER,
    ATTR_VEHICLE,
    ATTR_WALLBOX,
    DOMAIN,
)
from custom_components.rivian.coordinator import (
    ChargingCoordinator,
    DriverKeyCoordinator,
    UserCoordinator,
    VehicleCoordinator,
    WallboxCoordinator,
)
from custom_components.rivian.diagnostics import async_get_config_entry_diagnostics
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


@pytest.mark.asyncio
async def test_async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test async_get_config_entry_diagnostics returns redacted data."""
    # Create mock coordinators
    user_coordinator = MagicMock(spec=UserCoordinator)
    user_coordinator.data = {
        "userId": "user_123",
        "email": "test@example.com",
        "firstName": "Test",
        "lastName": "User",
    }

    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator._unsub_parallax = None
    vehicle_coordinator.data = {
        "vin": "TEST123456789",
        "batteryLevel": {"value": 80},
    }

    charging_coordinator = MagicMock(spec=ChargingCoordinator)
    charging_coordinator.data = {
        "vehicleChargerState": "CHARGING_ACTIVE",
    }

    drivers_coordinator = MagicMock(spec=DriverKeyCoordinator)
    drivers_coordinator.data = {
        "drivers": [],
    }

    vehicle_coordinator.charging_coordinator = charging_coordinator
    vehicle_coordinator.drivers_coordinator = drivers_coordinator

    wallbox_coordinator = MagicMock(spec=WallboxCoordinator)
    wallbox_coordinator.data = {
        "wallboxId": "wallbox_123",
        "power": 11.5,
    }

    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            ATTR_COORDINATOR: {
                ATTR_USER: user_coordinator,
                ATTR_VEHICLE: {"vehicle_1": vehicle_coordinator},
                ATTR_WALLBOX: wallbox_coordinator,
            }
        }
    }

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    # Should have all sections
    assert "user" in diagnostics
    assert "vehicle" in diagnostics
    assert "charging" in diagnostics
    assert "drivers" in diagnostics
    assert "wallbox" in diagnostics

    # Vehicle should be a list
    assert isinstance(diagnostics["vehicle"], list)
    assert len(diagnostics["vehicle"]) == 1

    # Charging should be a list
    assert isinstance(diagnostics["charging"], list)
    assert len(diagnostics["charging"]) == 1

    # Drivers should be a list
    assert isinstance(diagnostics["drivers"], list)
    assert len(diagnostics["drivers"]) == 1


@pytest.mark.asyncio
async def test_async_get_config_entry_diagnostics_multiple_vehicles(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test diagnostics with multiple vehicles."""
    user_coordinator = MagicMock(spec=UserCoordinator)
    user_coordinator.data = {"userId": "user_123"}

    vehicle_coordinator_1 = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator_1._unsub_parallax = None
    vehicle_coordinator_1.data = {"vin": "VIN1"}
    vehicle_coordinator_1.charging_coordinator = MagicMock(spec=ChargingCoordinator)
    vehicle_coordinator_1.charging_coordinator.data = {"state": "charging"}
    vehicle_coordinator_1.drivers_coordinator = MagicMock(spec=DriverKeyCoordinator)
    vehicle_coordinator_1.drivers_coordinator.data = {"drivers": []}

    vehicle_coordinator_2 = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator_2._unsub_parallax = None
    vehicle_coordinator_2.data = {"vin": "VIN2"}
    vehicle_coordinator_2.charging_coordinator = MagicMock(spec=ChargingCoordinator)
    vehicle_coordinator_2.charging_coordinator.data = {"state": "idle"}
    vehicle_coordinator_2.drivers_coordinator = MagicMock(spec=DriverKeyCoordinator)
    vehicle_coordinator_2.drivers_coordinator.data = {"drivers": []}

    wallbox_coordinator = MagicMock(spec=WallboxCoordinator)
    wallbox_coordinator.data = {"wallboxId": "wallbox_123"}

    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            ATTR_COORDINATOR: {
                ATTR_USER: user_coordinator,
                ATTR_VEHICLE: {
                    "vehicle_1": vehicle_coordinator_1,
                    "vehicle_2": vehicle_coordinator_2,
                },
                ATTR_WALLBOX: wallbox_coordinator,
            }
        }
    }

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    # Should have 2 vehicles
    assert len(diagnostics["vehicle"]) == 2
    assert len(diagnostics["charging"]) == 2
    assert len(diagnostics["drivers"]) == 2


class TestTokenRedaction:
    """helpers.py imported the token constants without listing them in TO_REDACT.

    Not a live leak -- diagnostics dumps coordinator data, never entry.data -- but
    the import implied coverage that did not exist, and the payload is exactly the
    thing users attach to bug reports.
    """

    def test_token_fields_are_redacted_wherever_they_appear(self) -> None:
        from custom_components.rivian.const import (
            CONF_ACCESS_TOKEN,
            CONF_REFRESH_TOKEN,
            CONF_USER_SESSION_TOKEN,
        )
        from custom_components.rivian.helpers import redact

        secret = "SHOULD-NEVER-APPEAR-IN-DIAGNOSTICS"
        payload = {
            CONF_ACCESS_TOKEN: secret,
            CONF_REFRESH_TOKEN: secret,
            CONF_USER_SESSION_TOKEN: secret,
            "nested": {CONF_ACCESS_TOKEN: secret},
        }
        assert secret not in str(redact(payload))

    def test_non_sensitive_diagnostic_data_survives(self) -> None:
        from custom_components.rivian.helpers import redact

        assert redact({"chargerState": "charging_active"})["chargerState"] == (
            "charging_active"
        )


class TestParallaxDiagnostics:
    """Parallax feeds the vehicle and charging coordinators, so its DATA is already
    in the dump. What is not otherwise visible is whether the subscription is live
    and which topics it asked for -- and "connected but receiving nothing" is a
    real state, because the gateway allows one subscription per user session."""

    async def test_reports_subscription_state_and_topics(
        self, hass, mock_config_entry
    ) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from rivian.parallax import CHARGING_RVMS, PARALLAX_RVMS

        from custom_components.rivian.const import (
            ATTR_COORDINATOR,
            ATTR_USER,
            ATTR_VEHICLE,
            ATTR_WALLBOX,
            DOMAIN,
        )
        from custom_components.rivian.diagnostics import (
            async_get_config_entry_diagnostics,
        )

        vehicle = MagicMock()
        vehicle.data = {}
        vehicle._unsub_parallax = AsyncMock()
        vehicle.charging_coordinator = MagicMock(data={})
        vehicle.drivers_coordinator = MagicMock(data={})

        hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {
                ATTR_COORDINATOR: {
                    ATTR_USER: MagicMock(data={}),
                    ATTR_VEHICLE: {"v1": vehicle},
                    ATTR_WALLBOX: MagicMock(data={}),
                }
            }
        }
        out = await async_get_config_entry_diagnostics(hass, mock_config_entry)
        px = out["parallax"]["v1"]
        assert px["subscribed"] is True
        # Requested topics must be the deduped union, which is what s06a fixed.
        assert px["rvms_requested"] == sorted({*PARALLAX_RVMS, *CHARGING_RVMS})
        assert len(px["rvms_requested"]) == len(set(px["rvms_requested"]))

    async def test_reports_an_absent_subscription(
        self, hass, mock_config_entry
    ) -> None:
        from unittest.mock import MagicMock

        from custom_components.rivian.const import (
            ATTR_COORDINATOR,
            ATTR_USER,
            ATTR_VEHICLE,
            ATTR_WALLBOX,
            DOMAIN,
        )
        from custom_components.rivian.diagnostics import (
            async_get_config_entry_diagnostics,
        )

        vehicle = MagicMock()
        vehicle.data = {}
        vehicle._unsub_parallax = None
        vehicle.charging_coordinator = MagicMock(data={})
        vehicle.drivers_coordinator = MagicMock(data={})
        hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {
                ATTR_COORDINATOR: {
                    ATTR_USER: MagicMock(data={}),
                    ATTR_VEHICLE: {"v1": vehicle},
                    ATTR_WALLBOX: MagicMock(data={}),
                }
            }
        }
        out = await async_get_config_entry_diagnostics(hass, mock_config_entry)
        assert out["parallax"]["v1"]["subscribed"] is False
