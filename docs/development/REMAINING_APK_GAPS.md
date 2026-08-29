# Remaining APK 3.15.0 HA-shaped gaps

Product catalog of Rivian Android app 3.15.0 features this Home Assistant
integration does not expose. A row is an **HA-shaped** analogue (an HA entity
or service that could exist). Completeness is linted by
`tests/test_apk_transcription.py::TestRemainingApkGaps`.

Probe evidence (live accepts, rejections, envelopes) stays in
[`COMMAND_COVERAGE.md`](COMMAND_COVERAGE.md). This file owns dispositions.

The APK is a lower bound: HA extras the app does not name are not APK gaps.

## Candidate-to-build

HA-shaped, APK has a cloud path, not in the named non-goals, no recorded VAS
`CONFLICT` / Parallax ISE. Gateway-accepted unwired VASCommands. Do **not**
implement these in the catalog change; live writes need owner OK.

| Gap | APK evidence | HA today | Proposed analogue |
|-----|--------------|----------|-------------------|
| Flash lights | `FLASH_EXTERNAL_LIGHTS` VASCommand; gateway accepted on this R1T (in-flight at 9.6s, no CONFLICT). [`COMMAND_COVERAGE.md:233-276`](COMMAND_COVERAGE.md) | none | `button` |
| Honk / external sound | `ACTIVATE_EXTERNAL_SOUND` VASCommand; gateway accepted, vehicle later `412`. Same section. | none | `button` |

## Listed-not-built (named non-goals)

Implementation non-goals from the remaining-features interview, or scoped out by
the story that shipped the neighbouring surface. Listed so they are not omitted;
not scheduled for implementation.

| Gap | APK evidence | Why listed-not-built |
|-----|--------------|----------------------|
| Interior camera feed | `INTERIOR_CAMERA`. A *picker option* only (`gear_guard.py:37-38`), never a gate source — `camera.gear_guard_live` gates on `LIVE_CAM`/`MOTION_CAM` (`gear_guard.py:24`), so a vehicle whose only camera flag is `INTERIOR_CAMERA` gets no camera entity. | s28 scoped it out (`tests/test_camera.py::test_no_interior_entity_even_with_interior_flag`); an interior-only vehicle gets nothing (`::test_not_created_without_camera_flags`). This R1T does not advertise the flag (`CAPABILITY_MATRIX.md:83`), so it cannot be probed on the available hardware. |
| Combined honk+flash | `HONK_AND_FLASH_LIGHTS` — **not** a VASCommand; live REJECTED twice | Button reverted; not a cloud path |
| Trip planner / active trip / add-stop / trailers / satmap | `ACTIVE_TRIP`, `V_TRIP`, `TRIP_ADD_STOP`, `TRIP_PLANNER_TRAILERS`, `V_SATMAP` | Round 4 non-goal. Navigation `notify` already exists. |
| Phone-key management UI | `KEY_PAAK`, `KEY_FOB_2`, `PIN_PROFILE`, `ORPHANED_PHONE_KEY_RECOVERY_HANDLING` | Pair button + counts only; Round 4 non-goal |

## Listed-not-built until a live accept

VAS-rejected / envelope-unknown commands, ISE Parallax writes, and unproven
GraphQL names. A live accept (command or name-probe) is what promotes a row,
not a decompile.

Invalid-wrapper seven (`tests/test_apk_transcription.py:406-412`):

