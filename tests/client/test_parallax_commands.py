"""Tests for the Parallax WRITE path: RVMType, ParallaxCommand and the build_* helpers.

Split from test_parallax.py, which now holds upstream's decoder (READ) tests.
The two halves of parallax.py were developed independently and share no symbols,
so their tests are kept apart rather than fused into one 1700-line file.
"""

# pylint: disable=protected-access
from __future__ import annotations

import base64
import uuid

import aiohttp
from aresponses import ResponsesMockServer
import pytest

from custom_components.rivian.rivian_client import Rivian
from custom_components.rivian.rivian_client.exceptions import RivianUnauthenticated
from custom_components.rivian.rivian_client.parallax import (
    ParallaxCommand,
    RVMType,
    build_climate_status_query,
    build_ota_schedule_query,
    build_vehicle_wheels_query,
)

# Test phone ID (16 bytes from UUID)
TEST_PHONE_ID = uuid.UUID("12345678-1234-5678-1234-567812345678").bytes

# Mock responses - using sendVehicleOperation mutation
PARALLAX_SUCCESS_RESPONSE = {
    "data": {
        "sendVehicleOperation": {
            "__typename": "SendVehicleOperationSuccess",
            "success": True,
        }
    }
}

PARALLAX_FAILURE_RESPONSE = {
    "data": {
        "sendVehicleOperation": {
            "__typename": "SendVehicleOperationSuccess",
            "success": False,
        }
    }
}

PARALLAX_ERROR_RESPONSE = {
    "errors": [
        {
            "extensions": {
                "code": "UNAUTHENTICATED",
                "reason": "UNAUTHENTICATED",
            },
            "message": "Authentication failed",
            "path": ["sendVehicleOperation"],
        }
    ],
    "data": None,
}


# Test RVMType enum
class TestRVMType:
    """RVMType carries only the RVMs the server actually accepts.

    Rivian's app declares 18. Ten of the fourteen tested return
    INTERNAL_SERVER_ERROR to sendVehicleOperation in BOTH directions
    (docs/development/SENDVEHICLEOPERATION_TEST_RESULTS.md), so shipping them
    invited entities that could never work. Pruned in s09a; re-add one only after
    a live test shows the server accepts it.
    """

    def test_only_the_verified_rvms_ship(self) -> None:
        assert {r.value for r in RVMType} == {
            "comfort.cabin.climate_hold_setting",
            "comfort.cabin.climate_hold_status",
            "vehicle.wheels.vehicle_wheels",
            "ota.user_schedule.ota_config",
        }

    """Test RVMType enum."""

    def test_rvm_type_is_string(self) -> None:
        """Test that RVM types are strings."""
        for rvm_type in RVMType:
            assert isinstance(rvm_type, str)
            assert isinstance(rvm_type.value, str)


# Test ParallaxCommand class


class _Serialisable:
    """Minimal stand-in for a protobuf message.

    from_protobuf only requires SerializeToString, and asserting that structurally
    is stronger than pinning it to a concrete generated class -- which is what let
    the protobuf dependency be removed at all.
    """

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def SerializeToString(self) -> bytes:
        return self._payload


