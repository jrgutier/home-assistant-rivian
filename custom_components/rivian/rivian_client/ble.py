"""Rivian BLE handler with Gen 1 and Gen 2 support.

This module provides unified BLE pairing support for both:
- Gen 1 (LEGACY): R1T/R1S early production (2021-2023)
- Gen 2 (PRE_CCC): R1T/R1S late 2023+

The appropriate protocol is automatically detected based on available BLE characteristics.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import secrets

from .utils import generate_ble_command_hmac

_LOGGER = logging.getLogger(__name__)

try:
    from bleak import BleakClient, BleakScanner, BLEDevice  # type: ignore
except ImportError:
    _LOGGER.error("Please install 'rivian-python-client[ble]' to use BLE features.")
    raise


DEVICE_LOCAL_NAME = "Rivian Phone Key"

# Gen 1 (LEGACY) BLE Characteristic UUIDs
GEN1_ACTIVE_ENTRY_CHARACTERISTIC_UUID = "5249565F-4D4F-424B-4559-5F5752495445"
GEN1_PHONE_ID_VEHICLE_ID_UUID = "AA49565A-4D4F-424B-4559-5F5752495445"
GEN1_PHONE_NONCE_VEHICLE_NONCE_UUID = "E020A15D-E730-4B2C-908B-51DAF9D41E19"

# Legacy names for backward compatibility
ACTIVE_ENTRY_CHARACTERISTIC_UUID = GEN1_ACTIVE_ENTRY_CHARACTERISTIC_UUID
PHONE_ID_VEHICLE_ID_UUID = GEN1_PHONE_ID_VEHICLE_ID_UUID
PHONE_NONCE_VEHICLE_NONCE_UUID = GEN1_PHONE_NONCE_VEHICLE_NONCE_UUID

# Gen 2 (PRE_CCC) BLE Characteristic UUIDs
GEN2_PLAIN_DATA_IN_UUID = "0823DA14-040B-4914-BF7C-450AFA2850DA"
GEN2_PLAIN_DATA_OUT_UUID = "29919A3C-A697-4A6F-BD3B-D14860CC9BCE"
GEN2_ENCRYPTED_DATA_IN_UUID = "9A69AEFF-E3FE-4E79-BB7D-5AE12272FD14"
GEN2_ENCRYPTED_DATA_OUT_UUID = "5EAA65C0-57EE-4CF4-A3D5-A4AAE20CBB0B"

CONNECT_TIMEOUT = 10.0
NOTIFICATION_TIMEOUT = 3.0


class BleNotificationResponse:
    """BLE notification response helper."""

    def __init__(self) -> None:
        """Initialize the BLE notification response helper."""
        self.data: bytearray | None = None
        self.event = asyncio.Event()

    def notification_handler(self, _, notification_data: bytearray) -> None:
        """Notification handler."""
        self.data = notification_data
        self.event.set()

    async def wait(self, timeout: float | None = NOTIFICATION_TIMEOUT) -> bool:
        """Wait for the notification response."""
        return await asyncio.wait_for(self.event.wait(), timeout)


async def create_notification_handler(
    client: BleakClient, char_specifier: str
) -> BleNotificationResponse:
    """Create a notification handler."""
    response = BleNotificationResponse()
    await client.start_notify(char_specifier, response.notification_handler)
    return response


async def detect_vehicle_generation(device: BLEDevice) -> int:
    """Detect vehicle generation (1 or 2) based on available BLE characteristics.

    Args:
        device: BLE device to check

    Returns:
        1 for Gen 1 (LEGACY), 2 for Gen 2 (PRE_CCC), 0 if unknown

    Raises:
        Exception: If unable to connect or read characteristics
    """
    try:
        async with BleakClient(device, timeout=CONNECT_TIMEOUT) as client:
            _LOGGER.debug("Detecting vehicle generation for %s", device)

            # Get all available services and characteristics
            services = client.services
            char_uuids = set()
            for service in services:
                for char in service.characteristics:
                    char_uuids.add(char.uuid.upper())

            _LOGGER.debug("Found %d characteristics", len(char_uuids))

            # Check for Gen 2 characteristics (PRE_CCC)
            gen2_chars = {
                GEN2_PLAIN_DATA_IN_UUID.upper(),
                GEN2_ENCRYPTED_DATA_OUT_UUID.upper(),
            }
            if gen2_chars.issubset(char_uuids):
                _LOGGER.info("Detected Gen 2 (PRE_CCC) vehicle")
                return 2

            # Check for Gen 1 characteristics (LEGACY)
            gen1_chars = {
                GEN1_PHONE_ID_VEHICLE_ID_UUID.upper(),
                GEN1_PHONE_NONCE_VEHICLE_NONCE_UUID.upper(),
            }
            if gen1_chars.issubset(char_uuids):
                _LOGGER.info("Detected Gen 1 (LEGACY) vehicle")
                return 1

            _LOGGER.warning("Unknown vehicle generation - no matching characteristics")
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
) -> bool:
    """Pair a phone locally via BLE (supports Gen 1 and Gen 2).

    The phone must first be enrolled via `rivian.enroll_phone`.
    This finishes the process to enable cloud and local vehicle control.

    Automatically detects vehicle generation (Gen 1 or Gen 2) and uses
    the appropriate pairing protocol.

    Args:
        device: BLE device to pair with
        phone_id: Phone UUID from enrollment
        vas_vehicle_id: VAS vehicle ID for validation
        vehicle_key: Vehicle public key (for Gen 2) or shared key (for Gen 1)
        private_key: Phone's private key (PEM format)
        force_generation: Force specific generation (1 or 2), or None for auto-detect

    Returns:
        True if pairing succeeded, False otherwise

    Raises:
        ValueError: If force_generation is invalid or vehicle generation unknown
    """
    # Detect vehicle generation if not forced
    if force_generation is None:
        try:
            generation = await detect_vehicle_generation(device)
        except Exception as ex:  # noqa: BLE001  # BLE pairing state machine; changing exception semantics here is out of scope for a transport merge
            _LOGGER.error("Failed to detect vehicle generation: %s", ex)
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

    # Route to appropriate pairing implementation
    if generation == 1:
        _LOGGER.info("Using Gen 1 (LEGACY) pairing protocol")
        return await _pair_phone_gen1(
            device, phone_id, vas_vehicle_id, vehicle_key, private_key
        )
    else:  # generation == 2
        _LOGGER.info("Using Gen 2 (PRE_CCC) pairing protocol")
        # Import Gen 2 module
        try:
            from .ble_gen2 import pair_phone_gen2
        except ImportError as ex:
            _LOGGER.error("Failed to import Gen 2 BLE module: %s", ex)
            return False

        return await pair_phone_gen2(
            device, phone_id, vas_vehicle_id, vehicle_key, private_key
        )


async def _pair_phone_gen1(
    device: BLEDevice,
    phone_id: str,
    vas_vehicle_id: str,
    vehicle_key: str,
    private_key: str,
) -> bool:
    """Pair a phone locally via Gen 1 (LEGACY) BLE protocol.

    This is the original implementation for early production vehicles.

    Args:
        device: BLE device to pair with
        phone_id: Phone UUID from enrollment
        vas_vehicle_id: VAS vehicle ID for validation
        vehicle_key: Shared vehicle key
        private_key: Phone's private key (PEM format)

    Returns:
        True if pairing succeeded, False otherwise
    """
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

            # Vehicle is authenticated, trigger bonding
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
    except Exception as ex:  # pylint: disable=broad-except # noqa: BLE001
        _LOGGER.debug(
            "Couldn't connect to %s. "
            'Make sure you are in the correct vehicle and have selected "Set Up" for the appropriate key and try again'
            "%s",
            device,
            ("" if isinstance(ex, asyncio.TimeoutError) else f": {ex}"),
        )
    return False


async def find_phone_key() -> BLEDevice | None:
    """Find phone key."""
    async with BleakScanner() as scanner:
        return await scanner.find_device_by_name(DEVICE_LOCAL_NAME)


async def set_bluez_pairable(device: BLEDevice) -> bool:
    """Set bluez to pairable on Linux systems."""
    if (_os := platform.system()) != "Linux":
        raise OSError(f"BlueZ is not available on {_os}-based systems")

    # pylint: disable=import-error, import-outside-toplevel
    from dbus_fast import BusType  # type: ignore
    from dbus_fast.aio import MessageBus  # type: ignore

    try:
        path = device.details["props"]["Adapter"]
    except Exception:  # pylint: disable=broad-except
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
    except Exception as ex:  # pylint: disable=broad-except # noqa: BLE001
        _LOGGER.error(ex)
        return False

    return True
