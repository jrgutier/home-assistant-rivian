#!/usr/bin/env python3
"""Record what the Parallax decoders return, so a rewrite can be held to it.

ONE-SHOT, AND ALREADY SPENT. `tests/client/fixtures/parallax_golden/golden.jsonl`
was recorded from the hand-rolled `rivian_client/parallax.py` at the commit named
in the file's `recorded_from` field, immediately before s49 replaced it with
decoders built on generated protobuf classes. The file is the old module's
behaviour, frozen. Re-running this script against the new decoders records the
new decoders' output and proves nothing -- never do it to make
`tests/client/test_parallax_golden.py` pass. The script is kept as provenance for
where the cases came from.

Three sources of payloads, all decoded by the decoder under record:

captured   every frame in `tests/client/fixtures/parallax/` whose topic has a
           decoder.
harvested  every payload the existing test suite hands to a decoder. The suite is
           run once with each `decode_*` wrapped; the authors' hand-built frames
           are the only coverage for topics the vehicle never emitted.
probed     single-field frames that ask each decoder which field numbers it
           reads: every field 1-40 as a varint (0, 1, 2, an unmapped 99, a
           two-byte 300), a float, a double, a string and a nested message, and
           one level down inside every nested field the decoder reacted to. Only
           probes that change the output are kept. This is what covers a decoder
           whose only real frame carries one field.
synthetic  mutations of the three above: the empty payload, each field dropped
           (absent is not zero in these decoders, and a real frame cannot show
           that), each varint set to 0, and each varint set to a value no enum
           maps. Applied at the top level and inside nested messages.

Truncated and otherwise malformed mutations are deliberately NOT generated: the
hand walker returns whatever it parsed before the damage and a real protobuf
parser rejects the message, and that difference is accepted (see
docs/development/PARALLAX_SCHEMAS.md). Malformed payloads the existing tests
themselves pass are harvested like any other.

Two smaller snapshots are written beside it, from the same commit:

surface.json    every topic and the decoder it reaches, the subscription lists,
                and every module-level name of `rivian_client.parallax` with its
                value -- what callers, tests and tooling can see of the module.
send_path.json  the exact bytes the hand-rolled encoders produce for the
                climate-hold payload and the operation envelope.

Usage:
    .venv/bin/python scripts/record_parallax_golden.py
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from enum import StrEnum
import functools
import inspect
import json
import logging
import math
from pathlib import Path
import struct
import subprocess
import sys
import types
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

FIXTURES = REPO / "tests" / "client" / "fixtures" / "parallax"
OUT = REPO / "tests" / "client" / "fixtures" / "parallax_golden" / "golden.jsonl"
SURFACE = OUT.with_name("surface.json")
SEND_PATH = OUT.with_name("send_path.json")

# Per decoder. The charging graphs alone would otherwise contribute thousands of
# near-identical per-sample mutations.
MAX_SYNTHETIC_PER_SEED = 60
MAX_CASES_PER_DECODER = 120
# decode_gnss stamps its result with the current time.
FROZEN_NOW = "2026-01-01T00:00:00+00:00"
UNMAPPED_ENUM_VALUE = 99
MUTATION_DEPTH = 3
PROBE_FIELDS = range(1, 41)
PROBE_VARINTS = (0, 1, 2, UNMAPPED_ENUM_VALUE, 300)


# --------------------------------------------------------------------------
# A strict tokenizer that keeps raw bytes, so a mutated frame re-encodes exactly.
# The decoders' own walker converts fixed32/fixed64 to float and is lossy.
# --------------------------------------------------------------------------


def _varint(data: bytes, i: int) -> tuple[int, int] | None:
    result = shift = 0
    while i < len(data):
        byte = data[i]
        result |= (byte & 0x7F) << shift
        shift += 7
        i += 1
        if not byte & 0x80:
            return result, i
        if shift > 63:
            return None
    return None


def _enc_varint(value: int) -> bytes:
    out = bytearray()
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def tokenize(data: bytes) -> list[tuple[bytes, int, bytes]] | None:
    """Split into (tag bytes, wire type, value bytes); None if not well-formed.

    For a length-delimited field the value bytes are the content, without the
    length prefix.
    """
    fields: list[tuple[bytes, int, bytes]] = []
    i = 0
    while i < len(data):
        start = i
        tag = _varint(data, i)
        if tag is None or tag[0] >> 3 == 0:
            return None
        value, i = tag
        tag_bytes = data[start:i]
        wire = value & 7
        if wire == 0:
            got = _varint(data, i)
            if got is None:
                return None
            fields.append((tag_bytes, wire, data[i : got[1]]))
            i = got[1]
        elif wire in (1, 5):
            width = 8 if wire == 1 else 4
            if i + width > len(data):
                return None
            fields.append((tag_bytes, wire, data[i : i + width]))
            i += width
        elif wire == 2:
            got = _varint(data, i)
            if got is None or got[1] + got[0] > len(data):
                return None
            fields.append((tag_bytes, wire, data[got[1] : got[1] + got[0]]))
            i = got[1] + got[0]
        else:
            return None
    return fields


def field_number(tag: bytes) -> int:
    """The field number in a tag as `tokenize` returns it."""
    key = _varint(tag, 0)
    assert key is not None
    return key[0] >> 3


def repeats_singular_field(descriptor: Any, raw: bytes) -> bool:
    """Whether `raw` sends a non-repeated field of `descriptor` twice, at any depth.

    `descriptor` is a google.protobuf Descriptor. A parser keeps the last
    occurrence; the hand walker's decoders each did their own thing.
    """
    seen: set[int] = set()
    for tag, wire, value in tokenize(raw) or []:
        field = descriptor.fields_by_number.get(field_number(tag))
        if field is None:
            continue
        if not field.is_repeated:
            if field.number in seen:
                return True
            seen.add(field.number)
        if (
            wire == 2
            and field.message_type is not None
            and repeats_singular_field(field.message_type, value)
        ):
            return True
    return False


def assemble(fields: list[tuple[bytes, int, bytes]]) -> bytes:
    out = bytearray()
    for tag, wire, value in fields:
        out += tag
        if wire == 2:
            out += _enc_varint(len(value))
        out += value
    return bytes(out)


def mutations(data: bytes, depth: int = MUTATION_DEPTH) -> list[bytes]:
    """Well-formed variants of `data`: fields dropped, varints zeroed or unmapped."""
    fields = tokenize(data)
    if not fields:
        return []
    out: list[bytes] = []
    for index, (tag, wire, value) in enumerate(fields):
        before, after = fields[:index], fields[index + 1 :]
        out.append(assemble(before + after))
        if wire == 0:
            out.extend(
                assemble([*before, (tag, wire, _enc_varint(replacement)), *after])
                for replacement in (0, UNMAPPED_ENUM_VALUE)
            )
        elif wire == 2 and depth > 1:
            out.extend(
                assemble([*before, (tag, wire, inner), *after])
                for inner in mutations(value, depth - 1)
            )
    return out


def _field(number: int, wire: int, value: bytes) -> bytes:
    return assemble([(_enc_varint(number << 3 | wire), wire, value)])


def _scalar_probes(number: int) -> list[bytes]:
    return [
        *(_field(number, 0, _enc_varint(v)) for v in PROBE_VARINTS),
        _field(number, 5, struct.pack("<f", 1.5)),
        _field(number, 1, struct.pack("<d", 1.5)),
        _field(number, 2, b"abc"),
    ]


def probes(func: Any) -> list[bytes]:
    """Single-field frames `func` reacts to, top level and one level down."""

    def decode(raw: bytes) -> Any:
        return func(base64.b64encode(raw).decode())

    kept: list[bytes] = []
    for number in PROBE_FIELDS:
        kept.extend(raw for raw in _scalar_probes(number) if decode(raw))
        # A nested message: find the inner fields that matter by comparing
        # against the same field carrying an inert inner field.
        inert = decode(_field(number, 2, _field(63, 0, b"\x01")))
        reactive = [
            inner
            for inner_number in PROBE_FIELDS
            for inner in _scalar_probes(inner_number)
            if decode(_field(number, 2, inner)) != inert
        ]
        kept.extend(_field(number, 2, inner) for inner in reactive)
        if reactive:
            # Everything the decoder read, in one message, so combinations are
            # exercised and the mutations below have something to drop.
            first_of_each = {inner[0]: inner for inner in reversed(reactive)}
            kept.append(_field(number, 2, b"".join(first_of_each.values())))
    if kept:
        first_of_each = {raw[0]: raw for raw in reversed(kept)}
        kept.append(b"".join(first_of_each.values()))
    # Every field at once, per kind: a decoder that needs two fields together
    # (decode_gnss wants latitude AND longitude) ignores every single-field probe.
    for index in range(len(_scalar_probes(1))):
        everything = b"".join(_scalar_probes(n)[index] for n in PROBE_FIELDS)
        if decode(everything):
            kept.append(everything)
    return kept


# --------------------------------------------------------------------------
# JSON that round-trips what decoders return.
# --------------------------------------------------------------------------


def to_jsonable(value: Any) -> Any:
    """Tag the types JSON cannot carry, and refuse anything unexpected."""
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        # json round-trips a finite float exactly and keeps it a float (1.0, not
        # 1). nan and inf become bare tokens that do not compare equal.
        return value if math.isfinite(value) else {"__float__": repr(value)}
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    if isinstance(value, tuple):
        return {"__tuple__": [to_jsonable(v) for v in value]}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            return {
                "__items__": [
                    [to_jsonable(k), to_jsonable(v)] for k, v in value.items()
                ]
            }
        return {k: to_jsonable(v) for k, v in value.items()}
    raise TypeError(f"decoder returned an unrecordable {type(value).__name__}")


# --------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------


class Harvester:
    """pytest plugin: wrap every decoder before any test module imports it."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.originals: dict[str, Any] = {}

    def pytest_configure(self) -> None:
        from custom_components.rivian.rivian_client import parallax

        wrapped: dict[Any, Any] = {}
        for name, func in list(vars(parallax).items()):
            if not name.startswith("decode_") or name == "decode_parallax_message":
                continue
            self.originals[name] = func
            wrapped[func] = self._wrap(name, func)
            setattr(parallax, name, wrapped[func])
        for topic, func in list(parallax.RVM_DECODERS.items()):
            parallax.RVM_DECODERS[topic] = wrapped[func]

    def _wrap(self, name: str, func: Any) -> Any:
        @functools.wraps(func)
        def wrapper(payload: Any, *args: Any, **kwargs: Any) -> Any:
            if isinstance(payload, str) and not args and not kwargs:
                self.calls.append((name, payload))
            return func(payload, *args, **kwargs)

        return wrapper


