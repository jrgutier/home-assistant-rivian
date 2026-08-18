import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
import rivian_base_pb2 as _rivian_base_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TripProgress(_message.Message):
    __slots__ = ("leg_eta_utc", "trip_eta_utc", "next_stop_index")
    LEG_ETA_UTC_FIELD_NUMBER: _ClassVar[int]
    TRIP_ETA_UTC_FIELD_NUMBER: _ClassVar[int]
    NEXT_STOP_INDEX_FIELD_NUMBER: _ClassVar[int]
    leg_eta_utc: _timestamp_pb2.Timestamp
    trip_eta_utc: _timestamp_pb2.Timestamp
    next_stop_index: int
    def __init__(self, leg_eta_utc: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., trip_eta_utc: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., next_stop_index: _Optional[int] = ...) -> None: ...

class TripWaypoint(_message.Message):
    __slots__ = ("location", "name", "address")
    LOCATION_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    ADDRESS_FIELD_NUMBER: _ClassVar[int]
    location: _rivian_base_pb2.Location
    name: str
    address: str
    def __init__(self, location: _Optional[_Union[_rivian_base_pb2.Location, _Mapping]] = ..., name: _Optional[str] = ..., address: _Optional[str] = ...) -> None: ...

class TripRoute(_message.Message):
    __slots__ = ("waypoints", "distance_meters", "duration_seconds", "initial_soc", "final_soc")
    WAYPOINTS_FIELD_NUMBER: _ClassVar[int]
    DISTANCE_METERS_FIELD_NUMBER: _ClassVar[int]
    DURATION_SECONDS_FIELD_NUMBER: _ClassVar[int]
    INITIAL_SOC_FIELD_NUMBER: _ClassVar[int]
    FINAL_SOC_FIELD_NUMBER: _ClassVar[int]
    waypoints: _containers.RepeatedCompositeFieldContainer[TripWaypoint]
    distance_meters: int
    duration_seconds: int
    initial_soc: float
    final_soc: float
    def __init__(self, waypoints: _Optional[_Iterable[_Union[TripWaypoint, _Mapping]]] = ..., distance_meters: _Optional[int] = ..., duration_seconds: _Optional[int] = ..., initial_soc: _Optional[float] = ..., final_soc: _Optional[float] = ...) -> None: ...

class TripPreferences(_message.Message):
    __slots__ = ("avoid_highways", "avoid_tolls", "avoid_ferries", "fastest_route", "most_efficient")
    AVOID_HIGHWAYS_FIELD_NUMBER: _ClassVar[int]
    AVOID_TOLLS_FIELD_NUMBER: _ClassVar[int]
    AVOID_FERRIES_FIELD_NUMBER: _ClassVar[int]
    FASTEST_ROUTE_FIELD_NUMBER: _ClassVar[int]
    MOST_EFFICIENT_FIELD_NUMBER: _ClassVar[int]
    avoid_highways: bool
    avoid_tolls: bool
    avoid_ferries: bool
    fastest_route: bool
    most_efficient: bool
    def __init__(self, avoid_highways: bool = ..., avoid_tolls: bool = ..., avoid_ferries: bool = ..., fastest_route: bool = ..., most_efficient: bool = ...) -> None: ...

class FasterRouteInfo(_message.Message):
    __slots__ = ("time_savings_seconds", "distance_difference_meters", "route")
    TIME_SAVINGS_SECONDS_FIELD_NUMBER: _ClassVar[int]
    DISTANCE_DIFFERENCE_METERS_FIELD_NUMBER: _ClassVar[int]
    ROUTE_FIELD_NUMBER: _ClassVar[int]
    time_savings_seconds: int
    distance_difference_meters: int
    route: TripRoute
    def __init__(self, time_savings_seconds: _Optional[int] = ..., distance_difference_meters: _Optional[int] = ..., route: _Optional[_Union[TripRoute, _Mapping]] = ...) -> None: ...

class TripInfo(_message.Message):
    __slots__ = ("id", "origin", "route", "preferences", "initial_soc_percentage", "departure_time", "faster_route")
    ID_FIELD_NUMBER: _ClassVar[int]
    ORIGIN_FIELD_NUMBER: _ClassVar[int]
    ROUTE_FIELD_NUMBER: _ClassVar[int]
    PREFERENCES_FIELD_NUMBER: _ClassVar[int]
    INITIAL_SOC_PERCENTAGE_FIELD_NUMBER: _ClassVar[int]
    DEPARTURE_TIME_FIELD_NUMBER: _ClassVar[int]
    FASTER_ROUTE_FIELD_NUMBER: _ClassVar[int]
    id: str
    origin: TripWaypoint
    route: TripRoute
    preferences: TripPreferences
    initial_soc_percentage: float
    departure_time: _timestamp_pb2.Timestamp
    faster_route: FasterRouteInfo
    def __init__(self, id: _Optional[str] = ..., origin: _Optional[_Union[TripWaypoint, _Mapping]] = ..., route: _Optional[_Union[TripRoute, _Mapping]] = ..., preferences: _Optional[_Union[TripPreferences, _Mapping]] = ..., initial_soc_percentage: _Optional[float] = ..., departure_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., faster_route: _Optional[_Union[FasterRouteInfo, _Mapping]] = ...) -> None: ...
