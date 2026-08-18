"""OTA update Protocol Buffer messages for Parallax protocol."""

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


class OTAState(_message.Message):
    """OTA update state.

    RVM: ota.ota_state.vehicle_ota_state

    Attributes:
        update_available: Whether an update is available
        current_version: Current software version
        available_version: Available software version
        download_progress: Download progress (0-100)
        install_state: Install state (e.g., "idle", "downloading", "installing")
    """

    def __init__(
        self,
        update_available: bool = False,
        current_version: str = "",
        available_version: str = "",
        download_progress: int = 0,
        install_state: str = "idle",
    ):
        """Initialize OTAState message."""
        super().__init__()
        self.update_available = update_available
        self.current_version = current_version
        self.available_version = available_version
        self.download_progress = download_progress
        self.install_state = install_state

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "update_available": self.update_available,
            "current_version": self.current_version,
            "available_version": self.available_version,
            "download_progress": self.download_progress,
            "install_state": self.install_state,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format.

        Returns:
            Serialized protobuf bytes
        """
        output = bytearray()
        if self.update_available:
            output.extend(
                self._encode_field_value(1, 1 if self.update_available else 0, 0)
            )
        if self.current_version:
            output.extend(self._encode_field_value(2, self.current_version, 2))
        if self.available_version:
            output.extend(self._encode_field_value(3, self.available_version, 2))
        if self.download_progress:
            output.extend(self._encode_field_value(4, self.download_progress, 0))
        if self.install_state:
            output.extend(self._encode_field_value(5, self.install_state, 2))
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
