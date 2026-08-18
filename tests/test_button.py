"""Tests for Rivian button platform."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.button import (
    RivianButtonEntity,
    RivianPairPhoneButtonEntity,
    async_setup_entry,
)
from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import (
    DriverKeyCoordinator,
    VehicleCoordinator,
)
from custom_components.rivian.data_classes import RivianButtonEntityDescription
from custom_components.rivian.rivian_client import VehicleCommand as _RealVehicleCommand
from homeassistant.components.button import ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, HomeAssistantError


@pytest.mark.asyncio
async def test_async_setup_entry_with_control_enabled(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test button platform setup with vehicle control enabled."""
    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator.data = {}

    drivers_coordinator = MagicMock(spec=DriverKeyCoordinator)
    drivers_coordinator.get_device_details = MagicMock(return_value={"isPaired": False})
    vehicle_coordinator.drivers_coordinator = drivers_coordinator

    vehicle_data = {
        "test_vehicle_123": {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
            "supported_features": ["SIDE_BIN_NXT_ACT"],
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

    # Should have wake button + 2 gear tunnel buttons + pair button
    assert len(entities_added) == 4
    assert any(isinstance(e, RivianButtonEntity) for e in entities_added)
    assert any(isinstance(e, RivianPairPhoneButtonEntity) for e in entities_added)


@pytest.mark.asyncio
async def test_async_setup_entry_without_control(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test button platform setup without vehicle control."""
    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator.data = {}

    # Add drivers_coordinator mock for the pair button logic
    drivers_coordinator = MagicMock(spec=DriverKeyCoordinator)
    drivers_coordinator.get_device_details = MagicMock(return_value=None)
    vehicle_coordinator.drivers_coordinator = drivers_coordinator

    vehicle_data = {
        "test_vehicle_123": {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            # No phone_identity_id - control not enabled
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

    # Should have no entities without phone_identity_id
    assert len(entities_added) == 0


@pytest.mark.asyncio
async def test_async_setup_entry_already_paired(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test button platform setup with already paired device."""
    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator.data = {}

    drivers_coordinator = MagicMock(spec=DriverKeyCoordinator)
    drivers_coordinator.get_device_details = MagicMock(
        return_value={"isPaired": True}  # Already paired
    )
    vehicle_coordinator.drivers_coordinator = drivers_coordinator

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

    # Should have wake button but no pair button (already paired)
    assert len(entities_added) == 1
    assert isinstance(entities_added[0], RivianButtonEntity)


class TestRivianButtonEntity:
    """Test RivianButtonEntity class."""

    async def test_async_press_with_command(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test pressing button with command."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.data = {}
        coordinator.send_vehicle_command = AsyncMock()

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = RivianButtonEntityDescription(
            key="wake",
            translation_key="wake",
            command=_RealVehicleCommand.WAKE_VEHICLE,
        )

        entity = RivianButtonEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _execute_command to bypass zone/park checks
        entity._execute_command = AsyncMock()

        await entity.async_press()

        # Should call _execute_command with the command
        entity._execute_command.assert_called_once_with(
            _RealVehicleCommand.WAKE_VEHICLE, None
        )

    async def test_async_press_with_press_fn(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test pressing button with press_fn."""
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

        press_fn = AsyncMock()
        description = RivianButtonEntityDescription(
            key="custom",
            translation_key="custom",
            press_fn=press_fn,
        )

        entity = RivianButtonEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        await entity.async_press()

        # Should call press_fn
        press_fn.assert_called_once_with(coordinator)

    async def test_async_press_with_command_params(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test pressing button with command and parameters."""
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

        command_params = {"param1": "value1"}
        description = RivianButtonEntityDescription(
            key="custom",
            translation_key="custom",
            command=_RealVehicleCommand.WAKE_VEHICLE,
            command_params=command_params,
        )

        entity = RivianButtonEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Mock _execute_command to bypass zone/park checks
        entity._execute_command = AsyncMock()

        await entity.async_press()

        # Should call _execute_command with command and params
        entity._execute_command.assert_called_once_with(
            _RealVehicleCommand.WAKE_VEHICLE, command_params
        )


class TestRivianPairPhoneButtonEntity:
    """Test RivianPairPhoneButtonEntity class."""

    async def test_async_press_pairing_in_progress(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test pressing button when pairing is already in progress."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.vehicle_id = "test_vehicle_123"

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = ButtonEntityDescription(key="pair", translation_key="pair")

        entity = RivianPairPhoneButtonEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Set pairing flag
        entity._pairing = True

        # Should raise error
        with pytest.raises(HomeAssistantError):
            await entity.async_press()

    async def test_handle_driver_update(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test _handle_driver_update does nothing (intentionally blank)."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
            "phone_identity_id": "test_phone_id",
        }

        description = ButtonEntityDescription(key="pair", translation_key="pair")

        entity = RivianPairPhoneButtonEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should not raise any error
        result = entity._handle_driver_update()

        # Should return None (method is intentionally blank)
        assert result is None


class TestPairButtonWithoutBleak:
    """bleak is not part of Home Assistant's Requires-Dist -- it belongs to the
    bluetooth integration -- so it can genuinely be absent.

    The import therefore lives inside the press handler, not at module scope:
    rivian_client.ble re-raises on a missing bleak, which at module scope would
    take down the WHOLE button platform, including this pairing button. Pressing
    it must report the problem instead.
    """

    def _entity(self, hass: HomeAssistant, mock_config_entry: ConfigEntry):
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.vehicle_id = "test_vehicle_123"
        return RivianPairPhoneButtonEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=ButtonEntityDescription(key="pair", translation_key="pair"),
            vehicle={
                "id": "test_vehicle_123",
                "vin": "TEST123456789",
                "name": "Test R1T",
                "model": "R1T",
                "phone_identity_id": "test_phone_id",
            },
        )

    @staticmethod
    def _hide_ble(monkeypatch) -> None:
        """Make `from .rivian_client import ble` raise ImportError.

        Patching sys.modules alone is not enough, and fails ONLY in a full run:
        once any test has imported the submodule, Python binds it as an attribute
        on the package, and `from pkg import name` resolves that attribute without
        ever consulting sys.modules. tests/client/test_ble.py imports it at module
        level, so the attribute has to go too. This was a genuinely
        order-dependent test until it did.
        """
        import sys

        import custom_components.rivian.rivian_client as pkg

        monkeypatch.setitem(
            sys.modules, "custom_components.rivian.rivian_client.ble", None
        )
        if hasattr(pkg, "ble"):
            monkeypatch.delattr(pkg, "ble")

    async def test_press_reports_a_clear_error_when_bleak_is_missing(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry, monkeypatch
    ) -> None:
        entity = self._entity(hass, mock_config_entry)
        self._hide_ble(monkeypatch)
        with pytest.raises(HomeAssistantError, match="Bluetooth support"):
            await entity.async_press()

    async def test_a_failed_import_does_not_wedge_the_button(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry, monkeypatch
    ) -> None:
        """_pairing must be released, or the button stays permanently 'in progress'
        and the user can never retry after installing bleak."""
        entity = self._entity(hass, mock_config_entry)
        self._hide_ble(monkeypatch)
        with pytest.raises(HomeAssistantError):
            await entity.async_press()
        assert entity._pairing is False

    def test_the_platform_imports_bleak_only_for_type_checking(self) -> None:
        """BLEDevice is used in one annotation, so it must live under
        TYPE_CHECKING. A runtime import would take the platform down wherever
        bleak is absent -- including the pairing button needed to fix that."""
        import ast
        import pathlib

        tree = ast.parse(pathlib.Path("custom_components/rivian/button.py").read_text())
        runtime, guarded = [], []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                runtime.append(node)
            elif (
                isinstance(node, ast.If)
                and getattr(node.test, "id", "") == "TYPE_CHECKING"
            ):
                guarded.extend(
                    n for n in node.body if isinstance(n, (ast.Import, ast.ImportFrom))
                )

        def modules(nodes):
            out = set()
            for n in nodes:
                if isinstance(n, ast.ImportFrom) and n.module:
                    out.add(n.module.split(".")[0])
                elif isinstance(n, ast.Import):
                    out.update(a.name.split(".")[0] for a in n.names)
            return out

        assert "bleak" not in modules(runtime), "bleak is imported at runtime"
        assert "bleak" in modules(guarded), (
            "the BLEDevice annotation import went missing"
        )
