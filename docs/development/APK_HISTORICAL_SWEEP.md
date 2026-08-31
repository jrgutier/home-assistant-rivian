# APK historical sweep — the ledger

What every published version of `com.rivian.android.consumer` on hand has named,
and how that compares to what this integration exposes. Produced by
`scripts/apk_corpus_sweep.py` over 26 decompiled dumps; gated by
`scripts/gates/s17.sh`.

**This file is the ledger.** The probe queue at the end is a prioritised *view*
over it, not a second inventory. A name can be fully recorded here and correctly
never be probed.

## What this is not

A decompile enumerates; only the vehicle promotes. Nothing here is evidence that
a command works — `REMAINING_APK_GAPS.md` keeps that rule and this file inherits
it. Equally, absence here is not evidence a command is invalid: **the app is a
lower bound, never the schema.**

## Provenance and its limit

26 dumps, versions 1.0.3 → 2.6.0 plus 3.15.0 build 4804. Three root layouts, and
version does not predict layout: `sources/` covers all 1.x *and* `rivian_2.0.0_beta`
(19 dumps), `java_src/` covers 2.2.0 onward (6), `jadx/sources/` the 3.15.0 tree.

Counts compare **only within a cohort**. Which decompiler wrote each 1.x/2.x dump
was never recorded, so a count that drops between versions cannot be attributed to
a real app change rather than a lossier extraction. Only cohort C has documented
provenance (jadx, per `docs/development/apk/REGENERATION.md`).

| cohort | dumps | decompiler |
|---|---|---|
| A/sources | 1.0.3 – 1.15.0, 2.0.0_beta | unrecorded |
| B/java_src | 2.2.0 – 2.6.0 | unrecorded |
| C/jadx | 3.15.0 build 4804 | jadx, documented |

## The headline: the corpus refutes claims 3.15.0 alone supports

`REGENERATION.md` records fifteen `vehicleState` fields we subscribe to that
appear in **zero** of 3.15.0's 32,941 files, measured by whole-word grep over
every file. This sweep measures something narrower — depth-1 names in the
compiled `vehicleState` documents — so the two are *not* the same metric. They
coincide at 15 for 3.15.0, which is what makes the comparison below meaningful:
holding this sweep's metric fixed and widening only the corpus, the residue
collapses to **two**.

| measured against | fields we subscribe to that the app never names |
|---|---|
| 3.15.0 alone | 15 |
| all 26 versions | **2** — `batteryCapacity`, `cabinHoldNotification` |

Thirteen of the fifteen *do* appear in earlier builds' documents. So does
`cloudConnection`, which 3.15.0 also does not name. Those claims are true of
3.15.0 and false of the app's history — which is the one question a single-build
extraction cannot answer, and the reason this corpus was worth assembling.

## Commands — the ledger

68 distinct command names. Transport is the union across every version that
named the command.

