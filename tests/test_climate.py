"""Tests for Rivian climate platform."""

from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from custom_components.rivian.climate import (
    DEFROST_DEFOG,
    RivianClimateEntity,
    async_setup_entry,
)
from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import VehicleCoordinator
from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant


def _climate_entity(
    mock_config_entry: ConfigEntry, vehicle: dict
) -> RivianClimateEntity:
    """Build the online, in-park cabin-climate entity every test here exercises."""
    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator.is_online = MagicMock(return_value=True)
    coordinator.data = {"gearStatus": {"value": "park"}}
    return RivianClimateEntity(
        coordinator=coordinator,
        config_entry=mock_config_entry,
        description=Mock(key="cabin_climate"),
        vehicle=vehicle,
    )


class TestRivianClimateEntity:
    """Test RivianClimateEntity class."""

    async def test_current_temperature(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test current_temperature property."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock _get_value
        entity._get_value = MagicMock(return_value=22.5)

        assert entity.current_temperature == 22.5

    async def test_target_temperature(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test target_temperature property."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock _get_value
        entity._get_value = MagicMock(return_value=20.0)

        assert entity.target_temperature == 20.0

    async def test_hvac_mode_off(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test hvac_mode returns OFF when preconditioning is NONE."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock _get_value
        def mock_get_value(key):
            if key == "defrostDefogStatus":
                return "Off"
            if key == "cabinPreconditioningType":
                return "NONE"
            return None

        entity._get_value = MagicMock(side_effect=mock_get_value)

        assert entity.hvac_mode == HVACMode.OFF

    async def test_hvac_mode_heat_cool(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test hvac_mode returns HEAT_COOL when preconditioning is active."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock _get_value
        def mock_get_value(key):
            if key == "defrostDefogStatus":
                return "Off"
            if key == "cabinPreconditioningType":
                return "SCHEDULED"
            return None

        entity._get_value = MagicMock(side_effect=mock_get_value)

        assert entity.hvac_mode == HVACMode.HEAT_COOL

    async def test_hvac_mode_heat_defrost(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test hvac_mode returns HEAT when defrost/defog is active."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock _get_value
        def mock_get_value(key):
            if key == "defrostDefogStatus":
                return "On"
            return None

        entity._get_value = MagicMock(side_effect=mock_get_value)

        assert entity.hvac_mode == HVACMode.HEAT

    async def test_preset_mode_defrost(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test preset_mode returns DEFROST_DEFOG when active."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock _get_value
        entity._get_value = MagicMock(return_value="On")

        assert entity.preset_mode == DEFROST_DEFOG

    async def test_preset_mode_lo(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test preset_mode returns LO for temperature 0."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock _get_value and target_temperature
        def mock_get_value(key):
            if key == "defrostDefogStatus":
                return "Off"
            if key == "cabinClimateDriverTemperature":
                return 0
            return None

        entity._get_value = MagicMock(side_effect=mock_get_value)

        assert entity.preset_mode == "LO"

    async def test_preset_mode_hi(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test preset_mode returns HI for temperature 63.5."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock _get_value and target_temperature
        def mock_get_value(key):
            if key == "defrostDefogStatus":
                return "Off"
            if key == "cabinClimateDriverTemperature":
                return 63.5
            return None

        entity._get_value = MagicMock(side_effect=mock_get_value)

        assert entity.preset_mode == "HI"

    async def test_supported_features(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test climate entity has correct supported features."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        assert entity.supported_features == (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.PRESET_MODE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )

    async def test_temperature_unit(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test climate entity uses Celsius."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        assert entity.temperature_unit == UnitOfTemperature.CELSIUS

    async def test_async_set_hvac_mode_heat(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test async_set_hvac_mode to HEAT (defrost/defog)."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock _execute_command
        entity._execute_command = AsyncMock()

        await entity.async_set_hvac_mode(HVACMode.HEAT)

        # Should call defrost/defog command
        entity._execute_command.assert_called_once_with(
            command="CABIN_HVAC_DEFROST_DEFOG", params={"level": 1}
        )

    async def test_async_set_hvac_mode_off(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test async_set_hvac_mode to OFF."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock _execute_command
        entity._execute_command = AsyncMock()

        await entity.async_set_hvac_mode(HVACMode.OFF)

        # Should call disable precondition command
        entity._execute_command.assert_called_once_with(
            command="VEHICLE_CABIN_PRECONDITION_DISABLE"
        )

    async def test_async_set_hvac_mode_heat_cool(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test async_set_hvac_mode to HEAT_COOL."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock _execute_command
        entity._execute_command = AsyncMock()

        await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)

        # Should call enable precondition command
        entity._execute_command.assert_called_once_with(
            command="VEHICLE_CABIN_PRECONDITION_ENABLE"
        )

    async def test_async_set_preset_mode_defrost(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test async_set_preset_mode to DEFROST_DEFOG."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock _execute_command
        entity._execute_command = AsyncMock()

        await entity.async_set_preset_mode(DEFROST_DEFOG)

        # Should call defrost/defog command
        entity._execute_command.assert_called_once_with(
            command="CABIN_HVAC_DEFROST_DEFOG", params={"level": 1}
        )

    async def test_async_set_preset_mode_lo(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test async_set_preset_mode to LO."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock async_set_temperature
        entity.async_set_temperature = AsyncMock()

        await entity.async_set_preset_mode("LO")

        # Should call async_set_temperature with 0
        entity.async_set_temperature.assert_called_once_with(temperature=0)

    async def test_async_set_preset_mode_hi(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test async_set_preset_mode to HI."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock async_set_temperature
        entity.async_set_temperature = AsyncMock()

        await entity.async_set_preset_mode("HI")

        # Should call async_set_temperature with 63.5
        entity.async_set_temperature.assert_called_once_with(temperature=63.5)

    async def test_async_set_temperature_basic(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test async_set_temperature basic case."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock _execute_command and _get_value
        entity._execute_command = AsyncMock()

        # Mock _get_value to return preset_mode=None and hvac_mode=HEAT_COOL
        def mock_get_value(key):
            if key == "defrostDefogStatus":
                return "Off"
            if key == "cabinPreconditioningType":
                return "SCHEDULED"
            return None

        entity._get_value = MagicMock(side_effect=mock_get_value)

        await entity.async_set_temperature(**{ATTR_TEMPERATURE: 22})

        # Should call set temp command
        entity._execute_command.assert_called_once_with(
            command="CABIN_PRECONDITIONING_SET_TEMP", params={"HVAC_set_temp": 22}
        )

    async def test_async_set_temperature_no_temperature(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test async_set_temperature with no temperature parameter."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock _execute_command
        entity._execute_command = AsyncMock()

        await entity.async_set_temperature()

        # Should not call any command
        entity._execute_command.assert_not_called()

    async def test_async_set_temperature_from_defrost(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test async_set_temperature when defrost is active."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock _execute_command and _get_value
        entity._execute_command = AsyncMock()

        # Mock _get_value to return preset_mode=DEFROST_DEFOG and hvac_mode=HEAT_COOL
        def mock_get_value(key):
            if key == "defrostDefogStatus":
                return "On"
            if key == "cabinPreconditioningType":
                return "SCHEDULED"
            return None

        entity._get_value = MagicMock(side_effect=mock_get_value)

        await entity.async_set_temperature(**{ATTR_TEMPERATURE: 22})

        # Should call defrost/defog off, then set temp
        assert entity._execute_command.call_count == 2
        entity._execute_command.assert_any_call(
            command="CABIN_HVAC_DEFROST_DEFOG", params={"level": 0}
        )
        entity._execute_command.assert_any_call(
            command="CABIN_PRECONDITIONING_SET_TEMP", params={"HVAC_set_temp": 22}
        )

    async def test_async_set_temperature_from_off(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_vehicle_paired: dict,
    ) -> None:
        """Test async_set_temperature when HVAC is off."""
        entity = _climate_entity(mock_config_entry, mock_vehicle_paired)

        # Mock _execute_command and _get_value
        entity._execute_command = AsyncMock()

        # Mock _get_value to return preset_mode=None and hvac_mode=OFF
        def mock_get_value(key):
            if key == "defrostDefogStatus":
                return "Off"
            if key == "cabinPreconditioningType":
                return "NONE"
            return None

        entity._get_value = MagicMock(side_effect=mock_get_value)

        await entity.async_set_temperature(**{ATTR_TEMPERATURE: 22})

        # Should call enable precondition, then set temp
        assert entity._execute_command.call_count == 2
        entity._execute_command.assert_any_call(
            command="VEHICLE_CABIN_PRECONDITION_ENABLE"
        )
        entity._execute_command.assert_any_call(
            command="CABIN_PRECONDITIONING_SET_TEMP", params={"HVAC_set_temp": 22}
        )


@pytest.mark.asyncio
async def test_async_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test climate platform setup."""
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

    # Should have created one climate entity
    assert len(entities_added) == 1
    assert isinstance(entities_added[0], RivianClimateEntity)


@pytest.mark.asyncio
async def test_async_setup_entry_no_phone_identity(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test climate platform setup without phone_identity_id (vehicle control not enabled)."""
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

    # Should not have created any climate entities (no vehicle control)
    assert len(entities_added) == 0
