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
| Passive-entry unlock fail reason | `passiveEntryUnlockFailReason` in 3.15.0's documents ([`APK_HISTORICAL_SWEEP.md`](APK_HISTORICAL_SWEEP.md)); **live-ACCEPTED 2026-08-31**, delivered `AT_HOME_DISABLE` ([`COMMAND_COVERAGE.md`](COMMAND_COVERAGE.md)) | none | `sensor` — but the value vocabulary is one sample; other reasons are unobserved |
| VAS access CAN faulted | `vasAccessCanFaulted`; **live-ACCEPTED 2026-08-31**, delivered `no_failure`. Same sections. | none | `binary_sensor` — `no_failure` is the healthy arm of a fault enum whose other arms are unobserved |
| VAS secure element faulted | `vasSecureElementFaulted`; **live-ACCEPTED 2026-08-31**, delivered `no_failure`. Same sections. | none | `binary_sensor`, same caveat |
| Honk / external sound | `ACTIVATE_EXTERNAL_SOUND` VASCommand; gateway accepted, vehicle later `412`. Same section. | none | `button` |

## Listed-not-built (named non-goals)

Implementation non-goals from the remaining-features interview, or scoped out by
the story that shipped the neighbouring surface. Listed so they are not omitted;
not scheduled for implementation.

