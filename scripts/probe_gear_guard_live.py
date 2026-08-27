#!/usr/bin/env python3
"""Measurement gate: start a Gear Guard live session and wait for signaling config.

Sends START_GEAR_GUARD_MASTER_SESSION with params.camera=left (the APK default),
then subscribes to gearGuardLiveConfig(vehicleId, commandId) — the exact 3.15.0
document. Prints a redacted summary only (no endpoint, channelArn, or ICE
credentials).

Pass: a config frame with endpoint, channelArn, role, and iceServers.
Fail: CONFLICT, or no config before timeout.

Usage:
    .venv/bin/python scripts/probe_gear_guard_live.py [--camera left] [--timeout 30]
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp

from custom_components.rivian.rivian_client import Rivian, VehicleCommand
from custom_components.rivian.rivian_client.exceptions import RivianApiException
from scripts.probe_vehicle_command import _is_terminal, load_env


def _redact_config(cfg: dict) -> dict:
    """Shape-only summary. Never include secrets."""
    ice = cfg.get("iceServers") or []
    endpoint = cfg.get("endpoint") or ""
    host = urlparse(endpoint).netloc if endpoint else None
    return {
        "has_endpoint": bool(endpoint),
        "endpoint_host": host,
        "has_channel_arn": bool(cfg.get("channelArn")),
        "role": cfg.get("role"),
        "ice_server_count": len(ice) if isinstance(ice, list) else None,
        "ice_has_credential": bool(
            isinstance(ice, list)
            and any(isinstance(s, dict) and s.get("credential") for s in ice)
        ),
    }


def _conflict_bits(ex: RivianApiException) -> str:
    for arg in ex.args:
        if isinstance(arg, dict) and arg.get("errors"):
            ext = arg["errors"][0].get("extensions") or {}
            return f"{ext.get('code')}/{ext.get('reason')}"
    return type(ex).__name__


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env", type=Path)
    parser.add_argument("--camera", default="left")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--wake", action="store_true", default=True)
    parser.add_argument("--no-wake", dest="wake", action="store_false")
    args = parser.parse_args()

    env = load_env(args.env)
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
            p
            for p in user["enrolledPhones"]
            if p["vas"]["publicKey"] == env["RIVIAN_PUBLIC_KEY"]
        )
        identity = next(
            e["identityId"]
            for e in phone["enrolled"]
            if e["vehicleId"] == vehicle["id"]
        )
        ids = {
            "vehicle_id": vehicle["id"],
            "phone_id": phone["vas"]["vasPhoneId"],
            "identity_id": identity,
            "vehicle_key": vehicle["vas"]["vehiclePublicKey"],
            "private_key": env["RIVIAN_PRIVATE_KEY"],
        }
        print(f"vehicle : {vehicle['vehicle']['model']} …{vehicle['vin'][-6:]}")
        print(f"camera  : {args.camera}")

        async def send(command: VehicleCommand, **kwargs):
            return await client.send_vehicle_command(
                command=command,
                vehicle_id=ids["vehicle_id"],
                phone_id=ids["phone_id"],
                identity_id=ids["identity_id"],
                vehicle_key=ids["vehicle_key"],
                private_key=ids["private_key"],
                **kwargs,
            )

        if args.wake:
            print("===== WAKE_VEHICLE =====")
            try:
                wake_id = await send(VehicleCommand.WAKE_VEHICLE)
            except RivianApiException as ex:
                print(f"WAKE REJECTED {_conflict_bits(ex)}")
                return 1
            print(f"wake id : {wake_id}")
            await asyncio.sleep(2)

        print("===== START_GEAR_GUARD_MASTER_SESSION =====")
        sent_at = time.monotonic()
        try:
            command_id = await send(
                VehicleCommand.START_GEAR_GUARD_MASTER_SESSION,
                params={"camera": args.camera},
            )
        except RivianApiException as ex:
            print(
                f"REJECTED at send after {time.monotonic() - sent_at:.2f}s  {_conflict_bits(ex)}"
            )
            print("GATE FAIL")
            return 1
        ack = time.monotonic() - sent_at
        print(f"command_id: {command_id}   (send ack in {ack:.2f}s)")
        if not command_id:
            print("REJECTED at send — no command id")
            print("GATE FAIL")
            return 1

        config_frames: list[dict] = []
        cmd_frames: list[dict] = []

        def on_config(msg: dict) -> None:
            data = ((msg.get("payload") or {}).get("data") or {}).get(
                "gearGuardLiveConfig"
            )
            if data is None and isinstance(msg.get("data"), dict):
                data = msg["data"].get("gearGuardLiveConfig")
            if data:
                config_frames.append(data)
                print(f"config  : {_redact_config(data)}")

        def on_cmd(msg: dict) -> None:
            data = ((msg.get("payload") or {}).get("data") or {}).get(
                "vehicleCommandState"
            )
            if data is None and isinstance(msg.get("data"), dict):
                data = msg["data"].get("vehicleCommandState")
            if data:
                cmd_frames.append(data)
                print(
                    f"cmdstate: state={data.get('state')} "
                    f"responseCode={data.get('responseCode')}"
                )

        unsub_cfg = await client.subscribe_gear_guard_live_config(
            ids["vehicle_id"], command_id, on_config
        )
        unsub_cmd = await client.subscribe_for_command_state(command_id, on_cmd)
        print("subscribed gearGuardLiveConfig + vehicleCommandState")

        deadline = time.monotonic() + args.timeout
        last_poll = None
        while time.monotonic() < deadline:
            await asyncio.sleep(0.5)
            state = await (await client.get_vehicle_command_state(command_id)).json()
            data = (state.get("data") or {}).get("getVehicleCommand")
            if data != last_poll:
                last_poll = data
                elapsed = time.monotonic() - sent_at
                print(
                    f"  t+{elapsed:>6.2f}s  state={data and data.get('state')} "
                    f"responseCode={data and data.get('responseCode')}"
                )
            if config_frames:
                print("GATE PASS — gearGuardLiveConfig arrived")
                if unsub_cfg:
                    unsub_cfg()
                if unsub_cmd:
                    unsub_cmd()
                await client.close()
                return 0
            if (
                data
                and _is_terminal(data.get("state"))
                and not config_frames
                and time.monotonic() > sent_at + 8
            ):
                break

        if unsub_cfg:
            unsub_cfg()
        if unsub_cmd:
            unsub_cmd()
        await client.close()
        print(
            f"GATE FAIL — no config in {args.timeout:.0f}s "
            f"(config_frames={len(config_frames)} cmd_frames={len(cmd_frames)})"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
