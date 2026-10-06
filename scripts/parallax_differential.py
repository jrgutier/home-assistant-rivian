#!/usr/bin/env python3
"""Run the old Parallax decoders and the new ones side by side on hostile input.

The golden corpus (`tests/client/test_parallax_golden.py`) holds the rebuilt
decoders to the old ones on well-formed payloads. This asks the other question:
where do the two DISAGREE, and is every disagreement one of the kinds s49
accepted? It feeds both the same payloads -- every captured frame and every
golden case, then mutations chosen to break things -- and sorts each
disagreement into a class. Anything it cannot classify is printed and fails the
run.

The old module is not in the tree. It is read out of git at `--ref` (default
`origin/master`, which is the pre-s49 module until s49 merges; afterwards pass
the commit before it) and executed in memory. Nothing is written.

Mutations, per seed payload, at every nesting depth the bytes parse to:

    truncate   cut the payload short at each byte
    duplicate  send each field twice
    zero       set each varint to 0
    wide       set each varint to 2**64 - 1

The accepted classes of disagreement (docs/development/PARALLAX_SCHEMAS.md):

    rejected   the schema cannot parse the payload. The walker reported what it
               had read before the damage; a parser refuses the message.
    repeated   a single-valued field sent more than once. The walker's decoders
               kept the first, the last, or a mixture; a parser keeps the last.
    wide       a varint that does not fit the field's declared 32-bit type. The
               walker passed 64 bits to the decoder; a parser truncates.

Usage:
    .venv/bin/python scripts/parallax_differential.py [--ref origin/master]
"""

from __future__ import annotations

import argparse
import base64
import binascii
from collections import Counter
import json
import logging
from pathlib import Path
import subprocess
import sys
import types
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from record_parallax_golden import _enc_varint, _varint, assemble, to_jsonable, tokenize

OLD_PATH = "custom_components/rivian/rivian_client/parallax.py"
FIXTURES = REPO / "tests" / "client" / "fixtures" / "parallax"
GOLDEN = REPO / "tests" / "client" / "fixtures" / "parallax_golden" / "golden.jsonl"
FROZEN_NOW = "2026-01-01T00:00:00+00:00"
MAX_DEPTH = 3
MAX_MUTATIONS_PER_SEED = 400


def load_old(ref: str) -> types.ModuleType:
    """The pre-s49 module at `ref`, executed in memory."""
    source = subprocess.run(
        ["git", "show", f"{ref}:{OLD_PATH}"],
        cwd=REPO, capture_output=True, text=True, check=False,
    )  # fmt: skip
    if source.returncode != 0:
        raise SystemExit(
            f"{OLD_PATH} does not exist at {ref}. After s49 merges, pass the "
            "commit before it with --ref."
        )
    # Its one relative import is a three-line varint encoder used by the WRITE
    # half, which this script never calls.
    text = source.stdout.replace(
        "from .proto.vehicle_operation import _encode_varint_field",
        "_encode_varint_field = None",
    )
    module = types.ModuleType("old_parallax")
    module.__file__ = f"{ref}:{OLD_PATH}"
    sys.modules[module.__name__] = module
    exec(compile(text, module.__file__, "exec"), module.__dict__)  # noqa: S102
    return module


def _number(tag: bytes) -> int:
    got = _varint(tag, 0)
    assert got is not None
    return got[0] >> 3


def mutations(data: bytes, depth: int = MAX_DEPTH) -> list[bytes]:
    out = [data[:cut] for cut in range(len(data))]
    fields = tokenize(data)
    if not fields:
        return out
    for index, (tag, wire, value) in enumerate(fields):
        before, after = fields[:index], fields[index + 1 :]
        out.append(assemble([*before, (tag, wire, value), (tag, wire, value), *after]))
        if wire == 0:
            out.extend(
                assemble([*before, (tag, wire, _enc_varint(replacement)), *after])
                for replacement in (0, 2**64 - 1)
            )
        elif wire == 2 and depth > 1:
            out.extend(
                assemble([*before, (tag, wire, inner), *after])
                for inner in mutations(value, depth - 1)
            )
    return out


