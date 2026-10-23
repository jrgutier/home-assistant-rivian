"""Tests for Gen 2 (PRE_CCC) BLE pairing.

The protocol is the one walthowd/rivian-gen2-key-poc verified on a 2026 R1S and
matched byte-for-byte against an over-the-air capture of the Android app (see
docs/development/GEN2_BLE_PROTOCOL.md). The sizes asserted here are the
captured ones: auth#1 is 90 bytes, auth#2 is 62 + len(model).

Every expected MAC is recomputed independently from `hmac`/`struct`, and the
vehicle's reply is spelled out byte by byte, never produced by the code under
test. A test that hands the code its own output back as the expectation cannot
fail when the protocol is wrong -- which is how a suite asserting an invented
48-byte frame stayed green for the previous implementation.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import logging
import struct
from typing import Self
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from bleak.exc import BleakError
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import pytest

from custom_components.rivian.rivian_client import ble_gen2, ble_trace
from custom_components.rivian.rivian_client.utils import (
    encode_private_key,
    encode_public_key,
    get_secret_key,
)

SECRET = bytes(range(32))
PHONE_ID = "00112233-4455-6677-8899-aabbccddeeff"
VAS_ID = "f0e1d2c3-b4a5-9687-7869-5a4b3c2d1e0f"
PHONE = UUID(PHONE_ID).bytes
VEHICLE = UUID(VAS_ID).bytes
PNONCE = bytes(range(100, 116))
VNONCE = bytes(range(200, 216))


def _hmac(*parts: bytes, key: bytes = SECRET) -> bytes:
    return hmac.new(key, b"".join(parts), hashlib.sha256).digest()


def vehicle_reply(
    phone_nonce: bytes = PNONCE,
    vehicle: bytes = VEHICLE,
    key: bytes = SECRET,
    flags: tuple[int, int] = (0, 0),
    include_id: bool = True,
    seq: int = 1,
) -> bytes:
    """The vehicle's reply on R, spelled out with fixed one-byte lengths."""
    credentials = (b"\x0a\x10" + vehicle if include_id else b"") + b"\x12\x10" + VNONCE
    auth = b"\x0a" + bytes([len(credentials)]) + credentials
    message = b"\x2a" + bytes([len(auth)]) + auth
    message_list = b"\x0a" + bytes([len(message)]) + message
    mac = _hmac(
        message_list,
        struct.pack("<I", seq),
        vehicle,
        b"" if flags[0] else phone_nonce,
        b"" if flags[1] else VNONCE,
        key=key,
    )
    signed = b"\x0a" + bytes([len(message_list)]) + message_list + bytes([0x10, seq])
    signed += (b"\x18\x01" if flags[0] else b"") + (b"\x20\x01" if flags[1] else b"")
    signed += b"\x2a\x24\x08\x01\x12\x20" + mac
    return b"\x12" + bytes([len(signed)]) + signed


# ── auth#1 ───────────────────────────────────────────────────────────


def test_auth1_matches_the_captured_layout_byte_for_byte() -> None:
    message_list = b"\x0a\x2a" + b"\x08\x01" + b"\x2a\x26\x0a\x24"
    message_list += b"\x0a\x10" + PHONE + b"\x12\x10" + PNONCE
    mac = _hmac(message_list, struct.pack("<I", 1), PHONE, PNONCE)
    signed = b"\x0a\x2c" + message_list + b"\x10\x01" + b"\x20\x01"
    signed += b"\x2a\x24\x08\x01\x12\x20" + mac
    expected = b"\x12\x58" + signed

    frame = ble_gen2.build_auth1(SECRET, PHONE, PNONCE)

    assert frame == expected
    assert len(frame) == 90


def test_auth1_rejects_wrong_length_inputs() -> None:
    with pytest.raises(ValueError):
        ble_gen2.build_auth1(SECRET, PHONE[:15], PNONCE)


# ── auth#2 ───────────────────────────────────────────────────────────


