"""Tests for Gen 2 (PRE_CCC) BLE pairing."""

from __future__ import annotations

import pytest

# Import only non-BLE functions for testing without bleak installed
from custom_components.rivian.rivian_client.ble_gen2_proto import VASMessage

# Try to import BLE functions, skip tests if not available
try:
    from custom_components.rivian.rivian_client.ble_gen2 import (
        AuthState,
        compute_gen2_hmac,
        derive_ecdh_shared_secret,
    )

    HAS_BLE = True
except ImportError:
    HAS_BLE = False

pytestmark = pytest.mark.skipif(not HAS_BLE, reason="BLE extras not installed")


def test_auth_state_enum() -> None:
    """Test AuthState enum values."""
    assert AuthState.INIT == 0
    assert AuthState.PID_PNONCE_SENT == 1
    assert AuthState.SIGNED_PARAMS_SENT == 2
    assert AuthState.AUTHENTICATED == 3


def test_protobuf_varint_encoding() -> None:
    """Test protobuf varint encoding."""
    from custom_components.rivian.rivian_client.ble_gen2_proto import _encode_varint

    # Test small values
    assert _encode_varint(0) == b"\x00"
    assert _encode_varint(1) == b"\x01"
    assert _encode_varint(127) == b"\x7f"

    # Test multi-byte values
    assert _encode_varint(128) == b"\x80\x01"
    assert _encode_varint(300) == b"\xac\x02"


def test_protobuf_phone_id_nonce_message() -> None:
    """Test building Phase 1 message (Phone ID + Nonce)."""
    csn = 1
    phone_id = bytes.fromhex("550e8400e29b41d4a716446655440000")
    phone_nonce = bytes.fromhex("1a2b3c4d5e6f70819a0b1c2d3e4f5061")

    message = VASMessage.build_phone_id_nonce_message(csn, phone_id, phone_nonce)

    # Verify message is not empty
    assert len(message) > 0

    # Verify it contains the CSN (field 1)
    assert message[0] == 0x08  # Field 1, wire type 0 (varint)
    assert message[1] == 0x01  # CSN value = 1

    # Verify it contains embedded messages (field 2 and 3 should be length-delimited)
    assert 0x12 in message or 0x1A in message  # Field 2 or 3, wire type 2


def test_protobuf_signed_params_message() -> None:
    """Test building Phase 3 message (SIGNED_PARAMS)."""
    csn = 3
    hmac_signature = b"0" * 32  # 32-byte signature

    message = VASMessage.build_signed_params_message(csn, hmac_signature)

    # Verify message is not empty
    assert len(message) > 0

    # Verify it contains the CSN (field 1)
    assert message[0] == 0x08  # Field 1, wire type 0 (varint)
    assert message[1] == 0x03  # CSN value = 3

    # Verify it contains the signature embedded in SignedData (field 4)
    # Field 4, wire type 2 = 0x22
    assert 0x22 in message


def test_hmac_input_construction() -> None:
    """Test HMAC input buffer construction."""
    serialized_protobuf = b"test_protobuf"
    csn = 5
    phone_id = bytes.fromhex("550e8400e29b41d4a716446655440000")
    phone_nonce = bytes.fromhex("1a2b3c4d5e6f70819a0b1c2d3e4f5061")
    vehicle_nonce = bytes.fromhex("aabbccdd")

    hmac_input = VASMessage.compute_hmac_input(
        serialized_protobuf, csn, phone_id, phone_nonce, vehicle_nonce
    )

    # Verify concatenation order
    expected_length = (
        len(serialized_protobuf)  # protobuf
        + 4  # CSN (4 bytes big-endian)
        + 16  # phone_id
        + 16  # phone_nonce
        + len(vehicle_nonce)  # vehicle_nonce
    )
    assert len(hmac_input) == expected_length

    # Verify components are in correct order
    offset = 0
    assert hmac_input[offset : offset + len(serialized_protobuf)] == serialized_protobuf
    offset += len(serialized_protobuf)

    # CSN in big-endian
    assert hmac_input[offset : offset + 4] == b"\x00\x00\x00\x05"
    offset += 4

    assert hmac_input[offset : offset + 16] == phone_id
    offset += 16

    assert hmac_input[offset : offset + 16] == phone_nonce
    offset += 16

    assert hmac_input[offset : offset + len(vehicle_nonce)] == vehicle_nonce


