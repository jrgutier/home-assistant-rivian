#!/usr/bin/env python3
"""Send one vehicle command outside Home Assistant, and poll its result.

Why this exists: a command sent through the integration reports TIMEOUT whenever
`vehicleCommandState` does not answer within 30 s, and TIMEOUT is not a refusal --
it says nothing about whether the vehicle accepted the command. This sends the
same command over the same client with the same HMAC material, then POLLS
`get_vehicle_command_state` instead of relying on the subscription, which
separates "the vehicle refused" from "the result never came back".

It moves the vehicle. Occupancy is the caller's responsibility.

Secrets: reads the tokens and the signing private key from .env, prints neither.

Usage:
    python scripts/probe_vehicle_command.py OPEN_TONNEAU_COVER [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp

from custom_components.rivian.rivian_client import Rivian, VehicleCommand

REQUIRED = (
    "RIVIAN_ACCESS_TOKEN",
    "RIVIAN_REFRESH_TOKEN",
    "RIVIAN_USER_SESSION_TOKEN",
    "RIVIAN_PUBLIC_KEY",
    "RIVIAN_PRIVATE_KEY",
)


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip("'\"")
    env |= {k: os.environ[k] for k in REQUIRED if k in os.environ}
    if missing := [k for k in REQUIRED if not env.get(k)]:
        raise SystemExit(f"missing from {path}: {', '.join(missing)}")  # names only
    return env


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--env", default=".env", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--poll", type=int, default=12, help="result polls")
    args = parser.parse_args()

    env = load_env(args.env)
    command = VehicleCommand(args.command)

    async with aiohttp.ClientSession() as session:
        client = Rivian(
            session=session,
            access_token=env["RIVIAN_ACCESS_TOKEN"],
            refresh_token=env["RIVIAN_REFRESH_TOKEN"],
            user_session_token=env["RIVIAN_USER_SESSION_TOKEN"],
        )
        payload = await (await client.get_user_information(True)).json()
        user = payload["data"]["currentUser"]
        vehicle = user["vehicles"][0]

        phone = next(
            (
                p
                for p in user["enrolledPhones"]
                if p["vas"]["publicKey"] == env["RIVIAN_PUBLIC_KEY"]
            ),
            None,
        )
        if phone is None:
            raise SystemExit(
                "the public key in .env is not enrolled on this account -- "
                f"{len(user['enrolledPhones'])} phone(s) enrolled"
            )
        identity = next(
            e["identityId"]
            for e in phone["enrolled"]
            if e["vehicleId"] == vehicle["id"]
        )

        print(f"vehicle   : {vehicle['vehicle']['model']} …{vehicle['vin'][-6:]}")
        print(f"command   : {command.value}")
        if args.dry_run:
            print("dry run — nothing sent")
            return 0

        command_id = await client.send_vehicle_command(
            command=command,
            vehicle_id=vehicle["id"],
            phone_id=phone["vas"]["vasPhoneId"],
            identity_id=identity,
            vehicle_key=vehicle["vas"]["vehiclePublicKey"],
            private_key=env["RIVIAN_PRIVATE_KEY"],
        )
        print(f"command_id: {command_id}")
        if not command_id:
            print("REJECTED at send — no command id returned")
            return 1

        for attempt in range(args.poll):
            await asyncio.sleep(5)
            state = await (await client.get_vehicle_command_state(command_id)).json()
            data = (state.get("data") or {}).get("getVehicleCommand")
            print(f"  t+{(attempt + 1) * 5:>3}s  {data}")
            if data and data.get("state") not in (None, "in_progress", "pending"):
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
