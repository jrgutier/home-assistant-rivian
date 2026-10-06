"""Hold the Parallax decoders to what the hand-rolled module returned.

`fixtures/parallax_golden/golden.jsonl` was recorded by
`scripts/record_parallax_golden.py` from `rivian_client/parallax.py` at the commit
in its header line, before s49 rebuilt the decoders on generated protobuf classes.
Every case is a payload and the exact dict the old decoder returned for it:
captured frames, the payloads the existing tests build by hand, single-field
probes, and mutations of all three (a field dropped, a varint zeroed, a varint no
enum maps).

Never re-record to make this pass. A failure here means a decoder's output
changed, which s49 promised it would not.

TWO CLASSES OF CASE ARE EXEMPT, and only two.

The first is a payload the topic's schema cannot parse at all. The hand walker had no schema, so it reported whatever it could
read out of bytes that are not a valid message -- a string field holding invalid
UTF-8, a submessage field holding bytes that are not a message. A protobuf
parser rejects the whole payload, and the decoder returns {}. Those cases must
return {} and must be machine-made (`probed` or `synthetic`): a captured frame or
a payload a test author wrote that stops parsing is a real regression, and fails.

The second is a payload that sends a singular field more than once. The walker
visited every occurrence in wire order, and what a decoder then did was its own
accident: some kept the first, some the last, one kept whichever was "on". A
parser keeps the last, by specification. No encoder produces such a message --
the recorder's field probes do, by concatenating probes for the same field -- so
these are held only to returning a dict.

docs/development/PARALLAX_SCHEMAS.md lists the accepted differences.
"""

from __future__ import annotations

import base64
import binascii
from collections import defaultdict
from datetime import datetime
import json
import math
import pathlib
import sys
from typing import Any

from freezegun import freeze_time
from google.protobuf.descriptor import Descriptor, FieldDescriptor
from google.protobuf.message import DecodeError
import pytest

from custom_components.rivian.rivian_client import parallax
from custom_components.rivian.rivian_client.parallax.core import RVMDecoder

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))
from record_parallax_golden import tokenize

GOLDEN = pathlib.Path(__file__).parent / "fixtures" / "parallax_golden" / "golden.jsonl"

_ROWS = [json.loads(line) for line in GOLDEN.read_text().splitlines()]
HEADER: dict[str, Any] = _ROWS[0]
CASES: dict[str, list[dict[str, Any]]] = defaultdict(list)
for _case in _ROWS[1:]:
    CASES[_case["decoder"]].append(_case)


def _revive(value: Any) -> Any:
    """Undo the recorder's tagging of types JSON cannot carry."""
    if isinstance(value, list):
        return [_revive(v) for v in value]
    if isinstance(value, dict):
        if value.keys() == {"__float__"}:
            return float(value["__float__"])
        if value.keys() == {"__datetime__"}:
            return datetime.fromisoformat(value["__datetime__"])
        if value.keys() == {"__bytes__"}:
            return bytes.fromhex(value["__bytes__"])
        if value.keys() == {"__tuple__"}:
            return tuple(_revive(v) for v in value["__tuple__"])
        if value.keys() == {"__items__"}:
            return {_revive(k): _revive(v) for k, v in value["__items__"]}
        return {k: _revive(v) for k, v in value.items()}
    return value


def _same(a: Any, b: Any) -> bool:
    """Equal, and of the same types all the way down.

    `==` alone lets 1 pass for 1.0 and True pass for 1, and a sensor's state is
    one of those and not the other.
    """
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, float) and math.isnan(a):
        return math.isnan(b)
    return a == b


def _schema_rejects(name: str, payload: str) -> bool:
    """Whether the topic's message class refuses to parse `payload`."""
    message = RVMDecoder.messages[HEADER["topics_by_decoder"][name][0]]
    try:
        message.FromString(base64.b64decode(payload))
    except (DecodeError, binascii.Error, ValueError):
        return True
    return False


