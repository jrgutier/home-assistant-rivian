from __future__ import annotations

from typing import Any

REDACTED = "<redacted>"

_SENSITIVE_KEYS = frozenset(
    {
        "a-sess",
        "u-sess",
        "csrf-token",
        "authorization",
        "password",
        "email",
        "otpcode",
        "otptoken",
        "accesstoken",
        "refreshtoken",
        "usersessiontoken",
    }
)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED if str(key).lower() in _SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value


class RivianApiException(Exception):
    def __init__(self, *args: Any) -> None:
        super().__init__(*(redact(arg) for arg in args))


class RivianExpiredTokenError(RivianApiException):
    pass


class RivianUnauthenticated(RivianApiException):
    pass


class RivianInvalidCredentials(RivianApiException):
    pass


class RivianInvalidOTP(RivianApiException):
    pass


class RivianDataError(RivianApiException):
    pass


class RivianTemporarilyLockedError(RivianApiException):
    pass


class RivianApiRateLimitError(RivianApiException):
    pass


class RivianPhoneLimitReachedError(RivianApiException):
    pass


class RivianBadRequestError(RivianApiException):
    pass


class RivianGraphQLError(RivianApiException):
    pass
