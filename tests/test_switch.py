"""Tests for Rivian switch platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.data_classes import RivianSwitchEntityDescription
from custom_components.rivian.switch import (
    RivianChargingScheduleEnabledEntity,
    RivianParallaxSwitchEntity,
    RivianSwitchEntity,
    async_setup_entry,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


class TestRivianSwitchEntity:
    """Test RivianSwitchEntity class."""

    async def test_is_on_true(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_on returns True when condition is met."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="true")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianSwitchEntityDescription(
            key="alarm",
            translation_key="alarm",
            is_on=lambda coor: coor.get("alarmSoundStatus") == "true",
            command_on="PANIC_ON",
            command_off="PANIC_OFF",
        )

        entity = RivianSwitchEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.is_on is True

    async def test_is_on_false(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_on returns False when condition is not met."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="false")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianSwitchEntityDescription(
            key="alarm",
            translation_key="alarm",
            is_on=lambda coor: coor.get("alarmSoundStatus") == "true",
            command_on="PANIC_ON",
            command_off="PANIC_OFF",
        )

        entity = RivianSwitchEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.is_on is False

    async def test_available_with_custom_lambda(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test available property with custom lambda."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(
            side_effect=lambda key: {
                "remoteChargingAvailable": 1,
                "gearStatus": "park",
            }.get(key)
        )
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianSwitchEntityDescription(
            key="charging_enabled",
            translation_key="charging_enabled",
            is_on=lambda coor: coor.get("chargerState") == "charging_active",
            available=lambda coor: coor.get("remoteChargingAvailable") == 1,
            command_on="START_CHARGING",
            command_off="STOP_CHARGING",
        )

        entity = RivianSwitchEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should be available when lambda returns True
        assert entity.available is True

    async def test_available_false_when_lambda_fails(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test available returns False when custom lambda fails."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(
            side_effect=lambda key: {
                "remoteChargingAvailable": 0,
                "gearStatus": "park",
            }.get(key)
        )
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianSwitchEntityDescription(
            key="charging_enabled",
            translation_key="charging_enabled",
            is_on=lambda coor: coor.get("chargerState") == "charging_active",
            available=lambda coor: coor.get("remoteChargingAvailable") == 1,
            command_on="START_CHARGING",
            command_off="STOP_CHARGING",
        )

        entity = RivianSwitchEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should not be available when lambda returns False
        assert entity.available is False

    async def test_async_turn_on_with_command(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_turn_on executes command."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="false")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianSwitchEntityDescription(
            key="alarm",
            translation_key="alarm",
            is_on=lambda coor: coor.get("alarmSoundStatus") == "true",
            command_on="PANIC_ON",
            command_off="PANIC_OFF",
        )

        entity = RivianSwitchEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _execute_command
        entity._execute_command = AsyncMock()

        await entity.async_turn_on()

        # Should call _execute_command with command_on
        entity._execute_command.assert_called_once_with("PANIC_ON", None)

    async def test_async_turn_on_with_params(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_turn_on executes command with params."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="Off")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianSwitchEntityDescription(
            key="steering_wheel_heat",
            translation_key="steering_wheel_heat",
            is_on=lambda coor: coor.get("steeringWheelHeat") != "Off",
            command_on="CABIN_HVAC_STEERING_HEAT",
            command_on_params={"level": 1},
            command_off="CABIN_HVAC_STEERING_HEAT",
            command_off_params={"level": 0},
        )

        entity = RivianSwitchEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _execute_command
        entity._execute_command = AsyncMock()

        await entity.async_turn_on()

        # Should call _execute_command with command and params
        entity._execute_command.assert_called_once_with(
            "CABIN_HVAC_STEERING_HEAT", {"level": 1}
        )

    async def test_async_turn_off_with_command(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_turn_off executes command."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="true")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianSwitchEntityDescription(
            key="alarm",
            translation_key="alarm",
            is_on=lambda coor: coor.get("alarmSoundStatus") == "true",
            command_on="PANIC_ON",
            command_off="PANIC_OFF",
        )

        entity = RivianSwitchEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _execute_command
        entity._execute_command = AsyncMock()

        await entity.async_turn_off()

        # Should call _execute_command with command_off
        entity._execute_command.assert_called_once_with("PANIC_OFF", None)

    async def test_async_turn_off_with_params(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_turn_off executes command with params."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="High")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianSwitchEntityDescription(
            key="steering_wheel_heat",
            translation_key="steering_wheel_heat",
            is_on=lambda coor: coor.get("steeringWheelHeat") != "Off",
            command_on="CABIN_HVAC_STEERING_HEAT",
            command_on_params={"level": 1},
            command_off="CABIN_HVAC_STEERING_HEAT",
            command_off_params={"level": 0},
        )

        entity = RivianSwitchEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _execute_command
        entity._execute_command = AsyncMock()

        await entity.async_turn_off()

        # Should call _execute_command with command and params
        entity._execute_command.assert_called_once_with(
            "CABIN_HVAC_STEERING_HEAT", {"level": 0}
        )

    async def test_async_turn_on_with_legacy_turn_on(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_turn_on with legacy turn_on function."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="false")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        turn_on_fn = AsyncMock()
        description = RivianSwitchEntityDescription(
            key="test_switch",
            translation_key="test_switch",
            is_on=lambda coor: False,
            turn_on=turn_on_fn,
        )

        entity = RivianSwitchEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        await entity.async_turn_on()

        # Should call turn_on function
        turn_on_fn.assert_called_once_with(coordinator)

    async def test_async_turn_off_with_legacy_turn_off(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_turn_off with legacy turn_off function."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="true")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        turn_off_fn = AsyncMock()
        description = RivianSwitchEntityDescription(
            key="test_switch",
            translation_key="test_switch",
            is_on=lambda coor: True,
            turn_off=turn_off_fn,
        )

        entity = RivianSwitchEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        await entity.async_turn_off()

        # Should call turn_off function
        turn_off_fn.assert_called_once_with(coordinator)


@pytest.mark.asyncio
async def test_async_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test switch platform setup."""
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

    # 5 SWITCHES + 4 PARALLAX_SWITCHES + upstream 1.5.3b5's charging-schedule switch.
    # SWITCHES: alarm, charging_enabled, gear_guard_video, steering_wheel_heat, cabin_climate_hold
    # PARALLAX_SWITCHES: halloween_enabled, cabin_ventilation, gear_guard_video_consent, passive_entry
    assert len(entities_added) == 10
    assert all(
        isinstance(
            e,
            (
                RivianSwitchEntity,
                RivianParallaxSwitchEntity,
                RivianChargingScheduleEnabledEntity,
            ),
        )
        for e in entities_added
    )
    # The charging-schedule switch is what upstream added; name it so this test
    # fails if the merge ever drops it again rather than merely changing a count.
    assert (
        sum(isinstance(e, RivianChargingScheduleEnabledEntity) for e in entities_added)
        == 1
    )


