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

`--live SECONDS` asks the same question of the vehicle instead of the corpus. It
opens a READ-ONLY subscription to every decoded topic (it sends no operation and
actuates nothing; like scripts/capture_rvm_frames.py it runs beside a live Home
Assistant), holds what arrives in memory, and reports per topic whether the two
decoders agree and whether the frame fits the schema. It prints verdicts and
sizes only -- never a frame or a decoded value, because several of these topics
carry coordinates, saved places and network names -- and writes nothing. Tokens
come from `.env`; none is printed.

Usage:
    .venv/bin/python scripts/parallax_differential.py [--ref origin/master]
    .venv/bin/python scripts/parallax_differential.py --live 150 [--system-dns]
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
from collections import Counter
import contextlib
import json
import logging
from pathlib import Path
import subprocess
import sys
import time
import types
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from record_parallax_golden import (
    FROZEN_NOW,
    _enc_varint,
    _varint,
    assemble,
    field_number,
    repeats_singular_field,
    to_jsonable,
    tokenize,
)

OLD_PATH = "custom_components/rivian/rivian_client/parallax.py"
FIXTURES = REPO / "tests" / "client" / "fixtures" / "parallax"
GOLDEN = REPO / "tests" / "client" / "fixtures" / "parallax_golden" / "golden.jsonl"
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


def _has_wide_varint(descriptor: Any, raw: bytes) -> bool:
    """Whether a varint in `raw` does not fit its field's declared 32-bit type."""
    from google.protobuf.descriptor import FieldDescriptor

    limits = {
        FieldDescriptor.TYPE_ENUM: 2**31,
        FieldDescriptor.TYPE_INT32: 2**31,
        FieldDescriptor.TYPE_SINT32: 2**31,
        FieldDescriptor.TYPE_UINT32: 2**32,
    }
    for tag, wire, value in tokenize(raw) or []:
        field = descriptor.fields_by_number.get(field_number(tag))
        if field is None:
            continue
        if wire == 0 and field.type in limits:
            got = _varint(value, 0)
            if got is not None and got[0] >= limits[field.type]:
                return True
        if (
            wire == 2
            and field.message_type is not None
            and _has_wide_varint(field.message_type, value)
        ):
            return True
    return False


def classify(message_class: Any, raw: bytes) -> str | None:
    """The accepted class a disagreement on `raw` falls in, or None."""
    from google.protobuf.message import DecodeError

    try:
        message_class.FromString(raw)
    except DecodeError:
        return "rejected"
    if repeats_singular_field(message_class.DESCRIPTOR, raw):
        return "repeated"
    if _has_wide_varint(message_class.DESCRIPTOR, raw):
        return "wide"
    return None


def mistyped(message: Any, path: str = "") -> list[str]:
    """Declared fields of `message` that arrived with another wire type.

    Protobuf files a field under "unknown" when its number is not in the schema
    -- or when it is, but arrived with a wire type the schema does not expect.
    The first is normal here. The second means the declared type is wrong, and a
    decoder reading that field silently sees its default.
    """
    from google.protobuf.unknown_fields import UnknownFieldSet

    path = path or message.DESCRIPTOR.name
    found = [
        f"{path}: field {unknown.field_number} is declared, "
        f"but arrived as wire type {unknown.wire_type}"
        for unknown in UnknownFieldSet(message)
        if unknown.field_number in message.DESCRIPTOR.fields_by_number
    ]
    for field, value in message.ListFields():
        if field.message_type is None:
            continue
        for index, item in enumerate(value if field.is_repeated else [value]):
            found += mistyped(item, f"{path}.{field.name}[{index}]")
    return found


