"""Rivian exceptions.

Every exception here is raised with the HTTP status, the response JSON, the
request headers AND the request body attached (``rivian.py:978`` and
``rivian.py:980``). None of these classes defines ``__init__``, so Python renders
all of those arguments through ``str(args)`` whenever the exception is logged,
printed, or formatted into a message.

That is a credential disclosure, and it is not theoretical:

* ``headers`` carries ``A-Sess``, ``U-Sess`` and ``Csrf-Token``.
* the ``Login`` mutation body carries ``{"variables": {"email", "password"}}``.
* the Home Assistant integration logs these with ``exc_info=1``, and logs the
  failed-login case specifically -- so a mistyped password is written to
  ``home-assistant.log``, the file people attach to bug reports.

``RivianApiException.__init__`` therefore redacts sensitive values as the
exception is constructed, before anything can render it.

Two properties are deliberate:

* **Shape-agnostic.** Redaction walks every argument by key name at any depth,
  rather than keying on argument position. ``rivian.py:978`` passes four
  positional arguments while ``rivian.py:980`` passes five, with ``headers`` and
  ``body`` shifted by one -- and the five-argument form is the fallback for every
  error code absent from ``ERROR_CODE_CLASS_MAP``, so a position-keyed
  implementation would miss precisely the unclassified failures.
* **Structure-preserving.** Only leaf values are replaced. ``args[1]`` stays a
  navigable mapping because the integration reads
  ``err.args[1]["errors"][0]["extensions"]["reason"]`` to decide whether to
  re-prompt for an OTP.
"""

from __future__ import annotations

from typing import Any

REDACTED = "<redacted>"

# Compared case-insensitively: headers arrive capitalised ("A-Sess") while
# GraphQL variables arrive camelCased ("otpCode").
_SENSITIVE_KEYS = frozenset(
    {
        # session and CSRF headers
        "a-sess",
        "u-sess",
        "csrf-token",
        "authorization",
        # credentials carried in a mutation body
        "password",
        "email",
        "otpcode",
        "otptoken",
        # tokens returned by a successful login, in case one is echoed back
        "accesstoken",
        "refreshtoken",
        "usersessiontoken",
    }
)


def redact(value: Any) -> Any:
    """Return ``value`` with any sensitively-named leaf replaced.

    Containers are rebuilt rather than mutated, so the caller's request headers
    and body are left untouched -- the exception must not corrupt the request it
    is reporting on.
    """
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
    """Base Rivian API exception."""

    def __init__(self, *args: Any) -> None:
        """Store the arguments with sensitive values redacted."""
        super().__init__(*(redact(arg) for arg in args))


class RivianExpiredTokenError(RivianApiException):
    """Access Token Expired Error"""


class RivianUnauthenticated(RivianApiException):
    """User Token Invalid Error"""


class RivianInvalidCredentials(RivianApiException):
    """Invalid User Credentials - Check Username and Password"""


class RivianInvalidOTP(RivianApiException):
    """User's One Time Password Invalid - Try Again"""


class RivianDataError(RivianApiException):
    """Rivian Server Data Error"""


class RivianTemporarilyLockedError(RivianApiException):
    """Rivian User Temporarily Locked Error"""


class RivianApiRateLimitError(RivianApiException):
    """Rivian API is being rate limited."""


class RivianPhoneLimitReachedError(RivianApiException):
    """Rivian phone limit has been reached."""


class RivianBadRequestError(RivianApiException):
    """Rivian API bad request."""