| command | versions | n | cohorts | transport |
|---|---|---|---|---|
| `ACTIVATE_EXTERNAL_SOUND` | 3.15.0 | 1 | C | cloud |
| `CABIN_HVAC_3RD_ROW_REAR_LEFT_SEAT_HEAT` | 3.15.0 | 1 | C | cloud |
| `CABIN_HVAC_3RD_ROW_REAR_RIGHT_SEAT_HEAT` | 3.15.0 | 1 | C | cloud |
| `CABIN_HVAC_DEFROST_DEFOG` | 1.9.0–3.15.0 | 15 | A, B, C | cloud |
| `CABIN_HVAC_LEFT_SEAT_HEAT` | 1.9.0–3.15.0 | 15 | A, B, C | cloud |
| `CABIN_HVAC_LEFT_SEAT_VENT` | 1.10.0–3.15.0 | 14 | A, B, C | cloud |
| `CABIN_HVAC_REAR_LEFT_SEAT_HEAT` | 1.9.0–3.15.0 | 15 | A, B, C | cloud |
| `CABIN_HVAC_REAR_RIGHT_SEAT_HEAT` | 1.9.0–3.15.0 | 15 | A, B, C | cloud |
| `CABIN_HVAC_RIGHT_SEAT_HEAT` | 1.9.0–3.15.0 | 15 | A, B, C | cloud |
| `CABIN_HVAC_RIGHT_SEAT_VENT` | 1.10.0–3.15.0 | 14 | A, B, C | cloud |
| `CABIN_HVAC_STEERING_HEAT` | 1.9.0–3.15.0 | 15 | A, B, C | cloud |
| `CABIN_PRECONDITIONING_SET_TEMP` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `CHARGING_LIMITS` | 1.8.0–3.15.0 | 16 | A, B, C | cloud |
| `CLIMATE_HOLD_OFF` | 3.15.0 | 1 | C | cloud |
| `CLIMATE_HOLD_ON` | 3.15.0 | 1 | C | cloud |
| `CLOSE_ALL_WINDOWS` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `CLOSE_CHARGE_PORT_DOOR` | 3.15.0 | 1 | C | cloud |
| `CLOSE_FRUNK` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `CLOSE_LIFTGATE` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `CLOSE_TONNEAU_COVER` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `DISABLE_GEAR_GUARD` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `DISABLE_GEAR_GUARD_VIDEO` | 1.8.0–3.15.0 | 16 | A, B, C | cloud |
| `ENABLE_GEAR_GUARD` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `ENABLE_GEAR_GUARD_VIDEO` | 1.8.0–3.15.0 | 16 | A, B, C | cloud |
| `FLASH_EXTERNAL_LIGHTS` | 3.15.0 | 1 | C | cloud |
| `HONK_AND_FLASH_LIGHTS` | 1.0.3–2.6.0 | 25 | A, B | cloud+ble |
| `INVALID_COMMAND` **(not in enum)** | 1.5.1–3.15.0 | 20 | A, B, C | cloud |
| `LOCK_ALL_CLOSURES_FEEDBACK` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `OPEN_ALL_WINDOWS` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `OPEN_CHARGE_PORT_DOOR` | 3.15.0 | 1 | C | cloud |
| `OPEN_FRUNK` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `OPEN_LIFTGATE` | 3.15.0 | 1 | C | cloud |
| `OPEN_LIFTGATE_UNLATCH_TAILGATE` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `OPEN_TAILGATE` | 3.15.0 | 1 | C | cloud |
| `OPEN_TONNEAU_COVER` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `OTA_INSTALL_NOW_ACKNOWLEDGE` | 1.2.1–3.15.0 | 25 | A, B, C | cloud+ble |
| `PANIC_OFF` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `PANIC_ON` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `PAUSE_FRUNK` **(not in enum)** | 1.0.3–2.6.0 | 25 | A, B | ble-only |
| `PAUSE_LIFTGATE` **(not in enum)** | 1.0.3–2.6.0 | 25 | A, B | ble-only |
| `PAUSE_TONNEAU_COVER` **(not in enum)** | 1.0.3–2.6.0 | 25 | A, B | ble-only |
| `PET_COMFORT_OFF` | 3.15.0 | 1 | C | invalid-wrapper |
| `PET_COMFORT_ON` | 3.15.0 | 1 | C | invalid-wrapper |
| `RELEASE_LEFT_SIDE_BIN` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `RELEASE_RIGHT_SIDE_BIN` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `START_CHARGING` | 1.8.0–3.15.0 | 16 | A, B, C | cloud |
| `START_GEAR_GUARD_MASTER_SESSION` | 3.15.0 | 1 | C | cloud |
| `START_VIDEO_DOWNLOADING_SESSION` | 3.15.0 | 1 | C | invalid-wrapper |
| `STOP_CHARGING` | 1.8.0–3.15.0 | 16 | A, B, C | cloud |
| `TWO_FACTOR_DRIVE_ALLOW` | 3.15.0 | 1 | C | invalid-wrapper |
| `TWO_FACTOR_DRIVE_DENY` | 3.15.0 | 1 | C | invalid-wrapper |
| `TWO_FACTOR_DRIVE_DISABLE` | 3.15.0 | 1 | C | invalid-wrapper |
| `TWO_FACTOR_DRIVE_ENABLE` | 3.15.0 | 1 | C | invalid-wrapper |
| `UNLOCK_ALL_AND_OPEN_WINDOWS` | 1.5.1–2.6.0 | 19 | A, B | cloud+ble |
| `UNLOCK_ALL_CLOSURES` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `UNLOCK_DRIVER_DOOR` | 1.5.1–2.6.0 | 19 | A, B | cloud+ble |
| `UNLOCK_PASSENGER_DOOR` | 1.5.1–2.6.0 | 19 | A, B | cloud+ble |
| `UNLOCK_USER_PREFERENCES_AND_DISABLE_ALARM` | 1.0.3–2.6.0 | 25 | A, B | cloud+ble |
| `VEHICLE_CABIN_PRECONDITION_DISABLE` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `VEHICLE_CABIN_PRECONDITION_ENABLE` | 1.0.3–3.15.0 | 26 | A, B, C | cloud+ble |
| `WAKE_VEHICLE` | 1.0.3–3.15.0 | 26 | A, B, C | cloud |
| `WINCH_ACCEPT_CONTROLLER_ROLE` **(not in enum)** | 1.3.0–1.4.1 | 4 | A | ble-only |
| `WINCH_CANCEL` **(not in enum)** | 1.0.3–1.4.1 | 6 | A | ble-only |
| `WINCH_FREE_SPOOL` **(not in enum)** | 1.0.3–1.4.1 | 6 | A | ble-only |
| `WINCH_IN` **(not in enum)** | 1.0.3–1.4.1 | 6 | A | ble-only |
| `WINCH_OUT` **(not in enum)** | 1.0.3–1.4.1 | 6 | A | ble-only |
| `WINCH_REENGAGE` **(not in enum)** | 1.3.0–1.4.1 | 4 | A | ble-only |
| `WINCH_REJECT_CONTROLLER_ROLE` **(not in enum)** | 1.3.0–1.4.1 | 4 | A | ble-only |

