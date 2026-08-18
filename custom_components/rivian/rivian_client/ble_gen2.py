"""Rivian Gen 2 (PRE_CCC) BLE pairing handler.

This module implements the Gen 2 BLE pairing protocol for late 2023+ Rivian vehicles.
Gen 2 uses a 4-state authentication flow with ECDH key derivation and HMAC-SHA256.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
from enum import IntEnum

from cryptography.hazmat.primitives.asymmetric import ec

from .ble_gen2_proto import VASMessage

_LOGGER = logging.getLogger(__name__)

try:
    from bleak import BleakClient, BLEDevice  # type: ignore
except ImportError:
    _LOGGER.error("Please install 'rivian-python-client[ble]' to use BLE features.")
    raise


# Gen 2 (PRE_CCC) BLE Characteristic UUIDs
DEVICE_LOCAL_NAME = "Rivian Phone Key"

# Service UUID (same as Gen 1)
RIVIAN_SERVICE_UUID = "52495356-454E-534F-5253-455256494345"

# Gen 2 Characteristics
PLAIN_DATA_IN_UUID = "0823DA14-040B-4914-BF7C-450AFA2850DA"  # Write unencrypted
PLAIN_DATA_OUT_UUID = "29919A3C-A697-4A6F-BD3B-D14860CC9BCE"  # Read unencrypted
ENCRYPTED_DATA_IN_UUID = "9A69AEFF-E3FE-4E79-BB7D-5AE12272FD14"  # Write encrypted
ENCRYPTED_DATA_OUT_UUID = "5EAA65C0-57EE-4CF4-A3D5-A4AAE20CBB0B"  # Read encrypted

CONNECT_TIMEOUT = 10.0
NOTIFICATION_TIMEOUT = 5.0
AUTH_TIMEOUT = 60.0


class AuthState(IntEnum):
    """Gen 2 authentication state machine.

    Based on EnumC11122B.java from Android app.
    """

    INIT = 0  # Initial state
    PID_PNONCE_SENT = 1  # Phone ID + nonce sent, waiting for vehicle nonce
    SIGNED_PARAMS_SENT = 2  # HMAC signature sent, waiting for auth confirmation
    AUTHENTICATED = 3  # Authentication complete


class BleNotificationResponse:
    """BLE notification response helper for Gen 2."""

    def __init__(self) -> None:
        """Initialize the BLE notification response helper."""
        self.data: bytes | None = None
        self.event = asyncio.Event()

    def notification_handler(self, _, notification_data: bytearray) -> None:
        """Notification handler."""
        self.data = bytes(notification_data)
        self.event.set()

    async def wait(self, timeout: float | None = NOTIFICATION_TIMEOUT) -> bool:
        """Wait for the notification response."""
        try:
            await asyncio.wait_for(self.event.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False


async def create_notification_handler(
    client: BleakClient, char_specifier: str
) -> BleNotificationResponse:
    """Create a notification handler."""
    response = BleNotificationResponse()
    await client.start_notify(char_specifier, response.notification_handler)
    return response


def derive_ecdh_shared_secret(private_key: str, vehicle_public_key: str) -> bytes:
    """Derive ECDH shared secret using P-256 curve.

    Args:
        private_key: Phone's ECDSA private key (PEM format)
        vehicle_public_key: Vehicle's public key (130 hex chars, starts with "04")

    Returns:
        32-byte shared secret for HMAC-SHA256

    Raises:
        ValueError: If keys are invalid

    Based on Android app's ECDH implementation (AbstractC14833a.java:~81)
    """
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    # Validate vehicle public key format
    if len(vehicle_public_key) != 130:
        raise ValueError(
            f"Vehicle public key must be 130 hex chars, got {len(vehicle_public_key)}"
        )
    if not vehicle_public_key.startswith("04"):
        raise ValueError('Vehicle public key must start with "04" (uncompressed point)')

    # Load phone's private key
    private_key_obj = load_pem_private_key(
        private_key.encode(), password=None, backend=default_backend()
    )

    if not isinstance(private_key_obj, ec.EllipticCurvePrivateKey):
        raise ValueError("Private key must be an EC private key")  # noqa: TRY004  # BLE pairing state machine; changing exception semantics here is out of scope for a transport merge

    # Parse vehicle's public key (uncompressed point format: 04 || X || Y)
    vehicle_pub_bytes = bytes.fromhex(vehicle_public_key)

    # Reconstruct EC public key from bytes
    vehicle_pub_key = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), vehicle_pub_bytes
    )

    # Perform ECDH key agreement
    shared_secret = private_key_obj.exchange(ec.ECDH(), vehicle_pub_key)

    # The shared secret is already 32 bytes for P-256
    return shared_secret


def compute_gen2_hmac(
    serialized_protobuf: bytes,
    csn: int,
    phone_id: bytes,
    phone_nonce: bytes,
    vehicle_nonce: bytes,
    shared_secret: bytes,
) -> bytes:
    """Compute Gen 2 HMAC-SHA256 signature.

    Args:
        serialized_protobuf: The protobuf message being signed
        csn: Command Sequence Number
        phone_id: 16-byte phone UUID (big-endian)
        phone_nonce: 16-byte random phone nonce
        vehicle_nonce: Variable-length vehicle nonce
        shared_secret: 32-byte ECDH shared secret

    Returns:
        32-byte HMAC-SHA256 signature

    Based on Android app's HMAC computation (C11162i.java:~1792, C15277l.java:~266)
    """
    # Build HMAC input buffer
    hmac_input = VASMessage.compute_hmac_input(
        serialized_protobuf, csn, phone_id, phone_nonce, vehicle_nonce
    )

    # Compute HMAC-SHA256
    hmac_obj = hmac.new(shared_secret, hmac_input, hashlib.sha256)
    signature = hmac_obj.digest()

    _LOGGER.debug(
        "Gen 2 HMAC computed: input_len=%d, signature=%s",
        len(hmac_input),
        signature.hex()[:32] + "...",
    )

    return signature


async def pair_phone_gen2(
    device: BLEDevice,
    phone_id: str,
    vas_vehicle_id: str,
    vehicle_public_key: str,
    private_key: str,
) -> bool:
    """Pair a phone locally via Gen 2 (PRE_CCC) BLE protocol.

    This implements the 4-state authentication flow:
    1. INIT: Generate phone nonce
    2. PID_PNONCE_SENT: Send phone ID + nonce → receive vehicle nonce
    3. SIGNED_PARAMS_SENT: Compute and send HMAC signature
    4. AUTHENTICATED: Complete authentication

    Args:
        device: BLE device to connect to
        phone_id: Phone UUID from enrollment (format: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        vas_vehicle_id: VAS vehicle ID for validation
        vehicle_public_key: Vehicle's EC public key (130 hex chars)
        private_key: Phone's EC private key (PEM format)

    Returns:
        True if pairing succeeded, False otherwise

    Based on Android app flow (C11162i.java, C11173t.java)
    """
    _LOGGER.debug("Starting Gen 2 (PRE_CCC) pairing with %s", device)

    state = AuthState.INIT
    csn = 1  # Command Sequence Number starts at 1, increments by 2

    try:
        async with BleakClient(device, timeout=CONNECT_TIMEOUT) as client:
            _LOGGER.debug("Connected to %s", device)

            # Set up notification handlers for encrypted responses
            encrypted_out_handler = await create_notification_handler(
                client, ENCRYPTED_DATA_OUT_UUID
            )

            # === Phase 1: Generate and send Phone ID + Phone Nonce ===
            state = AuthState.INIT
            _LOGGER.debug("Phase 1: Generating phone nonce")

            # Generate 16-byte random phone nonce
            phone_nonce = secrets.token_bytes(16)
            _LOGGER.debug("Phone nonce: %s", phone_nonce.hex())

            # Convert phone_id to bytes (UUID format, big-endian)
            phone_id_bytes = bytes.fromhex(phone_id.replace("-", ""))

            # Build Phase 1 protobuf message
            phase1_message = VASMessage.build_phone_id_nonce_message(
                csn, phone_id_bytes, phone_nonce
            )

            # Send via PLAIN_DATA_IN
            _LOGGER.debug("Sending Phone ID + Nonce (%d bytes)", len(phase1_message))
            await client.write_gatt_char(PLAIN_DATA_IN_UUID, phase1_message)
            state = AuthState.PID_PNONCE_SENT
            csn += 2

            # === Phase 2: Receive Vehicle Nonce ===
            _LOGGER.debug("Phase 2: Waiting for vehicle nonce")

            if not await encrypted_out_handler.wait(AUTH_TIMEOUT):
                _LOGGER.error("Timeout waiting for vehicle nonce")
                return False

            assert encrypted_out_handler.data is not None
            vehicle_response = encrypted_out_handler.data

            # Parse vehicle response
            parsed = VASMessage.parse_vehicle_nonce_response(vehicle_response)
            vehicle_nonce = parsed.get("vnonce")

            if vehicle_nonce is None:
                _LOGGER.error("No vehicle nonce in response")
                return False

            _LOGGER.debug("Received vehicle nonce: %s", vehicle_nonce.hex())

            # Validate vehicle ID if present in response (optional check)
            # The full validation logic is complex in Android app, simplified here

            # === Phase 3: Compute HMAC and send SIGNED_PARAMS ===
            _LOGGER.debug("Phase 3: Computing HMAC-SHA256 signature")

            # Derive ECDH shared secret
            try:
                shared_secret = derive_ecdh_shared_secret(
                    private_key, vehicle_public_key
                )
                _LOGGER.debug("ECDH shared secret derived (32 bytes)")
            except Exception as ex:  # noqa: BLE001  # BLE pairing state machine; changing exception semantics here is out of scope for a transport merge
                _LOGGER.error("Failed to derive ECDH shared secret: %s", ex)
                return False

            # Compute HMAC-SHA256
            hmac_signature = compute_gen2_hmac(
                phase1_message,  # Original protobuf message
                csn - 2,  # Use the CSN from phase 1
                phone_id_bytes,
                phone_nonce,
                vehicle_nonce,
                shared_secret,
            )

            # Build Phase 3 protobuf message with signature
            phase3_message = VASMessage.build_signed_params_message(csn, hmac_signature)

            # Reset notification handler for final auth response
            encrypted_out_handler.event.clear()
            encrypted_out_handler.data = None

            # Send SIGNED_PARAMS via PLAIN_DATA_IN
            _LOGGER.debug("Sending SIGNED_PARAMS (%d bytes)", len(phase3_message))
            await client.write_gatt_char(PLAIN_DATA_IN_UUID, phase3_message)
            state = AuthState.SIGNED_PARAMS_SENT
            csn += 2

            # === Phase 4: Wait for authentication confirmation ===
            _LOGGER.debug("Phase 4: Waiting for authentication confirmation")

            if not await encrypted_out_handler.wait(AUTH_TIMEOUT):
                _LOGGER.error("Timeout waiting for authentication confirmation")
                return False

            # Check for successful authentication
            # In the Android app, this checks for SUCCESS status in the response
            assert encrypted_out_handler.data is not None
            auth_response = encrypted_out_handler.data

            # Simple check: non-empty response indicates success
            # More sophisticated parsing could check status codes
            if len(auth_response) > 0:
                state = AuthState.AUTHENTICATED
                _LOGGER.debug("Authentication successful!")
                return True
            else:
                _LOGGER.error("Authentication failed: empty response")
                return False

    except Exception:
        _LOGGER.exception(
            "Gen 2 pairing failed at state %s",
            AuthState(state).name,
        )
        return False
