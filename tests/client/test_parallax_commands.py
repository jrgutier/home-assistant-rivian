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
from custom_components.rivian.rivian_client.proto.base import SessionCost, TimeOfDay
from custom_components.rivian.rivian_client.proto.charging import (
    ChargingScheduleTimeWindow,
    ChargingSessionLiveData,
)
from custom_components.rivian.rivian_client.proto.climate import (
    ClimateHoldSetting,
    ClimateHoldStatus,
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
        from custom_components.rivian.rivian_client.proto.climate import (
            ClimateHoldSetting,
        )

        setting = ClimateHoldSetting(
            enabled=True, duration_minutes=60, target_temp_celsius=22.0
        )
        cmd = ParallaxCommand.from_protobuf(RVMType.CLIMATE_HOLD_SETTING, setting)

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
        from custom_components.rivian.rivian_client.proto.base import TimeOfDay

        time = TimeOfDay(hour=10, minute=30)
        custom_id = "test-custom-id-456"
        cmd = ParallaxCommand.from_protobuf(
            RVMType.CLIMATE_HOLD_SETTING, time, custom_id
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
class TestProtobufMessages:
    """Test protobuf message classes."""

    def test_time_of_day_creation(self) -> None:
        """Test TimeOfDay message creation."""
        time = TimeOfDay(hour=10, minute=30)

        assert time.hour == 10
        assert time.minute == 30

    def test_time_of_day_to_dict(self) -> None:
        """Test TimeOfDay to_dict conversion."""
        time = TimeOfDay(hour=14, minute=45)
        time_dict = time.to_dict()

        assert time_dict == {"hour": 14, "minute": 45}

    def test_time_of_day_default(self) -> None:
        """Test TimeOfDay default values."""
        time = TimeOfDay()

        assert time.hour == 0
        assert time.minute == 0

    def test_session_cost_creation(self) -> None:
        """Test SessionCost message creation."""
        cost = SessionCost(amount=1250.0, currency="USD")

        assert cost.amount == 1250.0
        assert cost.currency == "USD"

    def test_session_cost_to_dict(self) -> None:
        """Test SessionCost to_dict conversion."""
        cost = SessionCost(amount=3500.0, currency="EUR")
        cost_dict = cost.to_dict()

        assert cost_dict == {"amount": 3500.0, "currency": "EUR"}

    def test_session_cost_default(self) -> None:
        """Test SessionCost default values."""
        cost = SessionCost()

        assert cost.amount == 0.0
        assert cost.currency == "USD"

    def test_climate_hold_setting_creation(self) -> None:
        """Test ClimateHoldSetting message creation."""
        setting = ClimateHoldSetting(
            enabled=True, duration_minutes=120, target_temp_celsius=22.0
        )

        assert setting.enabled is True
        assert setting.duration_minutes == 120
        assert setting.target_temp_celsius == 22.0

    def test_climate_hold_setting_to_dict(self) -> None:
        """Test ClimateHoldSetting to_dict conversion."""
        setting = ClimateHoldSetting(
            enabled=False, duration_minutes=60, target_temp_celsius=20.0
        )
        setting_dict = setting.to_dict()

        assert setting_dict == {
            "enabled": False,
            "duration_minutes": 60,
            "target_temp_celsius": 20.0,
        }

    def test_climate_hold_setting_serialization(self) -> None:
        """Test ClimateHoldSetting protobuf serialization.

        Validates that ClimateHoldSetting can be serialized to protobuf
        wire format and produces non-empty byte output.
        """
        setting = ClimateHoldSetting(
            enabled=True, duration_minutes=120, target_temp_celsius=22.0
        )
        serialized = setting.SerializeToString()

        assert isinstance(serialized, bytes)
        assert len(serialized) > 0

        # Test with all fields populated
        setting_full = ClimateHoldSetting(
            enabled=True, duration_minutes=180, target_temp_celsius=25.5
        )
        serialized_full = setting_full.SerializeToString()
        assert len(serialized_full) > 0

    def test_climate_hold_status_creation(self) -> None:
        """Test ClimateHoldStatus message creation."""
        status = ClimateHoldStatus(
            active=True,
            current_temp_celsius=20.5,
            target_temp_celsius=22.0,
            time_remaining_mins=45,
            mode="heating",
        )

        assert status.active is True
        assert status.current_temp_celsius == 20.5
        assert status.target_temp_celsius == 22.0
        assert status.time_remaining_mins == 45
        assert status.mode == "heating"

    def test_climate_hold_status_to_dict(self) -> None:
        """Test ClimateHoldStatus to_dict conversion."""
        status = ClimateHoldStatus(
            active=False,
            current_temp_celsius=25.0,
            target_temp_celsius=24.0,
            time_remaining_mins=0,
            mode="auto",
        )
        status_dict = status.to_dict()

        assert status_dict == {
            "active": False,
            "current_temp_celsius": 25.0,
            "target_temp_celsius": 24.0,
            "time_remaining_mins": 0,
            "mode": "auto",
        }

    def test_charging_session_live_data_creation(self) -> None:
        """Test ChargingSessionLiveData message creation."""
        data = ChargingSessionLiveData(
            total_kwh=45.5,
            pack_kwh=40.0,
            thermal_kwh=3.5,
            outlets_kwh=1.0,
            system_kwh=1.0,
            session_duration_mins=60,
            time_remaining_mins=30,
            range_added_kms=200,
            current_power=50.0,
            current_range_per_hour=250,
            is_free_session=False,
            charging_state=1,
        )

        assert data.total_kwh == 45.5
        assert data.pack_kwh == 40.0
        assert data.thermal_kwh == 3.5
        assert data.session_duration_mins == 60
        assert data.charging_state == 1

    def test_charging_session_live_data_to_dict(self) -> None:
        """Test ChargingSessionLiveData to_dict conversion."""
        cost = SessionCost(amount=1500.0, currency="USD")
        data = ChargingSessionLiveData(
            total_kwh=50.0,
            pack_kwh=45.0,
            session_cost=cost,
            is_free_session=False,
        )
        data_dict = data.to_dict()

        assert data_dict["total_kwh"] == 50.0
        assert data_dict["pack_kwh"] == 45.0
        assert data_dict["session_cost"] == {"amount": 1500.0, "currency": "USD"}
        assert data_dict["is_free_session"] is False

    def test_charging_session_live_data_default_cost(self) -> None:
        """Test ChargingSessionLiveData with default cost."""
        data = ChargingSessionLiveData()

        assert data.session_cost is not None
        assert data.session_cost.amount == 0.0
        assert data.session_cost.currency == "USD"

    def test_charging_schedule_time_window_creation(self) -> None:
        """Test ChargingScheduleTimeWindow message creation."""
        start_time = TimeOfDay(hour=22, minute=0)
        end_time = TimeOfDay(hour=6, minute=0)
        schedule = ChargingScheduleTimeWindow(
            start_time=start_time,
            end_time=end_time,
            start_day_of_week=0,
            end_day_of_week=6,
        )

        assert schedule.start_time.hour == 22
        assert schedule.start_time.minute == 0
        assert schedule.end_time.hour == 6
        assert schedule.end_time.minute == 0
        assert schedule.start_day_of_week == 0
        assert schedule.end_day_of_week == 6

    def test_charging_schedule_time_window_to_dict(self) -> None:
        """Test ChargingScheduleTimeWindow to_dict conversion."""
        start_time = TimeOfDay(hour=10, minute=30)
        end_time = TimeOfDay(hour=14, minute=45)
        schedule = ChargingScheduleTimeWindow(
            start_time=start_time,
            end_time=end_time,
            start_day_of_week=1,
            end_day_of_week=5,
        )
        schedule_dict = schedule.to_dict()

        assert schedule_dict == {
            "start_time": {"hour": 10, "minute": 30},
            "end_time": {"hour": 14, "minute": 45},
            "start_day_of_week": 1,
            "end_day_of_week": 5,
        }

    def test_charging_schedule_time_window_serialization(self) -> None:
        """Test ChargingScheduleTimeWindow protobuf serialization.

        Validates that ChargingScheduleTimeWindow with nested TimeOfDay
        messages can be serialized to protobuf wire format.
        """
        start_time = TimeOfDay(hour=22, minute=0)
        end_time = TimeOfDay(hour=6, minute=0)
        schedule = ChargingScheduleTimeWindow(
            start_time=start_time,
            end_time=end_time,
            start_day_of_week=0,
            end_day_of_week=6,
        )
        serialized = schedule.SerializeToString()

        assert isinstance(serialized, bytes)
        assert len(serialized) > 0

        # Test with weekday schedule
        schedule_weekdays = ChargingScheduleTimeWindow(
            start_time=TimeOfDay(hour=10, minute=30),
            end_time=TimeOfDay(hour=14, minute=45),
            start_day_of_week=1,
            end_day_of_week=5,
        )
        serialized_weekdays = schedule_weekdays.SerializeToString()
        assert len(serialized_weekdays) > 0

    def test_time_of_day_serialization_empty(self) -> None:
        """Test TimeOfDay serialization with default (empty) values.

        Validates that empty messages serialize to empty bytes since
        protobuf omits fields with default values.
        """
        time = TimeOfDay()
        serialized = time.SerializeToString()

        assert isinstance(serialized, bytes)
        # Empty message (all defaults) may serialize to empty bytes
        assert len(serialized) == 0

    def test_time_of_day_serialization_populated(self) -> None:
        """Test TimeOfDay serialization with all fields populated.

        Validates that messages with non-default values produce
        non-empty serialized output.
        """
        time = TimeOfDay(hour=14, minute=30)
        serialized = time.SerializeToString()

        assert isinstance(serialized, bytes)
        assert len(serialized) > 0

    def test_session_cost_serialization_empty(self) -> None:
        """Test SessionCost serialization with default values.

        Validates handling of empty SessionCost messages.
        """
        cost = SessionCost()
        serialized = cost.SerializeToString()

        assert isinstance(serialized, bytes)
        # Default amount (0.0) and currency may produce empty or minimal bytes

    def test_session_cost_serialization_populated(self) -> None:
        """Test SessionCost serialization with all fields populated.

        Validates that populated SessionCost messages serialize correctly.
        """
        cost = SessionCost(amount=2500.0, currency="EUR")
        serialized = cost.SerializeToString()

        assert isinstance(serialized, bytes)
        assert len(serialized) > 0

    def test_charging_session_live_data_serialization_nested(self) -> None:
        """Test ChargingSessionLiveData with nested SessionCost.

        Validates that nested message serialization works correctly.
        """
        cost = SessionCost(amount=1500.0, currency="USD")
        data = ChargingSessionLiveData(
            total_kwh=50.0,
            pack_kwh=45.0,
            thermal_kwh=3.0,
            outlets_kwh=1.0,
            system_kwh=1.0,
            session_duration_mins=90,
            time_remaining_mins=30,
            range_added_kms=250,
            current_power=48.5,
            current_range_per_hour=200,
            session_cost=cost,
            is_free_session=False,
            charging_state=1,
        )
        serialized = data.SerializeToString()

        assert isinstance(serialized, bytes)
        assert len(serialized) > 0

    def test_charging_session_live_data_serialization_empty(self) -> None:
        """Test ChargingSessionLiveData with default values.

        Validates handling of empty ChargingSessionLiveData messages.
        """
        data = ChargingSessionLiveData()
        serialized = data.SerializeToString()

        assert isinstance(serialized, bytes)
        # Empty/default values may produce empty or minimal bytes

    def test_ota_state_serialization_populated(self) -> None:
        """Test OTAState serialization with all fields populated.

        Validates that OTAState messages with all fields serialize correctly.
        """
        from custom_components.rivian.rivian_client.proto.ota import OTAState

        ota = OTAState(
            update_available=True,
            current_version="2024.10.1",
            available_version="2024.11.0",
            download_progress=75,
            install_state="downloading",
        )
        serialized = ota.SerializeToString()

        assert isinstance(serialized, bytes)
        assert len(serialized) > 0

    def test_ota_state_serialization_empty(self) -> None:
        """Test OTAState serialization with default values.

        Validates handling of empty OTAState messages.
        """
        from custom_components.rivian.rivian_client.proto.ota import OTAState

        ota = OTAState()
        serialized = ota.SerializeToString()

        assert isinstance(serialized, bytes)

    def test_trip_progress_serialization_populated(self) -> None:
        """Test TripProgress serialization with all fields populated.

        Validates that TripProgress messages with all fields serialize correctly.
        """
        from custom_components.rivian.rivian_client.proto.navigation import TripProgress

        trip = TripProgress(
            destination_name="San Francisco",
            distance_remaining_km=250.5,
            time_remaining_mins=180,
            battery_at_destination_percent=42,
            charging_stops_remaining=1,
        )
        serialized = trip.SerializeToString()

        assert isinstance(serialized, bytes)
        assert len(serialized) > 0

    def test_trip_progress_serialization_empty(self) -> None:
        """Test TripProgress serialization with default values.

        Validates handling of empty TripProgress messages.
        """
        from custom_components.rivian.rivian_client.proto.navigation import TripProgress

        trip = TripProgress()
        serialized = trip.SerializeToString()

        assert isinstance(serialized, bytes)

    def test_climate_hold_status_serialization_populated(self) -> None:
        """Test ClimateHoldStatus serialization with all fields populated.

        Validates that ClimateHoldStatus messages with all fields serialize correctly.
        """
        status = ClimateHoldStatus(
            active=True,
            current_temp_celsius=21.5,
            target_temp_celsius=22.0,
            time_remaining_mins=90,
            mode="heating",
        )
        serialized = status.SerializeToString()

        assert isinstance(serialized, bytes)
        assert len(serialized) > 0

    def test_climate_hold_status_serialization_empty(self) -> None:
        """Test ClimateHoldStatus serialization with default values.

        Validates handling of empty ClimateHoldStatus messages.
        """
        status = ClimateHoldStatus()
        serialized = status.SerializeToString()

        assert isinstance(serialized, bytes)


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
