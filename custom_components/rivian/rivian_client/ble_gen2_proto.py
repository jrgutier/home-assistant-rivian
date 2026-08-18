"""Protocol Buffer message builders for Gen 2 (PRE_CCC) BLE pairing.

This module provides Protocol Buffer message construction for the Gen 2
BLE pairing protocol without requiring .proto files. Messages are constructed
using the protobuf wire format based on reverse engineering of the Android app.
"""

from __future__ import annotations

import struct
from typing import Any


def _encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value & 0x7F)
    return bytes(result)


def _encode_field(field_number: int, wire_type: int, value: bytes) -> bytes:
    """Encode a protobuf field with tag and value."""
    tag = (field_number << 3) | wire_type
    return _encode_varint(tag) + value


def _encode_bytes_field(field_number: int, value: bytes) -> bytes:
    """Encode a bytes field (wire type 2 - length-delimited)."""
    return _encode_field(field_number, 2, _encode_varint(len(value)) + value)


def _encode_varint_field(field_number: int, value: int) -> bytes:
    """Encode a varint field (wire type 0)."""
    return _encode_field(field_number, 0, _encode_varint(value))


class VASMessage:
    """VAS (Vehicle Access System) Protocol Buffer message builder.

    Based on reverse engineering of the Android app's protocol buffer usage.
    This constructs messages without requiring compiled .proto files.
    """

    @staticmethod
    def build_phone_id_nonce_message(
        csn: int, phone_id: bytes, phone_nonce: bytes
    ) -> bytes:
        """Build Phase 1 message: Phone ID + Phone Nonce.

        Args:
            csn: Command Sequence Number (increments by 2)
            phone_id: 16-byte phone UUID in big-endian format
            phone_nonce: 16-byte random nonce from SecureRandom

        Returns:
            Serialized protobuf message bytes

        Message structure (approximate field numbers from Android analysis):
            message VASMessage {
                uint32 csn = 1;
                VehicleInfo vehicle_info = 2;
                QueryData query_data = 3;
            }

            message VehicleInfo {
                bytes phone_id = 1;
            }

            message QueryData {
                bytes phone_nonce = 1;
            }
        """
        # Build nested VehicleInfo message
        vehicle_info = _encode_bytes_field(1, phone_id)

        # Build nested QueryData message
        query_data = _encode_bytes_field(1, phone_nonce)

        # Build main VASMessage
        message = b""
        message += _encode_varint_field(1, csn)  # Field 1: csn
        message += _encode_bytes_field(2, vehicle_info)  # Field 2: vehicle_info
        message += _encode_bytes_field(3, query_data)  # Field 3: query_data

        return message

    @staticmethod
    def build_signed_params_message(csn: int, hmac_signature: bytes) -> bytes:
        """Build Phase 3 message: SIGNED_PARAMS with HMAC signature.

        Args:
            csn: Command Sequence Number
            hmac_signature: 32-byte HMAC-SHA256 signature

        Returns:
            Serialized protobuf message bytes

        Message structure (approximate):
            message VASMessage {
                uint32 csn = 1;
                SignedData signed_data = 4;
            }

            message SignedData {
                bytes signature = 1;
                // messages field is empty for this use case
            }
        """
        # Build SignedData message with signature
        signed_data = _encode_bytes_field(1, hmac_signature)

        # Build main VASMessage
        message = b""
        message += _encode_varint_field(1, csn)  # Field 1: csn
        message += _encode_bytes_field(4, signed_data)  # Field 4: signed_data

        return message

    @staticmethod
    def parse_vehicle_nonce_response(message: bytes) -> dict[str, Any]:
        """Parse Phase 2 response: Vehicle Nonce from vehicle.

        Args:
            message: Encrypted protobuf message from vehicle

        Returns:
            Dictionary with parsed fields:
            - vnonce: bytes (vehicle nonce)
            - status: str (SUCCESS, ERROR, etc.)
            - csn: int (command sequence number)

        Note: This is a simplified parser. The actual Android app uses
        full protobuf deserialization with nested message structures.
        """
        result: dict[str, Any] = {"vnonce": None, "status": None, "csn": None}

        # Simple parsing - look for length-delimited fields
        # This is a basic implementation and may need refinement based on testing
        pos = 0
        while pos < len(message):
            if pos >= len(message):
                break

            # Read tag (field number + wire type)
            tag_byte = message[pos]
            pos += 1

            field_number = tag_byte >> 3
            wire_type = tag_byte & 0x07

            if wire_type == 0:  # Varint
                # Read varint
                varint_value = 0
                shift = 0
                while pos < len(message):
                    byte = message[pos]
                    pos += 1
                    varint_value |= (byte & 0x7F) << shift
                    if (byte & 0x80) == 0:
                        break
                    shift += 7

                if field_number == 1:
                    result["csn"] = varint_value

            elif wire_type == 2:  # Length-delimited
                # Read length
                length = 0
                shift = 0
                while pos < len(message):
                    byte = message[pos]
                    pos += 1
                    length |= (byte & 0x7F) << shift
                    if (byte & 0x80) == 0:
                        break
                    shift += 7

                # Read value
                if pos + length <= len(message):
                    bytes_value = message[pos : pos + length]
                    pos += length

                    # Field 3 or nested fields typically contain the vnonce
                    # This may need adjustment based on actual protocol
                    if field_number == 3 and len(bytes_value) >= 16:
                        result["vnonce"] = bytes_value
                    elif field_number == 5:  # Status field (approximate)
                        try:
                            result["status"] = bytes_value.decode("utf-8")
                        except UnicodeDecodeError:
                            result["status"] = "UNKNOWN"
            else:
                # Skip unknown wire types
                break

        return result

    @staticmethod
    def compute_hmac_input(
        serialized_protobuf: bytes,
        csn: int,
        phone_id: bytes,
        phone_nonce: bytes,
        vehicle_nonce: bytes,
    ) -> bytes:
        """Compute HMAC-SHA256 input buffer for Gen 2 authentication.

        This follows the exact format from the Android app (C11162i.java:~1792):

        hmac_input = protobuf || csn (4B, BE) || phoneId (16B, BE) ||
                     pNonce (16B) || vNonce (variable)

        Args:
            serialized_protobuf: The serialized protobuf message
            csn: Command Sequence Number
            phone_id: 16-byte phone UUID
            phone_nonce: 16-byte phone nonce
            vehicle_nonce: Variable length vehicle nonce

        Returns:
            Concatenated byte buffer ready for HMAC-SHA256
        """
        # Concatenate all components in exact order
        hmac_input = b""
        hmac_input += serialized_protobuf
        hmac_input += struct.pack(">I", csn)  # 4 bytes, big-endian
        hmac_input += phone_id  # 16 bytes
        hmac_input += phone_nonce  # 16 bytes
        hmac_input += vehicle_nonce  # variable length

        return hmac_input