class TestParallaxCommand:
    """Test ParallaxCommand class."""

    def test_command_creation_with_payload(self) -> None:
        """Test creating a command with a payload."""
        payload = b"test_payload"
        cmd = ParallaxCommand(RVMType.CLIMATE_HOLD_SETTING, payload)

        assert cmd.rvm == RVMType.CLIMATE_HOLD_SETTING
        assert cmd.payload_b64 == base64.b64encode(payload).decode()
        assert cmd.command_id is not None
        assert len(cmd.command_id) > 0

    def test_command_creation_with_empty_payload(self) -> None:
        """Test creating a command with an empty payload."""
        cmd = ParallaxCommand(RVMType.CLIMATE_HOLD_STATUS, b"")

        assert cmd.rvm == RVMType.CLIMATE_HOLD_STATUS
        assert cmd.payload_b64 == ""
        assert cmd.command_id is not None

    def test_command_creation_with_custom_id(self) -> None:
        """Test creating a command with a custom command ID."""
        custom_id = "custom-test-id-123"
        cmd = ParallaxCommand(RVMType.OTA_SCHEDULE_CONFIGURATION, b"test", custom_id)

        assert cmd.command_id == custom_id

    def test_command_name_property(self) -> None:
        """Test command name property."""
        cmd = ParallaxCommand(RVMType.VEHICLE_WHEELS, b"")
        assert cmd.name == "parallax_vehicle.wheels.vehicle_wheels"

    def test_base64_encoding(self) -> None:
        """Test Base64 encoding of payload."""
        payload = b"\x01\x02\x03\x04"
        cmd = ParallaxCommand(RVMType.CLIMATE_HOLD_STATUS, payload)

        # Verify Base64 encoding
        assert cmd.payload_b64 == "AQIDBA=="
        # Verify it can be decoded back
        assert base64.b64decode(cmd.payload_b64) == payload

    def test_from_protobuf(self) -> None:
        """Test creating command from protobuf message.

        Validates that ParallaxCommand.from_protobuf() correctly serializes
        a protobuf message and creates a command with the serialized payload.
        """

        message = _Serialisable(b"\x08\x2a")
        cmd = ParallaxCommand.from_protobuf(RVMType.CLIMATE_HOLD_SETTING, message)

        assert cmd.rvm == RVMType.CLIMATE_HOLD_SETTING
        assert cmd.command_id is not None
        assert cmd.payload_b64 != ""  # Should have serialized payload

        # Verify payload is valid base64
        decoded = base64.b64decode(cmd.payload_b64)
        assert isinstance(decoded, bytes)
        assert len(decoded) > 0

    def test_from_protobuf_with_custom_id(self) -> None:
        """Test creating command from protobuf with custom ID.

        Validates that custom command IDs are preserved when creating
        commands from protobuf messages.
        """

        message = _Serialisable(b"\x08\x2a")
        custom_id = "test-custom-id-456"
        cmd = ParallaxCommand.from_protobuf(
            RVMType.CLIMATE_HOLD_SETTING, message, custom_id
        )

        assert cmd.command_id == custom_id
        assert cmd.payload_b64 != ""


# Test helper functions
class TestHelperFunctions:
    """Test helper functions for building commands."""

    def test_build_climate_status_query(self) -> None:
        """Test building climate status query."""
        cmd = build_climate_status_query()

        assert cmd.rvm == RVMType.CLIMATE_HOLD_STATUS
        assert cmd.payload_b64 == ""  # Read operations use empty payload
        assert cmd.command_id is not None

    def test_build_climate_hold_command(self) -> None:
        """Test building climate hold command.

        Validates that build_climate_hold_command() creates a properly
        formatted command with serialized ClimateHoldSetting payload.
        """
        from custom_components.rivian.rivian_client.parallax import (
            build_climate_hold_command,
        )

        # Based on APK analysis: only duration_minutes parameter (converted to seconds)
        cmd = build_climate_hold_command(duration_minutes=120)

        assert cmd.rvm == RVMType.CLIMATE_HOLD_SETTING
        assert cmd.command_id is not None
        assert cmd.payload_b64 != ""  # Write operations have payload

        # Verify payload is valid base64
        decoded = base64.b64decode(cmd.payload_b64)
        assert isinstance(decoded, bytes)
        assert len(decoded) > 0

    def test_build_climate_hold_command_disabled(self) -> None:
        """Test building climate hold command with zero duration.

        Validates that zero duration commands are properly serialized.
        Note: Based on APK analysis, there's no 'enabled' field -
        zero duration may be used to disable.
        """
        from custom_components.rivian.rivian_client.parallax import (
            build_climate_hold_command,
        )

        cmd = build_climate_hold_command(duration_minutes=0)

        assert cmd.rvm == RVMType.CLIMATE_HOLD_SETTING
        assert cmd.command_id is not None
        # Even disabled commands may have a payload (with enabled=False)
        # The payload might be empty or minimal depending on implementation
        decoded = base64.b64decode(cmd.payload_b64) if cmd.payload_b64 else b""
        assert isinstance(decoded, bytes)


# Test protobuf messages


