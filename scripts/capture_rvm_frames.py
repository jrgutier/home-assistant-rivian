#!/usr/bin/env python3
"""Capture Parallax RVM payloads to fixture files, so a decoder can be written.

READ-ONLY. This opens the `parallaxMessages` subscription and writes whatever
arrives. It sends no vehicle operation, signed or otherwise, and actuates
nothing.

**It does not require an outage.** `RVM_FIXTURES.md` once said capture had to run
as sole subscriber, with the Home Assistant config entry disabled; that claim was
RETRACTED on 2026-08-20 after measurement (`WS_CONTENTION.md`, claim C8): a second
connection received `connection_ack` in 0.0 s with production up, and the full
33-topic set arrived with production subscribed. Capture runs against a live
instance.

Why capture at all: a decoder needs the value vocabulary, and reading field
numbers out of the decompilation gives the shape but not the meaning of the
values. `docs/development/PARALLAX_DECODERS.md` builds vocabularies from live
values for exactly this reason. **A decoder without a frame is a sensor that
renders wrong values as confidently as right ones**, which is worse than the
recorded gap it replaces.

Silence is a result, not a failure. An RVM the vehicle does not currently publish
yields nothing no matter how long you wait -- `ota.user_schedule.ota_config`
returned 0 bytes across three sessions because the vehicle had no OTA schedule
configured. Record that outcome; do not synthesise a payload to fill it.

Identifiers are not interchangeable: `parallaxMessages` wants
`vehicles[0].id` (shape `01-XXXXXXXXX`). `RIVIAN_VEHICLE_ID` in `.env` matched
none of the three known identifiers and produced "Invalid vehicle ID".

Secrets: reads tokens from `.env` and prints none of them.

Usage:
    .venv/bin/python scripts/capture_rvm_frames.py --list
    .venv/bin/python scripts/capture_rvm_frames.py --seconds 90
    .venv/bin/python scripts/capture_rvm_frames.py --all --seconds 120 --write
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp
from f8_probe import load_env

from custom_components.rivian.rivian_client import Rivian

FIXTURES = (
    Path(__file__).resolve().parents[1] / "tests" / "client" / "fixtures" / "parallax"
)

TARGETS = (
    # Every dispatch-bound topic is already decoded -- `PARALLAX_DECODERS.md`
    # closed that search over all 32,941 files. This default is the frontier
    # build's OTA state, kept as a convenient single-topic smoke test rather
    # than as a decoding gap. Pass topics explicitly, or `--all <file>`, to
    # survey. Counts of "undecoded" have been wrong here four times; derive
    # them from the manifest, never from a filename.
    "ota.deployment.state",
)


# A frame from a real vehicle is not automatically safe to commit. These payloads
# carry saved-place NAMES, wifi SSIDs, MAC addresses, account and device UUIDs and
# GPS coordinates. A capture run that wrote every topic into the tracked fixtures
# directory put a child's school name and a home SSID one `git add` away from a
# public repository. That happened; this guard is why it cannot happen twice.
#
# The rule is deliberately blunt: a protobuf state frame is numbers and enum tags,
# so any run of printable text is a string field, and string fields in this
# protocol are overwhelmingly identifiers. Refuse those and report them, rather
# than trying to classify which strings are "safe".
PRINTABLE_RUN = re.compile(rb"[ -~]{5,}")

# Firmware versions and protobuf type names are the same on every vehicle, so
# they identify nobody.
SAFE_STRINGS = re.compile(rb"^(?:\d[\d.]+|[A-Z][A-Za-z]+State|[0-9a-f]{8})$")


def carries_identifiers(raw: bytes) -> list[str]:
    """Printable runs that are not obviously vehicle-independent.

    Requires three letters as well as length, because protobuf float payloads
    produce short printable runs of punctuation (`z,_@`) that are noise, not
    text. Withholding those would make the tool useless enough that someone
    disables the guard, which is a worse outcome than the false positive. The
    bias still errs toward withholding: an identifier that slips through reaches
    a public repository, while an over-withheld frame merely needs a look by hand.
    """
    return [
        run.decode("ascii", "replace")
        for run in PRINTABLE_RUN.findall(raw)
        if not SAFE_STRINGS.match(run)
        and sum(c.isalpha() for c in run.decode("ascii", "replace")) >= 3
    ]


async def capture(topics: tuple[str, ...], seconds: int, write: bool) -> int:
    env = load_env()
    seen: dict[str, bytes] = {}

    def on_message(data: dict) -> None:
        # Shape read from coordinator.py:1357-1369, not guessed. Two things bite:
        # the frame is wrapped in an extra `payload` layer, and `parallaxMessages`
        # is a SINGLE OBJECT, not a list. Getting either wrong makes every topic
        # look silent, which reads as "the vehicle publishes nothing" rather than
        # "the reader is broken".
        if not (envelope := data.get("payload")) or not (pdata := envelope.get("data")):
            return
        message = pdata.get("parallaxMessages")
        if not message:
            return
        rvm, encoded = message.get("rvm"), message.get("payload")
        if not rvm or encoded is None:
            return
        raw = base64.b64decode(encoded) if encoded else b""
        # Keep the LONGEST frame seen: a topic can publish an empty payload first
        # and a populated one later, and the empty one is not a useful fixture.
        if rvm not in seen or len(raw) > len(seen[rvm]):
            seen[rvm] = raw
            print(f"  {rvm:44s} {len(raw):>4}B  {raw.hex()[:64]}")

    async with aiohttp.ClientSession() as session:
        client = Rivian(
            session=session,
            access_token=env["RIVIAN_ACCESS_TOKEN"],
            refresh_token=env["RIVIAN_REFRESH_TOKEN"],
            user_session_token=env["RIVIAN_USER_SESSION_TOKEN"],
        )
        payload = await (await client.get_user_information(True)).json()
        vehicle_id = payload["data"]["currentUser"]["vehicles"][0]["id"]

        print(f"subscribing to {len(topics)} RVM(s) for {seconds}s\n")
        unsubscribe = await client.subscribe_for_parallax_messages(
            vehicle_id, on_message, rvms=list(topics)
        )
        if unsubscribe is None:
            print("subscription refused -- nothing captured", file=sys.stderr)
            return 2

        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            await asyncio.sleep(1)
        await unsubscribe()

    withheld: list[str] = []
    print("\n=== result ===")
    for topic in topics:
        raw = seen.get(topic)
        if raw is None:
            print(f"  {topic:44s} SILENT (not published)")
        elif not raw:
            print(f"  {topic:44s} EMPTY payload")
        else:
            print(f"  {topic:44s} {len(raw)}B")
            if write:
                if found := carries_identifiers(raw):
                    withheld.append(topic)
                    print(f"  {'':44s} WITHHELD -- carries {found[:2]}")
                    continue
                FIXTURES.mkdir(parents=True, exist_ok=True)
                out = FIXTURES / f"{topic.replace('.', '_')}.bin"
                out.write_bytes(raw)
                print(f"  {'':44s} -> {out.relative_to(Path.cwd())}")

    captured = sum(1 for t in topics if seen.get(t))
    print(f"\n{captured}/{len(topics)} produced a non-empty frame")
    if withheld:
        print(f"\n{len(withheld)} frame(s) WITHHELD as carrying identifiers:")
        for topic in withheld:
            print(f"  {topic}")
        print("Inspect them by hand if needed; do not commit them.")
    print("SILENT and EMPTY are recorded outcomes, not failures.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("topics", nargs="*", default=list(TARGETS), help="RVM topics")
    parser.add_argument("--seconds", type=int, default=90, help="listen window")
    parser.add_argument("--list", action="store_true", help="print targets and exit")
    parser.add_argument(
        "--all",
        type=Path,
        help="a file of RVM topics, one per line -- use to survey which publish at all",
    )
    parser.add_argument(
        "--write", action="store_true", help="write .bin fixtures for what arrives"
    )
    args = parser.parse_args()
    if args.all:
        topics = tuple(t.strip() for t in args.all.read_text().split() if t.strip())
    else:
        topics = tuple(args.topics) or TARGETS
    if args.list:
        for t in TARGETS:
            print(t)
        raise SystemExit(0)
    raise SystemExit(asyncio.run(capture(topics, args.seconds, args.write)))
