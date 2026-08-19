"""Support for Rivian button entities."""

from __future__ import annotations

import asyncio
import logging
import platform
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_COORDINATOR, ATTR_USER, ATTR_VEHICLE, DOMAIN
from .coordinator import UserCoordinator, VehicleCoordinator
from .data_classes import RivianButtonEntityDescription
from .entity import RivianVehicleControlEntity
from .rivian_client import VehicleCommand

if TYPE_CHECKING:
    # Annotation-only, all three. None of these ship with Home Assistant core:
    # bleak and home_assistant_bluetooth belong to the bluetooth integration, and
    # homeassistant.components.bluetooth pulls in homeassistant.components.usb,
    # whose aiousbwatcher and serialx are likewise absent from core's metadata.
    # Importing any of them at module scope takes the whole button platform down
    # -- including the wake and pairing buttons -- on a system where the bluetooth
    # integration was never set up. Verified: the artifact load test installs only
    # what manifest.json declares, and this module was the one that failed it.
    from bleak import BLEDevice
    from home_assistant_bluetooth import BluetoothServiceInfoBleak

_LOGGER = logging.getLogger(__name__)


BUTTONS: Final[dict[str | None, tuple[RivianButtonEntityDescription, ...]]] = {
    None: (
        RivianButtonEntityDescription(
            key="wake",
            translation_key="wake",
            icon="mdi:weather-night",
            available=lambda coordinator: coordinator.get("powerState") == "sleep",
            available_offline=True,
            command=VehicleCommand.WAKE_VEHICLE,
        ),
    ),
    "SIDE_BIN_NXT_ACT": (
        RivianButtonEntityDescription(
            key="open_gear_tunnel_left",
            translation_key="open_gear_tunnel_left",
            command=VehicleCommand.RELEASE_LEFT_SIDE_BIN,
        ),
        RivianButtonEntityDescription(
            key="open_gear_tunnel_right",
            translation_key="open_gear_tunnel_right",
            command=VehicleCommand.RELEASE_RIGHT_SIDE_BIN,
        ),
    ),
    "TAILGATE_CMD": (
        RivianButtonEntityDescription(
            key="drop_tailgate",
            translation_key="drop_tailgate",
            available=lambda coordinator: (
                coordinator.get("closureTailgateClosed") != "open"
            ),
            command=VehicleCommand.OPEN_LIFTGATE_UNLATCH_TAILGATE,
        ),
        # The dedicated tailgate command, as opposed to the combined one above
        # which opens the liftgate AND unlatches the tailgate. Both are ordinary
        # generateCloudDataWrapper commands in the app (VASCommand.UnlatchTailgate).
        #
        # Disabled by default because it MOVES A CLOSURE and has not been actuated
        # on the vehicle yet -- f7 does that. Shipping it enabled would put an
        # untested opener one tap away.
        RivianButtonEntityDescription(
            key="open_tailgate",
            translation_key="open_tailgate",
            entity_registry_enabled_default=False,
            available=lambda coordinator: (
                coordinator.get("closureTailgateClosed") != "open"
            ),
            command=VehicleCommand.OPEN_TAILGATE,
        ),
    ),
    "LIFTGATE_CMD": (
        # Same reasoning, and the same default. cover.liftgate already opens the
        # liftgate via the combined command; this is the dedicated one.
        #
        # The gate string stays LIFTGATE_CMD, which is a real VehicleFeature
        # featureName. This R1T structurally cannot report it, and that is NOT
        # evidence the flag is dead -- it is the tonneau inference reversed.
        RivianButtonEntityDescription(
            key="open_liftgate",
            translation_key="open_liftgate",
            entity_registry_enabled_default=False,
            available=lambda coordinator: (
                coordinator.get("closureLiftgateClosed") != "open"
            ),
            command=VehicleCommand.OPEN_LIFTGATE,
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the button entities."""
    data: dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    vehicles: dict[str, dict[str, Any]] = data[ATTR_VEHICLE]
    coordinators: dict[str, VehicleCoordinator] = data[ATTR_COORDINATOR][ATTR_VEHICLE]

    entities = [
        RivianButtonEntity(coordinators[vehicle_id], entry, description, vehicle)
        for vehicle_id, vehicle in vehicles.items()
        if vehicle.get("phone_identity_id")
        for feature, descriptions in BUTTONS.items()
        if feature is None or feature in (vehicle.get("supported_features", []))
        for description in descriptions
    ]
    entities.extend(
        RivianPairPhoneButtonEntity(
            coordinators[vehicle_id],
            entry,
            ButtonEntityDescription(key="pair", translation_key="pair"),
            vehicle,
        )
        for vehicle_id, vehicle in vehicles.items()
        if (
            device := coordinators[vehicle_id].drivers_coordinator.get_device_details(
                vehicle.get("phone_identity_id")
            )
        )
        and not device["isPaired"]
    )
    async_add_entities(entities)


class RivianButtonEntity(RivianVehicleControlEntity, ButtonEntity):
    """Representation of a Rivian button entity."""

    entity_description: RivianButtonEntityDescription

    async def async_press(self) -> None:
        """Press the button."""
        if self.entity_description.command:
            # Use new command state tracking
            await self._execute_command(
                self.entity_description.command,
                self.entity_description.command_params,
            )
        elif self.entity_description.press_fn:
            # Legacy support for press_fn
            await self.entity_description.press_fn(self.coordinator)
        else:
            _LOGGER.error(
                "Button %s has neither command nor press_fn defined", self.entity_id
            )


class RivianPairPhoneButtonEntity(RivianVehicleControlEntity, ButtonEntity):
    """Representation of a Rivian pair phone button entity."""

    _pairing: bool = False

    async def async_press(self) -> None:
        """Press the button."""
        if self._pairing:
            raise HomeAssistantError(
                "Either a pairing process is currently under way or pairing is already complete. Please try again later"
            )

        self._pairing = True

        # Imported here, not at module scope: rivian_client.ble re-raises when
        # bleak is missing, which would otherwise break the import of this whole
        # platform rather than just this one button.
        try:
            from homeassistant.components import bluetooth
            from homeassistant.components.bluetooth import BluetoothScanningMode

            from .rivian_client import ble as rivian_ble
        except ImportError as err:
            self._pairing = False
            raise HomeAssistantError(
                "Bluetooth support is unavailable: neither the 'bleak' library nor "
                "Home Assistant's bluetooth integration could be imported. Phone "
                "pairing requires both."
            ) from err

        entry_data = self.hass.data[DOMAIN][self._config_entry.entry_id]
        vehicle = entry_data[ATTR_VEHICLE][self.coordinator.vehicle_id]
        user: UserCoordinator = entry_data[ATTR_COORDINATOR][ATTR_USER]
        phone_info = user.get_enrolled_phone_data(
            self._config_entry.options.get("public_key")
        )

        rivian_phone_keys = set()

        def _process_more_advertisements(
            service_info: BluetoothServiceInfoBleak,
        ) -> bool:
            if service_info.address in rivian_phone_keys:
                return False
            _LOGGER.debug("Found %s (RSSI: %s)", service_info.device, service_info.rssi)
            rivian_phone_keys.add(service_info.address)
            return True

        async def _find_phone_key() -> tuple[BLEDevice, bool] | None:
            _LOGGER.debug("Searching for %s", rivian_ble.DEVICE_LOCAL_NAME)
            try:
                service_info = await bluetooth.async_process_advertisements(
                    self.hass,
                    _process_more_advertisements,
                    {"local_name": rivian_ble.DEVICE_LOCAL_NAME, "connectable": True},
                    BluetoothScanningMode.ACTIVE,
                    30,
                )
                return (
                    service_info.device,
                    str(UUID(vehicle["vas_id"])) in service_info.service_uuids,
                )
            except Exception as ex:  # noqa: BLE001
                _LOGGER.error(
                    "%s not found%s",
                    rivian_ble.DEVICE_LOCAL_NAME,
                    ("" if isinstance(ex, asyncio.TimeoutError) else f": {ex}"),
                )
                return None

        while search_result := await _find_phone_key():
            if platform.system() == "Linux":
                _LOGGER.debug("Making sure BT controller can be paired")
                # TODO: find out how BT proxy presents itself to avoid invalid warnings
                if not await rivian_ble.set_bluez_pairable(search_result[0]):
                    _LOGGER.warning(
                        "Couldn't set BT controller to pairable, phone pairing may fail"
                    )
            if await rivian_ble.pair_phone(
                search_result[0],
                phone_info[0],
                vehicle["vas_id"],
                vehicle["public_key"],
                self._config_entry.options.get("private_key"),
            ):
                _LOGGER.debug("Querying API to validate vehicle pairing was successful")
                await asyncio.sleep(10)
                await (coor := self.coordinator.drivers_coordinator).async_refresh()
                if (
                    device := coor.get_device_details(phone_info[1].get(vehicle["id"]))
                ) and device["isPaired"]:
                    _LOGGER.debug("Success, pairing is now complete")
                    self._available = False
                    self.async_write_ha_state()
                    return
                _LOGGER.warning(
                    "Unable to validate pairing was successful. "
                    "If the vehicle shows that your phone key is ready, then vehicle controls will be enabled shortly. "
                    "You may also manually reload the integration to force a refresh. "
                    "Otherwise, you will need to try the pairing process again."
                )
                self._pairing = False
                return
            if search_result[1]:
                # we found the appropriate key but pairing didn't work, so no need to continue
                break

        _LOGGER.debug("Unable to complete pairing")
        self._pairing = False

    def _handle_driver_update(self) -> None:
        """Handle driver update."""
        # This is purposefully blank to keep from disabling the entity pending BLE pairing
