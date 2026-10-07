"""Outbound Parallax operations: the RVM catalogue and command builders.

The write half, which this fork added; upstream is read-only. The RVMType
catalogue is reverse engineered from the Android app (EnumC6207c.java).

Every RVM here can be *read*, but Rivian currently accepts only one as a *write*
(comfort.cabin.climate_hold_setting). The other builders are retained until the
entities that call them are removed.
"""

from __future__ import annotations

import base64
from enum import StrEnum
from typing import Protocol
import uuid

from .proto import comfort_pb2


def encode_climate_hold_setting(hold_time_duration_seconds: int) -> bytes:
    """Encode a ClimateHoldSetting payload.

    This is the only RVM payload the integration ever encodes. The bytes are
    held to what the hand-rolled encoder produced before s49
    (tests/client/fixtures/parallax_golden/send_path.json), and twice to
    reality -- 08ac02 came back from a real vehicle after a five-minute hold,
    and 08a038 (7200s) is recorded in SENDVEHICLEOPERATION_TEST_RESULTS.md.

    Zero encodes to NOTHING: proto3 omits a field at its default, and the vehicle
    reports an unconfigured hold as an empty payload.
    """
    if hold_time_duration_seconds < 0:
        raise ValueError(
            f"hold duration must not be negative: {hold_time_duration_seconds}"
        )
    return comfort_pb2.ClimateHoldSetting(
        hold_time_duration_seconds=hold_time_duration_seconds
    ).SerializeToString()


class SupportsSerializeToString(Protocol):
    """Anything that can serialise itself to protobuf wire bytes.

    Structural, so from_protobuf takes a generated message and the plain
    classes in proto/vehicle_operation.py alike.
    """

    def SerializeToString(self) -> bytes: ...


class RVMType(StrEnum):
    """Remote Vehicle Module types this client ships.

    Rivian's Android app (EnumC6207c.java) declares 18. Only four are accepted by
    sendVehicleOperation -- the rest return INTERNAL_SERVER_ERROR in BOTH
    directions, recorded in docs/development/SENDVEHICLEOPERATION_TEST_RESULTS.md
    -- so the other 14 were pruned in s09a along with their builders and entities.
    Re-add one only after a live test shows the server accepts it.
    """

    # The one server-verified WRITE.
    CLIMATE_HOLD_SETTING = "comfort.cabin.climate_hold_setting"
    # Verified reads.
    CLIMATE_HOLD_STATUS = "comfort.cabin.climate_hold_status"
    VEHICLE_WHEELS = "vehicle.wheels.vehicle_wheels"
    # Accepted by the server, but it returns an empty payload unless the owner has
    # configured a schedule, so no entity ships for it (see RVM_FIXTURES.md).
    OTA_SCHEDULE_CONFIGURATION = "ota.user_schedule.ota_config"


class ParallaxCommand:
    """Parallax command wrapper for cloud-based vehicle operations.

    Attributes:
        rvm: Remote Vehicle Module type
        payload_b64: Base64-encoded protobuf payload
        command_id: Unique command identifier
    """

    def __init__(self, rvm: RVMType, payload: bytes, command_id: str | None = None):
        """Initialize ParallaxCommand.

        Args:
            rvm: RVM type identifier
            payload: Protobuf message bytes (operation-specific)
            command_id: Optional command UUID (generated if not provided)
        """
        self.rvm = rvm
        self.payload_b64 = base64.b64encode(payload).decode() if payload else ""
        self.command_id = command_id or str(uuid.uuid4())

    @property
    def name(self) -> str:
        """Get command name for logging/debugging."""
        return f"parallax_{self.rvm}"

    @classmethod
    def from_protobuf(
        cls,
        rvm: RVMType,
        message: SupportsSerializeToString,
        command_id: str | None = None,
    ) -> ParallaxCommand:
        """Create ParallaxCommand from a protobuf message.

        Args:
            rvm: RVM type identifier
            message: Protobuf message instance
            command_id: Optional command UUID

        Returns:
            ParallaxCommand instance with serialized message
        """
        payload = message.SerializeToString()
        return cls(rvm, payload, command_id)


# Helper functions for Phase 1 RVM types


def build_climate_status_query() -> ParallaxCommand:
    """Build a query for climate hold status.

    Returns:
        ParallaxCommand for RVM #14 (CLIMATE_HOLD_STATUS)

    Example:
        >>> cmd = build_climate_status_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Read operations use empty payload
    return ParallaxCommand(RVMType.CLIMATE_HOLD_STATUS, b"")


def build_climate_hold_command(duration_minutes: int = 120) -> ParallaxCommand:
    """Build a climate hold command.

    Args:
        duration_minutes: Hold duration in minutes (converted to seconds)

    Returns:
        ParallaxCommand for RVM #12 (CLIMATE_HOLD_SETTING)

    Note:
        Based on APK analysis, ClimateHoldSetting only has one field:
        hold_time_duration_seconds. Temperature and enabled state are not
        part of the protobuf message - they may be controlled separately
        via GraphQL or other commands.

    Example:
        >>> cmd = build_climate_hold_command(120)  # 2 hours
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    payload = encode_climate_hold_setting(duration_minutes * 60)

    return ParallaxCommand(RVMType.CLIMATE_HOLD_SETTING, payload)


def build_vehicle_wheels_query() -> ParallaxCommand:
    """Build a query for vehicle wheels configuration.

    Returns:
        ParallaxCommand for RVM #10 (VEHICLE_WHEELS)

    Example:
        >>> cmd = build_vehicle_wheels_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Read operations use empty payload
    return ParallaxCommand(RVMType.VEHICLE_WHEELS, b"")


def build_ota_schedule_query() -> ParallaxCommand:
    """Build a query for OTA schedule configuration.

    Returns:
        ParallaxCommand for RVM #5 (OTA_SCHEDULE_CONFIGURATION)

    Example:
        >>> cmd = build_ota_schedule_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Read operations use empty payload
    return ParallaxCommand(RVMType.OTA_SCHEDULE_CONFIGURATION, b"")
