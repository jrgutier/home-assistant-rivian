from __future__ import annotations

import asyncio
import logging
import platform
import secrets
from typing import Any

from bleak import BleakClient, BleakScanner, BLEDevice
from bleak.exc import BleakError

from . import ble_trace
from .utils import generate_ble_command_hmac

_LOGGER = logging.getLogger(__name__)

DEVICE_LOCAL_NAME = "Rivian Phone Key"

GEN1_ACTIVE_ENTRY_CHARACTERISTIC_UUID = "5249565F-4D4F-424B-4559-5F5752495445"
GEN1_PHONE_ID_VEHICLE_ID_UUID = "AA49565A-4D4F-424B-4559-5F5752495445"
GEN1_PHONE_NONCE_VEHICLE_NONCE_UUID = "E020A15D-E730-4B2C-908B-51DAF9D41E19"

GEN2_PLAIN_DATA_IN_UUID = "0823DA14-040B-4914-BF7C-450AFA2850DA"
GEN2_PLAIN_DATA_OUT_UUID = "29919A3C-A697-4A6F-BD3B-D14860CC9BCE"
GEN2_ENCRYPTED_DATA_OUT_UUID = "5EAA65C0-57EE-4CF4-A3D5-A4AAE20CBB0B"

CONNECT_TIMEOUT = 10.0
NOTIFICATION_TIMEOUT = 3.0


def advertisement_generation(
    name: str | None, service_uuids: list[str], vas_uuid: str
) -> int | None:
    if name == DEVICE_LOCAL_NAME:
        return 1
    if vas_uuid in service_uuids:
        return 2
    return None


class BleNotificationResponse:
    def __init__(self) -> None:
        self.data: bytearray | None = None
        self.event = asyncio.Event()

    def notification_handler(self, _, notification_data: bytearray) -> None:
        self.data = notification_data
        self.event.set()

    async def wait(self, timeout: float | None = NOTIFICATION_TIMEOUT) -> bool:
        return await asyncio.wait_for(self.event.wait(), timeout)


async def create_notification_handler(
    client: BleakClient, char_specifier: str
) -> BleNotificationResponse:
    response = BleNotificationResponse()
    await client.start_notify(char_specifier, response.notification_handler)
    return response


async def detect_vehicle_generation(
    device: BLEDevice, vehicle_id: str | None = None
) -> int:
    try:
        async with BleakClient(device, timeout=CONNECT_TIMEOUT) as client:
            _LOGGER.debug("Detecting vehicle generation for %s", device)

            services = client.services
            char_uuids = set()
            discovered: list[dict[str, Any]] = []
            for service in services:
                for char in service.characteristics:
                    char_uuids.add(char.uuid.upper())
                    if vehicle_id is not None:
                        discovered.append(
                            {
                                "uuid": char.uuid.upper(),
                                "properties": sorted(char.properties),
                            }
                        )

            if vehicle_id is not None:
                trace = ble_trace.get_trace(vehicle_id)
                trace.record_services(discovered)
                mtu = getattr(client, "mtu_size", None)
                if mtu is not None:
                    trace.record_mtu(mtu)

            _LOGGER.debug("Found %d characteristics", len(char_uuids))

            gen2_chars = {
                GEN2_PLAIN_DATA_IN_UUID.upper(),
                GEN2_ENCRYPTED_DATA_OUT_UUID.upper(),
            }
            if gen2_chars.issubset(char_uuids):
                _LOGGER.info("Detected Gen 2 (PRE_CCC) vehicle")
                return 2

            gen1_chars = {
                GEN1_PHONE_ID_VEHICLE_ID_UUID.upper(),
                GEN1_PHONE_NONCE_VEHICLE_NONCE_UUID.upper(),
            }
            if gen1_chars.issubset(char_uuids):
                _LOGGER.info("Detected Gen 1 (LEGACY) vehicle")
                return 1

            if not char_uuids:
                # A Gen 2 vehicle refuses the Service Changed subscription BlueZ
                # makes on every connection; BlueZ then drops its whole GATT
                # client while still reporting services resolved, so bleak sees
                # an empty device (docs/development/GEN2_BLE_PROTOCOL.md).
                _LOGGER.warning(
                    "The vehicle exposed no GATT services. On a local BlueZ "
                    "adapter this is a known Gen 2 incompatibility; see "
                    "GEN2_BLE_PROTOCOL.md for pairing this key from a Mac"
                )
            else:
                _LOGGER.warning(
                    "Unknown vehicle generation - no matching characteristics"
                )
            return 0

    except Exception as ex:
        _LOGGER.error("Failed to detect vehicle generation: %s", ex)
        raise


