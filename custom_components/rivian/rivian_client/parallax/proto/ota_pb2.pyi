from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DeploymentState(_message.Message):
    __slots__ = ("deployment",)
    class SoftwareCategory(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        SOFTWARE_CATEGORY_UNSPECIFIED: _ClassVar[DeploymentState.SoftwareCategory]
        SOFTWARE_CATEGORY_FIRMWARE: _ClassVar[DeploymentState.SoftwareCategory]
        SOFTWARE_CATEGORY_HD_MAPS: _ClassVar[DeploymentState.SoftwareCategory]
        SOFTWARE_CATEGORY_VEHICLE_CONFIG: _ClassVar[DeploymentState.SoftwareCategory]
    SOFTWARE_CATEGORY_UNSPECIFIED: DeploymentState.SoftwareCategory
    SOFTWARE_CATEGORY_FIRMWARE: DeploymentState.SoftwareCategory
    SOFTWARE_CATEGORY_HD_MAPS: DeploymentState.SoftwareCategory
    SOFTWARE_CATEGORY_VEHICLE_CONFIG: DeploymentState.SoftwareCategory
    class DeploymentIntent(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        DEPLOYMENT_INTENT_UNSPECIFIED: _ClassVar[DeploymentState.DeploymentIntent]
        DEPLOYMENT_INTENT_PERFORMANCE_UPGRADE: _ClassVar[DeploymentState.DeploymentIntent]
        DEPLOYMENT_INTENT_BUG_FIX: _ClassVar[DeploymentState.DeploymentIntent]
        DEPLOYMENT_INTENT_SECURITY_UPDATE: _ClassVar[DeploymentState.DeploymentIntent]
        DEPLOYMENT_INTENT_FEATURE_ADDITION: _ClassVar[DeploymentState.DeploymentIntent]
    DEPLOYMENT_INTENT_UNSPECIFIED: DeploymentState.DeploymentIntent
    DEPLOYMENT_INTENT_PERFORMANCE_UPGRADE: DeploymentState.DeploymentIntent
    DEPLOYMENT_INTENT_BUG_FIX: DeploymentState.DeploymentIntent
    DEPLOYMENT_INTENT_SECURITY_UPDATE: DeploymentState.DeploymentIntent
    DEPLOYMENT_INTENT_FEATURE_ADDITION: DeploymentState.DeploymentIntent
    class CurrentStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        CURRENT_STATUS_UNSPECIFIED: _ClassVar[DeploymentState.CurrentStatus]
        CURRENT_STATUS_INSTALL_SUCCESS: _ClassVar[DeploymentState.CurrentStatus]
        CURRENT_STATUS_INSTALL_FAILED: _ClassVar[DeploymentState.CurrentStatus]
        CURRENT_STATUS_INSTALL_UNABLE_TO_START: _ClassVar[DeploymentState.CurrentStatus]
    CURRENT_STATUS_UNSPECIFIED: DeploymentState.CurrentStatus
    CURRENT_STATUS_INSTALL_SUCCESS: DeploymentState.CurrentStatus
    CURRENT_STATUS_INSTALL_FAILED: DeploymentState.CurrentStatus
    CURRENT_STATUS_INSTALL_UNABLE_TO_START: DeploymentState.CurrentStatus
    class OtaPhase(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        OTA_PHASE_UNSPECIFIED: _ClassVar[DeploymentState.OtaPhase]
        OTA_PHASE_IDLE: _ClassVar[DeploymentState.OtaPhase]
        OTA_PHASE_READY_TO_DOWNLOAD: _ClassVar[DeploymentState.OtaPhase]
        OTA_PHASE_FAULT: _ClassVar[DeploymentState.OtaPhase]
        OTA_PHASE_CONNECTION_LOST: _ClassVar[DeploymentState.OtaPhase]
        OTA_PHASE_INSTALL_COUNTDOWN: _ClassVar[DeploymentState.OtaPhase]
        OTA_PHASE_PREPARING: _ClassVar[DeploymentState.OtaPhase]
        OTA_PHASE_DOWNLOADING: _ClassVar[DeploymentState.OtaPhase]
        OTA_PHASE_READY_TO_INSTALL: _ClassVar[DeploymentState.OtaPhase]
        OTA_PHASE_SCHEDULED_TO_INSTALL: _ClassVar[DeploymentState.OtaPhase]
        OTA_PHASE_AWAITING_INSTALL: _ClassVar[DeploymentState.OtaPhase]
        OTA_PHASE_INSTALLING: _ClassVar[DeploymentState.OtaPhase]
        OTA_PHASE_INSTALL_SUCCESS: _ClassVar[DeploymentState.OtaPhase]
        OTA_PHASE_DOWNLOAD_FAILED: _ClassVar[DeploymentState.OtaPhase]
        OTA_PHASE_INSTALL_FAILED: _ClassVar[DeploymentState.OtaPhase]
    OTA_PHASE_UNSPECIFIED: DeploymentState.OtaPhase
    OTA_PHASE_IDLE: DeploymentState.OtaPhase
    OTA_PHASE_READY_TO_DOWNLOAD: DeploymentState.OtaPhase
    OTA_PHASE_FAULT: DeploymentState.OtaPhase
    OTA_PHASE_CONNECTION_LOST: DeploymentState.OtaPhase
    OTA_PHASE_INSTALL_COUNTDOWN: DeploymentState.OtaPhase
    OTA_PHASE_PREPARING: DeploymentState.OtaPhase
    OTA_PHASE_DOWNLOADING: DeploymentState.OtaPhase
    OTA_PHASE_READY_TO_INSTALL: DeploymentState.OtaPhase
    OTA_PHASE_SCHEDULED_TO_INSTALL: DeploymentState.OtaPhase
    OTA_PHASE_AWAITING_INSTALL: DeploymentState.OtaPhase
    OTA_PHASE_INSTALLING: DeploymentState.OtaPhase
    OTA_PHASE_INSTALL_SUCCESS: DeploymentState.OtaPhase
    OTA_PHASE_DOWNLOAD_FAILED: DeploymentState.OtaPhase
    OTA_PHASE_INSTALL_FAILED: DeploymentState.OtaPhase
    class Deployment(_message.Message):
        __slots__ = ("software_category", "version", "progress_wrapper")
        SOFTWARE_CATEGORY_FIELD_NUMBER: _ClassVar[int]
        VERSION_FIELD_NUMBER: _ClassVar[int]
        PROGRESS_WRAPPER_FIELD_NUMBER: _ClassVar[int]
        software_category: DeploymentState.SoftwareCategory
        version: DeploymentState.Version
        progress_wrapper: DeploymentState.ProgressWrapper
        def __init__(self, software_category: _Optional[_Union[DeploymentState.SoftwareCategory, str]] = ..., version: _Optional[_Union[DeploymentState.Version, _Mapping]] = ..., progress_wrapper: _Optional[_Union[DeploymentState.ProgressWrapper, _Mapping]] = ...) -> None: ...
    class Version(_message.Message):
        __slots__ = ("version_string", "version_year", "version_build", "version_number", "build_id")
        VERSION_STRING_FIELD_NUMBER: _ClassVar[int]
        VERSION_YEAR_FIELD_NUMBER: _ClassVar[int]
        VERSION_BUILD_FIELD_NUMBER: _ClassVar[int]
        VERSION_NUMBER_FIELD_NUMBER: _ClassVar[int]
        BUILD_ID_FIELD_NUMBER: _ClassVar[int]
        version_string: str
        version_year: int
        version_build: int
        version_number: int
        build_id: str
        def __init__(self, version_string: _Optional[str] = ..., version_year: _Optional[int] = ..., version_build: _Optional[int] = ..., version_number: _Optional[int] = ..., build_id: _Optional[str] = ...) -> None: ...
    class ProgressWrapper(_message.Message):
        __slots__ = ("target_version", "ota_type", "progress", "install_time", "install_tod", "skip_count", "skip_allowed", "deployment_intent", "is_active")
        TARGET_VERSION_FIELD_NUMBER: _ClassVar[int]
        OTA_TYPE_FIELD_NUMBER: _ClassVar[int]
        PROGRESS_FIELD_NUMBER: _ClassVar[int]
        INSTALL_TIME_FIELD_NUMBER: _ClassVar[int]
        INSTALL_TOD_FIELD_NUMBER: _ClassVar[int]
        SKIP_COUNT_FIELD_NUMBER: _ClassVar[int]
        SKIP_ALLOWED_FIELD_NUMBER: _ClassVar[int]
        DEPLOYMENT_INTENT_FIELD_NUMBER: _ClassVar[int]
        IS_ACTIVE_FIELD_NUMBER: _ClassVar[int]
        target_version: DeploymentState.Version
        ota_type: int
        progress: DeploymentState.Progress
        install_time: int
        install_tod: int
        skip_count: int
        skip_allowed: bool
        deployment_intent: DeploymentState.DeploymentIntent
        is_active: bool
        def __init__(self, target_version: _Optional[_Union[DeploymentState.Version, _Mapping]] = ..., ota_type: _Optional[int] = ..., progress: _Optional[_Union[DeploymentState.Progress, _Mapping]] = ..., install_time: _Optional[int] = ..., install_tod: _Optional[int] = ..., skip_count: _Optional[int] = ..., skip_allowed: bool = ..., deployment_intent: _Optional[_Union[DeploymentState.DeploymentIntent, str]] = ..., is_active: bool = ...) -> None: ...
    class Progress(_message.Message):
        __slots__ = ("phase", "current_status", "download_progress", "install_progress", "time_remaining", "install_ready", "status_acknowledge", "install_duration")
        class Progress100(_message.Message):
            __slots__ = ("progress_percent",)
            PROGRESS_PERCENT_FIELD_NUMBER: _ClassVar[int]
            progress_percent: int
            def __init__(self, progress_percent: _Optional[int] = ...) -> None: ...
        PHASE_FIELD_NUMBER: _ClassVar[int]
        CURRENT_STATUS_FIELD_NUMBER: _ClassVar[int]
        DOWNLOAD_PROGRESS_FIELD_NUMBER: _ClassVar[int]
        INSTALL_PROGRESS_FIELD_NUMBER: _ClassVar[int]
        TIME_REMAINING_FIELD_NUMBER: _ClassVar[int]
        INSTALL_READY_FIELD_NUMBER: _ClassVar[int]
        STATUS_ACKNOWLEDGE_FIELD_NUMBER: _ClassVar[int]
        INSTALL_DURATION_FIELD_NUMBER: _ClassVar[int]
        phase: DeploymentState.OtaPhase
        current_status: DeploymentState.CurrentStatus
        download_progress: DeploymentState.Progress.Progress100
        install_progress: DeploymentState.Progress.Progress100
        time_remaining: int
        install_ready: bool
        status_acknowledge: int
        install_duration: int
        def __init__(self, phase: _Optional[_Union[DeploymentState.OtaPhase, str]] = ..., current_status: _Optional[_Union[DeploymentState.CurrentStatus, str]] = ..., download_progress: _Optional[_Union[DeploymentState.Progress.Progress100, _Mapping]] = ..., install_progress: _Optional[_Union[DeploymentState.Progress.Progress100, _Mapping]] = ..., time_remaining: _Optional[int] = ..., install_ready: bool = ..., status_acknowledge: _Optional[int] = ..., install_duration: _Optional[int] = ...) -> None: ...
    DEPLOYMENT_FIELD_NUMBER: _ClassVar[int]
    deployment: _containers.RepeatedCompositeFieldContainer[DeploymentState.Deployment]
    def __init__(self, deployment: _Optional[_Iterable[_Union[DeploymentState.Deployment, _Mapping]]] = ...) -> None: ...

class OtaConfig(_message.Message):
    __slots__ = ("schedule",)
    class Schedule(_message.Message):
        __slots__ = ("enabled", "repeats_daily", "single_occurrence")
        ENABLED_FIELD_NUMBER: _ClassVar[int]
        REPEATS_DAILY_FIELD_NUMBER: _ClassVar[int]
        SINGLE_OCCURRENCE_FIELD_NUMBER: _ClassVar[int]
        enabled: bool
        repeats_daily: OtaConfig.RepeatsDaily
        single_occurrence: OtaConfig.SingleOccurrence
        def __init__(self, enabled: bool = ..., repeats_daily: _Optional[_Union[OtaConfig.RepeatsDaily, _Mapping]] = ..., single_occurrence: _Optional[_Union[OtaConfig.SingleOccurrence, _Mapping]] = ...) -> None: ...
    class RepeatsDaily(_message.Message):
        __slots__ = ("starts_at",)
        STARTS_AT_FIELD_NUMBER: _ClassVar[int]
        starts_at: int
        def __init__(self, starts_at: _Optional[int] = ...) -> None: ...
    class SingleOccurrence(_message.Message):
        __slots__ = ("starts_at",)
        class StartsAt(_message.Message):
            __slots__ = ("seconds",)
            SECONDS_FIELD_NUMBER: _ClassVar[int]
            seconds: int
            def __init__(self, seconds: _Optional[int] = ...) -> None: ...
        STARTS_AT_FIELD_NUMBER: _ClassVar[int]
        starts_at: OtaConfig.SingleOccurrence.StartsAt
        def __init__(self, starts_at: _Optional[_Union[OtaConfig.SingleOccurrence.StartsAt, _Mapping]] = ...) -> None: ...
    SCHEDULE_FIELD_NUMBER: _ClassVar[int]
    schedule: _containers.RepeatedCompositeFieldContainer[OtaConfig.Schedule]
    def __init__(self, schedule: _Optional[_Iterable[_Union[OtaConfig.Schedule, _Mapping]]] = ...) -> None: ...

class VehicleOtaState(_message.Message):
    __slots__ = ("scheduled_install",)
    class ScheduledInstall(_message.Message):
        __slots__ = ("seconds",)
        SECONDS_FIELD_NUMBER: _ClassVar[int]
        seconds: int
        def __init__(self, seconds: _Optional[int] = ...) -> None: ...
    SCHEDULED_INSTALL_FIELD_NUMBER: _ClassVar[int]
    scheduled_install: VehicleOtaState.ScheduledInstall
    def __init__(self, scheduled_install: _Optional[_Union[VehicleOtaState.ScheduledInstall, _Mapping]] = ...) -> None: ...
