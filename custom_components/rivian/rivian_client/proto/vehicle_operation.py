"""The sendVehicleOperation envelope, as plain classes over the generated message.

The classes here are attribute holders with the interface the rest of the client
has always used -- keyword construction, `to_dict()`, `SerializeToString()`,
fields that may be assigned after construction. Until s49 each one also built its
own bytes by hand. Now `SerializeToString()` fills in the generated
`VehicleOperationRequest` from `parallax/proto/vehicle_operation.proto` and lets
protobuf write the bytes.

The bytes did not change, and
tests/client/fixtures/parallax_golden/send_path.json holds them to that. Two
things the hand-rolled encoder did are reproduced deliberately, because a
generated message does neither by default:

* It emitted every SUBMESSAGE, even an empty one: a request with a zero
  timestamp still carries `2a 00`. A generated message omits a submessage that
  was never touched, so each `_message()` below copies its children in
  explicitly, which marks them present.
* `Timestamp.from_datetime` computes nanos in floating point. google.protobuf's
  own `FromDatetime` is exact and gives a different last digit for some moments.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import uuid

from google.protobuf.message import Message

from ..parallax.proto import vehicle_operation_pb2

_Request = vehicle_operation_pb2.VehicleOperationRequest


def _encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value & 0x7F)
    return bytes(result)


def _encode_length_delimited(field_number: int, value: bytes) -> bytes:
    """Encode a length-delimited field by hand.

    Nothing in the client calls this. It is here for tests that build a frame
    byte by byte, so that a decoder test does not depend on an encoder to prove
    the decoder decodes.
    """
    return _encode_varint(field_number << 3 | 2) + _encode_varint(len(value)) + value


class _Message(ABC):
    """`SerializeToString` for a class that can build its generated message."""

    @abstractmethod
    def _message(self) -> Message:
        """Build the generated message from this object's current attributes."""

    def SerializeToString(self) -> bytes:
        """Serialize to protobuf wire format."""
        return self._message().SerializeToString()


class Timestamp(_Message):
    """Seconds and nanoseconds since the epoch; neither is emitted when zero."""

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

    def _message(self) -> _Request.Timestamp:
        return _Request.Timestamp(seconds=self.seconds, nanos=self.nanos)


class PhoneInfo(_Message):
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

    def _message(self) -> _Request.PhoneInfo:
        return _Request.PhoneInfo(version=self.version, phone_id=self.phone_id)


class Metadata(_Message):
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

    def _message(self) -> _Request.Metadata:
        message = _Request.Metadata(request_id=self.request_id)
        if self.phone_info:
            message.phone_info.CopyFrom(self.phone_info._message())
        return message


class Operation(_Message):
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

    def _message(self) -> _Request.Operation:
        message = _Request.Operation(
            rvm_type=self.rvm_type,
            operation_type=self.operation_type,
            operation_id=self.operation_id,
            payload=self.payload,
        )
        if self.timestamp:
            message.timestamp.CopyFrom(self.timestamp._message())
        return message


class VehicleOperationRequest(_Message):
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

    def _message(self) -> _Request:
        message = _Request()
        if self.metadata:
            message.metadata.CopyFrom(self.metadata._message())
        if self.operation:
            message.operation.CopyFrom(self.operation._message())
        return message