def classify(message_class: Any, raw: bytes) -> str | None:
    """The accepted class a disagreement on `raw` falls in, or None."""
    from google.protobuf.descriptor import FieldDescriptor
    from google.protobuf.message import DecodeError

    try:
        message_class.FromString(raw)
    except DecodeError:
        return "rejected"

    narrow = {
        FieldDescriptor.TYPE_ENUM: 2**31,
        FieldDescriptor.TYPE_INT32: 2**31,
        FieldDescriptor.TYPE_SINT32: 2**31,
        FieldDescriptor.TYPE_UINT32: 2**32,
    }

    def walk(descriptor: Any, data: bytes) -> str | None:
        seen: set[int] = set()
        found = None
        for tag, wire, value in tokenize(data) or []:
            field = descriptor.fields_by_number.get(_number(tag))
            if field is None:
                continue
            if not field.is_repeated:
                if field.number in seen:
                    return "repeated"
                seen.add(field.number)
            if wire == 0 and field.type in narrow:
                got = _varint(value, 0)
                if got is not None and got[0] >= narrow[field.type]:
                    found = "wide"
            if wire == 2 and field.type == FieldDescriptor.TYPE_MESSAGE:
                inner = walk(field.message_type, value)
                if inner == "repeated":
                    return inner
                found = found or inner
        return found

    return walk(message_class.DESCRIPTOR, raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ref", default="origin/master")
    parser.add_argument("--show", type=int, default=5, help="unexplained to print")
    args = parser.parse_args()

    from freezegun import freeze_time

    from custom_components.rivian.rivian_client import parallax as new
    from custom_components.rivian.rivian_client.parallax.core import RVMDecoder

    old = load_old(args.ref)
    logging.disable(logging.CRITICAL)

    seeds: dict[str, set[bytes]] = {topic: set() for topic in new.RVM_DECODERS}
    for topic, entry in json.loads((FIXTURES / "manifest.json").read_text()).items():
        if topic in seeds:
            seeds[topic].add((FIXTURES / entry["file"]).read_bytes())
    rows = [json.loads(line) for line in GOLDEN.read_text().splitlines()]
    for case in rows[1:]:
        try:
            raw = base64.b64decode(case["payload"])
        except (binascii.Error, ValueError):
            continue
        for topic in rows[0]["topics_by_decoder"][case["decoder"]]:
            seeds[topic].add(raw)

    totals: Counter[str] = Counter()
    per_topic: dict[str, Counter[str]] = {}
    unexplained: list[tuple[str, str, Any, Any]] = []
    with freeze_time(FROZEN_NOW):
        for topic in sorted(seeds):
            counts = per_topic.setdefault(topic, Counter())
            payloads: set[bytes] = set(seeds[topic])
            for seed in sorted(seeds[topic]):
                payloads.update(mutations(seed)[:MAX_MUTATIONS_PER_SEED])
            for raw in sorted(payloads):
                payload = base64.b64encode(raw).decode()
                was = to_jsonable(old.RVM_DECODERS[topic](payload))
                now = to_jsonable(new.RVM_DECODERS[topic](payload))
                if json.dumps(was, sort_keys=True) == json.dumps(now, sort_keys=True):
                    counts["same"] += 1
                    continue
                kind = classify(RVMDecoder.messages[topic], raw)
                counts[kind or "UNEXPLAINED"] += 1
                if kind is None:
                    unexplained.append((topic, payload, was, now))
            totals.update(counts)

    width = max(map(len, per_topic))
    columns = ["same", "rejected", "repeated", "wide", "UNEXPLAINED"]
    print(f"{'topic':{width}}  " + "  ".join(f"{c:>11}" for c in columns))
    for topic, counts in per_topic.items():
        if any(counts[c] for c in columns[1:]):
            print(f"{topic:{width}}  " + "  ".join(f"{counts[c]:>11}" for c in columns))
    print(f"{'TOTAL':{width}}  " + "  ".join(f"{totals[c]:>11}" for c in columns))
    quiet = sum(1 for c in per_topic.values() if not any(c[k] for k in columns[1:]))
    print(f"\n{quiet} of {len(per_topic)} topics agree on every payload (not listed).")
    print(f"old decoders from {args.ref}; {sum(totals.values())} payloads compared.")

    for topic, payload, was, now in unexplained[: args.show]:
        print(f"\nUNEXPLAINED {topic}\n  payload {payload}\n  old {was}\n  new {now}")
    return 1 if unexplained else 0


if __name__ == "__main__":
    raise SystemExit(main())