def test_auth2_matches_the_captured_layout_byte_for_byte() -> None:
    model = b"moto g play - 2024"
    empty_auth = b"\x08\x03\x2a\x02\x0a\x00"
    client = b"\x08\x05\x4a" + bytes([len(model) + 4]) + b"\x0a"
    client += bytes([len(model) + 2]) + b"\x12" + bytes([len(model)]) + model
    message_list = b"\x0a\x06" + empty_auth + b"\x0a" + bytes([len(client)]) + client
    mac = _hmac(message_list, struct.pack("<I", 2), PHONE, PNONCE, VNONCE)
    signed = b"\x0a" + bytes([len(message_list)]) + message_list + b"\x10\x02"
    signed += b"\x2a\x24\x08\x01\x12\x20" + mac
    expected = b"\x12" + bytes([len(signed)]) + signed

    frame = ble_gen2.build_auth2(SECRET, PHONE, PNONCE, VNONCE, model=model)

    assert frame == expected
    # The phone in the over-the-air capture sent this model in an 80-byte auth#2.
    assert len(frame) == 80


# ── the vehicle's reply ──────────────────────────────────────────────


def test_reply_verifies_and_yields_the_vehicle_nonce() -> None:
    assert (
        ble_gen2.verify_auth1_reply(vehicle_reply(), SECRET, VEHICLE, PNONCE) == VNONCE
    )


def test_reply_without_a_vehicle_id_still_verifies() -> None:
    reply = vehicle_reply(include_id=False)
    assert ble_gen2.verify_auth1_reply(reply, SECRET, VEHICLE, PNONCE) == VNONCE


def test_reply_from_another_vehicle_is_rejected() -> None:
    reply = vehicle_reply(vehicle=b"x" * 16)
    with pytest.raises(ValueError, match="mismatch"):
        ble_gen2.verify_auth1_reply(reply, SECRET, VEHICLE, PNONCE)


def test_reply_signed_under_another_key_is_rejected() -> None:
    reply = vehicle_reply(key=b"k" * 32)
    with pytest.raises(ValueError, match="HMAC"):
        ble_gen2.verify_auth1_reply(reply, SECRET, VEHICLE, PNONCE)


def test_replayed_reply_for_another_phone_nonce_is_rejected() -> None:
    reply = vehicle_reply(phone_nonce=bytes(16))
    with pytest.raises(ValueError, match="HMAC"):
        ble_gen2.verify_auth1_reply(reply, SECRET, VEHICLE, PNONCE)


@pytest.mark.parametrize("flags", [(1, 0), (0, 1)])
def test_reply_that_drops_a_nonce_from_its_mac_is_refused(flags) -> None:
    with pytest.raises(ValueError, match="omits"):
        ble_gen2.verify_auth1_reply(vehicle_reply(flags=flags), SECRET, VEHICLE, PNONCE)


def test_truncated_reply_is_rejected() -> None:
    with pytest.raises(ValueError):
        ble_gen2.verify_auth1_reply(vehicle_reply()[:40], SECRET, VEHICLE, PNONCE)


# ── key derivation ───────────────────────────────────────────────────


def test_get_secret_key_applies_hkdf_and_is_not_the_raw_ecdh_secret() -> None:
    """Gen 2 uses the Gen 1 / cloud-command key: HKDF-SHA256(ECDH), no salt or info."""
    phone_private = ec.generate_private_key(ec.SECP256R1())
    vehicle_public = ec.generate_private_key(ec.SECP256R1()).public_key()

    raw_ecdh = phone_private.exchange(ec.ECDH(), vehicle_public)
    expected = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"").derive(
        raw_ecdh
    )

    result = get_secret_key(
        encode_private_key(phone_private), encode_public_key(vehicle_public)
    )

    assert result == expected
    assert result != raw_ecdh


# ── pair_phone_gen2 against a fake vehicle ───────────────────────────


