#!/usr/bin/env python3
"""Re-verify WS_CONTENTION.md's concurrency claims against the live gateway.

Owner ruling 23. The document's evidence base is the same class of observation
that a parsing defect in f8_probe.py corrupted -- a subscription that *looked*
silent was never silent, it was unparsed -- and that single defect produced two
"inconclusive" f8 runs and two production outages taken to escape a contention
that does not exist.

Arms 3d and 3e were DROPPED by ruling 28: they provoke close codes 4401/4403,
and ws_monitor.py sets `_disconnect = True` on either, permanently and silently
stopping production's real-time path with no self-heal. They are absent here by
name so a dropped arm cannot be one typo from being run.

Nothing in this file disables, reloads, restarts or stops anything. Recovery
from a tripped liveness control is a human action, deliberately not automated:
a probe that can reload the config entry can also mask the failure it exists to
detect.

    .venv/bin/python scripts/ws_contention_probe.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp

from custom_components.rivian.const import VEHICLE_STATE_API_FIELDS
from custom_components.rivian.rivian_client import Rivian

HA = "root@192.168.1.5"
SSH = [
    "ssh",
    "-o",
    "BatchMode=yes",
    "-o",
    "IdentitiesOnly=yes",
    "-o",
    "IdentityAgent=none",
    "-i",
    str(Path.home() / ".ssh/id_ed25519"),
    "-o",
    "ConnectTimeout=10",
    HA,
]
# The exact text at ws_monitor.py -- a permanent stop, no reconnect.
REJECT_TEXT = "Web socket rejected by the server"
# sensor.r1t_altitude, NOT battery state of charge: 8968 rows/24h against 47,
# mean gap 9.5 s against 1838 s, both measured. The low-cadence entity could be
# satisfied while the real-time path was already dead.
LIVENESS_ENTITY = "sensor.r1t_altitude"


def _ssh(cmd: str) -> str:
    return subprocess.run(
        SSH + [cmd], capture_output=True, text=True, timeout=90, check=False
    ).stdout.strip()


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def newest_row_age() -> float | None:
    """Age in seconds of the newest liveness row. None if unreadable."""
    out = _ssh(
        "sqlite3 'file:/config/home-assistant_v2.db?mode=ro' \""
        "SELECT CAST(strftime('%s','now') - MAX(s.last_updated_ts) AS INT) "
        "FROM states s JOIN states_meta sm ON s.metadata_id=sm.metadata_id "
        f"WHERE sm.entity_id='{LIVENESS_ENTITY}';\""
    )
    try:
        return float(out)
    except ValueError:
        return None


def newest_row_ts() -> float | None:
    out = _ssh(
        "sqlite3 'file:/config/home-assistant_v2.db?mode=ro' \""
        "SELECT MAX(s.last_updated_ts) FROM states s "
        "JOIN states_meta sm ON s.metadata_id=sm.metadata_id "
        f"WHERE sm.entity_id='{LIVENESS_ENTITY}';\""
    )
    try:
        return float(out)
    except ValueError:
        return None


def rejection_count() -> int:
    out = _ssh(
        "ha core logs -n 4000 2>/dev/null | sed -E 's/\\x1b\\[[0-9;]*m//g' | "
        f"grep -cF '{REJECT_TEXT}'"
    )
    try:
        return int(out)
    except ValueError:
        return 0


def liveness(
    a0: float, w: float, t_close: float, baseline_rejects: int
) -> tuple[str, dict]:
    """One of three verdicts, after every arm, before the next begins.

    LIVENESS FAILED is not the same as LIVENESS INDETERMINATE: the first is a
    rejection line, which means the monitor stopped; the second is silence,
    which cannot distinguish a stopped monitor from a vehicle gone quiet. The
    step records that rather than guessing.
    """
    deadline = time.time() + w
    first_row = None
    while time.time() < deadline:
        if rejection_count() > baseline_rejects:
            return "LIVENESS FAILED", {"reason": REJECT_TEXT, "a0": a0, "w": w}
        ts = newest_row_ts()
        if ts and ts > t_close:
            first_row = ts
            break
        time.sleep(10)
    rejects = rejection_count()
    if rejects > baseline_rejects:
        return "LIVENESS FAILED", {"rejects": rejects, "a0": a0, "w": w}
    if first_row is None:
        return "LIVENESS INDETERMINATE", {
            "a0": a0,
            "w": w,
            "t_close": t_close,
            "row": None,
        }
    return "LIVENESS OK", {"a0": a0, "w": w, "t_close": t_close, "row": first_row}


def load_env() -> dict:
    env = {}
    for line in (Path(__file__).resolve().parents[1] / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v.strip().strip('"').strip("'")
    return env


async def arm_3a(client, vid) -> dict:
    """C1c: a second vehicleState subscription, production up throughout.

    CONTROL: batteryLevel and vehicleMileage non-null and >=100 fields. An empty
    control means instrument not proved and 3b/3c do not run.
    """
    got, ev = {}, asyncio.Event()

    def cb(data):
        # Unwrap payload BEFORE data, mirroring coordinator.py's own idiom.
        # This is the defect that must not recur: reading data["data"] is one
        # level too shallow, so nothing is ever parsed and every field reports
        # NOT DELIVERED no matter what actually arrives.
        payload = data.get("payload") or data
        vs = (payload.get("data") or {}).get("vehicleState") or {}
        for k, v in vs.items():
            if k != "__typename":
                got[k] = v
        if got:
            ev.set()

    opened = _utc()
    unsub = await client.subscribe_for_vehicle_updates(
        vid, cb, properties=set(VEHICLE_STATE_API_FIELDS)
    )
    try:
        await asyncio.wait_for(ev.wait(), timeout=30)
    except asyncio.TimeoutError:
        pass
    t_close = time.time()
    closed = _utc()
    try:
        await unsub()
    except Exception as e:  # noqa: BLE001 -- teardown must not mask the measurement
        print(f"    (unsubscribe: {type(e).__name__})")

    def val(k):
        v = got.get(k)
        return v.get("value") if isinstance(v, dict) else v

    delivered = len(got)
    control_ok = (
        delivered >= 100
        and val("batteryLevel") is not None
        and val("vehicleMileage") is not None
    )
    return {
        "arm": "3a",
        "opened": opened,
        "closed": closed,
        "t_close": t_close,
        "delivered": delivered,
        "batteryLevel": val("batteryLevel"),
        "vehicleMileage": val("vehicleMileage"),
        "control_ok": control_ok,
        "verdict": (
            "CONCURRENT SUBSCRIPTION ACCEPTED"
            if control_ok
            else "instrument not proved"
        ),
    }


async def arm_3b(client, vid) -> dict:
    """C8: a Parallax subscription concurrent with production's. Two verdicts only."""
    topics, ev = {}, asyncio.Event()

    def cb(data):
        payload = data.get("payload") or data
        d = (payload.get("data") or {}).get("parallaxMessages") or {}
        rvm = d.get("rvm")
        if rvm:
            topics[rvm] = topics.get(rvm, 0) + 1
            ev.set()

    opened = _utc()
    try:
        unsub = await client.subscribe_for_parallax_messages(vid, cb)
    except Exception as e:  # noqa: BLE001 -- a refusal is a result, not a crash
        return {
            "arm": "3b",
            "opened": opened,
            "closed": _utc(),
            "t_close": time.time(),
            "verdict": "PARALLAX REFUSED — sole subscriber required",
            "detail": f"{type(e).__name__}: {str(e)[:160]}",
        }
    try:
        await asyncio.wait_for(ev.wait(), timeout=45)
    except asyncio.TimeoutError:
        pass
    t_close = time.time()
    closed = _utc()
    try:
        await unsub()
    except Exception as e:  # noqa: BLE001
        print(f"    (unsubscribe: {type(e).__name__})")
    if topics:
        return {
            "arm": "3b",
            "opened": opened,
            "closed": closed,
            "t_close": t_close,
            "verdict": "PARALLAX CONCURRENT — sole subscriber NOT required",
            "topics": sorted(topics),
        }
    return {
        "arm": "3b",
        "opened": opened,
        "closed": closed,
        "t_close": t_close,
        "verdict": "PARALLAX REFUSED — sole subscriber required",
        "detail": "established but no RVM frame in 45 s",
    }