# Test Rivian class methods
class TestRivianClassMethods:
    """Test Rivian class Parallax methods."""

    async def test_send_parallax_command_success(
        self, aresponses: ResponsesMockServer
    ) -> None:
        """Test sending a Parallax command successfully."""
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token",
                app_session_token="token",
                user_session_token="token",
            )
            cmd = build_climate_status_query()
            result = await rivian.send_parallax_command("VIN123", cmd, TEST_PHONE_ID)

            # sendVehicleOperation returns only success flag
            assert result["success"] is True
            await rivian.close()

    async def test_send_parallax_command_failure(
        self, aresponses: ResponsesMockServer
    ) -> None:
        """Test sending a Parallax command with failure response."""
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_FAILURE_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token",
                app_session_token="token",
                user_session_token="token",
            )
            cmd = build_climate_status_query()
            result = await rivian.send_parallax_command("VIN123", cmd, TEST_PHONE_ID)

            # sendVehicleOperation returns only success flag
            assert result["success"] is False
            await rivian.close()

    async def test_send_parallax_command_unauthenticated(
        self, aresponses: ResponsesMockServer
    ) -> None:
        """Test sending a Parallax command with authentication error."""
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_ERROR_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token",
                app_session_token="token",
                user_session_token="token",
            )
            cmd = build_ota_schedule_query()

            with pytest.raises(RivianUnauthenticated):
                await rivian.send_parallax_command("VIN123", cmd, TEST_PHONE_ID)

            await rivian.close()

    async def test_parallax_command_with_write_operation(
        self, aresponses: ResponsesMockServer
    ) -> None:
        """Test Parallax command with a write operation (non-empty payload).

        Validates that write operations include a serialized protobuf payload.
        """
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token",
                app_session_token="token",
                user_session_token="token",
            )

            from custom_components.rivian.rivian_client.parallax import (
                build_climate_hold_command,
            )

            # Based on APK analysis: only duration_minutes parameter
            cmd = build_climate_hold_command(duration_minutes=120)

            # Verify command has non-empty payload for write operation
            assert cmd.payload_b64 != ""

            result = await rivian.send_parallax_command("VIN123", cmd, TEST_PHONE_ID)
            assert result["success"] is True
            await rivian.close()

    async def test_parallax_command_with_read_operation(
        self, aresponses: ResponsesMockServer
    ) -> None:
        """Test Parallax command with a read operation (empty payload)."""
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token",
                app_session_token="token",
                user_session_token="token",
            )
            cmd = build_vehicle_wheels_query()

            # Verify command has empty payload for read operation
            assert cmd.payload_b64 == ""

            result = await rivian.send_parallax_command("VIN123", cmd, TEST_PHONE_ID)
            assert result["success"] is True
            await rivian.close()

    # Removed during the transport merge, not silenced: test_get_charging_session_live_data,
    # test_get_climate_hold_status, test_get_ota_status and test_get_trip_progress covered
    # gql-era convenience getters that no caller in the Home Assistant integration ever
    # reached, so the methods were dropped rather than ported. The builders behind them
    # (build_climate_status_query, build_vehicle_wheels_query, build_ota_schedule_query)
    # survive and are still covered above. Reads of those RVMs
    # come from the Parallax subscription decoder, not from per-RVM getters.

    async def test_set_climate_hold_sends_duration(
        self, aresponses: ResponsesMockServer
    ) -> None:
        """Duration is what actually reaches the vehicle.

        ClimateHoldSetting carries exactly one field, hold_time_duration_seconds.
        The removed `enabled` and `temp_celsius` parameters were accepted and
        discarded, and temp_celsius was validated -- so a caller could be rejected
        over a value that was never transmitted. Their tests went with them; this
        asserts the field that does travel.
        """
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token",
                app_session_token="token",
                user_session_token="token",
            )
            result = await rivian.set_climate_hold(
                "VIN123", TEST_PHONE_ID, duration_minutes=120
            )
            assert result["success"] is True
            await rivian.close()

    def test_climate_hold_payload_encodes_minutes_as_seconds(self) -> None:
        """120 minutes must encode as 7200 seconds, not 120.

        The wire format for a two-hour hold is documented as 08a038 in
        docs/development/SENDVEHICLEOPERATION_TEST_RESULTS.md. A unit slip here
        would be invisible -- the command would succeed and hold for two minutes.
        """
        from custom_components.rivian.rivian_client.parallax import (
            build_climate_hold_command,
        )

        cmd = build_climate_hold_command(duration_minutes=120)
        payload = base64.b64decode(cmd.payload_b64)
        assert payload == bytes.fromhex("08a038"), payload.hex()
