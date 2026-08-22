"""f8 -- field residue probe over the GraphQL subscriptions, BISECTED.

Bisection is not optional: the server rejects the ENTIRE document if one field name
is unknown, so a single probe carrying all the new names cannot tell "these are
silent" from "one bad name killed the document" (the wheelsInstalled failure).

THREE documents, not one. After the app-parity change the integration sends two
subscriptions and carries a third as a fallback, and `VEHICLE_STATE_API_FIELDS` is
now the 149-name UNION of the two live ones -- a set that is never sent as a
document. Probing the union would test a document that does not exist, reporting
either a rejection production would never hit or an acceptance that proves nothing:

    main   VEHICLE_STATE_SUBSCRIPTION_FIELDS   137   operationName VehicleState
    tpms   TIRE_PRESSURE_SUBSCRIPTION_FIELDS    12   operationName tirePressureState
    core   CORE_VEHICLE_STATE_FIELDS            15   the S1 degraded fallback

The core document is the one that gets skipped, and it is the one with no live
evidence at all. It exists so a Rivian-side field rename degrades the integration
instead of zeroing it -- an unprobed fallback might itself be rejected at the exact
moment it is needed.

`NOT DELIVERED` is SILENCE, NOT FAILURE. A field the gateway accepts but does not
fill is a recorded finding, never grounds for deleting a sensor. See
docs/development/UNPOPULATED_FIELDS.md.

Requires the repo venv. Bare python3 already dies on `import aiohttp`; this probe
also imports from `custom_components.rivian.const`, which imports homeassistant.
The system interpreter has neither.

    .venv/bin/python scripts/f8_probe.py [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import aiohttp

from custom_components.rivian.const import (
    TIRE_PRESSURE_SUBSCRIPTION_FIELDS,
    VEHICLE_STATE_SUBSCRIPTION_FIELDS,
)
from custom_components.rivian.rivian_client import Rivian
from custom_components.rivian.rivian_client.const import CORE_VEHICLE_STATE_FIELDS

# The 25 names app parity added to the main document. Per-field delivery is reported
# for these. Written out rather than derived, because the delta is against the OLD
# 124-name derived set, which no longer exists to subtract from -- there is nothing
# left in the tree to compute it from. `_assert_targets_are_requested` below is what
# stops the list drifting from the document it is meant to measure.
TARGETS = [
    "batteryCellType",
    "batteryNeedsLfpCalibration",
    "btmOcHardwareFailureStatus",
    "cellularAntennaBars",
    "cellularCarrier",
    "cellularMode",
    "cellularSignalStrength",
    "chargingDisabledACFaultState",
    "chargingDisabledAll",
    "chargingTimeEstimationValidity",
    "chargingTripTargetMinsRemaining",
    "chargingTripTargetSoc",
    "coldRangeNotification",
    "geoLocation",
    "gnssError",
    "otaDeploymentIntent",
    "otaSoftwareCategory",
    "rearHitchStatus",
    "wifiAntennaBars",
    "wifiFreq",
    "wifiLinkSpeed",
    "wifiSecureStatus",
    "wifiSsid",
    "wifiStaDisabledReason",
    "wifiWpaStatus",
]
CONTROL = ["batteryLevel", "vehicleMileage"]  # known-good, proves the doc works at all


def _assert_targets_are_requested() -> None:
    """Every target must actually be in the main document, or the probe lies.

    A name in TARGETS but not in the document would be reported NOT DELIVERED
    forever, and read as a server-side silence rather than as our own omission.
    """
    stray = sorted(set(TARGETS) - set(VEHICLE_STATE_SUBSCRIPTION_FIELDS))
    if stray:
        raise SystemExit(
            f"TARGETS drifted: {stray} are not in VEHICLE_STATE_SUBSCRIPTION_FIELDS. "
            "Fix the list, do not fix the assertion."
        )


def load_env():
    env = {}
    env_path = REPO / ".env"
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v.strip().strip('"').strip("'")
    return env


def _report_field(name: str, raw) -> None:
    """Print one field's delivery, descending into structured fields.

    A structured field is a dict with NO `value` key -- gnssError is
    {timeStamp, positionVertical, positionHorizontal, speed, bearing} and
    gnssLocation is {latitude, longitude, timeStamp, isAuthorized}. The naive
    `raw.get("value")` returns None for both, so the probe printed

        gnssError = None

    which reads as "the gateway delivered it, empty" when the truth may be "all
    four leaves arrived with real values". That is a confident WRONG answer about
    the one field whose four sensors this story just shipped -- worse than no
    reporting at all, because nobody double-checks a definite-looking result.

    Detected by SHAPE, not by name: any future structured field reports correctly
    with no edit here. `TEMPLATE_MAP` (rivian_client/rivian.py) is the authority on
    which fields carry non-default selections, but keying off the delivered shape
    means the two cannot drift apart.
    """
    if isinstance(raw, dict) and "value" not in raw:
        leaves = {k: v for k, v in raw.items() if k != "__typename"}
        live = [k for k, v in leaves.items() if v is not None]
        print(f"      {name} -- structured, {len(live)}/{len(leaves)} leaves populated")
        for leaf, val in sorted(leaves.items()):
            if val is None:
                print(f"        .{leaf} -- NOT DELIVERED (silence, not failure)")
            else:
                print(f"        .{leaf} = {val}")
        return
    # A field the gateway NAMED but wrapped as {"value": None, "timeStamp":
    # ...} must read the same as one it never mentioned at all -- otherwise
    # "= None" looks like a real delivered value instead of silence, exactly
    # the misreading this wording exists to prevent.
    value = raw.get("value") if isinstance(raw, dict) else raw
    if value is None:
        print(f"      {name} -- NOT DELIVERED (silence, not failure)")
    else:
        print(f"      {name} = {value}")


def _collect(got: dict, ev: asyncio.Event):
    """Build the subscription callback that harvests delivered fields."""

    def cb(data):
        # The frame is {"id":..., "type":"next", "payload": {"data": {...}}}.
        # coordinator.py unwraps `payload` then `data`. Two earlier revisions of
        # this probe read data["data"] directly, one level too shallow, so `got`
        # stayed empty no matter what arrived and the run reported every field NOT
        # DELIVERED. That is what made f8 "inconclusive" twice -- not contention,
        # and not the property set. Accept both shapes so it cannot recur.
        payload = data.get("payload") or data
        vs = (payload.get("data") or {}).get("vehicleState") or {}
        for k, v in (vs or {}).items():
            if k != "__typename":
                got[k] = v
        if got:
            ev.set()

    return cb


async def attempt(client, vid, props, label, wait=25, tpms=False):
    """Return (accepted, got_ack, fields_delivered).

    `tpms=True` sends the second document via subscribe_for_tire_pressure_updates.
    The main path passes allow_core_fallback=False so a rejected main document
    reports as REJECTED instead of silently succeeding through the core retry --
    which would have the probe certify a document the gateway actually refused.
    """
    got: dict = {}
    ev = asyncio.Event()
    cb = _collect(got, ev)

    t0 = time.monotonic()
    try:
        if tpms:
            unsub = await client.subscribe_for_tire_pressure_updates(
                vid, cb, properties=set(props)
            )
        else:
            unsub = await client.subscribe_for_vehicle_updates(
                vid, cb, properties=set(props), allow_core_fallback=False
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
        if k in got:
            _report_field(k, got[k])
        else:
            print(f"      {k} -- NOT DELIVERED (silence, not failure)")
    try:
        await unsub()
    except Exception as e:  # noqa: BLE001 -- teardown of a probe; a failure here must not mask the measurement above
        print(f"  [{label}] (unsubscribe failed: {type(e).__name__})")
    return (True, True, delivered)


async def bisect(client, vid, names, label):
    """Halve until the offending name is isolated, then name it.

    Linear solo probes would also find it, but each one costs a full subscribe and
    a wait; halving turns 25 round trips into ~5.
    """
    if len(names) == 1:
        ok, _, _ = await attempt(
            client, vid, CONTROL + names, f"{label}:{names[0]}", 20
        )
        if not ok:
            print(f"\n  *** FATAL NAME ISOLATED: {names[0]} ***")
        return
    mid = len(names) // 2
    for half in (names[:mid], names[mid:]):
        ok, _, _ = await attempt(
            client, vid, CONTROL + half, f"{label}[{len(half)}]", 20
        )
        if not ok:
            await bisect(client, vid, half, label)


def _dry_run() -> int:
    """Print all three documents without connecting.

    The live window must not be spent discovering a typo.
    """
    _assert_targets_are_requested()
    for name, fields in (
        ("main  (VehicleState)", VEHICLE_STATE_SUBSCRIPTION_FIELDS),
        ("tpms  (tirePressureState)", TIRE_PRESSURE_SUBSCRIPTION_FIELDS),
        ("core  (S1 fallback)", CORE_VEHICLE_STATE_FIELDS),
    ):
        print(f"\n=== {name}: {len(fields)} fields ===")
        for f in sorted(fields):
            print(f"  {f}")
    print(f"\nBISECT targets ({len(TARGETS)} new names): {TARGETS}")
    print(f"CONTROL (known-good pair kept for BISECT): {CONTROL}")
    return 0


async def main():
    _assert_targets_are_requested()
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

        print("=== 1/4 CONTROL: known-good fields only ===")
        ok, _, ctl = await attempt(c, vid, CONTROL, "control")
        if not ok or not ctl:
            print("CONTROL FAILED -- the probe is not a valid instrument now. STOP.")
            return 2

        print(f"\n=== 2/4 MAIN document ({len(VEHICLE_STATE_SUBSCRIPTION_FIELDS)}) ===")
        ok, _, main_d = await attempt(
            c, vid, sorted(VEHICLE_STATE_SUBSCRIPTION_FIELDS), "main"
        )
        if not ok:
            print("\n  main document REJECTED -> bisecting the 25 new names")
            await bisect(c, vid, TARGETS, "main")
            return 3
        missing = [t for t in TARGETS if t not in main_d]
        print(
            f"\n  main accepted; {len(TARGETS) - len(missing)}/{len(TARGETS)} new "
            f"names delivered, {len(missing)} silent"
        )

        print(f"\n=== 3/4 TPMS document ({len(TIRE_PRESSURE_SUBSCRIPTION_FIELDS)}) ===")
        ok, _, tp = await attempt(
            c, vid, sorted(TIRE_PRESSURE_SUBSCRIPTION_FIELDS), "tpms", tpms=True
        )
        if not ok:
            print("  TPMS document REJECTED -> bisecting")
            await bisect(c, vid, sorted(TIRE_PRESSURE_SUBSCRIPTION_FIELDS), "tpms")
            return 4
        pressures = [
            k for k in tp if k.startswith("tirePressure") and "Status" not in k
        ]
        print(f"  tpms accepted; {len(pressures)}/4 pressures delivered")

        print(f"\n=== 4/4 CORE fallback ({len(CORE_VEHICLE_STATE_FIELDS)}) ===")
        ok, _, _ = await attempt(c, vid, sorted(CORE_VEHICLE_STATE_FIELDS), "core")
        if not ok:
            print("  CORE REJECTED -- the S1 fallback is itself broken. BLOCKING.")
            return 5

        print("\n=== ALL THREE DOCUMENTS ACCEPTED ===")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print all three subscription documents without connecting",
    )
    args = parser.parse_args()
    if args.dry_run:
        raise SystemExit(_dry_run())
    raise SystemExit(asyncio.run(main()))
