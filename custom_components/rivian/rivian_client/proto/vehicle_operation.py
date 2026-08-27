"""Vehicle operation Protocol Buffer messages for sendVehicleOperation mutation."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid


def _encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value & 0x7F)
    return bytes(result)


def _encode_field_tag(field_number: int, wire_type: int) -> bytes:
    """Encode a field tag (field number + wire type).

    Args:
        field_number: Protobuf field number
        wire_type: Wire type (0=varint, 1=64-bit, 2=length-delimited, 5=32-bit)

    Returns:
        Encoded tag bytes
    """
    tag = (field_number << 3) | wire_type
    return _encode_varint(tag)


def _encode_length_delimited(field_number: int, value: bytes) -> bytes:
    """Encode a length-delimited field.

    Args:
        field_number: Protobuf field number
        value: Bytes to encode

    Returns:
        Encoded field bytes with tag and length
    """
    tag = _encode_field_tag(field_number, 2)  # Wire type 2 = length-delimited
    length = _encode_varint(len(value))
    return tag + length + value


def _encode_string(field_number: int, value: str) -> bytes:
    """Encode a string field.

    Args:
        field_number: Protobuf field number
        value: String to encode

    Returns:
        Encoded field bytes
    """
    return _encode_length_delimited(field_number, value.encode("utf-8"))


def _encode_varint_field(field_number: int, value: int) -> bytes:
    """Encode a varint field.

    Args:
        field_number: Protobuf field number
        value: Integer value

    Returns:
        Encoded field bytes
    """
    tag = _encode_field_tag(field_number, 0)  # Wire type 0 = varint
    return tag + _encode_varint(value)


class Timestamp:
    """google.protobuf.Timestamp, hand-rolled.

    Two varint fields, seconds and nanos, and neither is emitted when zero --
    proto3 omits defaults. Replaces timestamp_pb2 so the package carries no
    protobuf runtime; verified byte-for-byte against the generated class.
    """

    def __init__(self, seconds: int = 0, nanos: int = 0) -> None:
        """Initialize a Timestamp."""
        self.seconds = seconds
        self.nanos = nanos

    @classmethod
    def from_datetime(cls, moment: datetime) -> Timestamp:
        """Build from an aware datetime."""
        epoch = moment.timestamp()
        seconds = int(epoch)
        return cls(seconds=seconds, nanos=int((epoch - seconds) * 1_000_000_000))

    def ToDatetime(self) -> datetime:
        """Return the moment as an aware UTC datetime."""
        return datetime.fromtimestamp(
            self.seconds + self.nanos / 1_000_000_000, tz=timezone.utc
        )

    def SerializeToString(self) -> bytes:
        """Serialize to protobuf wire format."""
        output = bytearray()
        if self.seconds:
            output.extend(_encode_varint_field(1, self.seconds))
        if self.nanos:
            output.extend(_encode_varint_field(2, self.nanos))
        return bytes(output)


class PhoneInfo:
    """Phone information for vehicle operation request.

    Attributes:
        version: Protocol version (always 1)
        phone_id: 16-byte phone identifier (uuid.UUID(vasPhoneId).bytes)
    """

    def __init__(self, version: int = 1, phone_id: bytes = b""):
        """Initialize PhoneInfo message."""
        self.version = version
        self.phone_id = phone_id

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "version": self.version,
            "phone_id": self.phone_id.hex(),
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format."""
        output = bytearray()
        if self.version:
            output.extend(_encode_varint_field(1, self.version))
        if self.phone_id:
            output.extend(_encode_length_delimited(2, self.phone_id))
        return bytes(output)


class Metadata:
    """Request metadata for vehicle operation.

    Attributes:
        phone_info: Phone information
        request_id: UUID string for this request
    """

    def __init__(self, phone_info: PhoneInfo | None = None, request_id: str = ""):
        """Initialize Metadata message."""
        self.phone_info = phone_info or PhoneInfo()
        self.request_id = request_id

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "phone_info": self.phone_info.to_dict(),
            "request_id": self.request_id,
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format."""
        output = bytearray()
        if self.phone_info:
            phone_info_bytes = self.phone_info.SerializeToString()
            output.extend(_encode_length_delimited(1, phone_info_bytes))
        if self.request_id:
            output.extend(_encode_string(2, self.request_id))
        return bytes(output)


class Operation:
    """Operation details for vehicle operation request.

    Attributes:
        rvm_type: RVM type string (e.g., "comfort.cabin.climate_hold_setting")
        operation_type: Operation type (1 = SET, 0 = GET?)
        operation_id: 16-byte UUID for this operation
        payload: Serialized protobuf payload (RVM-specific)
        timestamp: Operation timestamp
    """

    def __init__(
        self,
        rvm_type: str = "",
        operation_type: int = 1,
        operation_id: bytes | None = None,
        payload: bytes = b"",
        timestamp: Timestamp | None = None,
    ):
        """Initialize Operation message."""
        self.rvm_type = rvm_type
        self.operation_type = operation_type
        self.operation_id = operation_id or uuid.uuid4().bytes
        self.payload = payload
        if timestamp is None:
            timestamp = Timestamp.from_datetime(datetime.now(timezone.utc))
        self.timestamp = timestamp

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "rvm_type": self.rvm_type,
            "operation_type": self.operation_type,
            "operation_id": self.operation_id.hex(),
            "payload_size": len(self.payload),
            "timestamp": self.timestamp.ToDatetime().isoformat(),
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format."""
        output = bytearray()
        if self.rvm_type:
            output.extend(_encode_string(1, self.rvm_type))
        if self.operation_type:
            output.extend(_encode_varint_field(2, self.operation_type))
        if self.operation_id:
            output.extend(_encode_length_delimited(3, self.operation_id))
        if self.payload:
            output.extend(_encode_length_delimited(4, self.payload))
        if self.timestamp:
            timestamp_bytes = self.timestamp.SerializeToString()
            output.extend(_encode_length_delimited(5, timestamp_bytes))
        return bytes(output)


class VehicleOperationRequest:
    """Vehicle operation request wrapper for sendVehicleOperation mutation.

    Attributes:
        metadata: Request metadata with phone info and request ID
        operation: Operation details with RVM type and payload
    """

    def __init__(
        self,
        metadata: Metadata | None = None,
        operation: Operation | None = None,
    ):
        """Initialize VehicleOperationRequest message."""
        self.metadata = metadata or Metadata()
        self.operation = operation or Operation()

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "metadata": self.metadata.to_dict(),
            "operation": self.operation.to_dict(),
        }

    def SerializeToString(self) -> bytes:
        """Serialize message to protobuf wire format."""
        output = bytearray()
        if self.metadata:
            metadata_bytes = self.metadata.SerializeToString()
            output.extend(_encode_length_delimited(1, metadata_bytes))
        if self.operation:
            operation_bytes = self.operation.SerializeToString()
            output.extend(_encode_length_delimited(2, operation_bytes))
        return bytes(output)
