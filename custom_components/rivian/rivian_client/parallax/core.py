from __future__ import annotations

import base64
from collections.abc import Callable
import logging
from typing import Any, ClassVar, TypeVar

from google.protobuf.message import Message

_LOGGER = logging.getLogger(__package__)

_M = TypeVar("_M", bound=Message)

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


class RVMDecoder:
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

            decode.__name__ = func.__name__
            decode.__qualname__ = func.__qualname__
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
    return message.DESCRIPTOR.fields_by_number[number].name


def _fields(
    message: Message, spec: dict[str, tuple[str, dict[int, str] | None]]
) -> dict[str, Any]:
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
