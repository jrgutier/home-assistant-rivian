"""The schemas agree with what the vehicle actually sent.

Every frame in `fixtures/parallax/` was captured from a real vehicle. For each
one whose topic is decoded, this parses it with the topic's generated message
class and checks two things a unit test built from hand-written bytes cannot:

* it parses at all;
* no field the schema DECLARES turned up among the unknown fields. Protobuf
  files a field under "unknown" when its number is not in the schema -- or when
  it is, but arrived with a different wire type than the schema says. The first
  is expected here (the schemas leave unread length-delimited fields
  undeclared). The second means the declared type is wrong, and a decoder
  reading that field would silently see its default.
"""

from __future__ import annotations

import json
import pathlib

from google.protobuf.descriptor import FieldDescriptor
from google.protobuf.message import Message
from google.protobuf.unknown_fields import UnknownFieldSet
import pytest

from custom_components.rivian.rivian_client.parallax.core import RVMDecoder

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "parallax"
MANIFEST: dict[str, dict] = json.loads((FIXTURES / "manifest.json").read_text())
CAPTURED = sorted(topic for topic in MANIFEST if topic in RVMDecoder.messages)


def _mistyped(message: Message, path: str = "") -> list[str]:
    """Declared fields that arrived with a wire type the schema does not expect."""
    path = path or message.DESCRIPTOR.name
    found = [
        f"{path}: field {unknown.field_number} is declared, "
        f"but arrived as wire type {unknown.wire_type}"
        for unknown in UnknownFieldSet(message)
        if unknown.field_number in message.DESCRIPTOR.fields_by_number
    ]
    for field, value in message.ListFields():
        if field.type != FieldDescriptor.TYPE_MESSAGE:
            continue
        for index, item in enumerate(value if field.is_repeated else [value]):
            found += _mistyped(item, f"{path}.{field.name}[{index}]")
    return found


def test_most_decoded_topics_have_a_captured_frame() -> None:
    assert len(CAPTURED) >= 45


@pytest.mark.parametrize("topic", CAPTURED)
def test_captured_frame_parses(topic: str) -> None:
    raw = (FIXTURES / MANIFEST[topic]["file"]).read_bytes()
    RVMDecoder.messages[topic].FromString(raw)


@pytest.mark.parametrize("topic", CAPTURED)
def test_no_declared_field_arrived_with_another_wire_type(topic: str) -> None:
    raw = (FIXTURES / MANIFEST[topic]["file"]).read_bytes()
    assert not _mistyped(RVMDecoder.messages[topic].FromString(raw))


@pytest.mark.parametrize("topic", CAPTURED)
def test_captured_frame_survives_a_round_trip(topic: str) -> None:
    """Parse, serialise, parse: the same message. Unknown fields are carried."""
    message_class = RVMDecoder.messages[topic]
    first = message_class.FromString((FIXTURES / MANIFEST[topic]["file"]).read_bytes())
    assert message_class.FromString(first.SerializeToString()) == first