def _field_number(tag: bytes) -> int:
    key = shift = 0
    for byte in tag:
        key |= (byte & 0x7F) << shift
        shift += 7
    return key >> 3


def _repeats_a_singular_field(descriptor: Descriptor, raw: bytes) -> bool:
    """Whether `raw` sends a non-repeated field of `descriptor` twice, at any depth."""
    seen: set[int] = set()
    for tag, wire, value in tokenize(raw) or []:
        number = _field_number(tag)
        field = descriptor.fields_by_number.get(number)
        if field is None:
            continue
        if not field.is_repeated:
            if number in seen:
                return True
            seen.add(number)
        if (
            wire == 2
            and field.type == FieldDescriptor.TYPE_MESSAGE
            and _repeats_a_singular_field(field.message_type, value)
        ):
            return True
    return False


def _exempt(name: str, case: dict[str, Any]) -> str | None:
    """Why `case` is not held to its recorded output, or None if it is."""
    if case["source"] not in ("probed", "synthetic") or not case["payload"]:
        return None
    if _schema_rejects(name, case["payload"]):
        return "rejected"
    message = RVMDecoder.messages[HEADER["topics_by_decoder"][name][0]]
    if _repeats_a_singular_field(message.DESCRIPTOR, base64.b64decode(case["payload"])):
        return "repeated"
    return None


def test_every_registered_decoder_has_cases() -> None:
    """A decoder with no cases would pass this file by saying nothing."""
    registered = {func.__name__ for func in parallax.RVM_DECODERS.values()}
    assert registered == set(CASES)
    assert all(len(cases) >= 10 for cases in CASES.values())


def test_topics_still_reach_the_decoder_they_did() -> None:
    recorded = {k: sorted(v) for k, v in HEADER["topics_by_decoder"].items()}
    assert recorded == {
        name: sorted(
            topic
            for topic, func in parallax.RVM_DECODERS.items()
            if func.__name__ == name
        )
        for name in sorted(CASES)
    }


@pytest.mark.parametrize("name", sorted(CASES))
def test_decoder_output_is_unchanged(name: str) -> None:
    decoder = getattr(parallax, name)
    wrong = []
    with freeze_time(HEADER["frozen_now"]):
        for case in CASES[name]:
            got = decoder(case["payload"])
            expected = _revive(case["expected"])
            if _same(got, expected):
                continue
            why = _exempt(name, case)
            if why == "rejected" and got == {}:
                continue
            if why == "repeated" and isinstance(got, dict):
                continue
            wrong.append((case["source"], case["payload"], case["expected"], got))
    assert not wrong, (
        f"{len(wrong)} of {len(CASES[name])} cases differ; first: "
        f"source={wrong[0][0]} payload={wrong[0][1]!r}\n"
        f"  expected {wrong[0][2]!r}\n  got      {wrong[0][3]!r}"
    )


def test_the_exemption_is_narrow() -> None:
    """Most of the corpus must be held exactly, for every decoder.

    If a schema change made the parser reject most of a decoder's cases, the
    test above would pass on a decoder that returns {} for everything.
    """
    for name, cases in CASES.items():
        exempt = sum(_exempt(name, c) is not None for c in cases)
        assert exempt <= len(cases) * 0.7, (name, exempt, len(cases))
        held = [c for c in cases if c["expected"] and _exempt(name, c) is None]
        assert len(held) >= 5, (name, len(held))


@pytest.mark.parametrize("name", sorted(CASES))
def test_registry_dispatch_matches_the_named_decoder(name: str) -> None:
    """`decode_parallax_message` must reach the same function by topic."""
    case = next(c for c in CASES[name] if c["expected"] and _exempt(name, c) is None)
    with freeze_time(HEADER["frozen_now"]):
        for topic in HEADER["topics_by_decoder"][name]:
            got = parallax.decode_parallax_message(topic, case["payload"])
            assert _same(got, _revive(case["expected"]))