## The command-side result is negative, and that is the finding

The only cloud-sendable name in the app that is absent from `VehicleCommand` is
`INVALID_COMMAND`, a sentinel class rather than a vehicle command. **Twenty-six
versions of history yielded no new cloud-sendable command to probe.** Every other
app-only command is BLE-only and is listed in the appendix below.

Two enum members appear in **no version at all**:
`CABIN_HVAC_THIRD_ROW_LEFT_SEAT_HEAT` and `CABIN_HVAC_THIRD_ROW_RIGHT_SEAT_HEAT`.
`rivian_client/const.py` speculated these might belong to an older app; measured
across the full corpus, no app version has ever named them. They stay — the app
is a lower bound.

## Sensor surfaces

| surface | app | ours | app-only | ours-only | floor |
|---|---|---|---|---|---|
| `vehicleState` (depth-1) | 157 | 149 | 10 | 2 | 157 |
| Parallax RVM (3.x only) | 58 | 33 | 25 | 0 | 58 |
| `VehicleFeature` | 89 | 64 | 25 | 0 | 89 |
| charging / wallbox | 52 | 72 | 2 | 22 | 52 |

`vehicleState` uses the depth-1 metric of
`scripts/gates/helpers/apk_vehicle_state_fields.py`, not a union at any depth.
Only depth-1 names are comparable to `VEHICLE_STATE_API_FIELDS`, which is a set of
top-level subscribed fields. Parallax draws on 3.x only: `ParallaxAttributes` is
absent from every 2.x tree, so the historical corpus contributes nothing there.

Each surface carries its own floor; a union below it is an error and exits 1.
Growth is fine and reported.

### `vehicleState` fields the app names and we do not

