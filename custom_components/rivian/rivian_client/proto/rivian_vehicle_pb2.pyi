import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Wheel(_message.Message):
    __slots__ = ("wheel_package", "tire_odometer_mileage_meters", "saved_tire_odometer_mileage_delta_meters", "odometer_at_last_rotation_meters", "saved_odometer_at_last_rotation_delta_meters", "rotation_reminder_interval_meters", "is_installed", "timestamp", "tires", "current_odometer_meters")
    WHEEL_PACKAGE_FIELD_NUMBER: _ClassVar[int]
    TIRE_ODOMETER_MILEAGE_METERS_FIELD_NUMBER: _ClassVar[int]
    SAVED_TIRE_ODOMETER_MILEAGE_DELTA_METERS_FIELD_NUMBER: _ClassVar[int]
    ODOMETER_AT_LAST_ROTATION_METERS_FIELD_NUMBER: _ClassVar[int]
    SAVED_ODOMETER_AT_LAST_ROTATION_DELTA_METERS_FIELD_NUMBER: _ClassVar[int]
    ROTATION_REMINDER_INTERVAL_METERS_FIELD_NUMBER: _ClassVar[int]
    IS_INSTALLED_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    TIRES_FIELD_NUMBER: _ClassVar[int]
    CURRENT_ODOMETER_METERS_FIELD_NUMBER: _ClassVar[int]
    wheel_package: int
    tire_odometer_mileage_meters: int
    saved_tire_odometer_mileage_delta_meters: int
    odometer_at_last_rotation_meters: int
    saved_odometer_at_last_rotation_delta_meters: int
    rotation_reminder_interval_meters: int
    is_installed: bool
    timestamp: _timestamp_pb2.Timestamp
    tires: int
    current_odometer_meters: int
    def __init__(self, wheel_package: _Optional[int] = ..., tire_odometer_mileage_meters: _Optional[int] = ..., saved_tire_odometer_mileage_delta_meters: _Optional[int] = ..., odometer_at_last_rotation_meters: _Optional[int] = ..., saved_odometer_at_last_rotation_delta_meters: _Optional[int] = ..., rotation_reminder_interval_meters: _Optional[int] = ..., is_installed: bool = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., tires: _Optional[int] = ..., current_odometer_meters: _Optional[int] = ...) -> None: ...

class VehicleWheels(_message.Message):
    __slots__ = ("wheels_list",)
    WHEELS_LIST_FIELD_NUMBER: _ClassVar[int]
    wheels_list: _containers.RepeatedCompositeFieldContainer[Wheel]
    def __init__(self, wheels_list: _Optional[_Iterable[_Union[Wheel, _Mapping]]] = ...) -> None: ...

class OtaGeofence(_message.Message):
    __slots__ = ("location",)
    LOCATION_FIELD_NUMBER: _ClassVar[int]
    location: str
    def __init__(self, location: _Optional[str] = ...) -> None: ...

class OtaRepeatsDaily(_message.Message):
    __slots__ = ("starts_at_min", "geofence")
    STARTS_AT_MIN_FIELD_NUMBER: _ClassVar[int]
    GEOFENCE_FIELD_NUMBER: _ClassVar[int]
    starts_at_min: int
    geofence: OtaGeofence
    def __init__(self, starts_at_min: _Optional[int] = ..., geofence: _Optional[_Union[OtaGeofence, _Mapping]] = ...) -> None: ...

