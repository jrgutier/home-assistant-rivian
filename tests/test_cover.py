"""Tests for Rivian cover platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.cover import RivianCoverEntity, async_setup_entry
from custom_components.rivian.data_classes import RivianCoverEntityDescription
from homeassistant.components.cover import CoverDeviceClass, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


class TestRivianCoverEntity:
    """Test RivianCoverEntity class."""

    async def test_is_closed_true(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_closed returns True when cover is closed."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="closed")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianCoverEntityDescription(
            key="charge_port",
            translation_key="charge_port",
            device_class=CoverDeviceClass.DOOR,
            is_closed=lambda coor: coor.get("chargePortState") != "open",
            command_close="CLOSE_CHARGE_PORT_DOOR",
            command_open="OPEN_CHARGE_PORT_DOOR",
        )

        entity = RivianCoverEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.is_closed is True

    async def test_is_closed_false(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_closed returns False when cover is open."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="open")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianCoverEntityDescription(
            key="charge_port",
            translation_key="charge_port",
            device_class=CoverDeviceClass.DOOR,
            is_closed=lambda coor: coor.get("chargePortState") != "open",
            command_close="CLOSE_CHARGE_PORT_DOOR",
            command_open="OPEN_CHARGE_PORT_DOOR",
        )

        entity = RivianCoverEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.is_closed is False

    async def test_is_closed_with_multiple_windows(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_closed with windows (all must be closed)."""
        coordinator = MagicMock(spec=VehicleCoordinator)

        def mock_get(key):
            # Simulate window states - one is open
            states = {
                "windowFrontLeftClosed": "closed",
                "windowFrontRightClosed": "closed",
                "windowRearLeftClosed": "open",  # One window open
                "windowRearRightClosed": "closed",
            }
            return states.get(key, "closed")

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

        windows = (
            "windowFrontLeftClosed",
            "windowFrontRightClosed",
            "windowRearLeftClosed",
            "windowRearRightClosed",
        )
        description = RivianCoverEntityDescription(
            key="windows",
            translation_key="windows",
            device_class=CoverDeviceClass.WINDOW,
            is_closed=lambda coor: not any(coor.get(key) == "open" for key in windows),
            command_close="CLOSE_ALL_WINDOWS",
            command_open="OPEN_ALL_WINDOWS",
        )

        entity = RivianCoverEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should be open because one window is open
        assert entity.is_closed is False

    async def test_is_opening_with_next_action(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_opening uses next action state."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value=None)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianCoverEntityDescription(
            key="frunk",
            translation_key="frunk",
            device_class=CoverDeviceClass.DOOR,
            is_closed=lambda coor: coor.get("closureFrunkClosed") != "open",
            command_close="CLOSE_FRUNK",
            command_open="OPEN_FRUNK",
        )

        entity = RivianCoverEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Without next action state, should be False
        assert entity.is_opening is False

    async def test_is_closing_with_next_action(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_closing uses next action state."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value=None)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianCoverEntityDescription(
            key="liftgate",
            translation_key="liftgate",
            device_class=CoverDeviceClass.DOOR,
            is_closed=lambda coor: coor.get("closureLiftgateClosed") != "open",
            command_close="CLOSE_LIFTGATE",
            command_open="OPEN_LIFTGATE_UNLATCH_TAILGATE",
        )

        entity = RivianCoverEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Without next action state, should be False
        assert entity.is_closing is False

    async def test_extra_state_attributes_no_next_action(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test extra_state_attributes without next action state."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value=None)
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianCoverEntityDescription(
            key="charge_port",
            translation_key="charge_port",
            device_class=CoverDeviceClass.DOOR,
            is_closed=lambda coor: coor.get("chargePortState") != "open",
            command_close="CLOSE_CHARGE_PORT_DOOR",
            command_open="OPEN_CHARGE_PORT_DOOR",
        )

        entity = RivianCoverEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        attrs = entity.extra_state_attributes
        # Should return base class attributes (empty or with parent class attrs)
        assert isinstance(attrs, dict)

    async def test_supported_features(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test cover has open and close features."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="closed")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianCoverEntityDescription(
            key="charge_port",
            translation_key="charge_port",
            device_class=CoverDeviceClass.DOOR,
            is_closed=lambda coor: coor.get("chargePortState") != "open",
            command_close="CLOSE_CHARGE_PORT_DOOR",
            command_open="OPEN_CHARGE_PORT_DOOR",
        )

        entity = RivianCoverEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.supported_features == (
            CoverEntityFeature.CLOSE | CoverEntityFeature.OPEN
        )

    async def test_async_close_cover_with_command(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_close_cover executes command."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="open")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianCoverEntityDescription(
            key="charge_port",
            translation_key="charge_port",
            device_class=CoverDeviceClass.DOOR,
            is_closed=lambda coor: coor.get("chargePortState") != "open",
            command_close="CLOSE_CHARGE_PORT_DOOR",
            command_open="OPEN_CHARGE_PORT_DOOR",
        )

        entity = RivianCoverEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _execute_command
        entity._execute_command = AsyncMock()

        await entity.async_close_cover()

        # Should call _execute_command with command_close
        entity._execute_command.assert_called_once_with("CLOSE_CHARGE_PORT_DOOR", None)

    async def test_async_open_cover_with_command(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_open_cover executes command."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="closed")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianCoverEntityDescription(
            key="charge_port",
            translation_key="charge_port",
            device_class=CoverDeviceClass.DOOR,
            is_closed=lambda coor: coor.get("chargePortState") != "open",
            command_close="CLOSE_CHARGE_PORT_DOOR",
            command_open="OPEN_CHARGE_PORT_DOOR",
        )

        entity = RivianCoverEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _execute_command
        entity._execute_command = AsyncMock()

        await entity.async_open_cover()

        # Should call _execute_command with command_open
        entity._execute_command.assert_called_once_with("OPEN_CHARGE_PORT_DOOR", None)

    async def test_async_close_cover_with_params(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_close_cover with parameters."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="open")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianCoverEntityDescription(
            key="charge_port",
            translation_key="charge_port",
            device_class=CoverDeviceClass.DOOR,
            is_closed=lambda coor: coor.get("chargePortState") != "open",
            command_close="CLOSE_CHARGE_PORT_DOOR",
            command_close_params={"force": True},
            command_open="OPEN_CHARGE_PORT_DOOR",
        )

        entity = RivianCoverEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _execute_command
        entity._execute_command = AsyncMock()

        await entity.async_close_cover()

        # Should call _execute_command with command and params
        entity._execute_command.assert_called_once_with(
            "CLOSE_CHARGE_PORT_DOOR", {"force": True}
        )

    async def test_async_close_cover_with_legacy_function(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_close_cover with legacy close_cover function."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="open")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        close_fn = AsyncMock()
        description = RivianCoverEntityDescription(
            key="custom",
            translation_key="custom",
            device_class=CoverDeviceClass.DOOR,
            is_closed=lambda coor: False,
            close_cover=close_fn,
        )

        entity = RivianCoverEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        await entity.async_close_cover()

        # Should call close_cover function
        close_fn.assert_called_once_with(coordinator)

    async def test_async_open_cover_with_legacy_function(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test async_open_cover with legacy open_cover function."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="closed")
        coordinator.is_online = MagicMock(return_value=True)
        coordinator.data = {"gearStatus": {"value": "park"}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        open_fn = AsyncMock()
        description = RivianCoverEntityDescription(
            key="custom",
            translation_key="custom",
            device_class=CoverDeviceClass.DOOR,
            is_closed=lambda coor: True,
            open_cover=open_fn,
        )

        entity = RivianCoverEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        await entity.async_open_cover()

        # Should call open_cover function
        open_fn.assert_called_once_with(coordinator)


@pytest.mark.asyncio
async def test_async_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test cover platform setup."""
    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator.data = {}

    vehicle_data = {
        "test_vehicle_123": {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
            "supported_features": [],
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

    # A vehicle advertising NO capability flags still gets the two unconditional
    # covers. frunk is deliberately among them: gating it behind FRUNK_NXT_ACT
    # left vehicles that do not advertise that flag with no frunk control at all.
    assert len(entities_added) == 2
    assert all(isinstance(e, RivianCoverEntity) for e in entities_added)
    assert {e.entity_description.key for e in entities_added} == {"frunk", "windows"}


@pytest.mark.asyncio
async def test_async_setup_entry_with_all_features(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test cover platform setup with all supported features."""
    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    # The tonneau is no longer keyed on a capability flag, and (s19) no longer
    # keyed on field presence either -- closureTonneauClosed is in
    # VEHICLE_STATE_SUBSCRIPTION_FIELDS, the one wire document every vehicle
    # gets, so it is present in `data` regardless of hardware (confirmed on
    # two real R1S fixtures with no tonneau at all -- see
    # tests/test_cover_tonneau_gate.py). The gate is now option_code
    # membership, so it is the VEHICLE dict that has to carry the evidence,
    # not the coordinator. closureTonneauClosed is still supplied here so
    # this test also proves creation does not depend on it.
    vehicle_coordinator.data = {
        "closureTonneauClosed": {"value": "closed", "history": {"closed"}}
    }

    vehicle_data = {
        "test_vehicle_123": {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
            "supported_features": [
                "CHARG_PORT_DOOR_COMMAND",
                "LIFTGATE_CMD",
                "FRUNK_NXT_ACT",
            ],
            "option_codes": ["TON-P01"],
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

    # frunk and windows unconditionally, tonneau because this vehicle has
    # option_codes=["TON-P01"] (NOT because it reports closureTonneauClosed --
    # that's supplied too, precisely to prove it is not what's granting this),
    # plus charge_port and liftgate from the feature flags.
    assert len(entities_added) == 5
    assert {e.entity_description.key for e in entities_added} == {
        "frunk",
        "windows",
        "tonneau",
        "charge_port",
        "liftgate",
    }
    assert all(isinstance(e, RivianCoverEntity) for e in entities_added)


@pytest.mark.asyncio
async def test_async_setup_entry_no_phone_identity(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test cover platform setup without phone_identity_id (vehicle control not enabled)."""
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

    # Should not have created any cover entities (no vehicle control)
    assert len(entities_added) == 0


class TestRivianCoverEntityNextActionEdgeCases:
    """Test RivianCoverEntity next action edge cases."""

    async def test_get_next_action_state_not_in_mapping(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test _get_next_action_state returns None when key not in mapping."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.data = {}
        coordinator.get = MagicMock(return_value="some_value")

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        from custom_components.rivian.data_classes import RivianCoverEntityDescription

        # Create description with key not in NEXT_ACTION_MAPPING
        description = RivianCoverEntityDescription(
            key="unknown_cover",
            translation_key="unknown_cover",
            is_closed=lambda coord: False,
            command_open=None,
        )

        entity = RivianCoverEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should return None when key not in mapping (line 150)
        result = entity._get_next_action_state()
        assert result is None

    async def test_is_closed_with_next_action(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_closed uses next action when available."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.data = {}

        # Mock next action state
        mock_next_action = MagicMock()
        mock_next_action.is_closed = MagicMock(return_value=True)
        coordinator.get = MagicMock(return_value="CLOSED")

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        from custom_components.rivian.data_classes import RivianCoverEntityDescription

        description = RivianCoverEntityDescription(
            key="closureTonneauDoors",
            translation_key="tonneau",
            is_closed=lambda coord: False,  # Fallback should not be used
            command_open=None,
        )

        entity = RivianCoverEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _get_next_action_state to return mock with is_closed
        entity._get_next_action_state = MagicMock(return_value=mock_next_action)

        # Should use next action's is_closed (line 166)
        result = entity.is_closed
        assert result is True
        mock_next_action.is_closed.assert_called_once()

    async def test_is_opening_with_next_action(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_opening uses next action."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.data = {}

        mock_next_action = MagicMock()
        mock_next_action.is_opening = MagicMock(return_value=True)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        from custom_components.rivian.data_classes import RivianCoverEntityDescription

        description = RivianCoverEntityDescription(
            key="closureTonneauDoors",
            translation_key="tonneau",
            is_closed=lambda coord: False,
            command_open=None,
        )

        entity = RivianCoverEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        entity._get_next_action_state = MagicMock(return_value=mock_next_action)

        # Should use next action's is_opening (line 176)
        result = entity.is_opening
        assert result is True

    async def test_is_closing_with_next_action(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test is_closing uses next action."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.data = {}

        mock_next_action = MagicMock()
        mock_next_action.is_closing = MagicMock(return_value=True)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        from custom_components.rivian.data_classes import RivianCoverEntityDescription

        description = RivianCoverEntityDescription(
            key="closureTonneauDoors",
            translation_key="tonneau",
            is_closed=lambda coord: False,
            command_open=None,
        )

        entity = RivianCoverEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        entity._get_next_action_state = MagicMock(return_value=mock_next_action)

        # Should use next action's is_closing (line 184)
        result = entity.is_closing
        assert result is True

    async def test_extra_state_attributes_with_all_flags(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test extra_state_attributes with all condition flags."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.data = {}

        # Mock next action with all possible attributes
        mock_next_action = MagicMock()
        mock_next_action.value = "TEST_STATE"
        mock_next_action.is_faulted = MagicMock(return_value=True)
        mock_next_action.is_obstructed = MagicMock(return_value=True)
        mock_next_action.has_trailer_detected = MagicMock(return_value=True)
        mock_next_action.has_obstacle_detected = MagicMock(return_value=True)
        mock_next_action.needs_calibration = MagicMock(return_value=True)
        mock_next_action.needs_vehicle_angle_confirmation = MagicMock(return_value=True)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        from custom_components.rivian.data_classes import RivianCoverEntityDescription

        description = RivianCoverEntityDescription(
            key="closureTonneauDoors",
            translation_key="tonneau",
            is_closed=lambda coord: False,
            command_open=None,
        )

        entity = RivianCoverEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        entity._get_next_action_state = MagicMock(return_value=mock_next_action)

        # Should include all condition flags (lines 195-226)
        attrs = entity.extra_state_attributes
        assert attrs["next_action"] == "Test State"
        assert attrs["faulted"] is True
        assert attrs["obstructed"] is True
        assert attrs["trailer_detected"] is True
        assert attrs["obstacle_detected"] is True
        assert attrs["needs_calibration"] is True
        assert attrs["vehicle_angle_confirmation_needed"] is True
