"""The decoder registry and the helpers every topic module shares.

A decoder is written against a parsed message:

    @RVMDecoder.register(body_pb2.TrailerState, "body.trailer.state")
    def decode_trailer_state(m: body_pb2.TrailerState) -> dict[str, Any]: ...

and `register` hands back what the rest of the integration has always called: a
function taking the base64 payload off the subscription and returning a dict,
`{}` when there is nothing to report. Everything a decoder used to repeat --
the empty-payload check, base64, parsing, and swallowing a bad frame so it
cannot take the subscription down -- lives in that wrapper, once.

The registry is modelled on bretterer/rivian-python-client PR 205. It differs in
what `register` returns: upstream's decoders are called with a message, these
with the payload string, because that is the interface this integration's
callers and tests already use.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
import logging
from typing import Any, ClassVar, TypeVar

from google.protobuf.message import Message

# The package's logger, not this module's: every topic module logs here, and the
# name is what log configuration and caplog filters key on.
_LOGGER = logging.getLogger(__package__)

_M = TypeVar("_M", bound=Message)


class RVMDecoder:
    """Registry of RVM topic -> (message class, payload decoder)."""

    decoders: ClassVar[dict[str, Callable[[str], dict[str, Any]]]] = {}
    messages: ClassVar[dict[str, type[Message]]] = {}

    @classmethod
    def register(
        cls,
        message: type[_M],
        *rvms: str,
        empty_payload: bool = False,
        skip_empty_message: bool = False,
    ) -> Callable[[Callable[[_M], dict[str, Any]]], Callable[[str], dict[str, Any]]]:
        """Register the decorated function as the decoder for `rvms`.

        Returns the payload-taking function that replaces it.

        `empty_payload`: the decoder is run on an empty payload too. proto3
        encodes a message of all defaults as nothing, so for some topics no
        bytes is a statement -- "no hold is set", "neither mode is on" --
        and the decoder reports it. Without this an empty payload is `{}`.

        `skip_empty_message`: `{}` when the payload decodes to no bytes at all,
        for the decoders that otherwise report defaults for whatever arrived.

        Raises `ValueError` if a topic already has a decoder.
        """

        def wrap(
            func: Callable[[_M], dict[str, Any]],
        ) -> Callable[[str], dict[str, Any]]:
            def decode(payload: str) -> dict[str, Any]:
                if not payload and not empty_payload:
                    return {}
                try:
                    data = base64.b64decode(payload or "")
                    if skip_empty_message and not data:
                        return {}
                    return func(message.FromString(data))
                except Exception:
                    _LOGGER.debug("Failed to decode %s payload", rvms[0], exc_info=True)
                    return {}

            # Not functools.wraps: that would advertise the message-taking
            # signature, and this function takes the payload.
            decode.__name__ = func.__name__
            decode.__qualname__ = func.__qualname__
            decode.__doc__ = func.__doc__
            decode.__module__ = func.__module__

            for rvm in rvms:
                if rvm in cls.decoders:
                    raise ValueError(
                        f"RVM {rvm!r} is already registered to "
                        f"{cls.decoders[rvm].__qualname__!r}; "
                        f"cannot also register {func.__qualname__!r}"
                    )
                cls.decoders[rvm] = decode
                cls.messages[rvm] = message
            return decode

        return wrap


def _name(message: Message, number: int) -> str:
    """The schema's name for field `number` of `message`.

    For the vocabularies that are keyed by field number (`_WIFI_SPEC`,
    `_ENERGY_DISTRIBUTION`, ...): the number stays in one place, the schema.
    """
    return message.DESCRIPTOR.fields_by_number[number].name


def _fields(
    message: Message, spec: dict[str, tuple[str, dict[int, str] | None]]
) -> dict[str, Any]:
    """Report the fields of `message` that were sent, under their output names.

    `spec` maps field name -> (output key, value map). Every field named must be
    declared `optional`, so "sent as zero" and "not sent" stay different. A None
    map passes the value through; a map that has no entry for the value drops
    the field rather than inventing a name -- an unmapped enum value is new
    firmware, and guessing at it is how "SNA" became a valid sensor option once
    already.
    """
    result: dict[str, Any] = {}
    for field, (key, mapping) in spec.items():
        if not message.HasField(field):
            continue
        value = getattr(message, field)
        if mapping is None:
            result[key] = value
        elif value in mapping:
            result[key] = mapping[value]
    return result
