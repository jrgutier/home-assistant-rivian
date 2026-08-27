# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an unofficial Home Assistant custom integration for Rivian vehicles. It provides sensors, binary sensors, and vehicle control capabilities through the Rivian Cloud API and Bluetooth pairing. The integration is distributed through HACS (Home Assistant Community Store).

## Development Commands

### Environment setup

```bash
bash scripts/setup_dev_env.sh   # builds .venv/, then: .venv/bin/pytest -q
```

**`python3 -m venv` does not work here, and the way it fails is misleading.**
`requirements_test.txt` pins `pytest-homeassistant-custom-component`, which pins
`homeassistant==2026.8.2`, which requires **Python >= 3.14.2**. Distros ship 3.10-3.13,
and pip's response to a too-old interpreter is not an error about the interpreter --
it filters the index by `Requires-Python` and reports the newest version that *does*
match (`2024.3.3` on 3.11), which reads as a stale or broken package index. It is
not: PyPI is fine, the interpreter is too old. The script fetches 3.14 with `uv`,
mirroring `.github/workflows/test.yaml` so local and CI cannot drift.

`uv` being merely present is not enough either: a `uv` predating the 3.14 release
installs `3.14.0rc2`, which is *below* 3.14.2 under PEP 440, and the only symptom is
an unresolvable `homeassistant` pin. The script checks the interpreter uv can
actually produce and upgrades uv when it cannot.

Web sessions run this automatically -- `.claude/hooks/session-start.sh`, synchronous
so the venv exists before the first turn. Local checkouts are left alone.

### Linting and Formatting

The project uses Ruff for both linting and formatting:

```bash
# Run linter with auto-fix
ruff check --fix .

# Run formatter
ruff format .

# Pre-commit hooks (uses ruff)
pre-commit run --all-files
```

### Installation in Home Assistant

The integration is installed via HACS. For local development:

1. Copy `custom_components/rivian/` to your Home Assistant's `custom_components/` directory
2. Restart Home Assistant
3. Add the integration through the UI: Configuration → Integrations → Add Integration → "Rivian (Unofficial)"

### Dependencies

**The API client is vendored, not installed.** It lives at
`custom_components/rivian/rivian_client/` and is edited in place. There is no
package to bump, no publish step, and no external client repository to keep in
sync at install time.

`manifest.json` declares exactly one requirement:

```json
"requirements": ["bleak>=0.21"]
```

That is the whole list, and it is deliberate. Home Assistant core does not ship
`bleak` -- it belongs to the `bluetooth` integration -- so the pairing button needs
it declared. Everything else the client imports (`aiohttp`, `cryptography`) is
genuine HA core metadata.

It previously read:

```json
"requirements": ["rivian-python-client[ble] @ git+https://github.com/jrgutier/rivian-python-client.git@<branch>"]
```

which is why installs were not reproducible: a moving branch, needing `git` and a
source build inside HA, and unversionable, so HA could not tell whether it was
satisfied.

**Adding a requirement is not free.** Anything listed must be something the code
imports and HA core does not guarantee. `scripts/load_test.sh` installs only what
the manifest declares and imports every module out of the built zip; the test suite
cannot catch a missing entry, because its venv carries HA's full test extra and so
resolves imports that a user's install would not.

**Tracking upstream:** see [docs/UPSTREAM_MERGE_REHEARSAL.md](docs/UPSTREAM_MERGE_REHEARSAL.md).
The integration merges from `upstream/main` normally; the vendored client has no
merge path and is synced with `scripts/sync_upstream_client.sh`. `rivian_client/`
is linted with the rest of `custom_components/` (ruff check/format). After a
sync, run ruff so an upstream patch cannot reintroduce style drift.

## Git Workflow

**`master` is protected — everything lands via pull request.** There is no path that commits
straight to `master`, including for a one-line doc fix.

**One branch per story, cut from `origin/master`**, named for the story
(`s21-binary-sensor-apk-parity`). The `sNN:` commit prefix delineates one story from the next, and
the branch boundary agrees with it.

