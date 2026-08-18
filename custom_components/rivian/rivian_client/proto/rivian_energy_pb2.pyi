from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TimeEstimationValidityStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TIME_ESTIMATION_VALIDITY_STATUS_UNRECOGNIZED: _ClassVar[TimeEstimationValidityStatus]
    TIME_ESTIMATION_VALID: _ClassVar[TimeEstimationValidityStatus]
    TIME_ESTIMATION_INVALID: _ClassVar[TimeEstimationValidityStatus]

class ChargingState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CHARGING_STATE_UNRECOGNIZED: _ClassVar[ChargingState]
    CHARGING_STATE_IDLE: _ClassVar[ChargingState]
    CHARGING_STATE_CHARGING: _ClassVar[ChargingState]
    CHARGING_STATE_COMPLETE: _ClassVar[ChargingState]

class BarContext(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    BAR_CONTEXT_UNRECOGNIZED: _ClassVar[BarContext]
    BAR_CONTEXT_ACTUAL: _ClassVar[BarContext]
    BAR_CONTEXT_ESTIMATED: _ClassVar[BarContext]
TIME_ESTIMATION_VALIDITY_STATUS_UNRECOGNIZED: TimeEstimationValidityStatus
TIME_ESTIMATION_VALID: TimeEstimationValidityStatus
TIME_ESTIMATION_INVALID: TimeEstimationValidityStatus
CHARGING_STATE_UNRECOGNIZED: ChargingState
CHARGING_STATE_IDLE: ChargingState
CHARGING_STATE_CHARGING: ChargingState
CHARGING_STATE_COMPLETE: ChargingState
BAR_CONTEXT_UNRECOGNIZED: BarContext
BAR_CONTEXT_ACTUAL: BarContext
BAR_CONTEXT_ESTIMATED: BarContext

class EnergyDistribution(_message.Message):
    __slots__ = ("total_kwh", "thermal_kwh", "outlets_kwh", "system_kwh", "gear_guard_kwh", "total_range", "thermal_range", "outlets_range", "system_range", "gear_guard_range", "session_duration_mins")
    TOTAL_KWH_FIELD_NUMBER: _ClassVar[int]
    THERMAL_KWH_FIELD_NUMBER: _ClassVar[int]
    OUTLETS_KWH_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_KWH_FIELD_NUMBER: _ClassVar[int]
    GEAR_GUARD_KWH_FIELD_NUMBER: _ClassVar[int]
    TOTAL_RANGE_FIELD_NUMBER: _ClassVar[int]
    THERMAL_RANGE_FIELD_NUMBER: _ClassVar[int]
    OUTLETS_RANGE_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_RANGE_FIELD_NUMBER: _ClassVar[int]
    GEAR_GUARD_RANGE_FIELD_NUMBER: _ClassVar[int]
    SESSION_DURATION_MINS_FIELD_NUMBER: _ClassVar[int]
    total_kwh: float
    thermal_kwh: float
    outlets_kwh: float
    system_kwh: float
    gear_guard_kwh: float
    total_range: float
    thermal_range: float
    outlets_range: float
    system_range: float
    gear_guard_range: float
    session_duration_mins: int
    def __init__(self, total_kwh: _Optional[float] = ..., thermal_kwh: _Optional[float] = ..., outlets_kwh: _Optional[float] = ..., system_kwh: _Optional[float] = ..., gear_guard_kwh: _Optional[float] = ..., total_range: _Optional[float] = ..., thermal_range: _Optional[float] = ..., outlets_range: _Optional[float] = ..., system_range: _Optional[float] = ..., gear_guard_range: _Optional[float] = ..., session_duration_mins: _Optional[int] = ...) -> None: ...

class ParkEnergyDistributions(_message.Message):
    __slots__ = ("last_24_hours", "last_8_hours", "last_park_session")
    LAST_24_HOURS_FIELD_NUMBER: _ClassVar[int]
    LAST_8_HOURS_FIELD_NUMBER: _ClassVar[int]
    LAST_PARK_SESSION_FIELD_NUMBER: _ClassVar[int]
    last_24_hours: EnergyDistribution
    last_8_hours: EnergyDistribution
    last_park_session: EnergyDistribution
    def __init__(self, last_24_hours: _Optional[_Union[EnergyDistribution, _Mapping]] = ..., last_8_hours: _Optional[_Union[EnergyDistribution, _Mapping]] = ..., last_park_session: _Optional[_Union[EnergyDistribution, _Mapping]] = ...) -> None: ...

class ChargingGraphBar(_message.Message):
    __slots__ = ("soc", "power", "start_time_ms", "end_time_ms", "time_estimation_validity_status", "charging_state", "bar_context")
    SOC_FIELD_NUMBER: _ClassVar[int]
    POWER_FIELD_NUMBER: _ClassVar[int]
    START_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    END_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    TIME_ESTIMATION_VALIDITY_STATUS_FIELD_NUMBER: _ClassVar[int]
    CHARGING_STATE_FIELD_NUMBER: _ClassVar[int]
    BAR_CONTEXT_FIELD_NUMBER: _ClassVar[int]
    soc: int
    power: float
    start_time_ms: int
    end_time_ms: int
    time_estimation_validity_status: TimeEstimationValidityStatus
    charging_state: ChargingState
    bar_context: BarContext
    def __init__(self, soc: _Optional[int] = ..., power: _Optional[float] = ..., start_time_ms: _Optional[int] = ..., end_time_ms: _Optional[int] = ..., time_estimation_validity_status: _Optional[_Union[TimeEstimationValidityStatus, str]] = ..., charging_state: _Optional[_Union[ChargingState, str]] = ..., bar_context: _Optional[_Union[BarContext, str]] = ...) -> None: ...

class ChargingGraphGlobal(_message.Message):
    __slots__ = ("global_charging_graph_bar",)
    GLOBAL_CHARGING_GRAPH_BAR_FIELD_NUMBER: _ClassVar[int]
    global_charging_graph_bar: _containers.RepeatedCompositeFieldContainer[ChargingGraphBar]
    def __init__(self, global_charging_graph_bar: _Optional[_Iterable[_Union[ChargingGraphBar, _Mapping]]] = ...) -> None: ...
