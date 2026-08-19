"""f8 -- field residue probe over the GraphQL subscription, BISECTED.

Bisection is not optional: the server rejects the ENTIRE subscription if one field
name is unknown, so a single probe carrying all five cannot tell "these five are
silent" from "one bad name killed the document" (the wheelsInstalled failure).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import time

sys.path.insert(0, "/Users/jrgutier/src/ha-rivian/home-assistant-rivian")
import aiohttp

from custom_components.rivian.rivian_client import Rivian

TARGETS = [
    "tirePressureStatusValidFrontLeft",
    "tirePressureStatusValidFrontRight",
    "tirePressureStatusValidRearLeft",
    "tirePressureStatusValidRearRight",
    "cabinHoldNotification",
]
CONTROL = ["batteryLevel", "vehicleMileage"]  # known-good, proves the doc works at all

# The coordinator's ACTUAL property set. The first f8 run approximated it with a
# small explicit list and the control delivered nothing, which is why that run was
# inconclusive: the probe was not the instrument it claimed to be.
# coordinator.py:958 passes properties=VEHICLE_STATE_API_FIELDS -- NOT
# VEHICLE_STATES_SUBSCRIPTION_PROPERTIES, which is only the client default at
# rivian_client/rivian.py and which the coordinator never uses.
# Importing this pulls in homeassistant, so this script now REQUIRES the repo
# venv: .venv/bin/python scripts/f8_probe.py
from custom_components.rivian.const import VEHICLE_STATE_API_FIELDS


def load_env():
    env = {}
    for line in (
        Path("/Users/jrgutier/src/ha-rivian/home-assistant-rivian/.env")
        .read_text()
        .splitlines()
    ):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v.strip().strip('"').strip("'")
    return env


async def attempt(client, vid, props, label, wait=25):
    """Return (accepted, got_ack, fields_delivered)."""
    got = {}
    ev = asyncio.Event()

    def cb(data):
        vs = (data.get("data") or {}).get("vehicleState") or {}
        for k, v in (vs or {}).items():
            if k != "__typename":
                got[k] = v
        if got:
            ev.set()

    t0 = time.monotonic()
    try:
        unsub = await client.subscribe_for_vehicle_updates(
            vid, cb, properties=set(props)
        )
    except Exception as e:  # noqa: BLE001 -- a probe must report ANY failure shape; narrowing here would silently swallow the case it exists to observe
        msg = str(e)[:200].replace("\n", " ")
        print(f"  [{label}] SUBSCRIPTION REJECTED: {type(e).__name__}: {msg}")
        return (False, False, {})
    try:
        await asyncio.wait_for(ev.wait(), timeout=wait)
    except asyncio.TimeoutError:
        pass
    delivered = {
        k: (v.get("value") if isinstance(v, dict) else v) for k, v in got.items()
    }
    print(
        f"  [{label}] accepted; {len(delivered)} field(s) in {time.monotonic() - t0:.1f}s"
    )
    for k in props:
        if k in delivered:
            print(f"      {k} = {delivered[k]}")
        else:
            print(f"      {k} -- NOT DELIVERED")
    try:
        await unsub()
    except Exception as e:  # noqa: BLE001 -- teardown of a probe; a failure here must not mask the measurement above
        print(f"  [{label}] (unsubscribe failed: {type(e).__name__})")
    return (True, True, delivered)


async def main():
    env = load_env()
    async with aiohttp.ClientSession() as session:
        c = Rivian(
            session=session,
            access_token=env["RIVIAN_ACCESS_TOKEN"],
            refresh_token=env["RIVIAN_REFRESH_TOKEN"],
            user_session_token=env["RIVIAN_USER_SESSION_TOKEN"],
        )
        p = await (await c.get_user_information(True)).json()
        vid = p["data"]["currentUser"]["vehicles"][0]["id"]
        print("=== CONTROL: known-good fields only ===")
        # Control over the coordinator's real property set, not an approximation.
        ok, _, ctl = await attempt(c, vid, sorted(VEHICLE_STATE_API_FIELDS), "control")
        if not ok or not ctl:
            print(
                "CONTROL FAILED -- the probe itself is not a valid instrument right now. STOP."
            )
            return 2
        print("\n=== ALL FIVE TARGETS + control ===")
        ok, _, d = await attempt(c, vid, CONTROL + TARGETS, "all-five")
        if not ok:
            print("\n=== whole document rejected -> BISECT ===")
            for t in TARGETS:
                await attempt(c, vid, CONTROL + [t], f"solo:{t}", wait=20)
        else:
            missing = [t for t in TARGETS if t not in d]
            print(
                f"\n  accepted as a document; {len(TARGETS) - len(missing)}/5 delivered"
            )
            if missing:
                print("  bisecting the non-delivering ones individually:")
                for t in missing:
                    await attempt(c, vid, CONTROL + [t], f"solo:{t}", wait=20)
    return 0


sys.exit(asyncio.run(main()))