**Commit prefixes** use the repo's `sNN:` story convention.

**Releases are cut by hand, and so are version bumps.** Bump `manifest.json` *and* `const.py`'s
`VERSION` in a normal PR, then run the **Pre-Release Build** workflow manually
(`workflow_dispatch`). It tags exactly what the manifest says and refuses to re-cut an existing
tag.

This replaces a CI-owned bump (`chore: bump version [skip ci]`) that fired on every push to
master. Protecting `master` broke it: the bot's push was rejected with `GH006` and swallowed by
`|| echo "Push skipped"`, so the workflow reported success while the bump vanished. It also meant
a merge published a beta before its own test run had finished.

**Pre-commit needs `.venv/bin` on PATH** or commits fail with "pre-commit not found". Fix the PATH;
never reach for `--no-verify`. One of its hooks is `f11`, which checks that every `file.py:NN`
citation in `custom_components/` still points at what it claims; `scripts/gates/f11.sh --fix`
repairs drift. Note its corpus is `custom_components/` only — citations in `docs/` and `tests/`
are not checked and must be verified by hand.

**Amend before pushing, never after.** Once pushed, amending means a force-push, which rewrites
history under an open PR: review comments detach from the lines they were left on, and anyone who
pulled the branch cannot fast-forward.

**Worktrees.** Git refuses two worktrees on the same branch, so parallel agents each get a
short-lived `wt/<lane>` branch cut from the story branch. Merge it back into the *story branch* —
never into `master` — and delete both the branch and the worktree when the lane closes.

## Architecture

### Core Components

**Data Coordinators** (`coordinator.py`):
- `RivianDataUpdateCoordinator`: Abstract base class for all coordinators with error handling and rate limiting
- `VehicleCoordinator`: Main vehicle state coordinator using GraphQL subscriptions (NOT polling)
- `ChargingCoordinator`: Manages charging session data with adaptive polling (30s when plugged in, 15min when unplugged)
- `DriverKeyCoordinator`: Manages driver/key information (15min polling)
- `UserCoordinator`: User account information including enrolled phones for vehicle commands
- `WallboxCoordinator`: Rivian home charger data

**VehicleCoordinator Real-time Updates**:
The VehicleCoordinator uses GraphQL subscriptions via WebSocket for real-time vehicle state updates. It subscribes once during initialization and processes updates via callbacks. This is NOT a polling mechanism - polling is explicitly disabled in the `_fetch_data()` method.

**Entity Base Classes** (`entity.py`):
- `RivianEntity`: Base for all entities
- `RivianVehicleEntity`: For vehicle sensors/binary sensors
- `RivianVehicleControlEntity`: For controls (buttons, switches, covers, locks) - adds pairing status check and zone restrictions
- `RivianChargingEntity`: For charging-specific entities
- `RivianWallboxEntity`: For wallbox entities

### Entity Definitions

Entity definitions are centralized in `const.py`:
- `SENSORS`: Dictionary mapping vehicle types (R1, R1T, R1S) to sensor descriptions
- `BINARY_SENSORS`: Dictionary mapping vehicle types to binary sensor descriptions
- Entity descriptions use custom dataclasses from `data_classes.py` that extend Home Assistant's base entity descriptions

### Services

**Navigation Service** (`notify.py`):

The integration provides a navigation service for sending destinations to vehicles. Unlike vehicle commands, the navigation service does NOT require Bluetooth pairing or vehicle control setup - it operates purely through the cloud API.

**Technical Details:**
- Implemented as a notify platform that creates per-vehicle navigation services
- Service naming: `notify.rivian_{vehicle_name}_{vin_suffix}_navigation`
- VIN suffix (last 6 characters) ensures unique service names for multiple vehicles
- Uses `parseAndShareLocationToVehicle` GraphQL mutation
- Fire-and-forget operation: returns when cloud receives the request (not when vehicle receives it)