class OtaSingleOccurrence(_message.Message):
    __slots__ = ("starts_at_utc",)
    STARTS_AT_UTC_FIELD_NUMBER: _ClassVar[int]
    starts_at_utc: _timestamp_pb2.Timestamp
    def __init__(self, starts_at_utc: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class OtaSchedule(_message.Message):
    __slots__ = ("id", "is_enabled", "repeats_daily", "single_occurrence")
    ID_FIELD_NUMBER: _ClassVar[int]
    IS_ENABLED_FIELD_NUMBER: _ClassVar[int]
    REPEATS_DAILY_FIELD_NUMBER: _ClassVar[int]
    SINGLE_OCCURRENCE_FIELD_NUMBER: _ClassVar[int]
    id: str
    is_enabled: bool
    repeats_daily: OtaRepeatsDaily
    single_occurrence: OtaSingleOccurrence
    def __init__(self, id: _Optional[str] = ..., is_enabled: bool = ..., repeats_daily: _Optional[_Union[OtaRepeatsDaily, _Mapping]] = ..., single_occurrence: _Optional[_Union[OtaSingleOccurrence, _Mapping]] = ...) -> None: ...

class OtaConfig(_message.Message):
    __slots__ = ("schedules", "timestamp")
    SCHEDULES_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    schedules: _containers.RepeatedCompositeFieldContainer[OtaSchedule]
    timestamp: _timestamp_pb2.Timestamp
    def __init__(self, schedules: _Optional[_Iterable[_Union[OtaSchedule, _Mapping]]] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class BoolValue(_message.Message):
    __slots__ = ("value",)
    VALUE_FIELD_NUMBER: _ClassVar[int]
    value: bool
    def __init__(self, value: bool = ...) -> None: ...

class Int32Value(_message.Message):
    __slots__ = ("value",)
    VALUE_FIELD_NUMBER: _ClassVar[int]
    value: int
    def __init__(self, value: _Optional[int] = ...) -> None: ...

class StringValue(_message.Message):
    __slots__ = ("value",)
    VALUE_FIELD_NUMBER: _ClassVar[int]
    value: str
    def __init__(self, value: _Optional[str] = ...) -> None: ...

class HalloweenCostumeTheme(_message.Message):
    __slots__ = ("theme_name",)
    THEME_NAME_FIELD_NUMBER: _ClassVar[int]
    theme_name: str
    def __init__(self, theme_name: _Optional[str] = ...) -> None: ...

class HalloweenCelebrationSettings(_message.Message):
    __slots__ = ("costume_theme", "celebration_sound_volume", "music_enabled", "music_type", "sound_effect", "exterior_sound_effect", "exterior_sounds_muted", "light_show_enabled", "interior_overhead_lights_enabled", "exterior_light_show_enabled", "lights_color", "car_costume_availability", "motion_light_sound_enabled")
    COSTUME_THEME_FIELD_NUMBER: _ClassVar[int]
    CELEBRATION_SOUND_VOLUME_FIELD_NUMBER: _ClassVar[int]
    MUSIC_ENABLED_FIELD_NUMBER: _ClassVar[int]
    MUSIC_TYPE_FIELD_NUMBER: _ClassVar[int]
    SOUND_EFFECT_FIELD_NUMBER: _ClassVar[int]
    EXTERIOR_SOUND_EFFECT_FIELD_NUMBER: _ClassVar[int]
    EXTERIOR_SOUNDS_MUTED_FIELD_NUMBER: _ClassVar[int]
    LIGHT_SHOW_ENABLED_FIELD_NUMBER: _ClassVar[int]
    INTERIOR_OVERHEAD_LIGHTS_ENABLED_FIELD_NUMBER: _ClassVar[int]
    EXTERIOR_LIGHT_SHOW_ENABLED_FIELD_NUMBER: _ClassVar[int]
    LIGHTS_COLOR_FIELD_NUMBER: _ClassVar[int]
    CAR_COSTUME_AVAILABILITY_FIELD_NUMBER: _ClassVar[int]
    MOTION_LIGHT_SOUND_ENABLED_FIELD_NUMBER: _ClassVar[int]
    costume_theme: HalloweenCostumeTheme
    celebration_sound_volume: Int32Value
    music_enabled: BoolValue
    music_type: StringValue
    sound_effect: StringValue
    exterior_sound_effect: int
    exterior_sounds_muted: BoolValue
    light_show_enabled: BoolValue
    interior_overhead_lights_enabled: BoolValue
    exterior_light_show_enabled: BoolValue
    lights_color: StringValue
    car_costume_availability: StringValue
    motion_light_sound_enabled: bool
    def __init__(self, costume_theme: _Optional[_Union[HalloweenCostumeTheme, _Mapping]] = ..., celebration_sound_volume: _Optional[_Union[Int32Value, _Mapping]] = ..., music_enabled: _Optional[_Union[BoolValue, _Mapping]] = ..., music_type: _Optional[_Union[StringValue, _Mapping]] = ..., sound_effect: _Optional[_Union[StringValue, _Mapping]] = ..., exterior_sound_effect: _Optional[int] = ..., exterior_sounds_muted: _Optional[_Union[BoolValue, _Mapping]] = ..., light_show_enabled: _Optional[_Union[BoolValue, _Mapping]] = ..., interior_overhead_lights_enabled: _Optional[_Union[BoolValue, _Mapping]] = ..., exterior_light_show_enabled: _Optional[_Union[BoolValue, _Mapping]] = ..., lights_color: _Optional[_Union[StringValue, _Mapping]] = ..., car_costume_availability: _Optional[_Union[StringValue, _Mapping]] = ..., motion_light_sound_enabled: bool = ...) -> None: ...