async def arm_3c(client) -> dict:
    """C1c-vs-client: was the hand-rolled init acked in the SAME session 3a/3b used?"""
    opened = _utc()
    t0 = time.time()
    try:
        await client._ws_connect()
        await asyncio.wait_for(client._ws_monitor.connection_ack.wait(), timeout=30)
        acked, detail = True, "connection_ack on the same session"
    except Exception as e:  # noqa: BLE001 -- a refusal is a result
        acked, detail = False, f"{type(e).__name__}: {str(e)[:160]}"
    return {
        "arm": "3c",
        "opened": opened,
        "closed": _utc(),
        "t_close": time.time(),
        "acked": acked,
        "elapsed_s": round(time.time() - t0, 2),
        "detail": detail,
        "verdict": ("INIT ACKED IN SESSION" if acked else "INIT REFUSED"),
    }


def dry_run() -> int:
    print("=== DRY RUN — nothing connects ===\n")
    print(
        f"arm 3a  vehicleState subscription, {len(VEHICLE_STATE_API_FIELDS)} properties"
    )
    print(
        "        CONTROL: batteryLevel + vehicleMileage non-null, >=100 fields delivered"
    )
    print("        frame unwrap: payload -> data -> vehicleState\n")
    print("arm 3b  parallaxMessages subscription, client default RVM set")
    print("        CONTROL: at least one RVM frame in 45 s")
    print("        verdicts: PARALLAX CONCURRENT — sole subscriber NOT required")
    print("                | PARALLAX REFUSED — sole subscriber required\n")
    print("arm 3c  hand-rolled connection_init on the same session as 3a/3b")
    print("        CONTROL: 3a and 3b must both have passed control and liveness\n")
    print(f"liveness  entity {LIVENESS_ENTITY}; W = min(max(4 * A0, 600), 900)")
    print(f"          reject text: {REJECT_TEXT!r}")
    print("          verdicts: LIVENESS OK | LIVENESS FAILED | LIVENESS INDETERMINATE")
    print("\narms 3d and 3e: DROPPED by ruling 28; absent from this file by name.")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.dry_run:
        return dry_run()

    a0 = newest_row_age()
    if a0 is None or a0 > 300:
        print(
            f"A0 = {a0}; entry gate is A0 <= 300 s. The vehicle is in a quiet window,"
        )
        print(
            "the liveness control is blind, and no arm starts. Recorded and deferred."
        )
        return 2
    w = min(max(4 * a0, 600), 900)
    baseline = rejection_count()
    print(
        f"A0 = {a0:.0f} s   W = {w:.0f} s   rejection baseline = {baseline}   ({_utc()})\n"
    )

    env = load_env()
    results = []
    async with aiohttp.ClientSession() as session:
        client = Rivian(
            session=session,
            access_token=env["RIVIAN_ACCESS_TOKEN"],
            refresh_token=env["RIVIAN_REFRESH_TOKEN"],
            user_session_token=env["RIVIAN_USER_SESSION_TOKEN"],
        )
        payload = await (await client.get_user_information(True)).json()
        vid = payload["data"]["currentUser"]["vehicles"][0]["id"]

        for fn in (arm_3a, arm_3b):
            r = await fn(client, vid)
            results.append(r)
            print(json.dumps(r, indent=2, default=str))
            verdict, detail = liveness(a0, w, r["t_close"], baseline)
            r["liveness"] = verdict
            print(f"  -> {verdict}  {detail}\n")
            if verdict != "LIVENESS OK":
                print(
                    "Stopping. Recovery is a config-entry RELOAD, performed by a human,"
                )
                print(
                    "evidenced by a fresh row and a re-established A0 <= 300 -- never by"
                )
                print(
                    "the reload call returning. Remaining arms do not run on this pass."
                )
                return 1
            if not r.get("control_ok", True):
                print("instrument not proved -- 3b and 3c do not run.")
                return 1

        r = await arm_3c(client)
        results.append(r)
        print(json.dumps(r, indent=2, default=str))
        verdict, detail = liveness(a0, w, r["t_close"], baseline)
        r["liveness"] = verdict
        print(f"  -> {verdict}  {detail}\n")

    print("=== C6 and C7: UNVERIFIED — arms dropped by ruling 28 ===")
    print("Their arms provoke close codes that permanently stop production's monitor,")
    print(
        "and the no-harm criteria could not detect it. Recorded, not carried forward."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