**Supported Location Formats:**
- Full addresses: `"123 Main Street, Anytown, CA 12345"`
- City and state: `"San Francisco, CA"`
- Coordinates: `"40.7128,-74.0060"` (decimal latitude,longitude format)

**Implementation Notes:**
- Uses `send_location_to_vehicle()` from the vendored client (`rivian_client/rivian.py`)
- Reuses the authenticated GraphQL client from the integration (no new client created)
- Returns result value 0 on success
- Invalid locations raise exceptions that are handled and logged

**Example Usage:**
```yaml
# Send full address
service: notify.rivian_my_r1t_abc123_navigation
data:
  message: "123 Main Street, Anytown, CA 12345"

# Send coordinates
service: notify.rivian_my_r1t_abc123_navigation
data:
  message: "37.7749,-122.4194"
```

**Key Differences from Vehicle Commands:**
- No Bluetooth pairing required
- No vehicle state checks (park gear, zone restrictions)
- Cloud-only operation
- Available immediately after integration setup

### Vehicle Commands

Vehicle commands require:
1. Bluetooth pairing completed (one-time setup via phone key enrollment)
2. Vehicle in "park" gear
3. Optional: Vehicle within specified Home Assistant zones (if configured)

Commands are sent via `VehicleCoordinator.send_vehicle_command()` which:
- Wakes the vehicle if asleep
- Uses cryptographic keys from the pairing process
- Sends commands through Rivian Cloud API (not direct Bluetooth)

### Configuration Flow

`config_flow.py` handles:
1. Initial authentication (username/password)
2. OTP/MFA validation if enabled
3. Options flow for vehicle control setup (Bluetooth pairing), zone restrictions, and vehicle image style

## Key Concepts

### Vehicle State Fields

All vehicle state fields are defined in `const.py`:
- `VEHICLE_STATE_API_FIELDS`: Set of all fields subscribed to for vehicle state
- Fields map to Rivian's GraphQL API field names (e.g., `batteryLevel`, `doorFrontLeftClosed`)
- Sensor/binary sensor descriptions reference these fields via the `field` attribute

### Multi-Vehicle Support

The integration supports multiple vehicles per account:
- Each vehicle gets its own `VehicleCoordinator` instance
- Devices are identified by VIN and vehicle ID
- All entities are scoped to their specific vehicle

### Bluetooth Pairing for Vehicle Control

Vehicle commands require a one-time Bluetooth pairing:
1. User enables vehicle control in options
2. Integration generates a cryptographic key pair
3. User initiates pairing in-vehicle and clicks "Pair" button entity in HA
4. After pairing, commands are sent via cloud (no Bluetooth required after pairing)
5. Gen2 (2025) vehicles not currently supported due to BLE hardware changes

### Data Flow

1. User account is fetched via `UserCoordinator` to get available vehicles
2. For each vehicle, a `VehicleCoordinator` subscribes to real-time GraphQL updates
3. Charging and driver/key data are polled separately with their own coordinators
4. All platforms read from coordinator data to populate entity states
5. Control platforms send commands through `VehicleCoordinator.send_vehicle_command()`

## Important Notes

- The integration is cloud-push (`iot_class: "cloud_push"` in manifest)
- Main vehicle state uses GraphQL subscriptions for real-time updates, not polling
- Always check if a vehicle supports a feature via `supported_features` before creating entities
- Some entities are disabled by default (marked with `entity_registry_enabled_default=False`)
- Invalid sensor states (`fault`, `signal_not_available`, `undefined`) are filtered using history on both the GraphQL and Parallax coordinator paths. Dropping an invalid value with no previous was tried twice and reverted -- it makes the entity unavailable and takes the matching control down with it. `sensor.py` and `binary_sensor.py` also filter at the entity; the other platforms do not.
- When adding new sensors, update both `SENSORS`/`BINARY_SENSORS` in `const.py` AND `VEHICLE_STATE_API_FIELDS`

