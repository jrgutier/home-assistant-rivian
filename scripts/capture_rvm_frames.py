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

`--write` is ADDITIVE. It skips any topic already in `manifest.json`, refuses to
overwrite an existing `.bin`, and appends new entries to the manifest. Until
2026-09-01 it did none of that: it wrote `topic.replace(".", "_") + ".bin"`
unconditionally, so the documented "re-run while driving" would have replaced
every frame the decoder tests assert against. The three legacy-named fixtures
still carry an `alias` from a duplicate an earlier run wrote, and one of those
pairs holds different bytes.

Secrets: reads tokens from `.env` and prints none of them.

Usage:
    .venv/bin/python scripts/capture_rvm_frames.py --list
    .venv/bin/python scripts/capture_rvm_frames.py --seconds 90
    .venv/bin/python scripts/capture_rvm_frames.py \\
        --all scripts/rvm_topics_active_rerun.txt --seconds 180 --write
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
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
MANIFEST = FIXTURES / "manifest.json"

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


def load_manifest() -> dict[str, dict]:
    """`manifest.json`, or an empty mapping before the first fixture exists."""
    return json.loads(MANIFEST.read_text()) if MANIFEST.is_file() else {}


def fixture_name(topic: str) -> str:
    """The filename a NEW topic gets.

    `topic.replace(".", "_")` is the transform that produced four wrong counts,
    and it is fine HERE and nowhere else: this is the forward direction, applied
    once, and the result is recorded in the manifest so nothing ever has to
    invert it. The rule that matters is that a topic is never *derived back* out
    of a filename -- three fixtures predate this convention and would mis-map.
    Existing topics are looked up in the manifest, never passed through here.
    """
    return topic.replace(".", "_") + ".bin"


def manifest_entry(raw: bytes, filename: str) -> dict:
    """Match `manifest.json`'s existing shape exactly.

    `sha256_12` holds sixteen hex characters, not twelve. The name is a
    misnomer in the committed data; matching it is more useful than correcting
    it, because `tests/test_parallax_fixture_manifest.py` and three gates read
    these entries.
    """
    return {
        "bytes": len(raw),
        "file": filename,
        "sha256_12": hashlib.sha256(raw).hexdigest()[:16],
    }


def write_decision(
    topic: str, raw: bytes, manifest: dict[str, dict], fixtures: Path
) -> tuple[str, str]:
    """What `--write` should do with one frame, as a decision separated from IO.

    Split out so it can be tested without a vehicle. The alternative -- asserting
    the loop's behaviour by running a live capture -- is the reason this was
    broken for as long as it was: nobody re-ran it, so nobody saw that a second
    run overwrites.

    Returns `(action, detail)` where action is one of `already-fixtured`,
    `withheld`, `refused`, `write`.
    """
    if topic in manifest:
        return "already-fixtured", manifest[topic]["file"]
    if found := carries_identifiers(raw):
        return "withheld", ", ".join(found[:2])
    name = fixture_name(topic)
    if (fixtures / name).exists():
        return "refused", name
    return "write", name


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
    added: list[str] = []
    # Loaded ONCE, before the loop, so a topic added during this run cannot be
    # mistaken for one that was already committed.
    manifest = load_manifest()

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
                # A re-run must be additive. Overwriting would silently replace
                # the frame every committed test asserts against, and for the
                # three legacy-named fixtures it would not even overwrite -- it
                # would write a SECOND file under the derived name and leave an
                # orphan that `test_every_fixture_file_is_accounted_for` fails
                # on. Both were live until 2026-09-01.
                action, detail = write_decision(topic, raw, manifest, FIXTURES)
                if action == "already-fixtured":
                    print(f"  {'':44s} already fixtured ({detail}) -- kept")
                elif action == "withheld":
                    withheld.append(topic)
                    print(f"  {'':44s} WITHHELD -- carries {detail}")
                elif action == "refused":
                    print(f"  {'':44s} REFUSED -- {detail} exists, not in manifest")
                else:
                    FIXTURES.mkdir(parents=True, exist_ok=True)
                    out = FIXTURES / detail
                    out.write_bytes(raw)
                    manifest[topic] = manifest_entry(raw, detail)
                    added.append(topic)
                    print(f"  {'':44s} -> {out}")

    if added:
        # `indent=1` and a trailing newline are what the committed file already
        # uses -- measured, not assumed. Anything else reformats all 40 entries
        # and buries the one real addition in a 400-line diff.
        MANIFEST.write_text(json.dumps(dict(sorted(manifest.items())), indent=1) + "\n")

    captured = sum(1 for t in topics if seen.get(t))
    print(f"\n{captured}/{len(topics)} produced a non-empty frame")
    if withheld:
        print(f"\n{len(withheld)} frame(s) WITHHELD as carrying identifiers:")
        for topic in withheld:
            print(f"  {topic}")
        print("Inspect them by hand if needed; do not commit them.")
    if added:
        print(f"\n{len(added)} NEW fixture(s) written, and manifest.json updated:")
        for topic in added:
            print(f"  {topic}")
        print("Review each frame by hand before committing -- the text guard is")
        print("a floor, not a proof. A GPS pair as f64 doubles has no printable")
        print("run and passed every string check once already.")
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
