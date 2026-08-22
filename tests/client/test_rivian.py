"""Tests for `rivian.rivian`."""

# pylint: disable=protected-access
from __future__ import annotations

from typing import Any

import aiohttp
from aresponses import ResponsesMockServer
import pytest

from custom_components.rivian.rivian_client import Rivian
from custom_components.rivian.rivian_client.exceptions import (
    RivianApiException,
    RivianApiRateLimitError,
    RivianDataError,
    RivianInvalidOTP,
    RivianTemporarilyLockedError,
    RivianUnauthenticated,
)

from .responses import (
    AUTHENTICATION_OTP_RESPONSE,
    AUTHENTICATION_RESPONSE,
    CSRF_TOKEN_RESPONSE,
    LIVE_CHARGING_SESSION_RESPONSE,
    OTP_TOKEN_RESPONSE,
    SEND_LOCATION_TO_VEHICLE_RESPONSE,
    SET_CHARGING_SCHEDULES_RESPONSE,
    USER_INFORMATION_RESPONSE,
    VEHICLE_CHARGING_SCHEDULES_RESPONSE,
    WALLBOXES_RESPONSE,
    error_response,
    load_response,
)


async def test_csrf_token_request(aresponses: ResponsesMockServer) -> None:
    """Test CSRF token request."""
    aresponses.add(
        "rivian.com", "/api/gql/gateway/graphql", "POST", response=CSRF_TOKEN_RESPONSE
    )
    async with aiohttp.ClientSession():
        rivian = Rivian()
        await rivian.create_csrf_token()
        assert rivian._csrf_token == "valid_csrf_token"
        assert rivian._app_session_token == "valid_app_session_token"
        await rivian.close()


async def test_authentication(aresponses: ResponsesMockServer) -> None:
    """Test authentication."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=AUTHENTICATION_RESPONSE,
    )
    async with (
        aiohttp.ClientSession(),
        Rivian(csrf_token="token", app_session_token="token") as rivian,
    ):
        await rivian.authenticate("username", "password")
        assert rivian._access_token == "valid_access_token"
        assert rivian._refresh_token == "valid_refresh_token"
        assert rivian._user_session_token == "valid_user_session_token"


async def test_invalid_authentication(aresponses: ResponsesMockServer) -> None:
    """Test invalid authentication."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=error_response("UNAUTHENTICATED", "UNAUTHENTICATED"),
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(csrf_token="token", app_session_token="token")
        with pytest.raises(RivianUnauthenticated):
            await rivian.authenticate("username", "bad_password")
        await rivian.close()


async def test_authentication_with_otp(aresponses: ResponsesMockServer) -> None:
    """Test authentication with OTP enabled."""
    aresponses.add(
        "rivian.com", "/api/gql/gateway/graphql", "POST", response=OTP_TOKEN_RESPONSE
    )
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=AUTHENTICATION_OTP_RESPONSE,
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(csrf_token="token", app_session_token="token")
        await rivian.authenticate("username", "password")
        assert rivian._otp_needed
        assert rivian._otp_token == "token"

        await rivian.validate_otp("username", "code")
        assert rivian._access_token == "token"
        assert rivian._refresh_token == "token"
        assert rivian._user_session_token == "token"
        await rivian.close()


async def test_authentication_with_expired_otp(aresponses: ResponsesMockServer) -> None:
    """Test authentication with expired OTP token."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=error_response("UNAUTHENTICATED", "OTP_TOKEN_EXPIRED"),
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(csrf_token="token", app_session_token="token")
        rivian._otp_needed = True
        rivian._otp_token = "token"

        with pytest.raises(RivianInvalidOTP):
            await rivian.validate_otp("username", "expired_code")
        await rivian.close()


async def test_get_user_information(aresponses: ResponsesMockServer) -> None:
    """Test get user information request."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=USER_INFORMATION_RESPONSE,
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )
        response = await rivian.get_user_information()
        response_json = await response.json()
        assert response.status == 200
        assert (current_user := response_json["data"]["currentUser"])
        assert current_user["id"] == "id"
        assert len(current_user["vehicles"]) == 1
        await rivian.close()


