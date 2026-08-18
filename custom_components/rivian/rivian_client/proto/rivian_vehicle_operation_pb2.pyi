import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class VehicleOperationRequest(_message.Message):
    __slots__ = ("metadata", "operation")
    class PhoneInfo(_message.Message):
        __slots__ = ("version", "phone_id")
        VERSION_FIELD_NUMBER: _ClassVar[int]
        PHONE_ID_FIELD_NUMBER: _ClassVar[int]
        version: int
        phone_id: bytes
        def __init__(self, version: _Optional[int] = ..., phone_id: _Optional[bytes] = ...) -> None: ...
    class Metadata(_message.Message):
        __slots__ = ("phone_info", "request_id")
        PHONE_INFO_FIELD_NUMBER: _ClassVar[int]
        REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
        phone_info: VehicleOperationRequest.PhoneInfo
        request_id: str
        def __init__(self, phone_info: _Optional[_Union[VehicleOperationRequest.PhoneInfo, _Mapping]] = ..., request_id: _Optional[str] = ...) -> None: ...
    class Operation(_message.Message):
        __slots__ = ("rvm_type", "operation_type", "operation_id", "payload", "timestamp")
        RVM_TYPE_FIELD_NUMBER: _ClassVar[int]
        OPERATION_TYPE_FIELD_NUMBER: _ClassVar[int]
        OPERATION_ID_FIELD_NUMBER: _ClassVar[int]
        PAYLOAD_FIELD_NUMBER: _ClassVar[int]
        TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
        rvm_type: str
        operation_type: int
        operation_id: bytes
        payload: bytes
        timestamp: _timestamp_pb2.Timestamp
        def __init__(self, rvm_type: _Optional[str] = ..., operation_type: _Optional[int] = ..., operation_id: _Optional[bytes] = ..., payload: _Optional[bytes] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...
    METADATA_FIELD_NUMBER: _ClassVar[int]
    OPERATION_FIELD_NUMBER: _ClassVar[int]
    metadata: VehicleOperationRequest.Metadata
    operation: VehicleOperationRequest.Operation
    def __init__(self, metadata: _Optional[_Union[VehicleOperationRequest.Metadata, _Mapping]] = ..., operation: _Optional[_Union[VehicleOperationRequest.Operation, _Mapping]] = ...) -> None: ...

class SendVehicleOperationSuccess(_message.Message):
    __slots__ = ("success",)
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    def __init__(self, success: bool = ...) -> None: ...
