"""What the rest of the code can see of `rivian_client.parallax` did not change.

`fixtures/parallax_golden/surface.json` is the module as it stood before s49
turned it into a package (recorded by `scripts/record_parallax_golden.py`): which
decoder each topic reaches, the subscription lists, and every module-level name
with its value.

The subscription lists are the part with consequences outside this repository.
`coordinator.SUBSCRIBED_RVMS` is derived from `RVM_DECODERS`, so a topic gained or
lost here is a subscription the vehicle opens or stops serving.

Names may be ADDED. Nothing recorded as required may disappear or change value:
callers import them, tests import the private maps, and
`tests/test_parallax_gap_fill.py` walks every module-level dict.
"""

from __future__ import annotations

import inspect
import json
import logging
import pathlib
from typing import Any

import pytest

from custom_components.rivian import coordinator
from custom_components.rivian.rivian_client import parallax

SURFACE: dict[str, Any] = json.loads(
    (
        pathlib.Path(__file__).parent / "fixtures" / "parallax_golden" / "surface.json"
    ).read_text()
)
NAMES: dict[str, dict[str, Any]] = SURFACE["names"]
REQUIRED = sorted(name for name, entry in NAMES.items() if entry["required"])


def _canonical(value: Any) -> Any:
    """The recorder's encoding of a module constant."""
    if isinstance(value, (set, frozenset)):
        return {"__set__": sorted((_canonical(v) for v in value), key=repr)}
    if isinstance(value, range):
        return {"__range__": [value.start, value.stop, value.step]}
    if isinstance(value, dict):
        return {"__items__": [[_canonical(k), _canonical(v)] for k, v in value.items()]}
    if isinstance(value, (list, tuple)):
        return {"__seq__": [_canonical(v) for v in value], "type": type(value).__name__}
    return value


class TestSubscriptions:
    def test_topics_reach_the_same_decoders_in_the_same_order(self) -> None:
        now = [(topic, func.__name__) for topic, func in parallax.RVM_DECODERS.items()]
        assert now == list(SURFACE["rvm_decoders"].items())

    def test_parallax_rvms(self) -> None:
        assert parallax.PARALLAX_RVMS == SURFACE["parallax_rvms"]

    def test_charging_rvms(self) -> None:
        assert parallax.CHARGING_RVMS == SURFACE["charging_rvms"]

    def test_the_vehicle_is_asked_for_the_same_topics(self) -> None:
        assert list(coordinator.SUBSCRIBED_RVMS) == SURFACE["subscribed_rvms"]


class TestNames:
    def test_the_snapshot_is_not_empty(self) -> None:
        assert len(REQUIRED) > 100

    @pytest.mark.parametrize("name", REQUIRED)
    def test_name_survives_with_its_value(self, name: str) -> None:
        entry = NAMES[name]
        assert hasattr(parallax, name), f"{name} is gone from rivian_client.parallax"
        obj = getattr(parallax, name)
        kind = entry["kind"]
        if kind == "function":
            assert inspect.isfunction(obj)
            assert str(inspect.signature(obj)) == entry["signature"]
        elif kind == "class":
            assert inspect.isclass(obj)
            if "members" in entry:
                assert {m.name: m.value for m in obj} == entry["members"]
        elif kind == "logger":
            # caplog filters and log configuration key on this name.
            assert isinstance(obj, logging.Logger)
            assert obj.name == entry["value"]
        elif kind == "set":
            # The only mutable set is _WARNED_UNKNOWN_RVMS, which is run-time
            # state: its identity matters (see below), its contents do not.
            assert type(obj) is set
        else:
            assert type(obj).__name__ == kind
            assert _canonical(obj) == entry["value"]

    def test_decoder_table_is_a_plain_dict_of_callables(self) -> None:
        assert type(parallax.RVM_DECODERS) is dict
        assert all(callable(func) for func in parallax.RVM_DECODERS.values())

    def test_decoders_are_reachable_by_name(self) -> None:
        """`RVM_DECODERS[topic]` and `parallax.<name>` are the same object."""
        for func in parallax.RVM_DECODERS.values():
            assert getattr(parallax, func.__name__) is func

    def test_warned_topics_set_is_the_one_the_dispatcher_mutates(self) -> None:
        """Tests clear this set through the module; a rebound copy would not."""
        topic = "surface.test.unknown_topic"
        parallax._WARNED_UNKNOWN_RVMS.discard(topic)
        assert parallax.decode_parallax_message(topic, "") is None
        assert topic in parallax._WARNED_UNKNOWN_RVMS
        parallax._WARNED_UNKNOWN_RVMS.discard(topic)