async def test_get_registered_wallboxes(aresponses: ResponsesMockServer) -> None:
    """Test GraphQL Response for a getRegisteredWallboxes request"""
    aresponses.add(
        "rivian.com", "/api/gql/chrg/user/graphql", "POST", response=WALLBOXES_RESPONSE
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )
        response = await rivian.get_registered_wallboxes()
        response_json = await response.json()
        assert response.status == 200
        assert len(response_json["data"]["getRegisteredWallboxes"]) == 1
        assert (
            response_json["data"]["getRegisteredWallboxes"][0]["wallboxId"]
            == "W1-1113-3RV7-1-1234-00012"
        )
        await rivian.close()


async def test_get_live_charging_session(aresponses: ResponsesMockServer) -> None:
    """Test GraphQL Response for a getLiveSessionData request"""
    aresponses.add(
        "rivian.com",
        "/api/gql/chrg/user/graphql",
        "POST",
        response=LIVE_CHARGING_SESSION_RESPONSE,
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(app_session_token="token", user_session_token="token")
        response = await rivian.get_live_charging_session("vin", {})
        response_json = await response.json()
        assert response.status == 200
        assert (
            response_json["data"]["getLiveSessionData"]["vehicleChargerState"]["value"]
            == "charging_active"
        )
        await rivian.close()


async def test_get_charging_schedules(aresponses: ResponsesMockServer) -> None:
    """Test getting vehicle charging schedules."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=VEHICLE_CHARGING_SCHEDULES_RESPONSE,
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(app_session_token="token", user_session_token="token")
        response = await rivian.get_charging_schedules("vehicle_id")
        response_json = await response.json()
        assert response.status == 200
        schedules = response_json["data"]["getVehicle"]["chargingSchedules"]
        assert len(schedules) == 1
        assert schedules[0]["amperage"] == 32
        assert schedules[0]["enabled"] is True
        assert len(schedules[0]["weekDays"]) == 7
        await rivian.close()


async def test_set_charging_schedules(aresponses: ResponsesMockServer) -> None:
    """Test setting vehicle charging schedules."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=SET_CHARGING_SCHEDULES_RESPONSE,
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="csrf",
            app_session_token="token",
            user_session_token="token",
        )
        schedules = [
            {
                "weekDays": [
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday",
                    "Saturday",
                    "Sunday",
                ],
                "startTime": 0,
                "duration": 1440,
                "location": {"latitude": 37.7749, "longitude": -122.4194},
                "amperage": 16,
                "enabled": True,
            }
        ]
        response = await rivian.set_charging_schedules("vehicle_id", schedules)
        response_json = await response.json()
        assert response.status == 200
        assert response_json["data"]["setChargingSchedules"]["success"] is True
        await rivian.close()


async def test_graphql_errors(aresponses: ResponsesMockServer) -> None:
    """Test GraphQL error responses.

    The call is incidental -- these exercise __graphql_query's error handling, not
    the operation. They used get_vehicle_state until f4 deleted it; repointed at
    get_user_information rather than dropped, because the error paths are the
    coverage, and the client floor has under half a point of headroom.
    get_user_information posts to the same GRAPHQL_GATEWAY url the mock registers;
    get_registered_wallboxes posts to GRAPHQL_CHARGING and would not match.

    The bare-error block below uses get_vehicle_command_state instead of
    get_user_information: since s19, get_user_information retries once on an
    UNCLASSIFIED RivianApiException specifically (the mobileConfiguration
    option-code fragment being rejected), which `error_response()` with no
    code also produces -- consuming a second, unregistered mock and failing
    the test for a reason unrelated to what it is checking.
    get_vehicle_command_state has no such retry and stays a single round trip.
    """
    host = "rivian.com"
    path = "/api/gql/gateway/graphql"

    aresponses.add(host, path, "POST", response=error_response("RATE_LIMIT"))
    async with aiohttp.ClientSession():
        rivian = Rivian()
        with pytest.raises(RivianApiRateLimitError):
            await rivian.get_user_information()
        await rivian.close()

    aresponses.add(host, path, "POST", response=error_response("DATA_ERROR"))
    async with aiohttp.ClientSession():
        rivian = Rivian()
        with pytest.raises(RivianDataError):
            await rivian.get_user_information()
        await rivian.close()

    aresponses.add(host, path, "POST", response=error_response("SESSION_MANAGER_ERROR"))
    async with aiohttp.ClientSession():
        rivian = Rivian()
        with pytest.raises(RivianTemporarilyLockedError):
            await rivian.get_user_information()
        await rivian.close()

    aresponses.add(host, path, "POST", response=error_response())
    async with aiohttp.ClientSession():
        rivian = Rivian()
        with pytest.raises(RivianApiException):
            await rivian.get_vehicle_command_state("command_id")
        await rivian.close()

    aresponses.add(
        host, path, "POST", response=error_response("BAD_USER_INPUT", "INVALID_OTP")
    )
    async with aiohttp.ClientSession():
        rivian = Rivian()
        with pytest.raises(RivianInvalidOTP):
            await rivian.authenticate("", "")
        await rivian.close()