def _decode_b64(payload: str) -> bytes | None:
    try:
        return base64.b64decode(payload)
    except (binascii.Error, ValueError):
        return None


def _mutate_into(chosen: dict[str, str], payloads: list[str], budget: int) -> None:
    """Add mutations of `payloads` to `chosen` until it holds `budget` cases.

    Round-robin, so one large seed cannot spend the whole budget.
    """
    queues = [
        mutations(raw)[:MAX_SYNTHETIC_PER_SEED]
        for raw in map(_decode_b64, payloads)
        if raw is not None
    ]
    while any(queues) and len(chosen) < budget:
        for queue in queues:
            if queue and len(chosen) < budget:
                chosen.setdefault(base64.b64encode(queue.pop(0)).decode(), "synthetic")


def canonical(value: Any) -> Any:
    """Like to_jsonable, for module constants: sets, ranges and int-keyed dicts."""
    if isinstance(value, (set, frozenset)):
        return {"__set__": sorted((canonical(v) for v in value), key=repr)}
    if isinstance(value, range):
        return {"__range__": [value.start, value.stop, value.step]}
    if isinstance(value, dict):
        return {"__items__": [[canonical(k), canonical(v)] for k, v in value.items()]}
    if isinstance(value, (list, tuple)):
        return {"__seq__": [canonical(v) for v in value], "type": type(value).__name__}
    return to_jsonable(value)


