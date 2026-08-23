"""Tests for `parallaxMessages` WebSocket subscription."""

from __future__ import annotations

from typing import Any

import aiohttp
import pytest

from custom_components.rivian.rivian_client import Rivian
from custom_components.rivian.rivian_client.exceptions import RivianApiException


@pytest.mark.parametrize(
    "rvms",
    [
        None,
        [
            "comfort.cabin.climate_hold_status",
            "access.vehicle.passive_entry_status",
        ],
        [],
    ],
    ids=["no-filter", "with-rvms", "empty-rvms"],
)
async def test_subscribe_for_parallax_messages_raises_when_it_cannot_connect(
    rvms: list[str] | None,
) -> None:
    """A failed subscription must raise, not return None -- for every rvms shape.

    These previously asserted `is None`, describing the swallow as "designed to
    return None when connection fails". That is the defect: a dead subscription
    was indistinguishable from a healthy one.
    """
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )
        kwargs: dict[str, Any] = {} if rvms is None else {"rvms": rvms}
        with pytest.raises(RivianApiException):
            await rivian.subscribe_for_parallax_messages(
                vehicle_id="test-vehicle-123",
                callback=lambda data: None,
                **kwargs,
            )
        await rivian.close()
