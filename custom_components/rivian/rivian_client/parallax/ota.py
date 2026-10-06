"""Decoders for `ota.*` topics: the deployment state and install schedules."""

from __future__ import annotations

from typing import Any, Final

from .core import RVMDecoder
from .proto import ota_pb2

_OTA_SOFTWARE_CATEGORY_FIRMWARE: Final = 1
_OTA_STATUS: Final[dict[int, str]] = {
    1: "IDLE",
    2: "READY_TO_DOWNLOAD",
    3: "FAULT",
    4: "CONNECTION_LOST",
    5: "INSTALL_COUNTDOWN",
    6: "PREPARING",
    7: "DOWNLOADING",
    8: "READY_TO_INSTALL",
    9: "SCHEDULED_TO_INSTALL",
    10: "AWAITING_INSTALL",
    11: "INSTALLING",
    12: "INSTALL_SUCCESS",
    13: "DOWNLOAD_FAILED",
    14: "INSTALL_FAILED",
}
_OTA_CURRENT_STATUS: Final[dict[int, str]] = {
    1: "INSTALL_SUCCESS",
    2: "INSTALL_FAILED",
    3: "INSTALL_UNABLE_TO_START",
}


def _gql_case(name: str) -> str:
    """READY_TO_INSTALL -> Ready_To_Install, the GraphQL path's casing."""
    return "_".join(word.capitalize() for word in name.lower().split("_"))


def _ota_version(
    version: ota_pb2.DeploymentState.Version, prefix: str
) -> dict[str, Any]:
    """The app's software version message, as the gateway's field names.

    software_version_id has no gateway field.
    """
    suffixes = {
        "version_string": "",
        "version_year": "Year",
        "version_build": "Week",
        "version_number": "Number",
        "build_id": "GitHash",
    }
    return {
        prefix + suffix: getattr(version, field)
        for field, suffix in suffixes.items()
        if version.HasField(field)
    }


def _ota_progress(progress: ota_pb2.DeploymentState.Progress) -> dict[str, Any]:
    """`ota_progress` as the gateway's ota* fields.

    install_ready is a bool the app turns into the gateway's own strings,
    "ota_available" / "ota_not_available" (FOLLOWUP_S45.md, uf7.java:1778).
    proto3 omits False, so a progress message without it is not ready.
    progress_percent is a oneof member in the app, so it is sent even at 0.
    """
    out: dict[str, Any] = {
        "otaInstallReady": "ota_available"
        if progress.install_ready
        else "ota_not_available"
    }
    if progress.phase in _OTA_STATUS:
        out["otaStatus"] = _gql_case(_OTA_STATUS[progress.phase])
    if progress.current_status in _OTA_CURRENT_STATUS:
        out["otaCurrentStatus"] = _gql_case(
            _OTA_CURRENT_STATUS[progress.current_status]
        )
    if progress.download_progress.HasField("progress_percent"):
        out["otaDownloadProgress"] = progress.download_progress.progress_percent
    if progress.install_progress.HasField("progress_percent"):
        out["otaInstallProgress"] = progress.install_progress.progress_percent
    return out


@RVMDecoder.register(ota_pb2.DeploymentState, "ota.deployment.state")
def decode_ota_deployment_state(m: ota_pb2.DeploymentState) -> dict[str, Any]:
    """Decode ota.deployment.state -- `r1e` (bound, 3.16.0).

    Repeated #1 `softwares`, one per category; only FIRMWARE feeds the ota*
    fields (HD maps and vehicle config have none). Within it: #2 the installed
    version, #4 `available_ota` with its own #2 version and #5 progress.

    Values use the gateway's casing (`Ready_To_Install`), which update.py
    compares against. Fields the app has no unit or vocabulary for -- install
    time, duration, OTA type -- are not emitted.

    Returns dict with keys, each only when sent:
        - otaCurrentVersion, otaCurrentVersionYear/Week/Number/GitHash
        - otaAvailableVersion, otaAvailableVersionYear/Week/Number/GitHash
        - otaStatus, otaCurrentStatus, otaDownloadProgress, otaInstallProgress,
          otaInstallReady ("ota_available" / "ota_not_available")
    """
    for deployment in m.deployment:
        if deployment.software_category != _OTA_SOFTWARE_CATEGORY_FIRMWARE:
            continue
        result: dict[str, Any] = {}
        if deployment.HasField("version"):
            result |= _ota_version(deployment.version, "otaCurrentVersion")
        available = deployment.progress_wrapper
        if available.HasField("target_version"):
            result |= _ota_version(available.target_version, "otaAvailableVersion")
        if available.HasField("progress"):
            result |= _ota_progress(available.progress)
        return result
    return {}


@RVMDecoder.register(ota_pb2.VehicleOtaState, "ota.ota_state.vehicle_ota_state")
def decode_vehicle_ota_state(m: ota_pb2.VehicleOtaState) -> dict[str, Any]:
    """Decode ota.ota_state.vehicle_ota_state (name-match: `ugm`).

    #1 id (string), #2 install_time_epoch (Timestamp). The capture carries only
    the id, the literal "VehicleOTAState", so it decodes to {}.

    Returns dict with keys:
        - otaOneTimeInstallTime: int (epoch seconds), when sent
    """
    if m.scheduled_install.HasField("seconds"):
        return {"otaOneTimeInstallTime": m.scheduled_install.seconds}
    return {}


@RVMDecoder.register(
    ota_pb2.OtaConfig,
    "ota.user_schedule.ota_config",
    empty_payload=True,
)
def decode_ota_config(m: ota_pb2.OtaConfig) -> dict[str, Any]:
    """Decode ota.user_schedule.ota_config (name-match: `rfe`).

    Repeated #1 schedules {#1 id, #2 isenabled, #3 repeatsdaily {#1 startsatmin,
    #2 geofence {#1 location}}, #4 singleoccurrence {#1 startsatutc}}.

    Returns dict with keys:
        - otaInstallSchedules: list[dict] -- enabled, and either
          dailyStartMinute (minutes after midnight) or startsAt (epoch seconds)
    """
    schedules: list[dict[str, Any]] = []
    for schedule in m.schedule:
        entry: dict[str, Any] = {"enabled": schedule.enabled}
        if schedule.HasField("repeats_daily"):
            entry["dailyStartMinute"] = schedule.repeats_daily.starts_at
        if schedule.single_occurrence.HasField("starts_at"):
            starts_at = schedule.single_occurrence.starts_at
            # None when the time has not been picked yet: the key says a
            # one-time install exists, the value says it has no time.
            entry["startsAt"] = (
                starts_at.seconds if starts_at.HasField("seconds") else None
            )
        schedules.append(entry)
    return {"otaInstallSchedules": schedules}
