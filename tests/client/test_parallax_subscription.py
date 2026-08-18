"""Tests for `parallaxMessages` WebSocket subscription."""

from __future__ import annotations

from typing import Any

import aiohttp
import pytest

from custom_components.rivian.rivian_client import Rivian
from custom_components.rivian.rivian_client.exceptions import RivianApiException


async def test_subscribe_for_parallax_messages() -> None:
    """Test WebSocket subscription for Parallax messages."""
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
            await rivian.subscribe_for_parallax_messages(
                vehicle_id="test-vehicle-123", callback=test_callback
            )

        await rivian.close()


async def test_subscribe_for_parallax_messages_with_rvms() -> None:
    """Test WebSocket subscription for Parallax messages with RVM filter."""
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )

        def test_callback(data: dict[str, Any]) -> None:
            pass

        # Test with specific RVM types
        # Previously this asserted `is None`, describing the swallow as
        # "designed to return None when connection fails". That is the defect:
        # a dead subscription was indistinguishable from a healthy one.
        with pytest.raises(RivianApiException):
            await rivian.subscribe_for_parallax_messages(
                vehicle_id="test-vehicle-123",
                callback=test_callback,
                rvms=[
                    "comfort.cabin.climate_hold_status",
                    "access.vehicle.passive_entry_status",
                ],
            )

        await rivian.close()


async def test_subscribe_for_parallax_messages_with_empty_rvms() -> None:
    """Test WebSocket subscription for Parallax messages with empty RVM list."""
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )

        def test_callback(data: dict[str, Any]) -> None:
            pass

        # Test with empty RVM list (should subscribe to all)
        # Previously this asserted `is None`, describing the swallow as
        # "designed to return None when connection fails". That is the defect:
        # a dead subscription was indistinguishable from a healthy one.
        with pytest.raises(RivianApiException):
            await rivian.subscribe_for_parallax_messages(
                vehicle_id="test-vehicle-123",
                callback=test_callback,
                rvms=[],
            )

        await rivian.close()