async def test_get_drivers_and_keys(aresponses: ResponsesMockServer) -> None:
    """Test get drivers and keys."""
    host = "rivian.com"
    path = "/api/gql/gateway/graphql"

    aresponses.add(
        host, path, "POST", response=load_response("drivers_and_keys_success")
    )
    async with aiohttp.ClientSession():
        rivian = Rivian()

        response = await rivian.get_drivers_and_keys(vehicle_id="vehicleId")
        response_json = await response.json()
        assert response.status == 200
        assert (drivers_and_keys := response_json["data"]["getVehicle"])
        assert drivers_and_keys["id"] == "id"
        assert len(drivers_and_keys["invitedUsers"]) == 4
        await rivian.close()


# Tests for the four methods this fork carries that upstream 2.1.0 does not:
# the navigation share and the charging/cloud-connection/command-state
# subscriptions. The rest of this file is upstream's, because adopting its
# transport means adopting the ClientResponse contract its tests encode.
async def test_send_location_to_vehicle(aresponses: ResponsesMockServer) -> None:
    """Test sending location to vehicle."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=SEND_LOCATION_TO_VEHICLE_RESPONSE,
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )
        result = await rivian.send_location_to_vehicle(
            location_str="123 Main St, Springfield, IL 62701",
            vehicle_id="vehicle-123",
        )
        assert result["publishResponse"]["result"] == 0
        await rivian.close()


async def test_subscribe_for_charging_session() -> None:
    """Test WebSocket subscription for charging session updates."""
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )

        # Create a simple callback to track if it's called
        callback_called = False

        def test_callback(data: dict[str, Any]) -> None:
            nonlocal callback_called
            callback_called = True

        # Test that method can be called and returns None on error (no actual WebSocket server)
        # The method is designed to return None when connection fails
        # Previously this asserted `is None`, describing the swallow as
        # "designed to return None when connection fails". That is the defect:
        # a dead subscription was indistinguishable from a healthy one.
        with pytest.raises(RivianApiException):
            await rivian.subscribe_for_charging_session(
                vehicle_id="test-vehicle-123", callback=test_callback
            )

        await rivian.close()


async def test_subscribe_for_cloud_connection() -> None:
    """Test WebSocket subscription for cloud connection updates."""
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )

        # Create a simple callback to track if it's called
        callback_called = False

        def test_callback(data: dict[str, Any]) -> None:
            nonlocal callback_called
            callback_called = True

        # Test that method can be called and returns None on error (no actual WebSocket server)
        # The method is designed to return None when connection fails
        # Previously this asserted `is None`, describing the swallow as
        # "designed to return None when connection fails". That is the defect:
        # a dead subscription was indistinguishable from a healthy one.
        with pytest.raises(RivianApiException):
            await rivian.subscribe_for_cloud_connection(
                vehicle_id="test-vehicle-123", callback=test_callback
            )

        await rivian.close()


async def test_subscribe_for_command_state() -> None:
    """Test WebSocket subscription for command state updates."""
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )

        # Create a simple callback to track if it's called
        callback_called = False

        def test_callback(data: dict[str, Any]) -> None:
            nonlocal callback_called
            callback_called = True

        # Test that method can be called and returns None on error (no actual WebSocket server)
        # The method is designed to return None when connection fails
        # Note: This method takes command_id instead of vehicle_id
        # Previously this asserted `is None`, describing the swallow as
        # "designed to return None when connection fails". That is the defect:
        # a dead subscription was indistinguishable from a healthy one.
        with pytest.raises(RivianApiException):
            await rivian.subscribe_for_command_state(
                command_id="test-command-123", callback=test_callback
            )

        await rivian.close()
