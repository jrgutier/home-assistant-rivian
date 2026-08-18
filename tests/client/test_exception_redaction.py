"""Credentials must never survive into an exception's rendered form.

rivian.py raises with the request headers AND the request body attached, and
exceptions.py defines no __init__, so Python renders every argument via
str(args). The consequences are concrete:

  * headers carry A-Sess / U-Sess / Csrf-Token
  * the Login mutation body carries {"variables": {"email", "password"}}
  * home-assistant-rivian logs these exceptions with exc_info=1, and logs the
    Login failure specifically -- so a mistyped password lands in
    home-assistant.log, the file users attach to bug reports.

Every test below asserts on the RENDERED form (str/repr/logging), not on
attributes, because rendering is what reaches the log.
"""

import logging

import pytest

from custom_components.rivian.rivian_client.exceptions import (
    RivianApiException,
    RivianInvalidCredentials,
    RivianInvalidOTP,
    RivianUnauthenticated,
)

PASSWORD = "hunter2-do-not-log-me"
EMAIL = "driver@example.com"
A_SESS = "AAAA-app-session-token-AAAA"
U_SESS = "UUUU-user-session-token-UUUU"
CSRF = "CCCC-csrf-token-CCCC"
OTP_CODE = "123456"
OTP_TOKEN = "OOOO-otp-token-OOOO"

HEADERS = {
    "User-Agent": "RivianApp/707",
    "Csrf-Token": CSRF,
    "A-Sess": A_SESS,
    "U-Sess": U_SESS,
}
LOGIN_BODY = {
    "operationName": "Login",
    "variables": {"email": EMAIL, "password": PASSWORD},
}
OTP_BODY = {
    "operationName": "LoginWithOTP",
    "variables": {"email": EMAIL, "otpCode": OTP_CODE, "otpToken": OTP_TOKEN},
}
RESPONSE_JSON = {
    "errors": [
        {
            "message": "Unauthorized",
            "extensions": {"reason": "BAD_CURRENT_PASSWORD", "code": "UNAUTHENTICATED"},
        }
    ]
}

SECRETS = (PASSWORD, A_SESS, U_SESS, CSRF, OTP_TOKEN)


def _rendered(exc: Exception, caplog: pytest.LogCaptureFixture) -> str:
    """Every form the exception can reach a log or a UI through."""
    logger = logging.getLogger("rivian.test")
    with caplog.at_level(logging.ERROR, logger="rivian.test"):
        logger.error("%s", exc)
        logger.error("%r", exc)
        try:
            raise exc
        except Exception:
            # G201 says use .exception(); kept as .error(..., exc_info=...) on
            # purpose, because that is verbatim what coordinator.py:97,103,106
            # and __init__.py:68 do. The point is to render the real call site.
            logger.error("with traceback", exc_info=True)  # noqa: G201
    return "\n".join([str(exc), repr(exc), caplog.text])


class TestFourArgShape:
    """rivian.py:772 -- err_cls(status, response_json, headers, body)."""

    def test_password_never_renders(self, caplog) -> None:
        exc = RivianInvalidCredentials(401, RESPONSE_JSON, HEADERS, LOGIN_BODY)
        assert PASSWORD not in _rendered(exc, caplog)

    def test_session_tokens_never_render(self, caplog) -> None:
        exc = RivianUnauthenticated(401, RESPONSE_JSON, HEADERS, LOGIN_BODY)
        out = _rendered(exc, caplog)
        for secret in (A_SESS, U_SESS, CSRF):
            assert secret not in out

    def test_otp_credentials_never_render(self, caplog) -> None:
        exc = RivianInvalidOTP(401, RESPONSE_JSON, HEADERS, OTP_BODY)
        out = _rendered(exc, caplog)
        assert OTP_TOKEN not in out
        assert OTP_CODE not in out


class TestFiveArgShape:
    """rivian.py:773 -- RivianApiException(message, status, json, headers, body).

    The fallback for every code absent from ERROR_CODE_CLASS_MAP, so it is the
    shape a redaction keyed on argument POSITION would silently miss.
    """

    def test_all_secrets_redacted_despite_the_shifted_positions(self, caplog) -> None:
        exc = RivianApiException(
            "Error occurred while reading the graphql response from Rivian.",
            500,
            RESPONSE_JSON,
            HEADERS,
            LOGIN_BODY,
        )
        out = _rendered(exc, caplog)
        for secret in SECRETS:
            assert secret not in out


class TestStillUseful:
    """Redaction must not blind the maintainer, only the log reader."""

    def test_non_sensitive_context_survives(self, caplog) -> None:
        exc = RivianInvalidCredentials(401, RESPONSE_JSON, HEADERS, LOGIN_BODY)
        out = _rendered(exc, caplog)
        assert "401" in out
        assert "BAD_CURRENT_PASSWORD" in out
        assert "RivianApp/707" in out
        assert "Login" in out

    def test_args_1_stays_parseable(self) -> None:
        # home-assistant-rivian's config_flow.py:238 does exactly this to decide
        # whether to re-prompt for an OTP. Reshaping args would break the flow.
        exc = RivianInvalidOTP(401, RESPONSE_JSON, HEADERS, OTP_BODY)
        assert (
            exc.args[1]["errors"][0]["extensions"]["reason"] == "BAD_CURRENT_PASSWORD"
        )

    def test_the_secret_is_visibly_marked_not_silently_dropped(self, caplog) -> None:
        exc = RivianInvalidCredentials(401, RESPONSE_JSON, HEADERS, LOGIN_BODY)
        assert "REDACTED" in _rendered(exc, caplog).upper()


class TestNoRegression:
    def test_plain_message_exceptions_are_unchanged(self) -> None:
        assert str(RivianApiException("something broke")) == "something broke"

    def test_empty_construction_still_works(self) -> None:
        assert isinstance(RivianApiException(), RivianApiException)

    def test_subclasses_inherit_redaction(self, caplog) -> None:
        # All ten classes derive from RivianApiException; redaction must not be
        # something each one has to opt into.
        for cls in (RivianUnauthenticated, RivianInvalidCredentials, RivianInvalidOTP):
            exc = cls(401, RESPONSE_JSON, HEADERS, LOGIN_BODY)
            assert PASSWORD not in _rendered(exc, caplog)