class _FakeVehicle:
    """BleakClient double that plays the vehicle's side of the handshake.

    A write of auth#1 to Q is answered on R with `reply(phone_nonce)`; the phone
    nonce is cut out of the frame at its fixed captured offset, not parsed with
    the code under test. A T subscribe fails as the real vehicle's does
    (ATT 0x05) until `pair()` has been called, unless `bond_fails`; one before
    auth#2 is a protocol violation and fails the test. On macOS the OS bonds by
    itself on the first refusal (`darwin`).
    """

    def __init__(
        self,
        reply=vehicle_reply,
        bond_fails: bool = False,
        darwin: bool = False,
        uuids=(ble_gen2.Q_UUID, ble_gen2.R_UUID, ble_gen2.T_UUID),
    ) -> None:
        self.reply = reply
        self.bond_fails = bond_fails
        self.darwin = darwin
        self.bonded = False
        self.t_attempts = 0
        self.services = [
            MagicMock(characteristics=[MagicMock(uuid=u.lower()) for u in uuids])
        ]
        self.stop_notify = AsyncMock()
        self.is_connected = True
        self.mtu_size = 185
        self.handlers: dict[str, object] = {}
        self.written: list[tuple[str, bytes]] = []
        self.pair = AsyncMock(side_effect=self._pair)

    async def _pair(self) -> None:
        self.bonded = not self.bond_fails

    async def start_notify(self, uuid, handler) -> None:
        if uuid == ble_gen2.T_UUID:
            assert len(self.written) == 2, "T subscribed before auth#2"
            self.t_attempts += 1
            if not self.bonded:
                self.bonded = self.darwin
                raise BleakError("ATT error 0x05: insufficient authentication")
        self.handlers[uuid] = handler

    async def write_gatt_char(self, uuid, data, response=False) -> None:
        assert response is True, "the PoC writes Q with response"
        self.written.append((uuid, bytes(data)))
        if len(self.written) == 1 and self.reply is not None:
            # Envelope(2) + Signed(2) + list(2) + msg hdr(2+4) + id hdr(2) + id(16) + nonce hdr(2)
            nonce = bytes(data[32:48])
            self.handlers[ble_gen2.R_UUID](None, bytearray(self.reply(nonce)))

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False


ARGS = (MagicMock(address="AA:BB"), PHONE_ID, VAS_ID, "vehicle-public-key", "pk")


async def _pair(client: _FakeVehicle, vehicle_id: str | None = None) -> bool:
    with (
        patch.object(ble_gen2, "get_secret_key", return_value=SECRET),
        patch.object(ble_gen2, "BleakClient", lambda device, timeout=None: client),
        patch.object(
            ble_gen2.platform,
            "system",
            return_value="Darwin" if client.darwin else "Linux",
        ),
        patch.object(ble_gen2, "REPLY_TIMEOUT", 0.05),
        patch.object(ble_gen2, "BOND_TIMEOUT", 0.0),
        patch.object(ble_gen2.asyncio, "sleep", AsyncMock()),
    ):
        return await ble_gen2.pair_phone_gen2(*ARGS, vehicle_id)