def _referenced_outside_the_module(name: str) -> bool:
    """Whether a test or script names `name`, so removing it would break them."""
    hits = subprocess.run(
        ["git", "grep", "-lw", name, "--", "tests", "scripts", "custom_components"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    here = "custom_components/rivian/rivian_client/parallax.py"
    return any(hit != here for hit in hits)


def record_surface(sha: str) -> None:
    from custom_components.rivian import coordinator
    from custom_components.rivian.rivian_client import parallax

    names: dict[str, dict[str, Any]] = {}
    for name, obj in sorted(vars(parallax).items()):
        if name.startswith("__") or name == "RVM_DECODERS":
            continue
        if isinstance(obj, types.ModuleType):
            continue
        if inspect.isfunction(obj) or inspect.isclass(obj):
            if obj.__module__ != parallax.__name__:
                continue  # an import, not part of this module's surface
            entry: dict[str, Any] = {
                "kind": "class" if inspect.isclass(obj) else "function"
            }
            if inspect.isfunction(obj):
                entry["signature"] = str(inspect.signature(obj))
            elif issubclass(obj, StrEnum):
                entry["members"] = {member.name: member.value for member in obj}
        elif isinstance(obj, logging.Logger):
            entry = {"kind": "logger", "value": obj.name}
        elif isinstance(obj, (dict, set, frozenset, range, list, tuple, int, str)):
            entry = {"kind": type(obj).__name__, "value": canonical(obj)}
        else:
            continue  # typing aliases and other imports
        # A private function is an implementation detail unless something
        # outside the module reaches for it. Everything else must survive.
        entry["required"] = not (
            name.startswith("_") and entry["kind"] == "function"
        ) or _referenced_outside_the_module(name)
        names[name] = entry

    SURFACE.parent.mkdir(parents=True, exist_ok=True)
    SURFACE.write_text(
        json.dumps(
            {
                "recorded_from": sha,
                "rvm_decoders": {
                    topic: func.__name__
                    for topic, func in parallax.RVM_DECODERS.items()
                },
                "parallax_rvms": parallax.PARALLAX_RVMS,
                "charging_rvms": parallax.CHARGING_RVMS,
                "subscribed_rvms": list(coordinator.SUBSCRIBED_RVMS),
                "names": names,
            },
            indent=1,
        )
        + "\n"
    )


def record_send_path(sha: str) -> None:
    from custom_components.rivian.rivian_client import parallax
    from custom_components.rivian.rivian_client.proto import vehicle_operation as vo

    cases: list[dict[str, Any]] = []
    for seconds in (0, 1, 127, 128, 300, 7200, 2**31 - 1):
        cases.append(
            {
                "call": "encode_climate_hold_setting",
                "args": [seconds],
                "hex": parallax.encode_climate_hold_setting(seconds).hex(),
            }
        )
    for minutes in (0, 1, 5, 120):
        cases.append(
            {
                "call": "build_climate_hold_command",
                "args": [minutes],
                "payload_b64": parallax.build_climate_hold_command(minutes).payload_b64,
            }
        )
    phone_id, operation_id = bytes(range(16)), bytes(range(16, 32))
    hold = "comfort.cabin.climate_hold_setting"
    # version, phone id, request id, rvm, operation type, payload, (seconds, nanos).
    # The rows with zeros and empties are the point: the hand encoder omits a
    # default scalar but always emits every submessage, even an empty one.
    grid: list[tuple[int, bytes, str, str, int, bytes, tuple[int, int]]] = [
        (1, phone_id, "17-48c080c8-0000-4000-8000-000000000001", hold, 1,
         bytes.fromhex("08a038"), (1760000000, 123456789)),
        (1, phone_id, "req", hold, 1, b"", (1760000000, 0)),
        (1, phone_id, "req", "comfort.cabin.climate_hold_status", 0, b"", (0, 0)),
        (0, b"", "", "", 0, b"", (0, 0)),
        (1, phone_id, "req", "vehicle.wheels.vehicle_wheels", 2, b"\x00\xff", (0, 5)),
        (300, phone_id, "é-unicode", "ota.user_schedule.ota_config", 1,
         bytes(200), (2**31 - 1, 999999999)),
    ]  # fmt: skip
    for version, phone, request_id, rvm, op_type, payload, stamp in grid:
        request = vo.VehicleOperationRequest(
            metadata=vo.Metadata(
                phone_info=vo.PhoneInfo(version=version, phone_id=phone),
                request_id=request_id,
            ),
            operation=vo.Operation(
                rvm_type=rvm,
                operation_type=op_type,
                operation_id=operation_id,
                payload=payload,
                timestamp=vo.Timestamp(*stamp),
            ),
        )
        cases.append(
            {
                "call": "VehicleOperationRequest",
                "args": [version, phone.hex(), request_id, rvm, op_type,
                         operation_id.hex(), payload.hex(), list(stamp)],
                "hex": request.SerializeToString().hex(),
            }
        )  # fmt: skip
    for cls in ("Timestamp", "PhoneInfo", "Metadata"):
        cases.append(
            {
                "call": f"{cls}()",
                "args": [],
                "hex": getattr(vo, cls)().SerializeToString().hex(),
            }
        )
    for moment in (
        "2026-01-01T00:00:00+00:00",
        "2026-08-18T15:13:07.250000+00:00",
        "1970-01-01T00:00:00.999999+00:00",
        "2025-06-15T12:34:56.789012-07:00",
    ):
        stamp_obj = vo.Timestamp.from_datetime(datetime.fromisoformat(moment))
        cases.append(
            {
                "call": "Timestamp.from_datetime",
                "args": [moment],
                "seconds": stamp_obj.seconds,
                "nanos": stamp_obj.nanos,
                "hex": stamp_obj.SerializeToString().hex(),
                "roundtrip": stamp_obj.ToDatetime().isoformat(),
            }
        )
    SEND_PATH.write_text(
        json.dumps({"recorded_from": sha, "cases": cases}, indent=1) + "\n"
    )


def main() -> int:
    from freezegun import freeze_time
    import pytest

    dirty = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            "custom_components/rivian/rivian_client",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty:
        print(
            "refusing to record: rivian_client/ has uncommitted changes",
            file=sys.stderr,
        )
        return 2
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    record_surface(sha)
    record_send_path(sha)

    harvester = Harvester()
    pytest.main(
        [
            "-q",
            "-p",
            "no:cacheprovider",
            "--no-cov",
            "-x",
            "tests",
            # The golden test replays this file's own output; harvesting it
            # would relabel every recorded case as one the tests wrote.
            "--ignore=tests/client/test_parallax_golden.py",
        ],
        plugins=[harvester],
    )
    originals = harvester.originals

    from custom_components.rivian.rivian_client import parallax

    topics_by_decoder: dict[str, list[str]] = {}
    for topic, func in parallax.RVM_DECODERS.items():
        topics_by_decoder.setdefault(func.__name__, []).append(topic)

    seeds: dict[str, dict[str, str]] = {name: {} for name in originals}
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    for topic, entry in manifest.items():
        func = parallax.RVM_DECODERS.get(topic)
        if func is None:
            continue
        payload = base64.b64encode((FIXTURES / entry["file"]).read_bytes()).decode()
        seeds[func.__name__].setdefault(payload, "captured")
    for name, payload in harvester.calls:
        seeds[name].setdefault(payload, "harvested")

    cases: list[dict[str, Any]] = []
    freezer = freeze_time(FROZEN_NOW)
    freezer.start()
    for name in sorted(originals):
        func = originals[name]
        chosen: dict[str, str] = dict(seeds[name])
        chosen.setdefault("", "synthetic")

        # Real frames first: they get half the budget before any probe does.
        _mutate_into(chosen, list(seeds[name]), MAX_CASES_PER_DECODER // 2)
        probed = [base64.b64encode(raw).decode() for raw in probes(func)]
        # The multi-field probes are appended last and are the valuable ones.
        for payload in reversed(probed):
            if len(chosen) >= MAX_CASES_PER_DECODER * 3 // 4:
                break
            chosen.setdefault(payload, "probed")
        _mutate_into(chosen, probed[::-1], MAX_CASES_PER_DECODER)
        for payload, source in chosen.items():
            raw = _decode_b64(payload)
            cases.append(
                {
                    "decoder": name,
                    "payload": payload,
                    "source": source,
                    "wellformed": raw is not None and tokenize(raw) is not None,
                    "expected": to_jsonable(func(payload)),
                }
            )

    freezer.stop()

    # One case per line: a 120-case decoder stays diffable and the file stays
    # a third the size of indented JSON.
    header = {
        "recorded_from": sha,
        "frozen_now": FROZEN_NOW,
        "topics_by_decoder": dict(sorted(topics_by_decoder.items())),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in [header, *cases]) + "\n"
    )
    by_source: dict[str, int] = {}
    for case in cases:
        by_source[case["source"]] = by_source.get(case["source"], 0) + 1
    uncovered = sorted(n for n in originals if not seeds[n])
    print(f"recorded {len(cases)} cases from {sha[:9]}: {by_source}")
    print(f"decoders with no captured or harvested payload: {uncovered or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
