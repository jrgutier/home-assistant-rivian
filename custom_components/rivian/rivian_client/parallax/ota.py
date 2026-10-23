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
    return "_".join(word.capitalize() for word in name.lower().split("_"))


def _ota_version(
    version: ota_pb2.DeploymentState.Version, prefix: str
) -> dict[str, Any]:
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
    if m.scheduled_install.HasField("seconds"):
        return {"otaOneTimeInstallTime": m.scheduled_install.seconds}
    return {}


@RVMDecoder.register(
    ota_pb2.OtaConfig,
    "ota.user_schedule.ota_config",
    empty_payload=True,
)
def decode_ota_config(m: ota_pb2.OtaConfig) -> dict[str, Any]:
    schedules: list[dict[str, Any]] = []
    for schedule in m.schedule:
        entry: dict[str, Any] = {"enabled": schedule.enabled}
        if schedule.HasField("repeats_daily"):
            entry["dailyStartMinute"] = schedule.repeats_daily.starts_at
        if schedule.single_occurrence.HasField("starts_at"):
            starts_at = schedule.single_occurrence.starts_at
            entry["startsAt"] = (
                starts_at.seconds if starts_at.HasField("seconds") else None
            )
        schedules.append(entry)
    return {"otaInstallSchedules": schedules}