class TestPairPhoneGen2:
    async def test_happy_path_writes_both_auth_frames_to_q_and_bonds(self) -> None:
        client = _FakeVehicle()

        assert await _pair(client) is True

        assert [uuid for uuid, _ in client.written] == [ble_gen2.Q_UUID] * 2
        auth1, auth2 = (frame for _, frame in client.written)
        assert len(auth1) == 90
        assert len(auth2) == 62 + len(ble_gen2.DEFAULT_MODEL)
        client.pair.assert_awaited_once()
        assert ble_gen2.T_UUID in client.handlers
        # The verified order: T refused first (ATT 0x05), then bond, then retry.
        assert client.t_attempts == 2

    async def test_on_macos_the_refused_subscribe_bonds_without_pair(self) -> None:
        client = _FakeVehicle(darwin=True)
        assert await _pair(client) is True
        client.pair.assert_not_awaited()
        assert client.t_attempts == 2

    async def test_missing_phone_key_characteristics_fail_before_any_write(
        self,
    ) -> None:
        """What a local BlueZ adapter sees: no services. Fail with a reason,
        not a generic "characteristic not found" from deep in bleak."""
        client = _FakeVehicle(uuids=())
        assert await _pair(client) is False
        assert client.written == []

    async def test_auth2_mac_covers_the_vehicle_nonce_it_was_given(self) -> None:
        client = _FakeVehicle()
        assert await _pair(client) is True

        auth1, auth2 = (frame for _, frame in client.written)
        phone_nonce = auth1[32:48]
        message_list = auth2[4 : 4 + auth2[3]]
        assert auth2.endswith(
            _hmac(message_list, struct.pack("<I", 2), PHONE, phone_nonce, VNONCE)
        )

    async def test_bad_reply_fails_closed_without_auth2_or_bonding(self) -> None:
        client = _FakeVehicle(reply=lambda nonce: vehicle_reply(nonce, key=b"k" * 32))

        assert await _pair(client) is False

        assert len(client.written) == 1
        client.pair.assert_not_awaited()

    async def test_silent_vehicle_times_out(self) -> None:
        client = _FakeVehicle(reply=None)
        assert await _pair(client) is False
        client.pair.assert_not_awaited()

    async def test_refused_bond_is_a_failure(self) -> None:
        client = _FakeVehicle(bond_fails=True)
        assert await _pair(client) is False
        client.pair.assert_awaited_once()

    async def test_the_trace_records_the_exchange_with_identifiers_masked(self) -> None:
        """The diagnostics path must actually run: `_trace()` swallows errors by
        design, so a typo inside one of its lambdas would ship an empty trace."""
        vehicle_id = "trace-test-vehicle"
        trace = ble_trace.get_trace(vehicle_id)
        trace.reset()
        trace.start_attempt()

        assert await _pair(_FakeVehicle(), vehicle_id) is True

        rendered = trace.as_dict()
        assert rendered["generation"] == 2
        assert rendered["mtu"] == 185
        assert rendered["state_reached"] == "BONDED"
        assert rendered["attempts"][-1]["outcome"] == "bonded"
        assert [f["note"] for f in trace.frames] == [
            "auth#1",
            "auth#1 reply",
            "auth#2",
        ]
        dump = repr(rendered)
        assert PHONE.hex() not in dump
        assert VEHICLE.hex() not in dump
        assert trace.bonding == {"path": "subscribe-t", "outcome": "ok"}


class TestKeyMaterialNeverReachesLogs:
    """HA debug logs get pasted into public issues; a dependency's error string
    must not be able to carry the private key into one."""

    async def test_a_derive_failure_does_not_echo_the_private_key(self) -> None:
        secret = "SUPERSECRETPRIVATEKEYMATERIAL"
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        logger = logging.getLogger(ble_gen2.__name__)
        logger.addHandler(handler)
        previous = logger.level
        logger.setLevel(logging.DEBUG)

        def _raise_with_the_key(private_key, public_key):
            raise ValueError(f"bad key: {private_key}")

        try:
            with patch.object(ble_gen2, "get_secret_key", _raise_with_the_key):
                result = await ble_gen2.pair_phone_gen2(
                    MagicMock(), PHONE_ID, VAS_ID, "vehicle-public-key", secret
                )
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous)

        assert result is False
        assert secret not in buf.getvalue()
        assert "ValueError" in buf.getvalue()


async def test_key_derivation_failure_logs_only_the_exception_class(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _FakeVehicle()
    leak = "deadbeef-key-material"
    with (
        caplog.at_level(logging.DEBUG, logger=ble_gen2.__name__),
        patch.object(ble_gen2, "get_secret_key", side_effect=ValueError(leak)),
        patch.object(ble_gen2, "BleakClient", lambda device, timeout=None: client),
    ):
        assert await ble_gen2.pair_phone_gen2(*ARGS) is False

    assert "ValueError" in caplog.text
    assert leak not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    assert client.written == []