def test_gen2_hmac_computation() -> None:
    """Test Gen 2 HMAC-SHA256 computation."""
    serialized_protobuf = b"test_message"
    csn = 1
    phone_id = bytes.fromhex("550e8400e29b41d4a716446655440000")
    phone_nonce = bytes.fromhex("1a2b3c4d5e6f70819a0b1c2d3e4f5061")
    vehicle_nonce = bytes.fromhex("aabbccdd")
    shared_secret = b"0" * 32  # 32-byte ECDH shared secret

    signature = compute_gen2_hmac(
        serialized_protobuf,
        csn,
        phone_id,
        phone_nonce,
        vehicle_nonce,
        shared_secret,
    )

    # HMAC-SHA256 always produces 32-byte output
    assert len(signature) == 32

    # Verify deterministic output (same inputs = same output)
    signature2 = compute_gen2_hmac(
        serialized_protobuf,
        csn,
        phone_id,
        phone_nonce,
        vehicle_nonce,
        shared_secret,
    )
    assert signature == signature2

    # Verify different input produces different output
    signature3 = compute_gen2_hmac(
        serialized_protobuf,
        csn + 1,  # Different CSN
        phone_id,
        phone_nonce,
        vehicle_nonce,
        shared_secret,
    )
    assert signature != signature3


def test_ecdh_key_derivation_invalid_inputs() -> None:
    """Test ECDH key derivation with invalid inputs."""
    # Valid test keys (example - in real use these come from enrollment)
    private_key_pem = """-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQg1234567890abcdef
1234567890abcdef1234567890abcdefahFoAECBQQgaabbccddaabbccddaabbccdd
aabbccddaabbccddaabbccddaabbccdd
-----END PRIVATE KEY-----"""

    # Invalid vehicle public key (wrong length)
    with pytest.raises(ValueError, match="must be 130 hex chars"):
        derive_ecdh_shared_secret(private_key_pem, "04aabbcc")

    # Invalid vehicle public key (wrong prefix)
    with pytest.raises(ValueError, match='must start with "04"'):
        derive_ecdh_shared_secret(
            private_key_pem,
            "05" + "aa" * 64,  # Wrong prefix
        )


def test_vehicle_nonce_response_parsing() -> None:
    """Test parsing vehicle nonce response."""
    # Create a simple mock protobuf message
    # Field 1 (CSN) = varint = 5
    # Field 3 (vnonce) = length-delimited = 16 bytes
    mock_message = b"\x08\x05"  # Field 1: CSN = 5
    mock_message += b"\x1a\x10"  # Field 3: length = 16
    mock_message += b"aabbccdd" * 4  # 16 bytes vnonce

    parsed = VASMessage.parse_vehicle_nonce_response(mock_message)

    assert parsed["csn"] == 5
    assert parsed["vnonce"] is not None
    assert len(parsed["vnonce"]) >= 16


def test_protobuf_message_integration() -> None:
    """Integration test for full message flow."""
    # Phase 1: Build phone ID + nonce message
    csn = 1
    phone_id = bytes.fromhex("550e8400e29b41d4a716446655440000")
    phone_nonce = bytes.fromhex("1a2b3c4d5e6f70819a0b1c2d3e4f5061")

    phase1_msg = VASMessage.build_phone_id_nonce_message(csn, phone_id, phone_nonce)
    assert len(phase1_msg) > 0

    # Simulate receiving vehicle nonce
    vehicle_nonce = bytes.fromhex("aabbccddaabbccddaabbccddaabbccdd")

    # Phase 3: Compute HMAC
    shared_secret = b"x" * 32
    hmac_sig = compute_gen2_hmac(
        phase1_msg, csn, phone_id, phone_nonce, vehicle_nonce, shared_secret
    )
    assert len(hmac_sig) == 32

    # Phase 3: Build signed params message
    phase3_msg = VASMessage.build_signed_params_message(csn + 2, hmac_sig)
    assert len(phase3_msg) > 0

    # Verify phase 3 message contains the signature
    assert hmac_sig[:16] in phase3_msg or hmac_sig[16:] in phase3_msg