async def listen(topics: list[str], seconds: int) -> dict[str, set[bytes]] | None:
    """Every distinct frame the vehicle publishes on `topics` in `seconds`."""
    import aiohttp
    from f8_probe import load_env

    from custom_components.rivian.rivian_client import Rivian

    frames: dict[str, set[bytes]] = {}

    def on_message(data: dict) -> None:
        # The frame is wrapped in an extra `payload` layer and parallaxMessages
        # is one object, not a list (coordinator._process_parallax_data).
        message = ((data.get("payload") or {}).get("data") or {}).get(
            "parallaxMessages"
        )
        if message and message.get("rvm"):
            encoded = message.get("payload")
            frames.setdefault(message["rvm"], set()).add(
                base64.b64decode(encoded) if encoded else b""
            )

    env = load_env()
    async with aiohttp.ClientSession() as session:
        client = Rivian(
            session=session,
            access_token=env["RIVIAN_ACCESS_TOKEN"],
            refresh_token=env["RIVIAN_REFRESH_TOKEN"],
            user_session_token=env["RIVIAN_USER_SESSION_TOKEN"],
        )
        info = await (await client.get_user_information(True)).json()
        vehicle_id = info["data"]["currentUser"]["vehicles"][0]["id"]
        unsubscribe = await client.subscribe_for_parallax_messages(
            vehicle_id, on_message, rvms=topics
        )
        if unsubscribe is None:
            return None
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            await asyncio.sleep(1)
        await unsubscribe()
    return frames


def live(old: types.ModuleType, seconds: int) -> int:
    from freezegun import freeze_time
    from google.protobuf.message import DecodeError

    from custom_components.rivian.rivian_client import parallax as new
    from custom_components.rivian.rivian_client.parallax.core import RVMDecoder

    topics = sorted(new.RVM_DECODERS)
    frames = asyncio.run(listen(topics, seconds))
    if frames is None:
        print("subscription refused -- nothing compared", file=sys.stderr)
        return 2

    width = max(map(len, topics))
    print(f"{'topic':{width}}  frames  agree  schema  bytes")
    differing = 0
    with freeze_time(FROZEN_NOW):
        for topic in topics:
            got = sorted(frames.get(topic, ()))
            if not got:
                print(f"{topic:{width}}  {'-':>6}  silent")
                continue
            agree = fits = 0
            for raw in got:
                payload = base64.b64encode(raw).decode()
                was = json.dumps(
                    to_jsonable(old.RVM_DECODERS[topic](payload)), sort_keys=True
                )
                now = json.dumps(
                    to_jsonable(new.RVM_DECODERS[topic](payload)), sort_keys=True
                )
                agree += was == now
                # A frame the schema rejects does not fit, and is counted as such.
                with contextlib.suppress(DecodeError):
                    fits += not mistyped(RVMDecoder.messages[topic].FromString(raw))
            ok = agree == len(got) == fits
            differing += not ok
            sizes = (
                f"{len(got[0])}" if len(got) == 1 else f"{len(got[0])}-{len(got[-1])}"
            )
            print(
                f"{topic:{width}}  {len(got):>6}  {agree:>3}/{len(got):<2} "
                f"{fits:>3}/{len(got):<2}  {sizes}{'' if ok else '   <-- LOOK'}"
            )
    published = sum(1 for topic in topics if frames.get(topic))
    total = sum(len(frames[topic]) for topic in topics if frames.get(topic))
    print(
        f"\n{published} of {len(topics)} decoded topics published in {seconds}s; "
        f"{total} distinct frames; {differing} topic(s) where the decoders "
        "disagree or the schema does not fit."
    )
    print(f"old decoders from {old.__file__.rsplit(':', 1)[0]}.")
    return 1 if differing else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ref", default="origin/master")
    parser.add_argument("--show", type=int, default=5, help="unexplained to print")
    parser.add_argument(
        "--live", type=int, metavar="SECONDS", help="compare on frames from the vehicle"
    )
    parser.add_argument(
        "--system-dns",
        action="store_true",
        help="with --live: resolve through the OS instead of aiodns, for a "
        "network where aiodns times out",
    )
    args = parser.parse_args()
    if args.live:
        if args.system_dns:
            import aiohttp.connector
            import aiohttp.resolver

            aiohttp.connector.DefaultResolver = aiohttp.resolver.ThreadedResolver
        logging.disable(logging.CRITICAL)
        return live(load_old(args.ref), args.live)

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
