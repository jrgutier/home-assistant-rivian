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
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
import math
import pathlib
from typing import Any

from freezegun import freeze_time
import pytest

from custom_components.rivian.rivian_client import parallax

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
            if not _same(got, _revive(case["expected"])):
                wrong.append((case["source"], case["payload"], case["expected"], got))
    assert not wrong, (
        f"{len(wrong)} of {len(CASES[name])} cases differ; first: "
        f"source={wrong[0][0]} payload={wrong[0][1]!r}\n"
        f"  expected {wrong[0][2]!r}\n  got      {wrong[0][3]!r}"
    )


@pytest.mark.parametrize("name", sorted(CASES))
def test_registry_dispatch_matches_the_named_decoder(name: str) -> None:
    """`decode_parallax_message` must reach the same function by topic."""
    case = next(c for c in CASES[name] if c["expected"])
    with freeze_time(HEADER["frozen_now"]):
        for topic in HEADER["topics_by_decoder"][name]:
            got = parallax.decode_parallax_message(topic, case["payload"])
            assert _same(got, _revive(case["expected"]))
