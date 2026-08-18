import rivian_base_pb2 as _rivian_base_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ChargingSessionLiveData(_message.Message):
    __slots__ = ("total_kwh", "pack_kwh", "thermal_kwh", "outlets_kwh", "system_kwh", "session_duration_mins", "time_remaining_mins", "range_added_kms", "current_power", "current_range_per_hour", "session_cost", "is_free_session", "charging_state")
    TOTAL_KWH_FIELD_NUMBER: _ClassVar[int]
    PACK_KWH_FIELD_NUMBER: _ClassVar[int]
    THERMAL_KWH_FIELD_NUMBER: _ClassVar[int]
    OUTLETS_KWH_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_KWH_FIELD_NUMBER: _ClassVar[int]
    SESSION_DURATION_MINS_FIELD_NUMBER: _ClassVar[int]
    TIME_REMAINING_MINS_FIELD_NUMBER: _ClassVar[int]
    RANGE_ADDED_KMS_FIELD_NUMBER: _ClassVar[int]
    CURRENT_POWER_FIELD_NUMBER: _ClassVar[int]
    CURRENT_RANGE_PER_HOUR_FIELD_NUMBER: _ClassVar[int]
    SESSION_COST_FIELD_NUMBER: _ClassVar[int]
    IS_FREE_SESSION_FIELD_NUMBER: _ClassVar[int]
    CHARGING_STATE_FIELD_NUMBER: _ClassVar[int]
    total_kwh: float
    pack_kwh: float
    thermal_kwh: float
    outlets_kwh: float
    system_kwh: float
    session_duration_mins: int
    time_remaining_mins: int
    range_added_kms: int
    current_power: float
    current_range_per_hour: int
    session_cost: _rivian_base_pb2.Money
    is_free_session: bool
    charging_state: int
    def __init__(self, total_kwh: _Optional[float] = ..., pack_kwh: _Optional[float] = ..., thermal_kwh: _Optional[float] = ..., outlets_kwh: _Optional[float] = ..., system_kwh: _Optional[float] = ..., session_duration_mins: _Optional[int] = ..., time_remaining_mins: _Optional[int] = ..., range_added_kms: _Optional[int] = ..., current_power: _Optional[float] = ..., current_range_per_hour: _Optional[int] = ..., session_cost: _Optional[_Union[_rivian_base_pb2.Money, _Mapping]] = ..., is_free_session: bool = ..., charging_state: _Optional[int] = ...) -> None: ...

class WindowData(_message.Message):
    __slots__ = ("start_time", "end_time", "duration", "amps", "location", "start_day_of_week", "end_day_of_week")
    START_TIME_FIELD_NUMBER: _ClassVar[int]
    END_TIME_FIELD_NUMBER: _ClassVar[int]
    DURATION_FIELD_NUMBER: _ClassVar[int]
    AMPS_FIELD_NUMBER: _ClassVar[int]
    LOCATION_FIELD_NUMBER: _ClassVar[int]
    START_DAY_OF_WEEK_FIELD_NUMBER: _ClassVar[int]
    END_DAY_OF_WEEK_FIELD_NUMBER: _ClassVar[int]
    start_time: int
    end_time: int
    duration: int
    amps: int
    location: _rivian_base_pb2.Location
    start_day_of_week: int
    end_day_of_week: int
    def __init__(self, start_time: _Optional[int] = ..., end_time: _Optional[int] = ..., duration: _Optional[int] = ..., amps: _Optional[int] = ..., location: _Optional[_Union[_rivian_base_pb2.Location, _Mapping]] = ..., start_day_of_week: _Optional[int] = ..., end_day_of_week: _Optional[int] = ...) -> None: ...

class ChargingScheduleTimeWindow(_message.Message):
    __slots__ = ("is_valid", "window_data")
    IS_VALID_FIELD_NUMBER: _ClassVar[int]
    WINDOW_DATA_FIELD_NUMBER: _ClassVar[int]
    is_valid: bool
    window_data: WindowData
    def __init__(self, is_valid: bool = ..., window_data: _Optional[_Union[WindowData, _Mapping]] = ...) -> None: ...

class ChargingSessionChartData(_message.Message):
    __slots__ = ("session_id", "timestamps", "power_values", "soc_values", "voltage_values", "current_values", "total_energy_kwh", "duration_minutes")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMPS_FIELD_NUMBER: _ClassVar[int]
    POWER_VALUES_FIELD_NUMBER: _ClassVar[int]
    SOC_VALUES_FIELD_NUMBER: _ClassVar[int]
    VOLTAGE_VALUES_FIELD_NUMBER: _ClassVar[int]
    CURRENT_VALUES_FIELD_NUMBER: _ClassVar[int]
    TOTAL_ENERGY_KWH_FIELD_NUMBER: _ClassVar[int]
    DURATION_MINUTES_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    timestamps: _containers.RepeatedScalarFieldContainer[int]
    power_values: _containers.RepeatedScalarFieldContainer[float]
    soc_values: _containers.RepeatedScalarFieldContainer[float]
    voltage_values: _containers.RepeatedScalarFieldContainer[float]
    current_values: _containers.RepeatedScalarFieldContainer[float]
    total_energy_kwh: float
    duration_minutes: int
    def __init__(self, session_id: _Optional[str] = ..., timestamps: _Optional[_Iterable[int]] = ..., power_values: _Optional[_Iterable[float]] = ..., soc_values: _Optional[_Iterable[float]] = ..., voltage_values: _Optional[_Iterable[float]] = ..., current_values: _Optional[_Iterable[float]] = ..., total_energy_kwh: _Optional[float] = ..., duration_minutes: _Optional[int] = ...) -> None: ...
