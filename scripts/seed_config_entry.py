#!/usr/bin/env python3
"""Seed the devcontainer's Home Assistant with an authenticated Rivian entry.

Why this exists: signing in through the UI needs a password and an OTP code from
the owner's phone, which makes "boot the devcontainer and look at the entities" a
manual ceremony every time the config directory is recreated. The credentials
already sit in .env for the live probes, so this writes them straight into
.storage in the shape config_flow would have produced.

What it writes, mirroring custom_components/rivian/config_flow.py:
  data    <- _async_create_entry: username, access_token, refresh_token,
             user_session_token
  options <- validate_vehicle_control: public_key, private_key, vehicle_control,
             vehicle_image_style

Secrets discipline. This script reads secrets and writes them to a gitignored
path, and that is all it does with them: it never prints a value, never logs one,
and the file it writes is chmod 600. Both ends are gitignored, and the seeded entry
must never be committed.

It defaults to config-dev/, NOT config/. config/ holds a recorder database and a
.storage written by an older Home Assistant; booting the pinned 2026.8.2 against it
migrates both one-way. The devcontainer gets its own directory so that cannot
happen by accident.

Usage:
    python scripts/seed_config_entry.py [--env .env] [--config config-dev] [--force]

Idempotent: an existing rivian entry is replaced in place, keeping its entry_id
so the device and entity registries stay attached to it. Entries for other
domains in the same file are left untouched.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

# .env name -> where it lands in the entry. Splitting these two dicts is what
# keeps the script honest about the config_flow shape it is imitating.
DATA_KEYS = {
    "RIVIAN_USERNAME": "username",
    "RIVIAN_ACCESS_TOKEN": "access_token",
    "RIVIAN_REFRESH_TOKEN": "refresh_token",
    "RIVIAN_USER_SESSION_TOKEN": "user_session_token",
}
OPTION_KEYS = {
    "RIVIAN_PUBLIC_KEY": "public_key",
    "RIVIAN_PRIVATE_KEY": "private_key",
}
# Not a credential, but the entry is useless without it: vehicle_control holds the
# 32-char hex device ids the control entities are keyed on. Note this is a third,
# non-interchangeable vehicle identifier -- not vehicles[0].id (01-...) and not
# vas.vasVehicleId (a UUID).
VEHICLE_CONTROL_KEY = "RIVIAN_VEHICLE_CONTROL_DEVICES"

STORAGE_VERSION = 1
STORAGE_MINOR_VERSION = 5
ENTRY_VERSION = 1
ENTRY_MINOR_VERSION = 1


def read_env(path: Path) -> dict[str, str]:
    """Parse a dotenv file. Deliberately minimal -- no interpolation, no export."""
    if not path.is_file():
        sys.exit(f"error: {path} not found. It holds the credentials to seed.")
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        values[key.strip()] = val
    return values


def build_entry(env: dict[str, str], entry_id: str) -> dict:
    """Assemble the entry. Raises if anything required is missing or blank."""
    missing = [
        k
        for k in (*DATA_KEYS, *OPTION_KEYS, VEHICLE_CONTROL_KEY)
        if not env.get(k, "").strip()
    ]
    if missing:
        sys.exit(
            "error: .env is missing (or has blank) "
            + ", ".join(sorted(missing))
            + "\nNames only are shown; no values are ever printed."
        )

    now = datetime.now(timezone.utc).isoformat()
    vehicle_control = [
        v.strip() for v in env[VEHICLE_CONTROL_KEY].split(",") if v.strip()
    ]
    return {
        "created_at": now,
        "data": {dest: env[src] for src, dest in DATA_KEYS.items()},
        "disabled_by": None,
        "discovery_keys": {},
        "domain": "rivian",
        "entry_id": entry_id,
        "minor_version": ENTRY_MINOR_VERSION,
        "modified_at": now,
        "options": {
            **{dest: env[src] for src, dest in OPTION_KEYS.items()},
            "vehicle_control": vehicle_control,
            "vehicle_image_style": env.get("RIVIAN_VEHICLE_IMAGE_STYLE", "cel"),
        },
        "pref_disable_new_entities": False,
        "pref_disable_polling": False,
        "source": "user",
        "subentries": [],
        "title": "Rivian (Unofficial)",
        "unique_id": None,
        "version": ENTRY_VERSION,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--config", type=Path, default=Path("config-dev"))
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing rivian entry instead of refusing",
    )
    args = parser.parse_args()

    env = read_env(args.env)
    storage = args.config / ".storage" / "core.config_entries"
    storage.parent.mkdir(parents=True, exist_ok=True)

    if storage.exists():
        blob = json.loads(storage.read_text())
        entries = blob.setdefault("data", {}).setdefault("entries", [])
    else:
        blob = {
            "version": STORAGE_VERSION,
            "minor_version": STORAGE_MINOR_VERSION,
            "key": "core.config_entries",
            "data": {"entries": []},
        }
        entries = blob["data"]["entries"]

    existing = next(
        (i for i, e in enumerate(entries) if e.get("domain") == "rivian"), None
    )
    if existing is not None and not args.force:
        sys.exit(
            "error: a rivian entry is already present. Re-run with --force to "
            "replace it (its entry_id is kept, so registries stay attached)."
        )

    # Reusing the entry_id matters: device and entity registry rows reference it,
    # and a new id orphans every entity the user has already renamed or automated.
    entry_id = (
        entries[existing]["entry_id"] if existing is not None else uuid.uuid4().hex
    )
    entry = build_entry(env, entry_id)

    if existing is not None:
        entry["created_at"] = entries[existing].get("created_at", entry["created_at"])
        entries[existing] = entry
    else:
        entries.append(entry)

    storage.write_text(json.dumps(blob, indent=2))
    os.chmod(storage, 0o600)

    action = "replaced" if existing is not None else "created"
    print(f"{action} the rivian config entry in {storage}")
    print(f"  entry_id       {entry_id}")
    print(f"  data keys      {', '.join(sorted(entry['data']))}")
    print(f"  options keys   {', '.join(sorted(entry['options']))}")
    print(f"  vehicles       {len(entry['options']['vehicle_control'])}")
    print("  values are not printed, and this file must never be committed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
