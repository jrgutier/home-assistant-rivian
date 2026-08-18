"""Base Protocol Buffer message types for Parallax protocol."""

import struct
from typing import Any

from google.protobuf import message as _message


def _encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value & 0x7F)
    return bytes(result)


class TimeOfDay(_message.Message):
    """Time of day representation.

    Attributes:
        hour: Hour of day (0-23)
        minute: Minute of hour (0-59)
    """

    def __init__(self, hour: int = 0, minute: int = 0):
        """Initialize TimeOfDay message.

        Args:
            hour: Hour of day (0-23)
            minute: Minute of hour (0-59)
        """
        super().__init__()
        self.hour = hour
        self.minute = minute

    def to_dict(self) -> dict:
        """Convert message to dictionary.

        Returns:
            dict with hour and minute fields
        """
        return {"hour": self.hour, "minute": self.minute}

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.hour:
            output.extend(self._encode_field_value(1, self.hour, 0))
        if self.minute:
            output.extend(self._encode_field_value(2, self.minute, 0))
        return bytes(output)

    def _encode_field_value(
        self, field_number: int, value: Any, wire_type: int
    ) -> bytes:
        """Encode a field value with tag.

        Args:
            field_number: Protobuf field number
            value: Field value
            wire_type: Wire type (0=varint, 1=64-bit, 2=length-delimited, 5=32-bit)

        Returns:
            Encoded field bytes
        """
        tag = (field_number << 3) | wire_type
        tag_bytes = _encode_varint(tag)

        if wire_type == 0:  # Varint
            return tag_bytes + _encode_varint(value)
        return tag_bytes


class SessionCost(_message.Message):
    """Session cost representation.

    Attributes:
        amount: Cost amount in minor currency units (e.g., cents for USD)
        currency: ISO 4217 currency code (e.g., "USD", "EUR")
    """

    def __init__(self, amount: float = 0.0, currency: str = "USD"):
        """Initialize SessionCost message.

        Args:
            amount: Cost amount (will be converted to minor units internally)
            currency: ISO 4217 currency code
        """
        super().__init__()
        self.amount = amount
        self.currency = currency

    def to_dict(self) -> dict:
        """Convert message to dictionary.

        Returns:
            dict with amount and currency fields
        """
        return {"amount": self.amount, "currency": self.currency}

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.amount:
            output.extend(self._encode_field_value(1, self.amount, 1))
        if self.currency:
            output.extend(self._encode_field_value(2, self.currency, 2))
        return bytes(output)

    def _encode_field_value(
        self, field_number: int, value: Any, wire_type: int
    ) -> bytes:
        """Encode a field value with tag.

        Args:
            field_number: Protobuf field number
            value: Field value
            wire_type: Wire type (0=varint, 1=64-bit, 2=length-delimited, 5=32-bit)

        Returns:
            Encoded field bytes
        """
        tag = (field_number << 3) | wire_type
        tag_bytes = _encode_varint(tag)

        if wire_type == 1:  # 64-bit (double)
            return tag_bytes + struct.pack("<d", value)
        elif wire_type == 2:  # Length-delimited (string/bytes)
            if isinstance(value, str):
                value_bytes = value.encode("utf-8")
            else:
                value_bytes = value
            return tag_bytes + _encode_varint(len(value_bytes)) + value_bytes
        return tag_bytes
