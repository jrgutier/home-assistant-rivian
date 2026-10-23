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

from . import async_create_gen2_pairing_issue, async_delete_gen2_pairing_issue
from .connectivity import ConnectivityState
from .const import ATTR_COORDINATOR, ATTR_USER, ATTR_VEHICLE, DOMAIN
from .coordinator import UserCoordinator, VehicleCoordinator
from .data_classes import RivianButtonEntityDescription
from .entity import RivianVehicleControlEntity, vehicle_control_enabled
from .rivian_client import VehicleCommand, ble as rivian_ble, ble_trace

if TYPE_CHECKING:
    from bleak import BLEDevice
    from home_assistant_bluetooth import BluetoothServiceInfoBleak

_LOGGER = logging.getLogger(__name__)


BUTTONS: Final[dict[str | None, tuple[RivianButtonEntityDescription, ...]]] = {
    None: (
        RivianButtonEntityDescription(
            key="wake",
            translation_key="wake",
            icon="mdi:weather-night",
            available=lambda coordinator: (
                coordinator.connectivity_state() is ConnectivityState.SLEEPING
            ),
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
    data: dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    vehicles: dict[str, dict[str, Any]] = data[ATTR_VEHICLE]
    coordinators: dict[str, VehicleCoordinator] = data[ATTR_COORDINATOR][ATTR_VEHICLE]

    entities = [
        RivianButtonEntity(coordinators[vehicle_id], entry, description, vehicle)
        for vehicle_id, vehicle in vehicles.items()
        if vehicle_control_enabled(vehicle)
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
    entity_description: RivianButtonEntityDescription

    async def async_press(self) -> None:
        await self._run_action(
            self.entity_description.command,
            self.entity_description.command_params,
            self.entity_description.press_fn,
        )


GEN2_MAX_ATTEMPTS = 3


class RivianPairPhoneButtonEntity(RivianVehicleControlEntity, ButtonEntity):
    _pairing: bool = False

    async def async_press(self) -> None:
        if self._pairing:
            raise HomeAssistantError(
                "Either a pairing process is currently under way or pairing is already complete. Please try again later"
            )

        self._pairing = True
        paired = False
        try:
            paired = await self._pair()
        finally:
            self._pairing = paired

    async def _pair(self) -> bool:
        try:
            from homeassistant.components import bluetooth
            from homeassistant.components.bluetooth import BluetoothScanningMode
        except ImportError as err:
            raise HomeAssistantError(
                "Phone pairing needs Home Assistant's bluetooth integration, "
                "which could not be imported."
            ) from err

        entry_data = self.hass.data[DOMAIN][self._config_entry.entry_id]
        vehicle = entry_data[ATTR_VEHICLE][self.coordinator.vehicle_id]
        user: UserCoordinator = entry_data[ATTR_COORDINATOR][ATTR_USER]
        phone_info = user.get_enrolled_phone_data(
            self._config_entry.options.get("public_key")
        )

        rivian_phone_keys = set()
        vas_uuid = str(UUID(vehicle["vas_id"]))

        def _process_more_advertisements(
            service_info: BluetoothServiceInfoBleak,
        ) -> bool:
            if service_info.address in rivian_phone_keys:
                return False
            # Matched in Python, not by HA's matcher: a Gen 2 vehicle has no
            # local name, and a matcher cannot say "this name OR this UUID".
            if not rivian_ble.advertisement_generation(
                service_info.name, service_info.service_uuids, vas_uuid
            ):
                return False
            _LOGGER.debug("Found %s (RSSI: %s)", service_info.device, service_info.rssi)
            rivian_phone_keys.add(service_info.address)
            return True

        async def _find_phone_key() -> tuple[BLEDevice, bool, int | None] | None:
            _LOGGER.debug(
                "Searching for the vehicle (%s or its VAS service UUID)",
                rivian_ble.DEVICE_LOCAL_NAME,
            )
            try:
                service_info = await bluetooth.async_process_advertisements(
                    self.hass,
                    _process_more_advertisements,
                    {"connectable": True},
                    BluetoothScanningMode.ACTIVE,
                    30,
                )
                return (
                    service_info.device,
                    vas_uuid in service_info.service_uuids,
                    rivian_ble.advertisement_generation(
                        service_info.name, service_info.service_uuids, vas_uuid
                    ),
                )
            except (TimeoutError, RuntimeError) as ex:
                _LOGGER.error(
                    "%s not found%s",
                    rivian_ble.DEVICE_LOCAL_NAME,
                    ("" if isinstance(ex, asyncio.TimeoutError) else f": {ex}"),
                )
                return None

        trace = ble_trace.get_trace(self.coordinator.vehicle_id)
        trace.reset()

        while search_result := await _find_phone_key():
            trace.start_attempt()
            if platform.system() == "Linux":
                _LOGGER.debug("Making sure BT controller can be paired")
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
                # Gen 2 is known from the advert, so skip detection's extra
                # connection -- which on BlueZ sees no services and fails.
                force_generation=2 if search_result[2] == 2 else None,
                vehicle_id=self.coordinator.vehicle_id,
            ):
                _LOGGER.debug("Querying API to validate vehicle pairing was successful")
                await asyncio.sleep(10)
                await (coor := self.coordinator.drivers_coordinator).async_refresh()
                if (
                    device := coor.get_device_details(phone_info[1].get(vehicle["id"]))
                ) and device["isPaired"]:
                    _LOGGER.debug("Success, pairing is now complete")
                    async_delete_gen2_pairing_issue(
                        self.hass, self.coordinator.vehicle_id
                    )
                    self._available = False
                    self.async_write_ha_state()
                    return True
                _LOGGER.warning(
                    "Unable to validate pairing was successful. "
                    "If the vehicle shows that your phone key is ready, then vehicle controls will be enabled shortly. "
                    "You may also manually reload the integration to force a refresh. "
                    "Otherwise, you will need to try the pairing process again."
                )
                return False
            # Gen 2 gets a few tries: its private address rotates, and HA can
            # hand back a cached advert from an address the vehicle has dropped.
            if search_result[1] and (
                search_result[2] != 2 or len(trace.attempts) >= GEN2_MAX_ATTEMPTS
            ):
                break

        _LOGGER.debug("Unable to complete pairing")
        if trace.generation == 2:
            async_create_gen2_pairing_issue(self.hass, self.coordinator.vehicle_id)
        return False

    def _handle_driver_update(self) -> None:
        pass
