"""The login flow: OTP branching, and what reaches the user on failure.

This is where the plaintext password disclosure lived (config_flow.py logs the
exception on a failed login, and the exception used to carry the request body).
The redaction now happens in the client, but the flow's own behaviour was
untested, so nothing pinned WHICH string reaches the UI.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.rivian.config_flow import RivianFlowHandler
from custom_components.rivian.rivian_client.exceptions import RivianUnauthenticated
from homeassistant.core import HomeAssistant

USERNAME = "driver@example.com"
PASSWORD = "hunter2-never-log-me"


@pytest.fixture
def flow(hass: HomeAssistant) -> RivianFlowHandler:
    handler = RivianFlowHandler()
    handler.hass = hass
    handler.context = {}
    return handler


def _client(*, otp_needed=False, authenticate=None, validate_otp=None) -> MagicMock:
    api = MagicMock()
    api.create_csrf_token = AsyncMock()
    api.authenticate = AsyncMock(side_effect=authenticate)
    api.validate_otp = AsyncMock(side_effect=validate_otp)
    api.close = AsyncMock()
    api._otp_needed = otp_needed
    api._access_token = "access"
    api._refresh_token = "refresh"
    api._user_session_token = "session"
    return api


class TestPasswordLogin:
    async def test_a_successful_login_creates_the_entry(self, flow) -> None:
        flow._rivian = _client()
        with patch.object(
            flow, "_async_create_entry", AsyncMock(return_value="created")
        ):
            result = await flow.async_step_user(
                {"username": USERNAME, "password": PASSWORD}
            )
        assert result == "created"

    async def test_an_account_needing_otp_is_sent_to_the_otp_step(self, flow) -> None:
        flow._rivian = _client(otp_needed=True)
        with patch.object(flow, "_show_otp_field", AsyncMock(return_value="otp-form")):
            assert (
                await flow.async_step_user({"username": USERNAME, "password": PASSWORD})
                == "otp-form"
            )

    async def test_a_bad_password_shows_a_generic_error_not_the_exception(
        self, flow
    ) -> None:
        """The UI must show the translation key `invalid_auth`, never the exception
        text -- which for a Login failure carried the submitted password."""
        flow._rivian = _client(
            authenticate=RivianUnauthenticated(
                401,
                {"errors": []},
                {"A-Sess": "secret"},
                {"variables": {"email": USERNAME, "password": PASSWORD}},
            )
        )
        with patch.object(
            flow, "_show_credential_fields", AsyncMock(return_value="form")
        ):
            await flow.async_step_user({"username": USERNAME, "password": PASSWORD})
        assert flow._errors["base"] == "invalid_auth"
        assert PASSWORD not in str(flow._errors)


class TestOtpStep:
    async def test_a_valid_otp_creates_the_entry(self, flow) -> None:
        flow._rivian = _client()
        flow._data = {"username": USERNAME}
        with patch.object(
            flow, "_async_create_entry", AsyncMock(return_value="created")
        ):
            assert await flow.async_step_user({"otp": "123456"}) == "created"

    async def test_a_wrong_otp_re_prompts_for_the_otp(self, flow) -> None:
        """INVALID_OTP_TOKEN means the code was wrong, not the password -- sending
        the user back to the credential form would make them retype everything."""
        flow._rivian = _client(
            validate_otp=RivianUnauthenticated(
                401,
                {
                    "errors": [
                        {
                            "message": "bad",
                            "extensions": {"reason": "INVALID_OTP_TOKEN"},
                        }
                    ]
                },
                {},
                {},
            )
        )
        flow._data = {"username": USERNAME}
        with patch.object(flow, "_show_otp_field", AsyncMock(return_value="otp-form")):
            assert await flow.async_step_user({"otp": "000000"}) == "otp-form"

    async def test_an_expired_otp_returns_to_the_credentials(self, flow) -> None:
        flow._rivian = _client(
            validate_otp=RivianUnauthenticated(
                401,
                {
                    "errors": [
                        {
                            "message": "expired",
                            "extensions": {"reason": "OTP_TOKEN_EXPIRED"},
                        }
                    ]
                },
                {},
                {},
            )
        )
        flow._data = {"username": USERNAME}
        with patch.object(
            flow, "_show_credential_fields", AsyncMock(return_value="form")
        ):
            assert await flow.async_step_user({"otp": "000000"}) == "form"

    async def test_a_missing_token_after_otp_reports_communication(self, flow) -> None:
        api = _client()
        api._access_token = None
        flow._rivian = api
        flow._data = {"username": USERNAME}
        with patch.object(
            flow, "_show_credential_fields", AsyncMock(return_value="form")
        ):
            await flow.async_step_user({"otp": "123456"})
        assert flow._errors["base"] == "communication"


class TestEntryCreation:
    async def test_the_session_is_closed_and_tokens_stored(self, flow, hass) -> None:
        flow._rivian = _client()
        flow._data = {"username": USERNAME}
        flow._access_token = "A"
        flow._refresh_token = "R"
        flow._user_session_token = "S"
        flow.context = {}
        with patch.object(
            flow, "async_create_entry", MagicMock(return_value="entry")
        ) as create:
            assert await flow._async_create_entry() == "entry"
        flow._rivian.close.assert_awaited()
        data = create.call_args.kwargs["data"]
        assert data["access_token"] == "A"
        assert data["refresh_token"] == "R"
        assert data["user_session_token"] == "S"

    async def test_reauth_updates_the_existing_entry_and_reloads(
        self, flow, hass
    ) -> None:
        """Reauth must not create a second entry -- that would duplicate every
        entity."""
        existing = MagicMock(entry_id="abc")
        flow._rivian = _client()
        flow._data = {"username": USERNAME}
        flow.context = {"entry_id": "abc"}
        hass.config_entries.async_get_entry = MagicMock(return_value=existing)
        hass.config_entries.async_update_entry = MagicMock()
        hass.config_entries.async_reload = AsyncMock()
        with patch.object(flow, "async_abort", MagicMock(return_value="aborted")):
            assert await flow._async_create_entry() == "aborted"
        hass.config_entries.async_update_entry.assert_called_once()
        hass.config_entries.async_reload.assert_awaited_once_with("abc")
