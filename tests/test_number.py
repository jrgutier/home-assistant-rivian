"""Tests for Rivian number platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.data_classes import RivianNumberEntityDescription
from custom_components.rivian.number import (
    RivianChargingScheduleAmperageEntity,
    RivianNumberEntity,
    async_setup_entry,
)
from homeassistant.components.number import NumberDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant


class TestRivianNumberEntity:
    """Test RivianNumberEntity class."""

    async def test_native_value(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test native_value returns field value."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        description = RivianNumberEntityDescription(
            key="battery_limit",
            translation_key="battery_limit",
            device_class=NumberDeviceClass.BATTERY,
            native_min_value=50,
            native_unit_of_measurement=PERCENTAGE,
            field="batteryLimit",
            set_fn=lambda coordinator, value: coordinator.send_vehicle_command(
                command="CHARGING_LIMITS", params={"SOC_limit": int(value)}
            ),
        )

        entity = RivianNumberEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle_paired,
        )

        # Mock _get_value
        entity._get_value = MagicMock(return_value=80)

        assert entity.native_value == 80

    async def test_native_unit_of_measurement(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test native_unit_of_measurement is percentage."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        description = RivianNumberEntityDescription(
            key="battery_limit",
            translation_key="battery_limit",
            device_class=NumberDeviceClass.BATTERY,
            native_min_value=50,
            native_unit_of_measurement=PERCENTAGE,
            field="batteryLimit",
            set_fn=lambda coordinator, value: coordinator.send_vehicle_command(
                command="CHARGING_LIMITS", params={"SOC_limit": int(value)}
            ),
        )

        entity = RivianNumberEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle_paired,
        )

        assert entity.native_unit_of_measurement == PERCENTAGE

    async def test_device_class(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test device_class is BATTERY."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        description = RivianNumberEntityDescription(
            key="battery_limit",
            translation_key="battery_limit",
            device_class=NumberDeviceClass.BATTERY,
            native_min_value=50,
            native_unit_of_measurement=PERCENTAGE,
            field="batteryLimit",
            set_fn=lambda coordinator, value: coordinator.send_vehicle_command(
                command="CHARGING_LIMITS", params={"SOC_limit": int(value)}
            ),
        )

        entity = RivianNumberEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle_paired,
        )

        assert entity.device_class == NumberDeviceClass.BATTERY

    async def test_async_set_native_value(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test async_set_native_value calls set_fn."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}
        coordinator.send_vehicle_command = AsyncMock()

        description = RivianNumberEntityDescription(
            key="battery_limit",
            translation_key="battery_limit",
            device_class=NumberDeviceClass.BATTERY,
            native_min_value=50,
            native_unit_of_measurement=PERCENTAGE,
            field="batteryLimit",
            set_fn=lambda coordinator, value: coordinator.send_vehicle_command(
                command="CHARGING_LIMITS", params={"SOC_limit": int(value)}
            ),
        )

        entity = RivianNumberEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle_paired,
        )

        await entity.async_set_native_value(85)

        # Should call send_vehicle_command with charging limits
        coordinator.send_vehicle_command.assert_called_once_with(
            command="CHARGING_LIMITS", params={"SOC_limit": 85}
        )

    async def test_async_set_native_value_converts_to_int(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test async_set_native_value converts float to int."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}
        coordinator.send_vehicle_command = AsyncMock()

        description = RivianNumberEntityDescription(
            key="battery_limit",
            translation_key="battery_limit",
            device_class=NumberDeviceClass.BATTERY,
            native_min_value=50,
            native_unit_of_measurement=PERCENTAGE,
            field="batteryLimit",
            set_fn=lambda coordinator, value: coordinator.send_vehicle_command(
                command="CHARGING_LIMITS", params={"SOC_limit": int(value)}
            ),
        )

        entity = RivianNumberEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle_paired,
        )

        await entity.async_set_native_value(85.7)

        # Should call send_vehicle_command with int value
        coordinator.send_vehicle_command.assert_called_once_with(
            command="CHARGING_LIMITS", params={"SOC_limit": 85}
        )


@pytest.mark.asyncio
async def test_async_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test number platform setup."""
    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator.data = {}

    vehicle_data = {
        "test_vehicle_123": {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
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

    # Should have created 6 number entities (1 NUMBERS + 5 PARALLAX_NUMBERS)
    # - battery_limit
    # - halloween_brightness, cabin_ventilation_windows, cabin_ventilation_sunroof,
    #   cabin_ventilation_duration, passive_entry_distance
    # 1 NUMBER + upstream 1.5.3b5's charging-schedule amperage. The five
    # PARALLAX_NUMBERS were removed in s09a: their RVMs return
    # INTERNAL_SERVER_ERROR, so they never worked.
    assert len(entities_added) == 2
    assert isinstance(entities_added[0], RivianNumberEntity)
    assert (
        sum(isinstance(e, RivianChargingScheduleAmperageEntity) for e in entities_added)
        == 1
    )


@pytest.mark.asyncio
async def test_async_setup_entry_no_phone_identity(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test number platform setup without phone_identity_id (vehicle control not enabled)."""
    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator.data = {}

    vehicle_data = {
        "test_vehicle_123": {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            # No phone_identity_id - vehicle control not enabled
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

    # Parallax numbers require pairing; the charging-schedule amperage does not,
    # because it drives a GraphQL mutation rather than a signed vehicle command.
    assert len(entities_added) == 1
    assert isinstance(entities_added[0], RivianChargingScheduleAmperageEntity)


class TestRivianChargingScheduleAmperageEntity:
    """Upstream 1.5.3b5's charging-schedule amperage number."""

    def _entity(self, mock_config_entry, schedule):
        from custom_components.rivian.number import CHARGING_SCHEDULE_AMPERAGE_NUMBER

        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.charging_schedule = schedule
        coordinator.update_charging_schedule_data = AsyncMock()
        vehicle = {"id": "v1", "vin": "V", "name": "R1T", "model": "R1T"}
        return (
            RivianChargingScheduleAmperageEntity(
                coordinator,
                mock_config_entry,
                CHARGING_SCHEDULE_AMPERAGE_NUMBER,
                vehicle,
            ),
            coordinator,
        )

    def test_native_value_reads_the_schedule(self, mock_config_entry) -> None:
        entity, _ = self._entity(mock_config_entry, {"amperage": 32})
        assert entity.native_value == 32

    def test_native_value_falls_back_to_the_default(self, mock_config_entry) -> None:
        # An empty schedule must still render a number rather than going unavailable.
        entity, _ = self._entity(mock_config_entry, {})
        assert entity.native_value == 48

    def test_native_value_is_none_when_explicitly_null(self, mock_config_entry) -> None:
        entity, _ = self._entity(mock_config_entry, {"amperage": None})
        assert entity.native_value is None

    async def test_set_value_writes_an_int(self, mock_config_entry) -> None:
        # HA hands NumberEntity a float; the API expects an int amperage.
        entity, coordinator = self._entity(mock_config_entry, {"amperage": 32})
        await entity.async_set_native_value(24.0)
        coordinator.update_charging_schedule_data.assert_awaited_once_with(
            {"amperage": 24}
        )

    def test_available_tracks_the_coordinator(self, mock_config_entry) -> None:
        entity, _ = self._entity(mock_config_entry, {})
        entity._available = False
        assert entity.available is False
        entity._available = True
        assert entity.available is True