async def pair_phone(
    device: BLEDevice,
    phone_id: str,
    vas_vehicle_id: str,
    vehicle_key: str,
    private_key: str,
    force_generation: int | None = None,
    vehicle_id: str | None = None,
) -> bool:
    if force_generation is None:
        try:
            generation = await detect_vehicle_generation(device, vehicle_id=vehicle_id)
        except (BleakError, TimeoutError, OSError):
            return False
        except Exception:
            _LOGGER.exception("Failed to detect vehicle generation")
            return False

        if generation == 0:
            _LOGGER.error(
                "Unknown vehicle generation - cannot determine pairing protocol"
            )
            return False
    else:
        if force_generation not in (1, 2):
            raise ValueError(f"Invalid generation: {force_generation}")
        generation = force_generation
        _LOGGER.info("Forcing vehicle generation %d", generation)

    if generation == 1:
        _LOGGER.info("Using Gen 1 (LEGACY) pairing protocol")
        return await _pair_phone_gen1(
            device, phone_id, vas_vehicle_id, vehicle_key, private_key
        )
    else:
        _LOGGER.info("Using Gen 2 (PRE_CCC) pairing protocol")
        try:
            from .ble_gen2 import pair_phone_gen2
        except ImportError as ex:
            _LOGGER.error("Failed to import Gen 2 BLE module: %s", ex)
            return False

        return await pair_phone_gen2(
            device, phone_id, vas_vehicle_id, vehicle_key, private_key, vehicle_id
        )


async def _pair_phone_gen1(
    device: BLEDevice,
    phone_id: str,
    vas_vehicle_id: str,
    vehicle_key: str,
    private_key: str,
) -> bool:
    _LOGGER.debug("Gen 1: Connecting to %s", device)
    try:
        async with BleakClient(device, timeout=CONNECT_TIMEOUT) as client:
            _LOGGER.debug("Gen 1: Connected to %s", device)
            vehicle_id_handler = await create_notification_handler(
                client, GEN1_PHONE_ID_VEHICLE_ID_UUID
            )
            nonce_handler = await create_notification_handler(
                client, GEN1_PHONE_NONCE_VEHICLE_NONCE_UUID
            )

            _LOGGER.debug("Gen 1: Validating id")
            await client.write_gatt_char(
                GEN1_PHONE_ID_VEHICLE_ID_UUID, bytes.fromhex(phone_id.replace("-", ""))
            )
            await vehicle_id_handler.wait()

            assert vehicle_id_handler.data
            vehicle_id_response = vehicle_id_handler.data.hex()
            if vehicle_id_response != vas_vehicle_id.replace("-", ""):
                _LOGGER.debug(
                    "Incorrect vehicle id: received %s, expected %s",
                    vehicle_id_response,
                    vas_vehicle_id,
                )
                return False

            _LOGGER.debug("Gen 1: Exchanging nonce")
            phone_nonce = secrets.token_bytes(16)
            hmac = generate_ble_command_hmac(phone_nonce, vehicle_key, private_key)
            await client.write_gatt_char(
                GEN1_PHONE_NONCE_VEHICLE_NONCE_UUID, phone_nonce + hmac
            )
            await nonce_handler.wait()

            _LOGGER.debug("Gen 1: Attempting to pair")
            if platform.system() == "Darwin":
                # Mac BLE API doesn't have an explicit way to trigger bonding
                # Instead, enable notification on protected characteristic to trigger bonding manually
                await client.start_notify(
                    GEN1_ACTIVE_ENTRY_CHARACTERISTIC_UUID, lambda _, __: None
                )
            else:
                await client.pair()

            _LOGGER.debug("Gen 1: Successfully paired with %s", device)
            return True
    except (BleakError, TimeoutError, OSError) as ex:
        _LOGGER.debug(
            "Couldn't connect to %s. "
            'Make sure you are in the correct vehicle and have selected "Set Up" for the appropriate key and try again'
            "%s",
            device,
            ("" if isinstance(ex, asyncio.TimeoutError) else f": {ex}"),
        )
    return False


async def find_phone_key() -> BLEDevice | None:
    async with BleakScanner() as scanner:
        return await scanner.find_device_by_name(DEVICE_LOCAL_NAME)


async def set_bluez_pairable(device: BLEDevice) -> bool:
    if (_os := platform.system()) != "Linux":
        raise OSError(f"BlueZ is not available on {_os}-based systems")

    from dbus_fast import BusType
    from dbus_fast.aio import MessageBus
    from dbus_fast.errors import DBusFastError

    try:
        path = device.details["props"]["Adapter"]
    except Exception:
        path = "/org/bluez/hci0"
        _LOGGER.warning(
            "Couldn't determine BT controller path, defaulting to %s: %s",
            path,
            device.details,
            exc_info=True,
        )

    try:
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await bus.introspect("org.bluez", path)
        pobject = bus.get_proxy_object("org.bluez", path, introspection)
        iface = pobject.get_interface("org.bluez.Adapter1")
        if not await iface.get_pairable():  # type: ignore[attr-defined]
            await iface.set_pairable(True)  # type: ignore[attr-defined]
        bus.disconnect()
    except (DBusFastError, OSError, EOFError) as ex:
        _LOGGER.error(ex)
        return False

    return True