| Gap | APK evidence | Why listed-not-built |
|-----|--------------|----------------------|
| Interior camera feed | `INTERIOR_CAMERA`. A *picker option* only (`gear_guard.py:37-38`), never a gate source — `camera.gear_guard_live` gates on `LIVE_CAM`/`MOTION_CAM` (`gear_guard.py:24`), so a vehicle whose only camera flag is `INTERIOR_CAMERA` gets no camera entity. | s28 scoped it out (`tests/test_camera.py::test_no_interior_entity_even_with_interior_flag`); an interior-only vehicle gets nothing (`::test_not_created_without_camera_flags`). This R1T does not advertise the flag (`CAPABILITY_MATRIX.md:83`), so it cannot be probed on the available hardware. |
| Combined honk+flash | `HONK_AND_FLASH_LIGHTS` — not a VASCommand **in 3.15.0**; live REJECTED twice. Corrected 2026-08-31 (s32): it *was* one in all 25 corpus versions 1.0.3–2.6.0, cloud+ble. A dropped command, not one that never existed. | Button reverted; not a cloud path in the shipping app |
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
| 8 Parallax RVMs with a captured frame and no schema | `charging.energy.state`, `charging.session.{notification,remote_command,soc_slider}`, `comfort.cabin.hvac_settings_status`, `comfort.user_modes.state`, `energy_edge_compute.graphs.cold_weather_soc`, `ota.ota_state.vehicle_ota_state`. Frames committed ([`APK_HISTORICAL_SWEEP.md`](APK_HISTORICAL_SWEEP.md)) | **Neither a named `.proto` schema nor a dispatch binding.** A decoder could only emit `field_3`-style keys, and a mislabelled sensor outlasts a recorded gap. The frames ship so a future attempt starts from evidence rather than from scratch. Re-entry: a build that binds the topic, or a schema. |
| `ota.deployment.state` | Dispatch binds it to message class `vkd`; no `.proto`. 54-byte frame carries `2026.31.0`. Same source. | **The best remaining decode candidate.** Field names are recoverable from the decompilation via `vkd` -- real work, but not guesswork, unlike the eight above. Not done in s34 only because the four with named schemas were cheaper and safer first. |
| Halloween celebration settings | `holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings`; named schema at `rivian_vehicle.proto:84`, frame committed. Same source. | Decodable and deliberately not decoded. `HalloweenCostumeTheme` is a **message, not an enum**, so there is no value vocabulary to map; and the `HLWN_25` family is already dispositioned ISE with its entities removed (row above). Decoding would subscribe a feature this repo decided against. |
| `charging.schedule.time_window` | Named schema at `rivian_charging.proto:40`. **Fixture withheld.** | Its frame carries a GPS coordinate in a nested `WindowData.location` field -- two f64 doubles, no printable run, so every text-shaped privacy guard passed it. A decoder with nothing to verify against does not ship. Re-entry: a frame captured with no schedule location set. |
| Halloween 2025 | `HLWN_25` | `sendVehicleOperation` ISE; entities removed 1.6.0 |
| Cabin vent / auto-vent | `AUTO_VENT`, `CLM_HOLD_AUTO_VENT`; RVM `cabin_ventilation_setting` undecoded | ISE both directions; entities removed |
| Favorite geofences | RVM `favoriteGeofences` undecoded; `rivian.set_geofences` existed | ISE; service removed. HA-shaped (service) so it stays in the catalog. |
| Passive-entry settings | `PASSIVE_ENTRY_PROTO_V2` | ISE; entities removed |
| Rear window status | `rearWindowStatus` (`.apk/3.15.0/jadx/sources/com/rivian/android/consumer/data/model/VehicleState2.java:60`) | Not in the five Apollo vehicleState documents. No VASCommand (no cover). Name-probe required. |
| Charger damaged | `vehicleChargerDamaged` (`VehicleState2.java:62`) | Unproven GraphQL name. |
| Driver occupancy | `driverOccupancyStatus` (`.apk/3.15.0/jadx/sources/com/rivian/android/consumer/data/model/VehicleState.java:39`) | Unproven GraphQL name. Occupancy *is* HA-shaped (`binary_sensor`). |
| 2FA challenge surface | `driveAuthorizationUserInputRequestStatus` (`VehicleState2.java:38`) | Unproven GraphQL name. |
| Winch control (7 commands) | `WINCH_IN`, `WINCH_OUT`, `WINCH_CANCEL`, `WINCH_FREE_SPOOL`, `WINCH_REENGAGE`, `WINCH_ACCEPT_CONTROLLER_ROLE`, `WINCH_REJECT_CONTROLLER_ROLE` — real VASCommands in 1.0.3–1.4.1 only, then dropped. Same source. | **BLE-only in every version; no cloud wrapper ever existed**, and this integration sends via cloud after pairing. Not sendable without new BLE plumbing. Re-entry: a cloud wrapper appearing in a future build. |
| AC charging disabled | `chargingDisabledAC`, declared in `rivian_client/schemas/gateway.graphql` and carried by the app itself (s33 corpus sweep). **Live-ACCEPTED 2026-09-01**, delivered `0` ([`COMMAND_COVERAGE.md`](COMMAND_COVERAGE.md)) | Name proven; **semantics are not**. One numeric sample, and the neighbouring `chargingDisabledACFaultState` uses a string vocabulary -- `0` could be a flag, a count, or an enum's zero arm. Needs a second sample under a different charging state before it is a sensor. |

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
| Per-door unlock / `UNLOCK_ALL_AND_OPEN_WINDOWS` | **Miscategorized — corrected 2026-08-31 (s32).** "Absent from APK 3.15.0" is TRUE and stays enforced (`test_apk_transcription.py`), but "HA extras" is wrong: these are app commands 3.15.0 **dropped**. The historical corpus carries `UNLOCK_DRIVER_DOOR`, `UNLOCK_PASSENGER_DOOR` and `UNLOCK_ALL_AND_OPEN_WINDOWS` as full dual-transport VASCommands in 19 versions (1.5.1–2.6.0), and `UNLOCK_USER_PREFERENCES_AND_DISABLE_ALARM` in 25 (1.0.3–2.6.0). Held out of the probe queue: all four were live-REJECTED `CONFLICT/VEHICLE_COMMAND_ERROR` on 2026-08-26 ([`COMMAND_COVERAGE.md`](COMMAND_COVERAGE.md)). **Re-entry condition:** a firmware change, or a materially different vehicle state — per Principle -1 above, a CONFLICT is not a capability failure. They stay in the enum. |
| `OPEN_LIFTGATE` / `OPEN_TAILGATE` | Already wired, disabled by default. Tailgate actuation owner-prohibited (garage). |
| `START_GEAR_GUARD_MASTER_SESSION` | Already wired by s28 as `camera.gear_guard_live` (`camera.py:388`). No stop VASCommand exists; tear-down is local. Clip download (`START_VIDEO_DOWNLOADING_SESSION`) is a different path and stays unwired. |
| Unpopulated `tirePressureStatusValid*` / `cabinHoldNotification` | Not missing; subscribed and empty. Stay. |
| s26 optional-hardware gating | Separate story; not a missing feature |
| Gen2 BLE pairing | Separate spec; no hardware |
| Pause-frunk / pause-liftgate / pause-tonneau | `cloudData=null` — not cloud commands. Corroborated across the corpus (s32): `PAUSE_FRUNK`, `PAUSE_LIFTGATE`, `PAUSE_TONNEAU_COVER` are BLE-only in all 25 versions 1.0.3–2.6.0, and in 3.15.0 the three classes lost the BLE path without gaining a cloud one. [`APK_HISTORICAL_SWEEP.md`](APK_HISTORICAL_SWEEP.md) |
| `CABIN_HVAC_THIRD_ROW_{LEFT,RIGHT}_SEAT_HEAT` | Absent from **every** app version 1.0.3–3.15.0, measured across 26 dumps (s32). `rivian_client/const.py` speculated they might belong to an older firmware or app; no app version has ever named them. They **stay** in the enum — the app is a lower bound, never the schema, and the neighbouring `CABIN_HVAC_3RD_ROW_*` spelling is the one 3.15.0 actually sends. [`APK_HISTORICAL_SWEEP.md`](APK_HISTORICAL_SWEEP.md) |
| Wallbox controls | Wallbox is 7 sensors; no APK VASCommand evidence gathered this interview — do not invent a row |
