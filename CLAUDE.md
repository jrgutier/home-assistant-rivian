# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an unofficial Home Assistant custom integration for Rivian vehicles. It provides sensors, binary sensors, and vehicle control capabilities through the Rivian Cloud API and Bluetooth pairing. The integration is distributed through HACS (Home Assistant Community Store).

## Development Commands

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
merge path and is synced with `scripts/sync_upstream_client.sh`. Do not run
`ruff --fix` across `rivian_client/` -- it is excluded in `pyproject.toml` because
reformatting vendored code recreates the divergence vendoring removed.

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

### Platform Files

Each Home Assistant platform is implemented in its own file:
- `binary_sensor.py`, `sensor.py`: Read-only state sensors
- `button.py`, `switch.py`, `cover.py`, `lock.py`, `number.py`, `select.py`, `climate.py`: Control entities
- `device_tracker.py`: GPS location tracking
- `update.py`: OTA software update status
- `image.py`: Vehicle images
- `notify.py`: Navigation service for sending destinations to vehicles

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

## File Structure

```
custom_components/rivian/
├── __init__.py          # Integration setup, coordinator initialization
├── manifest.json        # Integration metadata and dependencies
├── const.py            # Entity definitions, constants, sensor configurations
├── coordinator.py      # Data update coordinators (real-time subscriptions + polling)
├── entity.py           # Base entity classes with shared logic
├── data_classes.py     # Custom entity description dataclasses
├── config_flow.py      # Config and options flows
├── helpers.py          # Utility functions
├── diagnostics.py      # Debug data collection
├── recorder.py         # Database recorder configuration
├── notify.py           # Navigation service implementation
└── [platform].py       # Platform implementations (sensor, switch, etc.)
```

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

- The integration is cloud-polling for some data (`iot_class: "cloud_polling"` in manifest)
- Main vehicle state uses GraphQL subscriptions for real-time updates, not polling
- Always check if a vehicle supports a feature via `supported_features` before creating entities
- Some entities are disabled by default (marked with `entity_registry_enabled_default=False`)
- Invalid sensor states (`fault`, `signal_not_available`, `undefined`) are filtered using history
- When adding new sensors, update both `SENSORS`/`BINARY_SENSORS` in `const.py` AND `VEHICLE_STATE_API_FIELDS`

## Development Branch

The `dev` branch is the main development branch. The current working branch is `dev-climate-hold` which is being used to develop a climate hold feature.
