from __future__ import annotations

import base64
from enum import StrEnum
from typing import Protocol
import uuid

from .proto import comfort_pb2


def encode_climate_hold_setting(hold_time_duration_seconds: int) -> bytes:
    if hold_time_duration_seconds < 0:
        raise ValueError(
            f"hold duration must not be negative: {hold_time_duration_seconds}"
        )
    return comfort_pb2.ClimateHoldSetting(
        hold_time_duration_seconds=hold_time_duration_seconds
    ).SerializeToString()


class SupportsSerializeToString(Protocol):
    def SerializeToString(self) -> bytes: ...


class RVMType(StrEnum):
    CLIMATE_HOLD_SETTING = "comfort.cabin.climate_hold_setting"
    CLIMATE_HOLD_STATUS = "comfort.cabin.climate_hold_status"
    VEHICLE_WHEELS = "vehicle.wheels.vehicle_wheels"
    OTA_SCHEDULE_CONFIGURATION = "ota.user_schedule.ota_config"


class ParallaxCommand:
    def __init__(self, rvm: RVMType, payload: bytes, command_id: str | None = None):
        self.rvm = rvm
        self.payload_b64 = base64.b64encode(payload).decode() if payload else ""
        self.command_id = command_id or str(uuid.uuid4())

    @property
    def name(self) -> str:
        return f"parallax_{self.rvm}"

    @classmethod
    def from_protobuf(
        cls,
        rvm: RVMType,
        message: SupportsSerializeToString,
        command_id: str | None = None,
    ) -> ParallaxCommand:
        payload = message.SerializeToString()
        return cls(rvm, payload, command_id)


def build_climate_status_query() -> ParallaxCommand:
    return ParallaxCommand(RVMType.CLIMATE_HOLD_STATUS, b"")


def build_climate_hold_command(duration_minutes: int = 120) -> ParallaxCommand:
    payload = encode_climate_hold_setting(duration_minutes * 60)

    return ParallaxCommand(RVMType.CLIMATE_HOLD_SETTING, payload)


def build_vehicle_wheels_query() -> ParallaxCommand:
    return ParallaxCommand(RVMType.VEHICLE_WHEELS, b"")


def build_ota_schedule_query() -> ParallaxCommand:
    return ParallaxCommand(RVMType.OTA_SCHEDULE_CONFIGURATION, b"")
