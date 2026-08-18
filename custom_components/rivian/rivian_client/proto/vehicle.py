"""Vehicle-related Protocol Buffer messages for Parallax protocol."""

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


class WheelInfo(_message.Message):
    """Individual wheel information.

    Attributes:
        position: Wheel position ("FRONT_LEFT", "FRONT_RIGHT", "REAR_LEFT", "REAR_RIGHT")
        tire_size: Tire size specification
        pressure_psi: Tire pressure in PSI
        tread_depth_mm: Tread depth in millimeters
    """

    def __init__(
        self,
        position: str = "",
        tire_size: str = "",
        pressure_psi: float = 0.0,
        tread_depth_mm: float = 0.0,
    ):
        """Initialize WheelInfo message."""
        super().__init__()
        self.position = position
        self.tire_size = tire_size
        self.pressure_psi = pressure_psi
        self.tread_depth_mm = tread_depth_mm

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "position": self.position,
            "tire_size": self.tire_size,
            "pressure_psi": self.pressure_psi,
            "tread_depth_mm": self.tread_depth_mm,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.position:
            output.extend(self._encode_field_value(1, self.position, 2))
        if self.tire_size:
            output.extend(self._encode_field_value(2, self.tire_size, 2))
        if self.pressure_psi:
            output.extend(self._encode_field_value(3, self.pressure_psi, 1))
        if self.tread_depth_mm:
            output.extend(self._encode_field_value(4, self.tread_depth_mm, 1))
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
        elif wire_type == 2:  # Length-delimited (string)
            if isinstance(value, str):
                value_bytes = value.encode("utf-8")
            else:
                value_bytes = value
            return tag_bytes + _encode_varint(len(value_bytes)) + value_bytes
        return tag_bytes


class VehicleWheels(_message.Message):
    """Complete wheel configuration.

    RVM: vehicle.wheels.vehicle_wheels

    Attributes:
        wheels: List of WheelInfo messages (one per wheel)
        wheel_type: Wheel type identifier (e.g., "20_INCH_BRIGHT", "22_INCH_DARK")
        installed_date: Installation date (ISO timestamp)
    """

    def __init__(
        self,
        wheels: list["WheelInfo"] | None = None,
        wheel_type: str = "",
        installed_date: str = "",
    ):
        """Initialize VehicleWheels message."""
        super().__init__()
        self.wheels = wheels if wheels is not None else []
        self.wheel_type = wheel_type
        self.installed_date = installed_date

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "wheels": [wheel.to_dict() for wheel in self.wheels],
            "wheel_type": self.wheel_type,
            "installed_date": self.installed_date,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        # Field 1: repeated wheels (each is length-delimited)
        for wheel in self.wheels:
            wheel_bytes = wheel.SerializeToString()
            output.extend(self._encode_field_value(1, wheel_bytes, 2))
        if self.wheel_type:
            output.extend(self._encode_field_value(2, self.wheel_type, 2))
        if self.installed_date:
            output.extend(self._encode_field_value(3, self.installed_date, 2))
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

        if wire_type == 2:  # Length-delimited (string/bytes)
            if isinstance(value, str):
                value_bytes = value.encode("utf-8")
            else:
                value_bytes = value
            return tag_bytes + _encode_varint(len(value_bytes)) + value_bytes
        return tag_bytes


class HalloweenSettings(_message.Message):
    """Halloween light show settings.

    RVM: holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings

    Attributes:
        enabled: Whether Halloween light show is enabled
        animation_mode: Animation mode ("SPOOKY", "FESTIVE", "OFF")
        brightness: Brightness level (0-100)
        repeat_count: Number of times to repeat animation
        schedule_enabled: Whether scheduled activation is enabled
        schedule_time: Scheduled time in "HH:MM" format
    """

    def __init__(
        self,
        enabled: bool = False,
        animation_mode: str = "OFF",
        brightness: int = 100,
        repeat_count: int = 1,
        schedule_enabled: bool = False,
        schedule_time: str = "",
    ):
        """Initialize HalloweenSettings message."""
        super().__init__()
        self.enabled = enabled
        self.animation_mode = animation_mode
        self.brightness = brightness
        self.repeat_count = repeat_count
        self.schedule_enabled = schedule_enabled
        self.schedule_time = schedule_time

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "enabled": self.enabled,
            "animation_mode": self.animation_mode,
            "brightness": self.brightness,
            "repeat_count": self.repeat_count,
            "schedule_enabled": self.schedule_enabled,
            "schedule_time": self.schedule_time,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.enabled:
            output.extend(self._encode_field_value(1, 1 if self.enabled else 0, 0))
        if self.animation_mode:
            output.extend(self._encode_field_value(2, self.animation_mode, 2))
        if self.brightness:
            output.extend(self._encode_field_value(3, self.brightness, 0))
        if self.repeat_count:
            output.extend(self._encode_field_value(4, self.repeat_count, 0))
        if self.schedule_enabled:
            output.extend(
                self._encode_field_value(5, 1 if self.schedule_enabled else 0, 0)
            )
        if self.schedule_time:
            output.extend(self._encode_field_value(6, self.schedule_time, 2))
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