@pytest.mark.asyncio
async def test_async_setup_entry_no_phone_identity(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test switch platform setup without phone_identity_id (vehicle control not enabled)."""
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

    # Command switches all require pairing, so none of them appear. The
    # charging-schedule switch does NOT: it drives a GraphQL mutation rather than
    # an HMAC-signed vehicle command, so it is created without vehicle control.
    assert len(entities_added) == 1
    assert isinstance(entities_added[0], RivianChargingScheduleEnabledEntity)


class TestRivianSwitchEntityErrorPaths:
    """Test RivianSwitchEntity error paths."""

    async def test_async_turn_off_no_command_or_function(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_turn_off with neither command nor function defined."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        from custom_components.rivian.data_classes import RivianSwitchEntityDescription

        description = RivianSwitchEntityDescription(
            key="test_switch",
            translation_key="test_switch",
            is_on=lambda coord: False,
            # No command_off or turn_off function
        )

        entity = RivianSwitchEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should log error but not raise
        await entity.async_turn_off()

    async def test_async_turn_on_no_command_or_function(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_turn_on with neither command nor function defined."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        from custom_components.rivian.data_classes import RivianSwitchEntityDescription

        description = RivianSwitchEntityDescription(
            key="test_switch",
            translation_key="test_switch",
            is_on=lambda coord: False,
            # No command_on or turn_on function
        )

        entity = RivianSwitchEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should log error but not raise
        await entity.async_turn_on()


class TestRivianChargingScheduleEnabledEntity:
    """Upstream 1.5.3b5's charging-schedule switch.

    It is deliberately NOT a vehicle-control entity: it drives a GraphQL mutation
    rather than an HMAC-signed command, so it must work without phone pairing.
    """

    def _entity(self, mock_config_entry, enabled=True):
        from custom_components.rivian.switch import CHARGING_SCHEDULE_ENABLED_SWITCH

        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.charging_schedule = {"enabled": enabled}
        coordinator.update_charging_schedule_data = AsyncMock()
        vehicle = {"id": "v1", "vin": "V", "name": "R1T", "model": "R1T"}
        return (
            RivianChargingScheduleEnabledEntity(
                coordinator,
                mock_config_entry,
                CHARGING_SCHEDULE_ENABLED_SWITCH,
                vehicle,
            ),
            coordinator,
        )

    def test_is_on_reflects_the_schedule(self, mock_config_entry) -> None:
        entity, _ = self._entity(mock_config_entry, enabled=True)
        assert entity.is_on is True
        entity, _ = self._entity(mock_config_entry, enabled=False)
        assert entity.is_on is False

    async def test_turn_on_writes_enabled_true(self, mock_config_entry) -> None:
        entity, coordinator = self._entity(mock_config_entry, enabled=False)
        await entity.async_turn_on()
        coordinator.update_charging_schedule_data.assert_awaited_once_with(
            {"enabled": True}
        )

    async def test_turn_off_writes_enabled_false(self, mock_config_entry) -> None:
        entity, coordinator = self._entity(mock_config_entry, enabled=True)
        await entity.async_turn_off()
        coordinator.update_charging_schedule_data.assert_awaited_once_with(
            {"enabled": False}
        )

    def test_available_tracks_the_coordinator(self, mock_config_entry) -> None:
        entity, _ = self._entity(mock_config_entry)
        entity._available = False
        assert entity.available is False
        entity._available = True
        assert entity.available is True
