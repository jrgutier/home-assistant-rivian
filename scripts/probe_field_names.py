#!/usr/bin/env python3
"""Ask the gateway whether it knows a `vehicleState` field name. One at a time.

READ-ONLY. This opens subscriptions and reads what comes back. It sends no
vehicle command and actuates nothing.

Why one at a time, and why a scratch document: the server rejects the ENTIRE
document if a single field name is unknown, so a probe carrying several
candidates cannot tell "all fine" from "one bad name killed it" -- the failure
`scripts/f8_probe.py` exists to bisect around. Here each candidate rides alone
with two known-good control fields, so a rejection names its own culprit and no
bisection is needed.

The candidates must NOT be added to `VEHICLE_STATE_API_FIELDS` first. Doing that
puts an unproven name into the document the integration actually sends, where a
rejection takes out every sensor at once rather than one probe.

Three outcomes, and they are not the same thing:

    ACCEPTED + delivered   the gateway knows the name and has a value for it
    ACCEPTED + silent      the gateway knows the name and sent nothing. That is
                           SILENCE, NOT FAILURE -- see UNPOPULATED_FIELDS.md. It
                           is a recorded finding, never grounds for deleting a
                           sensor
    REJECTED               the gateway does not know the name in this document

A decompile never promotes a row; only a live accept does. That rule is why this
script exists at all -- `docs/development/APK_HISTORICAL_SWEEP.md` found these
names in the app, which is a reason to probe them and not a reason to ship them.

Secrets: reads tokens from `.env` and prints none of them.

Requires the repo venv (`aiohttp`, and the client imports homeassistant).

Usage:
    .venv/bin/python scripts/probe_field_names.py --dry-run
    .venv/bin/python scripts/probe_field_names.py passiveEntryUnlockFailReason
    .venv/bin/python scripts/probe_field_names.py            # all defaults
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp
from f8_probe import CONTROL, attempt, load_env

from custom_components.rivian.rivian_client import Rivian

# Found in 3.15.0's compiled documents and absent from ours -- see
# docs/development/APK_HISTORICAL_SWEEP.md. Being in the CURRENT build is what
# makes these worth the gateway's time; the historical-only names are not here.
DEFAULT_CANDIDATES = (
    "passiveEntryUnlockFailReason",
    "vasAccessCanFaulted",
    "vasSecureElementFaulted",
)


def _dry_run(candidates: tuple[str, ...]) -> int:
    """Print what would be sent, without connecting."""
    print(f"control fields: {CONTROL}")
    for candidate in candidates:
        print(f"  scratch document for {candidate}: {[*CONTROL, candidate]}")
    print("\nno network calls made")
    return 0


async def run(candidates: tuple[str, ...]) -> int:
    env = load_env()
    async with aiohttp.ClientSession() as session:
        client = Rivian(
            session=session,
            access_token=env["RIVIAN_ACCESS_TOKEN"],
            refresh_token=env["RIVIAN_REFRESH_TOKEN"],
            user_session_token=env["RIVIAN_USER_SESSION_TOKEN"],
        )
        payload = await (await client.get_user_information(True)).json()
        vehicle_id = payload["data"]["currentUser"]["vehicles"][0]["id"]

        # The control proves the instrument before any candidate is judged by it.
        # Without this, a broken session reads as "every name rejected".
        print(f"=== CONTROL {CONTROL} ===")
        accepted, _, delivered = await attempt(client, vehicle_id, CONTROL, "control")
        if not accepted or not delivered:
            print("CONTROL FAILED -- the probe is not a valid instrument now. STOP.")
            return 2
        print("control accepted\n")

        results: dict[str, str] = {}
        for candidate in candidates:
            print(f"=== {candidate} ===")
            accepted, _, got = await attempt(
                client, vehicle_id, [*CONTROL, candidate], candidate
            )
            if not accepted:
                results[candidate] = "REJECTED"
            elif candidate in got:
                results[candidate] = "ACCEPTED, delivered"
            else:
                results[candidate] = "ACCEPTED, silent"
            print(f"  -> {results[candidate]}\n")

        print("=== summary ===")
        for candidate, verdict in results.items():
            print(f"  {candidate:34s} {verdict}")
        print(
            "\nACCEPTED+silent is silence, not failure. Record every result in "
            "docs/development/COMMAND_COVERAGE.md before acting on it."
        )
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "candidates",
        nargs="*",
        default=list(DEFAULT_CANDIDATES),
        help="field names to probe (default: the three from the corpus sweep)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the scratch documents without connecting",
    )
    args = parser.parse_args()
    names = tuple(args.candidates) or DEFAULT_CANDIDATES
    if args.dry_run:
        raise SystemExit(_dry_run(names))
    raise SystemExit(asyncio.run(run(names)))