| Gap | APK evidence | Blocker |
|-----|--------------|---------|
| Pet comfort off | `PET_COMFORT_OFF`; invalid-wrapper; VAS REJECTED | Parallax envelope NOT DERIVABLE ([`PARALLAX_SEND_PATH.md`](PARALLAX_SEND_PATH.md)). Pet *state* sensors already exist. |
| Pet comfort on | `PET_COMFORT_ON`; invalid-wrapper; VAS REJECTED | Same |
| Gear Guard video download | `START_VIDEO_DOWNLOADING_SESSION`; invalid-wrapper; VAS REJECTED | Same family |
| Two-factor drive allow | `TWO_FACTOR_DRIVE_ALLOW`; VAS REJECTED | No readable state surface |
| Two-factor drive deny | `TWO_FACTOR_DRIVE_DENY`; VAS REJECTED | Same |
| Two-factor drive disable | `TWO_FACTOR_DRIVE_DISABLE`; VAS REJECTED | Same |
| Two-factor drive enable | `TWO_FACTOR_DRIVE_ENABLE`; VAS REJECTED | Same |
| Gear Guard lock enable | `ENABLE_GEAR_GUARD`; live 2026-08-26 **REJECTED** `CONFLICT/VEHICLE_COMMAND_ERROR` (no command id). `rivian_client/const.py:313-316`. Video pair stays wired (`switch.py:51-58`). | Same class as `PET_COMFORT_ON` / `HONK_AND_FLASH_LIGHTS`. HMAC was working: climate-hold VAS returned command ids on the same session. Principle -1: CONFLICT is not a capability failure. |
| Gear Guard lock disable | `DISABLE_GEAR_GUARD`; same CONFLICT, twice (before and after ENABLE). | Same |
| Halloween 2025 | `HLWN_25` | `sendVehicleOperation` ISE; entities removed 1.6.0 |
| Cabin vent / auto-vent | `AUTO_VENT`, `CLM_HOLD_AUTO_VENT`; RVM `cabin_ventilation_setting` undecoded | ISE both directions; entities removed |
| Favorite geofences | RVM `favoriteGeofences` undecoded; `rivian.set_geofences` existed | ISE; service removed. HA-shaped (service) so it stays in the catalog. |
| Passive-entry settings | `PASSIVE_ENTRY_PROTO_V2` | ISE; entities removed |
| Rear window status | `rearWindowStatus` (`.apk/3.15.0/jadx/sources/com/rivian/android/consumer/data/model/VehicleState2.java:60`) | Not in the five Apollo vehicleState documents. No VASCommand (no cover). Name-probe required. |
| Charger damaged | `vehicleChargerDamaged` (`VehicleState2.java:62`) | Unproven GraphQL name. |
| Driver occupancy | `driverOccupancyStatus` (`.apk/3.15.0/jadx/sources/com/rivian/android/consumer/data/model/VehicleState.java:39`) | Unproven GraphQL name. Occupancy *is* HA-shaped (`binary_sensor`). |
| 2FA challenge surface | `driveAuthorizationUserInputRequestStatus` (`VehicleState2.java:38`) | Unproven GraphQL name. |
| AC charging disabled | `chargingDisabledAC` (`rivian_client/schemas/gateway.graphql:677`) | Schema-declared sibling of subscribed `chargingDisabledACFaultState`. Not in `VEHICLE_STATE_API_FIELDS`. Name-probe required before adding to the live document. |

## Already at parity via other transport

Sendable VASCommands whose HA analogue already exists via another transport.
Lint home so `SENDABLE_COMMANDS` completeness has no hole. Not remaining gaps.

| Command | HA analogue | Why unused VAS |
|---------|-------------|----------------|
| `CLIMATE_HOLD_ON` | Cabin climate hold switch (`switch.py:69-93`); `tests/test_climate_hold_wiring.py:10-12` | VAS is gateway-accepted (2026-08-26) then vehicle `responseCode` 417; hold stayed off. Working write is Parallax. The comment at `switch.py:72` must not count as wiring. |
| `CLIMATE_HOLD_OFF` | Same switch | Same: gateway-accepted, `417`, hold stayed off. |

## Out of catalog

Not HA-shaped, HA extras the APK does not name, already wired, or out of this
story. Inclusive OR: a wired sendable may also appear here (`OPEN_LIFTGATE`,
`OPEN_TAILGATE` in `button.py:86` and `button.py:103`).

| Item | Why out |
|------|---------|
| Shop, account, Stripe, MapLibre, charging-network signup | Not HA-shaped (Round 5) |
| Energy graphs / cold-weather bar charts | Not an entity/service; sensors for SoC already exist |
| Per-door unlock / `UNLOCK_ALL_AND_OPEN_WINDOWS` | HA extras **absent from APK 3.15.0** — not an APK gap (lower bound) |
| `OPEN_LIFTGATE` / `OPEN_TAILGATE` | Already wired, disabled by default. Tailgate actuation owner-prohibited (garage). |
| `START_GEAR_GUARD_MASTER_SESSION` | Already wired by s28 as `camera.gear_guard_live` (`camera.py:388`). No stop VASCommand exists; tear-down is local. Clip download (`START_VIDEO_DOWNLOADING_SESSION`) is a different path and stays unwired. |
| Unpopulated `tirePressureStatusValid*` / `cabinHoldNotification` | Not missing; subscribed and empty. Stay. |
| s26 optional-hardware gating | Separate story; not a missing feature |
| Gen2 BLE pairing | Separate spec; no hardware |
| Pause-frunk / pause-liftgate / pause-tonneau | `cloudData=null` — not cloud commands |
| Wallbox controls | Wallbox is 7 sensors; no APK VASCommand evidence gathered this interview — do not invent a row |
