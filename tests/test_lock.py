"""Tests for Rivian lock platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.const import (
    ATTR_COORDINATOR,
    ATTR_VEHICLE,
    DOMAIN,
    INVALID_SENSOR_STATES,
    LOCK_STATE_ENTITIES,
)
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


# Live 2026-08-19 12:31 CDT on the production R1T. The three LOCK-device-class
# binary sensors already return None for signal_not_available (f0); lock.py
# used to report a confident Locked over the same inputs.
_LIVE_SNA_KEYS = (
    "closureTailgateLocked",
    "closureTonneauLocked",
    "closureSideBinRightLocked",
)


def _production_is_locked(values: dict) -> bool | None:
    from custom_components.rivian.lock import LOCKS

    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator.get = MagicMock(side_effect=values.get)
    (description,) = LOCKS
    return description.is_locked(coordinator)


def _locked_except(**overrides: str) -> dict[str, str]:
    values = {key: "locked" for key in LOCK_STATE_ENTITIES}
    values.update(overrides)
    return values


class TestClosuresIgnoreInvalidMembers:
    """lock.r1t_closures must not become permanently unknown on this truck.

    Shape (b): ignore members in INVALID_SENSOR_STATES, compute over the rest,
    None only if none are valid. (a) "None if any invalid" is permanently
    unknown here -- three members are SNA right now. (c) model-scoping the
    member set does not save it: tailgate and tonneau are genuine R1T
    closures (BINARY_SENSORS "R1" / "R1T"), not R1S-only liftgate.
    """

    @pytest.mark.parametrize("invalid", sorted(INVALID_SENSOR_STATES))
    def test_live_sna_combination_stays_usable(self, invalid: str) -> None:
        values = _locked_except(**dict.fromkeys(_LIVE_SNA_KEYS, invalid))
        assert _production_is_locked(values) is True

    @pytest.mark.parametrize("invalid", sorted(INVALID_SENSOR_STATES))
    def test_an_unlocked_usable_member_wins(self, invalid: str) -> None:
        values = _locked_except(
            **dict.fromkeys(_LIVE_SNA_KEYS, invalid),
            doorFrontLeftLocked="unlocked",
        )
        assert _production_is_locked(values) is False

    @pytest.mark.parametrize("invalid", sorted(INVALID_SENSOR_STATES))
    def test_none_when_every_member_is_invalid(self, invalid: str) -> None:
        values = {key: invalid for key in LOCK_STATE_ENTITIES}
        assert _production_is_locked(values) is None

    def test_model_scoping_would_not_drop_the_live_sna_members(self) -> None:
        """Scoping LOCK_STATE_ENTITIES the way BINARY_SENSORS is removes
        closureLiftgateLocked (R1S-only) and keeps both keys the live
        record holds as SNA."""
        from custom_components.rivian.const import BINARY_SENSORS

        r1_fields = {d.field for d in BINARY_SENSORS["R1"] if isinstance(d.field, str)}
        r1t_fields = {
            d.field for d in BINARY_SENSORS["R1T"] if isinstance(d.field, str)
        }
        assert "closureTailgateLocked" in LOCK_STATE_ENTITIES
        assert "closureTonneauLocked" in LOCK_STATE_ENTITIES
        assert "closureSideBinRightLocked" in LOCK_STATE_ENTITIES
        assert "closureTailgateLocked" in r1_fields
        assert "closureTonneauLocked" in r1t_fields
        assert "closureSideBinRightLocked" in r1t_fields


class TestClosureCoverageAttribute:
    """The aggregate must say how much of the closure set it rests on.

    `_closures_are_locked` ignores invalid members, so `locked` can be reported
    while a member that is genuinely unlocked reads signal_not_available. On the
    production R1T three of ten members read SNA live (2026-08-19 12:31 CDT), so
    a partial reading is the normal case. An automation consuming this entity --
    "Lock at Home" is live on that instance -- cannot otherwise distinguish a
    full reading from a partial one.
    """

    def test_full_coverage_is_not_partial(self) -> None:
        from custom_components.rivian.lock import _closure_coverage

        coordinator = MagicMock()
        coordinator.get = lambda key: "locked"
        usable, total = _closure_coverage(coordinator)
        assert usable == total
        assert usable == len(LOCK_STATE_ENTITIES)

    def test_the_live_sna_combination_is_reported_as_partial(self) -> None:
        from custom_components.rivian.lock import _closure_coverage

        coordinator = MagicMock()
        live = {
            "closureTailgateLocked": "signal_not_available",
            "closureTonneauLocked": "signal_not_available",
            "closureSideBinRightLocked": "signal_not_available",
        }
        coordinator.get = lambda key: live.get(key, "locked")
        usable, total = _closure_coverage(coordinator)
        assert usable == total - 3
        assert usable < total

    @pytest.mark.parametrize("invalid", sorted(INVALID_SENSOR_STATES))
    def test_no_usable_member_reports_zero_coverage(self, invalid: str) -> None:
        from custom_components.rivian.lock import _closure_coverage

        coordinator = MagicMock()
        coordinator.get = lambda key: invalid
        usable, total = _closure_coverage(coordinator)
        assert usable == 0
        assert total == len(LOCK_STATE_ENTITIES)

    def test_coverage_and_is_locked_agree_on_when_state_is_none(self) -> None:
        """Zero coverage is exactly the condition under which is_locked is None."""
        from custom_components.rivian.lock import (
            _closure_coverage,
            _closures_are_locked,
        )

        coordinator = MagicMock()
        coordinator.get = lambda key: "signal_not_available"
        usable, _ = _closure_coverage(coordinator)
        assert usable == 0
        assert _closures_are_locked(coordinator) is None
