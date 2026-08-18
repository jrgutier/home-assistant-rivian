"""Tests for Rivian lock platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.data_classes import RivianLockEntityDescription
from custom_components.rivian.lock import RivianLockEntity, async_setup_entry
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


class TestRivianLockEntity:
    """Test RivianLockEntity class."""

    async def test_is_locked_true(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_locked returns True when all closures are locked."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        # All closures are locked
        coordinator.get = MagicMock(return_value="locked")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianLockEntityDescription(
            key="closures",
            translation_key="closures",
            is_locked=lambda coordinator: coordinator.get("doorState") == "locked",
            command_lock="LOCK_ALL_CLOSURES_FEEDBACK",
            command_unlock="UNLOCK_ALL_CLOSURES",
        )

        entity = RivianLockEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.is_locked is True

    async def test_is_locked_false(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_locked returns False when any closure is unlocked."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        # At least one closure is unlocked
        coordinator.get = MagicMock(return_value="unlocked")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianLockEntityDescription(
            key="closures",
            translation_key="closures",
            is_locked=lambda coordinator: coordinator.get("doorState") != "unlocked",
            command_lock="LOCK_ALL_CLOSURES_FEEDBACK",
            command_unlock="UNLOCK_ALL_CLOSURES",
        )

        entity = RivianLockEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.is_locked is False

    async def test_is_locked_with_complex_lambda(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_locked with complex lambda checking multiple entities."""
        coordinator = MagicMock(spec=VehicleCoordinator)

        def mock_get(key):
            # Simulate different lock states
            states = {
                "doorFrontLeft": "locked",
                "doorFrontRight": "locked",
                "doorRearLeft": "locked",
                "doorRearRight": "unlocked",  # One door unlocked
            }
            return states.get(key, "locked")

        coordinator.get = MagicMock(side_effect=mock_get)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        lock_entities = [
            "doorFrontLeft",
            "doorFrontRight",
            "doorRearLeft",
            "doorRearRight",
        ]
        description = RivianLockEntityDescription(
            key="closures",
            translation_key="closures",
            is_locked=lambda coordinator: (
                not any(coordinator.get(key) == "unlocked" for key in lock_entities)
            ),
            command_lock="LOCK_ALL_CLOSURES_FEEDBACK",
            command_unlock="UNLOCK_ALL_CLOSURES",
        )

        entity = RivianLockEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should be unlocked because one door is unlocked
        assert entity.is_locked is False

    async def test_async_lock_with_command(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_lock executes command."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="unlocked")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianLockEntityDescription(
            key="closures",
            translation_key="closures",
            is_locked=lambda coordinator: coordinator.get("doorState") == "locked",
            command_lock="LOCK_ALL_CLOSURES_FEEDBACK",
            command_unlock="UNLOCK_ALL_CLOSURES",
        )

        entity = RivianLockEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _execute_command
        entity._execute_command = AsyncMock()

        await entity.async_lock()

        # Should call _execute_command with command_lock
        entity._execute_command.assert_called_once_with(
            "LOCK_ALL_CLOSURES_FEEDBACK", None
        )

    async def test_async_lock_with_params(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_lock executes command with params."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="unlocked")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianLockEntityDescription(
            key="closures",
            translation_key="closures",
            is_locked=lambda coordinator: coordinator.get("doorState") == "locked",
            command_lock="LOCK_ALL_CLOSURES_FEEDBACK",
            command_lock_params={"feedback": True},
            command_unlock="UNLOCK_ALL_CLOSURES",
        )

        entity = RivianLockEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _execute_command
        entity._execute_command = AsyncMock()

        await entity.async_lock()

        # Should call _execute_command with command and params
        entity._execute_command.assert_called_once_with(
            "LOCK_ALL_CLOSURES_FEEDBACK", {"feedback": True}
        )

    async def test_async_unlock_with_command(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_unlock executes command."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="locked")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianLockEntityDescription(
            key="closures",
            translation_key="closures",
            is_locked=lambda coordinator: coordinator.get("doorState") == "locked",
            command_lock="LOCK_ALL_CLOSURES_FEEDBACK",
            command_unlock="UNLOCK_ALL_CLOSURES",
        )

        entity = RivianLockEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _execute_command
        entity._execute_command = AsyncMock()

        await entity.async_unlock()

        # Should call _execute_command with command_unlock
        entity._execute_command.assert_called_once_with("UNLOCK_ALL_CLOSURES", None)

    async def test_async_lock_with_legacy_lock(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_lock with legacy lock function."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="unlocked")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        lock_fn = AsyncMock()
        description = RivianLockEntityDescription(
            key="closures",
            translation_key="closures",
            is_locked=lambda coordinator: False,
            lock=lock_fn,
        )

        entity = RivianLockEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        await entity.async_lock()

        # Should call lock function
        lock_fn.assert_called_once_with(coordinator)

    async def test_async_unlock_with_legacy_unlock(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_unlock with legacy unlock function."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="locked")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        unlock_fn = AsyncMock()
        description = RivianLockEntityDescription(
            key="closures",
            translation_key="closures",
            is_locked=lambda coordinator: True,
            unlock=unlock_fn,
        )

        entity = RivianLockEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        await entity.async_unlock()

        # Should call unlock function
        unlock_fn.assert_called_once_with(coordinator)


@pytest.mark.asyncio
async def test_async_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test lock platform setup."""
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

    # Should have created lock entities (1 defined in LOCKS)
    assert len(entities_added) == 1
    assert all(isinstance(e, RivianLockEntity) for e in entities_added)


@pytest.mark.asyncio
async def test_async_setup_entry_no_phone_identity(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test lock platform setup without phone_identity_id (vehicle control not enabled)."""
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

    # Should not have created any lock entities (no vehicle control)
    assert len(entities_added) == 0


class TestRivianLockEntityErrorPaths:
    """Test RivianLockEntity error paths."""

    async def test_async_lock_no_command_or_function(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_lock with neither command nor function defined."""
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

        # Create description with neither command nor function
        from custom_components.rivian.data_classes import RivianLockEntityDescription

        description = RivianLockEntityDescription(
            key="test_lock",
            translation_key="test_lock",
            is_locked=lambda coord: False,
            # No command_lock or lock function
        )

        entity = RivianLockEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should log error but not raise
        await entity.async_lock()

    async def test_async_unlock_no_command_or_function(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_unlock with neither command nor function defined."""
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

        from custom_components.rivian.data_classes import RivianLockEntityDescription

        description = RivianLockEntityDescription(
            key="test_lock",
            translation_key="test_lock",
            is_locked=lambda coord: False,
            # No command_unlock or unlock function
        )

        entity = RivianLockEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should log error but not raise
        await entity.async_unlock()
