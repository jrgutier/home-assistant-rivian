"""Tests for Rivian button platform."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.rivian.button import (
    RivianButtonEntity,
    RivianPairPhoneButtonEntity,
    async_setup_entry,
)
from custom_components.rivian.const import (
    ATTR_COORDINATOR,
    ATTR_USER,
    ATTR_VEHICLE,
    DOMAIN,
)
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


class TestPairingSequence:
    """The pairing loop: what happens after the phone key is found.

    Pairing is a prerequisite for every HMAC-signed vehicle command, and its
    failure modes are quiet by nature -- a BLE scan that finds nothing, a pair
    that reports success but never registers server-side. What is pinned here is
    the CONTROL FLOW: when the loop stops, when it retries, and whether the button
    is left usable afterwards.
    """

    def _entity(self, hass: HomeAssistant, mock_config_entry: ConfigEntry):
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.vehicle_id = "v1"
        coordinator.drivers_coordinator = MagicMock()
        coordinator.drivers_coordinator.async_refresh = AsyncMock()
        entity = RivianPairPhoneButtonEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=ButtonEntityDescription(key="pair", translation_key="pair"),
            vehicle={
                "id": "v1",
                "vin": "VIN",
                "name": "R1T",
                "model": "R1T",
                "phone_identity_id": "identity-1",
            },
        )
        entity.hass = hass
        entity.async_write_ha_state = MagicMock()
        user = MagicMock()
        user.get_enrolled_phone_data = MagicMock(
            return_value=("phone-uuid", {"v1": "identity-1"})
        )
        hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {
                ATTR_VEHICLE: {
                    "v1": {
                        "id": "v1",
                        "vas_id": "11111111-2222-3333-4444-555555555555",
                        "public_key": "PUB",
                    }
                },
                ATTR_COORDINATOR: {ATTR_USER: user},
            }
        }
        return entity, coordinator

    async def test_no_phone_key_found_releases_the_button(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """A scan that finds nothing must leave the button pressable; otherwise the
        user can never retry after moving the phone closer."""
        entity, _ = self._entity(hass, mock_config_entry)
        with patch(
            "homeassistant.components.bluetooth.async_process_advertisements",
            AsyncMock(side_effect=TimeoutError),
        ):
            await entity.async_press()
        assert entity._pairing is False

    async def test_a_successful_pair_that_the_api_confirms_disables_the_button(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        entity, coordinator = self._entity(hass, mock_config_entry)
        coordinator.drivers_coordinator.get_device_details = MagicMock(
            return_value={"isPaired": True}
        )
        service_info = MagicMock()
        service_info.address = "AA:BB"
        service_info.device = MagicMock()
        service_info.service_uuids = ["11111111-2222-3333-4444-555555555555"]
        with (
            patch(
                "homeassistant.components.bluetooth.async_process_advertisements",
                AsyncMock(return_value=service_info),
            ),
            patch(
                "custom_components.rivian.rivian_client.ble.pair_phone",
                AsyncMock(return_value=True),
            ),
            patch("asyncio.sleep", AsyncMock()),
        ):
            await entity.async_press()
        # Paired means there is nothing left to do, so the button goes away.
        assert entity._available is False

    async def test_a_pair_the_api_cannot_confirm_leaves_the_button_usable(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """BLE reported success but the server does not show the key. The user must
        be able to try again rather than be stuck with a dead button."""
        entity, coordinator = self._entity(hass, mock_config_entry)
        coordinator.drivers_coordinator.get_device_details = MagicMock(
            return_value={"isPaired": False}
        )
        service_info = MagicMock()
        service_info.address = "AA:BB"
        service_info.device = MagicMock()
        service_info.service_uuids = ["11111111-2222-3333-4444-555555555555"]
        with (
            patch(
                "homeassistant.components.bluetooth.async_process_advertisements",
                AsyncMock(return_value=service_info),
            ),
            patch(
                "custom_components.rivian.rivian_client.ble.pair_phone",
                AsyncMock(return_value=True),
            ),
            patch("asyncio.sleep", AsyncMock()),
        ):
            await entity.async_press()
        assert entity._pairing is False
        assert entity._available is not False

    async def test_the_right_key_failing_to_pair_stops_the_loop(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """When the advertised service UUID matches this vehicle, a failed pair is
        final -- retrying would scan forever against the correct, unwilling key."""
        entity, _ = self._entity(hass, mock_config_entry)
        service_info = MagicMock()
        service_info.address = "AA:BB"
        service_info.device = MagicMock()
        service_info.service_uuids = ["11111111-2222-3333-4444-555555555555"]
        pair = AsyncMock(return_value=False)
        with (
            patch(
                "homeassistant.components.bluetooth.async_process_advertisements",
                AsyncMock(return_value=service_info),
            ),
            patch("custom_components.rivian.rivian_client.ble.pair_phone", pair),
        ):
            await entity.async_press()
        pair.assert_awaited_once()
        assert entity._pairing is False


class TestTheWakeButtonIsUsableWhenAsleep:
    """The one control that must work on a sleeping vehicle.

    RivianVehicleControlEntity.available checks coordinator.is_online() before
    anything else, and a sleeping vehicle is not online -- so every control goes
    unavailable, including wake. From Home Assistant there was no way to wake the
    vehicle: the only command that would have worked was guaranteed to be
    unavailable, and the user has to open the Rivian app instead.

    Confirmed on a real R1T: cloud_connected off, all nineteen controls
    unavailable including button.*_wake, and sending WAKE_VEHICLE over the same
    cloud API succeeded immediately -- so the command works, the gate was simply
    wrong about it.
    """

    def test_the_wake_description_opts_out_of_the_online_gate(self) -> None:
        from custom_components.rivian.button import BUTTONS

        wake = next(d for d in BUTTONS[None] if d.key == "wake")
        assert wake.available_offline is True

    def test_no_other_button_opts_out(self) -> None:
        """The exemption must stay narrow: any other command needs the vehicle
        online, and a control that looks usable but always fails is worse than one
        that is honestly unavailable."""
        from custom_components.rivian.button import BUTTONS

        offline = [
            d.key
            for group in BUTTONS.values()
            for d in group
            if getattr(d, "available_offline", False)
        ]
        assert offline == ["wake"]

    def test_an_offline_coordinator_still_hides_ordinary_controls(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """The gate itself must survive: only the flagged description bypasses it."""
        from custom_components.rivian.entity import RivianVehicleControlEntity

        coordinator = MagicMock()
        coordinator.is_online.return_value = False
        entity = RivianVehicleControlEntity.__new__(RivianVehicleControlEntity)
        entity.coordinator = coordinator
        entity.entity_description = MagicMock(spec=[])  # no available_offline
        entity._config_entry = mock_config_entry
        assert RivianVehicleControlEntity.available.fget(entity) is False
