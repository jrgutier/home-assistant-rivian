#!/usr/bin/env python3
"""Print the vehicles' live supportedFeatures, and nothing else.

Uses the SAME query the integration already runs (`get_user_information`, whose
`supportedFeatures { name status }` block coordinator.py:777-783 reads), so this
adds no new API surface -- it just shows what the server is actually saying about
this account's vehicles.

Why it matters: `supportedFeatures` is the only source for the capability gates
in cover.py and button.py, and the tonneau result showed it is a LOWER BOUND on
what the vehicle can do, not a description of it. `TONNEAU_CMD` appears here for
nobody, while both tonneau commands physically move the cover. So this output is
evidence of what the server volunteers, never evidence of absence.

Secrets discipline: reads tokens from .env, prints feature names, model and the
last six of the VIN. It never prints a token, and the VIN suffix is there only so
a two-vehicle account is readable.

Usage:
    python scripts/dump_supported_features.py [--env .env] [--json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp

from custom_components.rivian.rivian_client import Rivian

REQUIRED = ("RIVIAN_ACCESS_TOKEN", "RIVIAN_REFRESH_TOKEN", "RIVIAN_USER_SESSION_TOKEN")


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip("'\"")
    for key in REQUIRED:
        if key in os.environ:
            env[key] = os.environ[key]
    missing = [k for k in REQUIRED if not env.get(k)]
    if missing:
        # Names only. Never the values.
        raise SystemExit(f"missing from {path}: {', '.join(missing)}")
    return env


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env", type=Path)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    env = load_env(args.env)
    async with aiohttp.ClientSession() as session:
        client = Rivian(
            session=session,
            access_token=env["RIVIAN_ACCESS_TOKEN"],
            refresh_token=env["RIVIAN_REFRESH_TOKEN"],
            user_session_token=env["RIVIAN_USER_SESSION_TOKEN"],
        )
        response = await client.get_user_information()
        payload = await response.json()

    vehicles = payload["data"]["currentUser"]["vehicles"]
    out = []
    for vehicle in vehicles:
        features = (
            vehicle.get("vehicle", {}).get("vehicleState", {}).get("supportedFeatures")
            or []
        )
        out.append(
            {
                "vin_suffix": vehicle["vin"][-6:],
                "model": vehicle.get("vehicle", {}).get("model"),
                "model_year": vehicle.get("vehicle", {}).get("modelYear"),
                # Every status, not only AVAILABLE. coordinator.py keeps only
                # AVAILABLE, and the difference is exactly what a capability
                # matrix needs to show.
                "features": sorted(
                    (f["name"], f["status"]) for f in features if f.get("name")
                ),
            }
        )

    if args.json:
        print(json.dumps(out, indent=2))
        return 0

    for vehicle in out:
        print(
            f"=== {vehicle['model']} {vehicle['model_year']} (…{vehicle['vin_suffix']}) ==="
        )
        print(f"{len(vehicle['features'])} features")
        for name, status in vehicle["features"]:
            print(f"  {status:12s} {name}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
