from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GeofenceType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    GEOFENCE_TYPE_UNRECOGNIZED: _ClassVar[GeofenceType]
    GEOFENCE_TYPE_HOME: _ClassVar[GeofenceType]
    GEOFENCE_TYPE_WORK: _ClassVar[GeofenceType]
    GEOFENCE_TYPE_CUSTOM: _ClassVar[GeofenceType]

class GearGuardConsentStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    GEAR_GUARD_CONSENT_UNRECOGNIZED: _ClassVar[GearGuardConsentStatus]
    GEAR_GUARD_CONSENTED: _ClassVar[GearGuardConsentStatus]
    GEAR_GUARD_NOT_CONSENTED: _ClassVar[GearGuardConsentStatus]
    GEAR_GUARD_NOT_APPLICABLE: _ClassVar[GearGuardConsentStatus]
    GEAR_GUARD_UNKNOWN: _ClassVar[GearGuardConsentStatus]

class GearGuardDailyLimitStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    GEAR_GUARD_DAILY_LIMIT_UNRECOGNIZED: _ClassVar[GearGuardDailyLimitStatus]
    GEAR_GUARD_DAILY_LIMIT_UNDEFINED: _ClassVar[GearGuardDailyLimitStatus]
    GEAR_GUARD_DAILY_LIMIT_NOT_HIT: _ClassVar[GearGuardDailyLimitStatus]
    GEAR_GUARD_DAILY_LIMIT_HIT: _ClassVar[GearGuardDailyLimitStatus]

class CccPassivePermissionStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CCC_PASSIVE_PERMISSION_STATUS_UNRECOGNIZED: _ClassVar[CccPassivePermissionStatus]
    CCC_PASSIVE_PERMISSION_STATUS_SNA: _ClassVar[CccPassivePermissionStatus]
    CCC_PASSIVE_PERMISSION_STATUS_ENABLED: _ClassVar[CccPassivePermissionStatus]
    CCC_PASSIVE_PERMISSION_STATUS_DISABLED: _ClassVar[CccPassivePermissionStatus]
GEOFENCE_TYPE_UNRECOGNIZED: GeofenceType
GEOFENCE_TYPE_HOME: GeofenceType
GEOFENCE_TYPE_WORK: GeofenceType
GEOFENCE_TYPE_CUSTOM: GeofenceType
GEAR_GUARD_CONSENT_UNRECOGNIZED: GearGuardConsentStatus
GEAR_GUARD_CONSENTED: GearGuardConsentStatus
GEAR_GUARD_NOT_CONSENTED: GearGuardConsentStatus
GEAR_GUARD_NOT_APPLICABLE: GearGuardConsentStatus
GEAR_GUARD_UNKNOWN: GearGuardConsentStatus
GEAR_GUARD_DAILY_LIMIT_UNRECOGNIZED: GearGuardDailyLimitStatus
GEAR_GUARD_DAILY_LIMIT_UNDEFINED: GearGuardDailyLimitStatus
GEAR_GUARD_DAILY_LIMIT_NOT_HIT: GearGuardDailyLimitStatus
GEAR_GUARD_DAILY_LIMIT_HIT: GearGuardDailyLimitStatus
CCC_PASSIVE_PERMISSION_STATUS_UNRECOGNIZED: CccPassivePermissionStatus
CCC_PASSIVE_PERMISSION_STATUS_SNA: CccPassivePermissionStatus
CCC_PASSIVE_PERMISSION_STATUS_ENABLED: CccPassivePermissionStatus
CCC_PASSIVE_PERMISSION_STATUS_DISABLED: CccPassivePermissionStatus

class Geofence(_message.Message):
    __slots__ = ("type", "name")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    type: GeofenceType
    name: str
    def __init__(self, type: _Optional[_Union[GeofenceType, str]] = ..., name: _Optional[str] = ...) -> None: ...

class FavoriteGeofences(_message.Message):
    __slots__ = ("favorites",)
    FAVORITES_FIELD_NUMBER: _ClassVar[int]
    favorites: _containers.RepeatedCompositeFieldContainer[Geofence]
    def __init__(self, favorites: _Optional[_Iterable[_Union[Geofence, _Mapping]]] = ...) -> None: ...

class GearGuardStreamingInVehicleConsent(_message.Message):
    __slots__ = ("user_consent",)
    USER_CONSENT_FIELD_NUMBER: _ClassVar[int]
    user_consent: GearGuardConsentStatus
    def __init__(self, user_consent: _Optional[_Union[GearGuardConsentStatus, str]] = ...) -> None: ...

class GearGuardStreamingDailyLimit(_message.Message):
    __slots__ = ("daily_limit", "next_reset_time_unix_sec")
    DAILY_LIMIT_FIELD_NUMBER: _ClassVar[int]
    NEXT_RESET_TIME_UNIX_SEC_FIELD_NUMBER: _ClassVar[int]
    daily_limit: GearGuardDailyLimitStatus
    next_reset_time_unix_sec: int
    def __init__(self, daily_limit: _Optional[_Union[GearGuardDailyLimitStatus, str]] = ..., next_reset_time_unix_sec: _Optional[int] = ...) -> None: ...

class PassiveEntrySetting(_message.Message):
    __slots__ = ("hold_time_duration_seconds",)
    HOLD_TIME_DURATION_SECONDS_FIELD_NUMBER: _ClassVar[int]
    hold_time_duration_seconds: int
    def __init__(self, hold_time_duration_seconds: _Optional[int] = ...) -> None: ...

class PassiveEntryStatus(_message.Message):
    __slots__ = ("allow_passive_entry_via_bluetooth_while_in_ccc", "ccc_passive_permission_status")
    ALLOW_PASSIVE_ENTRY_VIA_BLUETOOTH_WHILE_IN_CCC_FIELD_NUMBER: _ClassVar[int]
    CCC_PASSIVE_PERMISSION_STATUS_FIELD_NUMBER: _ClassVar[int]
    allow_passive_entry_via_bluetooth_while_in_ccc: bool
    ccc_passive_permission_status: CccPassivePermissionStatus
    def __init__(self, allow_passive_entry_via_bluetooth_while_in_ccc: bool = ..., ccc_passive_permission_status: _Optional[_Union[CccPassivePermissionStatus, str]] = ...) -> None: ...
