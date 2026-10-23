"""Rivian Gen 2 (PRE_CCC) BLE phone-key pairing.

The wire protocol is the one documented and verified on a 2026 R1S by
walthowd/rivian-gen2-key-poc (MIT), whose message layouts were confirmed
byte-for-byte against an over-the-air capture of the official Android app. The
message builders and the reply check below are ported from that project's
`protocol.py`.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from enum import IntEnum
import hashlib
import hmac
import logging
import platform
import secrets
import struct
from uuid import UUID

from bleak import BleakClient, BLEDevice
from bleak.exc import BleakError

from . import ble_trace
from .ble import (
    CONNECT_TIMEOUT,
    GEN2_ENCRYPTED_DATA_OUT_UUID as T_UUID,
    GEN2_PLAIN_DATA_IN_UUID as Q_UUID,
    GEN2_PLAIN_DATA_OUT_UUID as R_UUID,
    create_notification_handler,
)
from .proto.vehicle_operation import (
    encode_length_delimited as _f_len,
    encode_varint as _varint,
)
from .utils import get_secret_key

_LOGGER = logging.getLogger(__name__)

REPLY_TIMEOUT = 10.0
# Bonding is a few seconds of SMP, plus however long the platform takes to
# accept it. The PoC allows 45s on macOS, where a user must click Connect.
BOND_TIMEOUT = 45.0

DEFAULT_MODEL = b"home assistant"

HMAC_SHA256 = 1


class AuthState(IntEnum):
    INIT = 0
    AUTH1_SENT = 1
    VEHICLE_VERIFIED = 2
    AUTH2_SENT = 3
    BONDED = 4


def _f_var(field: int, value: int) -> bytes:
    return _varint(field << 3) + _varint(value)


def parse_fields(data: bytes) -> dict[int, list[int | bytes]]:
    fields: dict[int, list[int | bytes]] = {}
    offset = 0

    def varint() -> int:
        nonlocal offset
        value = 0
        for shift in range(0, 70, 7):
            if offset >= len(data):
                raise ValueError("truncated protobuf varint")
            byte = data[offset]
            offset += 1
            if shift == 63 and byte > 1:
                raise ValueError("protobuf varint overflow")
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value
        raise ValueError("protobuf varint overflow")

    while offset < len(data):
        tag = varint()
        field, wire = tag >> 3, tag & 7
        if not 0 < field < (1 << 29):
            raise ValueError("invalid protobuf field number")
        value: int | bytes
        if wire == 0:
            value = varint()
        elif wire in (1, 2, 5):
            length = varint() if wire == 2 else (8 if wire == 1 else 4)
            if offset + length > len(data):
                raise ValueError("truncated protobuf field")
            value = data[offset : offset + length]
            offset += length
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
        fields.setdefault(field, []).append(value)
    return fields


def _one(fields: dict[int, list], field: int, default=None):
    values = fields.get(field, [])
    if len(values) > 1:
        raise ValueError(f"repeated singular field {field}")
    return values[0] if values else default


def _mac(secret_key: bytes, message_list: bytes, seq: int, sender_id: bytes, *nonces):
    data = message_list + struct.pack("<I", seq) + sender_id + b"".join(nonces)
    return hmac.new(secret_key, data, hashlib.sha256).digest()


def _signed(
    message_list: bytes, seq: int, mac: bytes, excludes_vehicle_nonce: bool = False
) -> bytes:
    signature = _f_var(1, HMAC_SHA256) + _f_len(2, mac)
    body = _f_len(1, message_list) + _f_var(2, seq)
    if excludes_vehicle_nonce:
        body += _f_var(4, 1)
    return _f_len(2, body + _f_len(5, signature))


def build_auth1(secret_key: bytes, phone_id: bytes, phone_nonce: bytes) -> bytes:
    if len(phone_id) != 16 or len(phone_nonce) != 16:
        raise ValueError("phone_id and phone_nonce must be 16 bytes")
    credentials = _f_len(1, phone_id) + _f_len(2, phone_nonce)
    message = _f_var(1, 1) + _f_len(5, _f_len(1, credentials))
    message_list = _f_len(1, message)
    mac = _mac(secret_key, message_list, 1, phone_id, phone_nonce)
    return _signed(message_list, 1, mac, excludes_vehicle_nonce=True)


def build_auth2(
    secret_key: bytes,
    phone_id: bytes,
    phone_nonce: bytes,
    vehicle_nonce: bytes,
    model: bytes = DEFAULT_MODEL,
) -> bytes:
    empty_auth = _f_var(1, 3) + _f_len(5, _f_len(1, b""))
    client = _f_var(1, 5) + _f_len(9, _f_len(1, _f_len(2, model)))
    message_list = _f_len(1, empty_auth) + _f_len(1, client)
    mac = _mac(secret_key, message_list, 2, phone_id, phone_nonce, vehicle_nonce)
    return _signed(message_list, 2, mac)


def verify_auth1_reply(
    reply: bytes, secret_key: bytes, vehicle_id: bytes, phone_nonce: bytes
) -> bytes:
    signed = parse_fields(_one(parse_fields(reply), 2, b""))
    message_list = _one(signed, 1, b"")
    messages = parse_fields(message_list).get(1, [])
    if not messages:
        raise ValueError("reply carries no message")
    auth = parse_fields(_one(parse_fields(messages[0]), 5, b""))
    credentials = parse_fields(_one(auth, 1, b""))
    received_id = _one(credentials, 1, b"")
    vehicle_nonce = _one(credentials, 2, b"")
    if received_id and received_id != vehicle_id:
        raise ValueError("vehicle id mismatch (a different vehicle answered)")
    if not isinstance(vehicle_nonce, bytes) or len(vehicle_nonce) != 16:
        raise ValueError("vehicle nonce must be 16 bytes")
    seq = _one(signed, 2, 0)
    if not isinstance(seq, int) or not 0 <= seq <= 0xFFFFFFFF:
        raise ValueError("invalid vehicle sequence number")
    signature = parse_fields(_one(signed, 5, b""))
    mac = _one(signature, 2, b"")
    if _one(signature, 1) != HMAC_SHA256 or len(mac) != 32:
        raise ValueError("missing or unsupported signature")
    if _one(signed, 3, 0) or _one(signed, 4, 0):
        raise ValueError("vehicle signature omits a session nonce")
    expected = _mac(
        secret_key, message_list, seq, vehicle_id, phone_nonce, vehicle_nonce
    )
    if not hmac.compare_digest(mac, expected):
        raise ValueError("vehicle HMAC verification failed")
    return vehicle_nonce


async def _subscribe_encrypted(client: BleakClient, handler) -> None:
    """Subscribe to T, which bonds the link -- in the order the PoC verified.

    The vehicle refuses the first, unencrypted T subscribe with ATT 0x05.
    CoreBluetooth (like a phone) bonds on that refusal by itself, so on macOS
    the subscribe is simply retried until the user has accepted the pairing;
    elsewhere bleak bonds only when asked, so pair() follows the refusal. The
    vehicle requires the central to distribute its IRK and to accept Just
    Works -- a BlueZ adapter without privacy enabled, or with an agent that
    insists on MITM, is refused (see GEN2_BLE_PROTOCOL.md).
    """
    try:
        await client.start_notify(T_UUID, handler)
        return
    except BleakError as ex:
        _LOGGER.debug("Gen 2: T subscribe before bonding: %s", type(ex).__name__)
    if platform.system() != "Darwin":
        # Some backends keep the refused subscription's callback registered
        # and would reject the retry as a duplicate.
        with suppress(Exception):
            await client.stop_notify(T_UUID)
        await client.pair()
    deadline = asyncio.get_running_loop().time() + BOND_TIMEOUT
    while True:
        try:
            await client.start_notify(T_UUID, handler)
            return
        except Exception:
            if not client.is_connected or asyncio.get_running_loop().time() > deadline:
                raise
            await asyncio.sleep(2)


async def pair_phone_gen2(
    device: BLEDevice,
    phone_id: str,
    vas_vehicle_id: str,
    vehicle_public_key: str,
    private_key: str,
    vehicle_id: str | None = None,
) -> bool:
    _LOGGER.debug("Starting Gen 2 (PRE_CCC) pairing with %s", device)
    state = AuthState.INIT
    trace = ble_trace.get_trace(vehicle_id) if vehicle_id is not None else None

    def _trace(record) -> None:
        if trace is None:
            return
        try:
            record()
        except Exception:
            _LOGGER.debug("Gen 2: trace recording failed", exc_info=True)

    if trace is not None:
        trace.generation = 2

    try:
        secret_key = get_secret_key(private_key, vehicle_public_key)
        phone = UUID(phone_id).bytes
        vehicle = UUID(vas_vehicle_id).bytes
    except (ValueError, TypeError) as ex:
        _trace(lambda: trace.record_attempt_outcome("key_derivation_failed"))
        _LOGGER.error("Gen 2: failed to derive the shared key (%s)", type(ex).__name__)
        return False

    _trace(
        lambda: trace.record_identifiers(
            phone_id=phone_id, vas_vehicle_id=vas_vehicle_id, address=device.address
        )
    )

    def _set_state(new_state: AuthState) -> None:
        nonlocal state
        state = new_state
        _trace(lambda: trace.record_state(new_state.name))

    def _on_t(_, data: bytearray) -> None:
        _LOGGER.debug("Gen 2: T notification (%d bytes)", len(data))

    try:
        async with BleakClient(device, timeout=CONNECT_TIMEOUT) as client:
            _LOGGER.debug("Gen 2: connected to %s", device)
            mtu = getattr(client, "mtu_size", None)
            if mtu is not None:
                _trace(lambda: trace.record_mtu(mtu))

            chars = {
                char.uuid.upper()
                for service in client.services
                for char in service.characteristics
            }
            _trace(lambda: trace.record_services([{"uuid": u} for u in sorted(chars)]))
            if not {Q_UUID, R_UUID, T_UUID} <= chars:
                _trace(lambda: trace.record_attempt_outcome("no_gatt_services"))
                _LOGGER.error(
                    "Gen 2: the vehicle's phone-key characteristics are missing "
                    "(%d characteristics seen). Either Set up timed out, or this "
                    "is a local BlueZ adapter, which cannot see a Gen 2 "
                    "vehicle's services; see GEN2_BLE_PROTOCOL.md",
                    len(chars),
                )
                return False

            reply_handler = await create_notification_handler(client, R_UUID)

            phone_nonce = secrets.token_bytes(16)
            auth1 = build_auth1(secret_key, phone, phone_nonce)
            _trace(lambda: trace.record_frame("write", Q_UUID, auth1, "auth#1"))
            await client.write_gatt_char(Q_UUID, auth1, response=True)
            _set_state(AuthState.AUTH1_SENT)

            try:
                await reply_handler.wait(REPLY_TIMEOUT)
            except TimeoutError:
                _trace(lambda: trace.record_attempt_outcome("timeout"))
                _LOGGER.error(
                    "Gen 2: no reply to auth#1. Is the vehicle showing Set up "
                    "for this key, under the right driver?"
                )
                return False
            reply = bytes(reply_handler.data or b"")
            _trace(lambda: trace.record_frame("notify", R_UUID, reply, "auth#1 reply"))

            try:
                vehicle_nonce = verify_auth1_reply(
                    reply, secret_key, vehicle, phone_nonce
                )
            except ValueError as ex:
                _trace(lambda: trace.record_attempt_outcome("bad_reply"))
                _LOGGER.error("Gen 2: rejected the vehicle's reply: %s", ex)
                return False
            _set_state(AuthState.VEHICLE_VERIFIED)

            auth2 = build_auth2(secret_key, phone, phone_nonce, vehicle_nonce)
            _trace(lambda: trace.record_frame("write", Q_UUID, auth2, "auth#2"))
            await client.write_gatt_char(Q_UUID, auth2, response=True)
            _set_state(AuthState.AUTH2_SENT)

            try:
                await _subscribe_encrypted(client, _on_t)
            except Exception as ex:
                reason = type(ex).__name__
                _trace(lambda: trace.record_bonding("subscribe-t", f"error:{reason}"))
                _LOGGER.error(
                    "Gen 2: bonding failed. If this adapter paired with the "
                    "vehicle before, remove that stale bond (e.g. "
                    "`bluetoothctl remove <address>`) and try again"
                )
                raise
            _trace(lambda: trace.record_bonding("subscribe-t", "ok"))
            _set_state(AuthState.BONDED)
            _trace(lambda: trace.record_attempt_outcome("bonded"))
            _LOGGER.debug("Gen 2: bonded with %s", device)
            return True
    except Exception:
        _trace(lambda: trace.record_attempt_outcome("exception"))
        _LOGGER.exception("Gen 2 pairing failed at state %s", state.name)
        return False
