import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ClimateHoldSetting(_message.Message):
    __slots__ = ("hold_time_duration_seconds",)
    HOLD_TIME_DURATION_SECONDS_FIELD_NUMBER: _ClassVar[int]
    hold_time_duration_seconds: int
    def __init__(self, hold_time_duration_seconds: _Optional[int] = ...) -> None: ...

class ClimateHoldStatus(_message.Message):
    __slots__ = ("status", "availability", "unavailability_reason", "hold_end_time")
    class Status(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        STATUS_UNSPECIFIED: _ClassVar[ClimateHoldStatus.Status]
        STATUS_UNAVAILABLE: _ClassVar[ClimateHoldStatus.Status]
        STATUS_OFF: _ClassVar[ClimateHoldStatus.Status]
        STATUS_ON: _ClassVar[ClimateHoldStatus.Status]
        STATUS_FAULT: _ClassVar[ClimateHoldStatus.Status]
    STATUS_UNSPECIFIED: ClimateHoldStatus.Status
    STATUS_UNAVAILABLE: ClimateHoldStatus.Status
    STATUS_OFF: ClimateHoldStatus.Status
    STATUS_ON: ClimateHoldStatus.Status
    STATUS_FAULT: ClimateHoldStatus.Status
    class Availability(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        AVAILABILITY_UNSPECIFIED: _ClassVar[ClimateHoldStatus.Availability]
        AVAILABILITY_AVAILABLE: _ClassVar[ClimateHoldStatus.Availability]
        AVAILABILITY_CONTROLLABLE: _ClassVar[ClimateHoldStatus.Availability]
        AVAILABILITY_UNAVAILABLE: _ClassVar[ClimateHoldStatus.Availability]
    AVAILABILITY_UNSPECIFIED: ClimateHoldStatus.Availability
    AVAILABILITY_AVAILABLE: ClimateHoldStatus.Availability
    AVAILABILITY_CONTROLLABLE: ClimateHoldStatus.Availability
    AVAILABILITY_UNAVAILABLE: ClimateHoldStatus.Availability
    class UnavailabilityReason(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        UNAVAILABILITY_REASON_UNSPECIFIED: _ClassVar[ClimateHoldStatus.UnavailabilityReason]
        UNAVAILABILITY_REASON_UNKNOWN: _ClassVar[ClimateHoldStatus.UnavailabilityReason]
        UNAVAILABILITY_REASON_LOW_SOC: _ClassVar[ClimateHoldStatus.UnavailabilityReason]
    UNAVAILABILITY_REASON_UNSPECIFIED: ClimateHoldStatus.UnavailabilityReason
    UNAVAILABILITY_REASON_UNKNOWN: ClimateHoldStatus.UnavailabilityReason
    UNAVAILABILITY_REASON_LOW_SOC: ClimateHoldStatus.UnavailabilityReason
    STATUS_FIELD_NUMBER: _ClassVar[int]
    AVAILABILITY_FIELD_NUMBER: _ClassVar[int]
    UNAVAILABILITY_REASON_FIELD_NUMBER: _ClassVar[int]
    HOLD_END_TIME_FIELD_NUMBER: _ClassVar[int]
    status: ClimateHoldStatus.Status
    availability: ClimateHoldStatus.Availability
    unavailability_reason: ClimateHoldStatus.UnavailabilityReason
    hold_end_time: _timestamp_pb2.Timestamp
    def __init__(self, status: _Optional[_Union[ClimateHoldStatus.Status, str]] = ..., availability: _Optional[_Union[ClimateHoldStatus.Availability, str]] = ..., unavailability_reason: _Optional[_Union[ClimateHoldStatus.UnavailabilityReason, str]] = ..., hold_end_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class CabinVentilationSetting(_message.Message):
    __slots__ = ("enabled", "mode", "windows_open_percent", "sunroof_open_percent", "duration_minutes")
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    WINDOWS_OPEN_PERCENT_FIELD_NUMBER: _ClassVar[int]
    SUNROOF_OPEN_PERCENT_FIELD_NUMBER: _ClassVar[int]
    DURATION_MINUTES_FIELD_NUMBER: _ClassVar[int]
    enabled: bool
    mode: str
    windows_open_percent: int
    sunroof_open_percent: int
    duration_minutes: int
    def __init__(self, enabled: bool = ..., mode: _Optional[str] = ..., windows_open_percent: _Optional[int] = ..., sunroof_open_percent: _Optional[int] = ..., duration_minutes: _Optional[int] = ...) -> None: ...
