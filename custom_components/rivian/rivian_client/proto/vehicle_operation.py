from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
import uuid

from google.protobuf.message import Message

from ..parallax.proto import vehicle_operation_pb2

_Request = vehicle_operation_pb2.VehicleOperationRequest


def encode_varint(value: int) -> bytes:
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value & 0x7F)
    return bytes(result)


def encode_length_delimited(field_number: int, value: bytes) -> bytes:
    return encode_varint(field_number << 3 | 2) + encode_varint(len(value)) + value


_encode_length_delimited = encode_length_delimited


class _Message(ABC):
    @abstractmethod
    def _message(self) -> Message:
        pass

    def SerializeToString(self) -> bytes:
        return self._message().SerializeToString()


class Timestamp(_Message):
    def __init__(self, seconds: int = 0, nanos: int = 0) -> None:
        self.seconds = seconds
        self.nanos = nanos

    @classmethod
    def from_datetime(cls, moment: datetime) -> Timestamp:
        epoch = moment.timestamp()
        seconds = int(epoch)
        return cls(seconds=seconds, nanos=int((epoch - seconds) * 1_000_000_000))

    def ToDatetime(self) -> datetime:
        return datetime.fromtimestamp(self.seconds + self.nanos / 1_000_000_000, tz=UTC)

    def _message(self) -> _Request.Timestamp:
        return _Request.Timestamp(seconds=self.seconds, nanos=self.nanos)


class PhoneInfo(_Message):
    def __init__(self, version: int = 1, phone_id: bytes = b""):
        self.version = version
        self.phone_id = phone_id

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "phone_id": self.phone_id.hex(),
        }

    def _message(self) -> _Request.PhoneInfo:
        return _Request.PhoneInfo(version=self.version, phone_id=self.phone_id)


class Metadata(_Message):
    def __init__(self, phone_info: PhoneInfo | None = None, request_id: str = ""):
        self.phone_info = phone_info or PhoneInfo()
        self.request_id = request_id

    def to_dict(self) -> dict:
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
    def __init__(
        self,
        rvm_type: str = "",
        operation_type: int = 1,
        operation_id: bytes | None = None,
        payload: bytes = b"",
        timestamp: Timestamp | None = None,
    ):
        self.rvm_type = rvm_type
        self.operation_type = operation_type
        self.operation_id = operation_id or uuid.uuid4().bytes
        self.payload = payload
        if timestamp is None:
            timestamp = Timestamp.from_datetime(datetime.now(UTC))
        self.timestamp = timestamp

    def to_dict(self) -> dict:
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
    def __init__(
        self,
        metadata: Metadata | None = None,
        operation: Operation | None = None,
    ):
        self.metadata = metadata or Metadata()
        self.operation = operation or Operation()

    def to_dict(self) -> dict:
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
