"""Client-side tests for the S19 option-code fragment on `getUserInfo`.

`get_user_information()` asks for `mobileConfiguration { tonneauOption
wheelOption }` on top of the vehicle fragment it already sent. That fragment
rides on `getUserInfo`, which is setup-critical, so a rejection of the two new
fields must not cost setup itself: rivian.py retries ONCE with the base
fragment (no mobileConfiguration) and records which one won via
`option_codes_available()`. See rivian_client/rivian.py's
get_user_information() docstring.
"""

from __future__ import annotations

import aiohttp
from aiohttp.web import json_response
from aresponses import ResponsesMockServer
import pytest

from custom_components.rivian.rivian_client import Rivian
from custom_components.rivian.rivian_client.exceptions import (
    RivianApiException,
    RivianApiRateLimitError,
)

from .responses import USER_INFORMATION_RESPONSE, error_response

HOST = "rivian.com"
PATH = "/api/gql/gateway/graphql"


async def test_the_extended_fragment_is_sent_and_accepted(
    aresponses: ResponsesMockServer,
) -> None:
    """The first (and only, on success) attempt asks for the two new fields."""
    calls: list[str] = []

    async def handler(request: aiohttp.web.Request):
        calls.append(await request.text())
        return json_response(USER_INFORMATION_RESPONSE)

    aresponses.add(HOST, PATH, "POST", response=handler)
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )
        response = await rivian.get_user_information()
        assert response.status == 200
        assert len(calls) == 1
        assert "mobileConfiguration" in calls[0]
        assert "tonneauOption" in calls[0]
        assert "wheelOption" in calls[0]
        assert rivian.option_codes_available() is True
        await rivian.close()


async def test_a_rejected_fragment_retries_once_without_it(
    aresponses: ResponsesMockServer,
) -> None:
    """Requirement 3: an unclassified rejection retries once with the base
    fragment, and setup succeeds off the second response."""
    calls: list[str] = []

    async def handler(request: aiohttp.web.Request):
        calls.append(await request.text())
        if len(calls) == 1:
            # unclassified: "field not found" analogue
            return json_response(error_response())
        return json_response(USER_INFORMATION_RESPONSE)

    aresponses.add(HOST, PATH, "POST", response=handler, repeat=2)
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )
        response = await rivian.get_user_information()
        assert response.status == 200
        assert len(calls) == 2
        assert "mobileConfiguration" in calls[0]
        assert "mobileConfiguration" not in calls[1]
        assert rivian.option_codes_available() is False
        await rivian.close()


async def test_a_rejection_of_both_attempts_still_raises(
    aresponses: ResponsesMockServer,
) -> None:
    """The retry reduces the blast radius; it does not eliminate the failure
    mode -- if the base fragment is rejected too, this must still surface."""
    calls: list[str] = []

    async def handler(request: aiohttp.web.Request):
        calls.append(await request.text())
        return json_response(error_response())

    aresponses.add(HOST, PATH, "POST", response=handler, repeat=2)
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )
        with pytest.raises(RivianApiException):
            await rivian.get_user_information()
        assert len(calls) == 2
        assert rivian.option_codes_available() is False
        await rivian.close()


async def test_a_classified_error_does_not_retry(
    aresponses: ResponsesMockServer,
) -> None:
    """Narrow on purpose: RATE_LIMIT (and every other ERROR_CODE_CLASS_MAP
    entry) is a RivianApiException SUBCLASS and must propagate immediately --
    retrying a rate limit with a smaller query would double the damage rather
    than reduce it."""
    calls: list[str] = []

    async def handler(request: aiohttp.web.Request):
        calls.append(await request.text())
        return json_response(error_response("RATE_LIMIT"))

    # repeat=2 so a wrongly-added second attempt would still be served (and
    # caught by the call count assertion) rather than failing the test for an
    # unrelated reason (no route left to match).
    aresponses.add(HOST, PATH, "POST", response=handler, repeat=2)
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )
        with pytest.raises(RivianApiRateLimitError):
            await rivian.get_user_information()
        assert len(calls) == 1
        # Neither branch of get_user_information ran to completion, so the
        # flag is untouched from its post-__init__ default.
        assert rivian.option_codes_available() is None
        await rivian.close()
