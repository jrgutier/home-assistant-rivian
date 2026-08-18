"""Climate-related Protocol Buffer messages for Parallax protocol."""

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


class ClimateHoldSetting(_message.Message):
    """Climate hold setting.

    RVM: comfort.cabin.climate_hold_setting

    Attributes:
        enabled: Whether climate hold is enabled
        duration_minutes: Hold duration (minutes)
        target_temp_celsius: Target temperature (Celsius)
    """

    def __init__(
        self,
        enabled: bool = False,
        duration_minutes: int = 0,
        target_temp_celsius: float = 20.0,
    ):
        """Initialize ClimateHoldSetting message."""
        super().__init__()
        self.enabled = enabled
        self.duration_minutes = duration_minutes
        self.target_temp_celsius = target_temp_celsius

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "enabled": self.enabled,
            "duration_minutes": self.duration_minutes,
            "target_temp_celsius": self.target_temp_celsius,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.enabled:
            output.extend(self._encode_field_value(1, 1 if self.enabled else 0, 0))
        if self.duration_minutes:
            output.extend(self._encode_field_value(2, self.duration_minutes, 0))
        if self.target_temp_celsius:
            output.extend(self._encode_field_value(3, self.target_temp_celsius, 1))
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
        elif wire_type == 1:  # 64-bit (double)
            return tag_bytes + struct.pack("<d", value)
        return tag_bytes


class ClimateHoldStatus(_message.Message):
    """Climate hold status.

    RVM: comfort.cabin.climate_hold_status

    Attributes:
        active: Whether climate hold is currently active
        current_temp_celsius: Current cabin temperature (Celsius)
        target_temp_celsius: Target temperature (Celsius)
        time_remaining_mins: Time remaining (minutes)
        mode: Climate mode (e.g., "cooling", "heating", "auto")
    """

    def __init__(
        self,
        active: bool = False,
        current_temp_celsius: float = 20.0,
        target_temp_celsius: float = 20.0,
        time_remaining_mins: int = 0,
        mode: str = "auto",
    ):
        """Initialize ClimateHoldStatus message."""
        super().__init__()
        self.active = active
        self.current_temp_celsius = current_temp_celsius
        self.target_temp_celsius = target_temp_celsius
        self.time_remaining_mins = time_remaining_mins
        self.mode = mode

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "active": self.active,
            "current_temp_celsius": self.current_temp_celsius,
            "target_temp_celsius": self.target_temp_celsius,
            "time_remaining_mins": self.time_remaining_mins,
            "mode": self.mode,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.active:
            output.extend(self._encode_field_value(1, 1 if self.active else 0, 0))
        if self.current_temp_celsius:
            output.extend(self._encode_field_value(2, self.current_temp_celsius, 1))
        if self.target_temp_celsius:
            output.extend(self._encode_field_value(3, self.target_temp_celsius, 1))
        if self.time_remaining_mins:
            output.extend(self._encode_field_value(4, self.time_remaining_mins, 0))
        if self.mode:
            output.extend(self._encode_field_value(5, self.mode, 2))
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
        elif wire_type == 1:  # 64-bit (double)
            return tag_bytes + struct.pack("<d", value)
        elif wire_type == 2:  # Length-delimited (string)
            if isinstance(value, str):
                value_bytes = value.encode("utf-8")
            else:
                value_bytes = value
            return tag_bytes + _encode_varint(len(value_bytes)) + value_bytes
        return tag_bytes


class CabinVentilationSetting(_message.Message):
    """Cabin ventilation configuration.

    RVM: comfort.cabin.cabin_ventilation_setting

    Attributes:
        enabled: Whether ventilation is enabled
        mode: Ventilation mode ("AUTO", "MANUAL", "OFF")
        windows_open_percent: Window opening percentage (0-100)
        sunroof_open_percent: Sunroof opening percentage (0-100)
        duration_minutes: Duration in minutes
    """

    def __init__(
        self,
        enabled: bool = False,
        mode: str = "AUTO",
        windows_open_percent: int = 0,
        sunroof_open_percent: int = 0,
        duration_minutes: int = 0,
    ):
        """Initialize CabinVentilationSetting message."""
        super().__init__()
        self.enabled = enabled
        self.mode = mode
        self.windows_open_percent = windows_open_percent
        self.sunroof_open_percent = sunroof_open_percent
        self.duration_minutes = duration_minutes

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "windows_open_percent": self.windows_open_percent,
            "sunroof_open_percent": self.sunroof_open_percent,
            "duration_minutes": self.duration_minutes,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.enabled:
            output.extend(self._encode_field_value(1, 1 if self.enabled else 0, 0))
        if self.mode:
            output.extend(self._encode_field_value(2, self.mode, 2))
        if self.windows_open_percent:
            output.extend(self._encode_field_value(3, self.windows_open_percent, 0))
        if self.sunroof_open_percent:
            output.extend(self._encode_field_value(4, self.sunroof_open_percent, 0))
        if self.duration_minutes:
            output.extend(self._encode_field_value(5, self.duration_minutes, 0))
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
        elif wire_type == 2:  # Length-delimited (string)
            if isinstance(value, str):
                value_bytes = value.encode("utf-8")
            else:
                value_bytes = value
            return tag_bytes + _encode_varint(len(value_bytes)) + value_bytes
        return tag_bytes