| field | seen |
|---|---|
| `cloudConnection` | 1.5.1–2.0.0_beta |
| `otaPreconditionFailActiveMode` | 1.5.1 |
| `otaPreconditionFailFastCharging` | 1.5.1 |
| `otaPreconditionFailHVBattLow` | 1.5.1 |
| `otaPreconditionFailLVBatt` | 1.5.1 |
| `otaPreconditionFailNotParked` | 1.5.1 |
| `otaPreconditionFailOther` | 1.5.1 |
| `passiveEntryUnlockFailReason` | 3.15.0 |
| `vasAccessCanFaulted` | 3.15.0 |
| `vasSecureElementFaulted` | 3.15.0 |

### charging / wallbox names the vendored schema does not declare

| field | seen |
|---|---|
| `activated` | 1.0.3 |
| `updatedAt` | 1.8.0–2.6.0 |

## Appendix — BLE-only commands

No cloud path in any version, so none is sendable by this integration, which
sends commands via cloud after pairing. Recorded because the ledger is the union
of what the app named, not the subset that is actionable.

| command | versions | n |
|---|---|---|
| `PAUSE_FRUNK` | 1.0.3–2.6.0 | 25 |
| `PAUSE_LIFTGATE` | 1.0.3–2.6.0 | 25 |
| `PAUSE_TONNEAU_COVER` | 1.0.3–2.6.0 | 25 |
| `WINCH_ACCEPT_CONTROLLER_ROLE` | 1.3.0–1.4.1 | 4 |
| `WINCH_CANCEL` | 1.0.3–1.4.1 | 6 |
| `WINCH_FREE_SPOOL` | 1.0.3–1.4.1 | 6 |
| `WINCH_IN` | 1.0.3–1.4.1 | 6 |
| `WINCH_OUT` | 1.0.3–1.4.1 | 6 |
| `WINCH_REENGAGE` | 1.3.0–1.4.1 | 4 |
| `WINCH_REJECT_CONTROLLER_ROLE` | 1.3.0–1.4.1 | 4 |

The winch family ran 1.0.3 – 1.4.1 and was dropped. `PAUSE_*` persisted to 2.6.0,
corroborating `REMAINING_APK_GAPS.md`'s existing row: `cloudData=null`, not cloud
commands.

## Probe queue — a prioritised view over the ledger

Ordered by expected yield. Rows with a recorded live rejection are **held out with
a re-entry condition**, not foreclosed: `REMAINING_APK_GAPS.md` is explicit that a
`CONFLICT` is not a capability failure.

| # | target | kind | expected signal | promotes on |
|---|---|---|---|---|
| 1 | `passiveEntryUnlockFailReason` | name-probe | subscription accepts the name | any live value |
| 2 | `vasAccessCanFaulted` | name-probe | subscription accepts the name | any live value |
| 3 | `vasSecureElementFaulted` | name-probe | subscription accepts the name | any live value |
| 4 | 25 undecoded Parallax RVMs | decode | RVM frames already arriving | a decoded value |
| 5 | `activated`, `updatedAt` (wallbox) | name-probe | schema accepts the name | any live value |

Rows 1–3 are the strongest: they are in the **current** build, so the live gateway
plausibly still serves them. A single unknown name is fatal to an entire
subscription, so probe them one at a time against a scratch document, never by
adding them to `VEHICLE_STATE_API_FIELDS` first.

### Held out, with re-entry conditions

| target | why held | re-entry |
|---|---|---|
| `UNLOCK_ALL_AND_OPEN_WINDOWS`, `UNLOCK_DRIVER_DOOR`, `UNLOCK_PASSENGER_DOOR`, `UNLOCK_USER_PREFERENCES_AND_DISABLE_ALARM` | live-REJECTED `CONFLICT` 2026-08-26 (`COMMAND_COVERAGE.md`) | firmware change, or a materially different vehicle state |
| `HONK_AND_FLASH_LIGHTS` | same class, REJECTED twice | same |
| 7 winch + 3 pause commands | BLE-only in every version; no cloud path exists | a cloud wrapper appearing in a future build |
| 6 `otaPreconditionFail*`, `cloudConnection` | app named them only historically; dropped | reappearance in a current build |

Nothing here is scheduled. A probe is an owner decision, and command sends
actuate a real vehicle.
