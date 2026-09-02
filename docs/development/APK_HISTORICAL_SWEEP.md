# APK historical sweep — the ledger

What every version of `com.rivian.android.consumer` on hand has named, and how
that compares to what this integration exposes. Produced by
`scripts/apk_corpus_sweep.py` over **54 decompiled versions**; gated by
`scripts/gates/s17.sh` and by `TestShippedLedgerIsGuarded` in
`tests/test_apk_corpus_sweep.py`.

**This file is the ledger.** The probe queue at the end is a prioritised *view*
over it, not a second inventory. A name can be fully recorded here and correctly
never be probed.

## What this is not

A decompile enumerates; only the vehicle promotes. Nothing here is evidence that
a command works — `REMAINING_APK_GAPS.md` keeps that rule and this file inherits
it. Equally, absence here is not evidence a name is invalid: **the app is a lower
bound, never the schema.**

## Provenance, and why cohorts matter

54 versions, 1.0.3 through 3.16.0. Three root layouts, and version does not
predict layout:

| cohort | layout | versions | decompiler |
|---|---|---|---|
| A | `sources/` | 19 — all 1.x plus `rivian_2.0.0_beta` | **unrecorded** |
| B | `java_src/` | 6 — 2.2.0 through 2.6.0 | **unrecorded** |
| C | `jadx/sources/` | 29 — 2.6.1 through 3.16.0 | jadx 1.5.6, documented |

Counts compare **only within a cohort**. Which decompiler wrote each A/B tree was
never recorded, so a count that moves between them cannot be attributed to a real
app change rather than a lossier extraction. Cohort C was decompiled here from
APKMirror bundles with one tool version, so its counts *are* comparable to each
other, and 3.15.0 remains its known ground truth (5 documents).

### The Apollo document count is non-monotonic

Measured with one metric (`grep -rl --include='*.java' 'vehicleState(id:'`):

| versions | documents |
|---|---|
| 1.0.3 – 1.4.1 | 0 |
| 1.5.1 – 1.10.0 | 2 |
| 1.11.0 – 2.0.0_beta | 3 |
| 2.2.0 – 2.5.1 | **2** (a decrease) |
| 2.6.0 – 2.6.1 | 3 |
| 2.7.0 – 2.10.1 | **4** |
| 2.19.1 – 3.10.0 | **3** (a decrease) |
| 3.11.0 – 3.16.0 | 5 |

Two corrections are recorded rather than silently applied. An earlier revision
reported 1.15.0 → 4 and rested the non-monotonic claim on it; that count was
wrong (the fourth match was `resources/classes2.dex`, a binary, admitted by an
unfiltered grep). A later revision over-corrected and declared the corpus
non-decreasing from a subsequence. Both were wrong: the corpus rises *and* falls
repeatedly. The cohort rule does not depend on which way it runs — it rests on
attribution, and the real decreases strengthen it.

## The headline: the corpus keeps refuting single-build claims

`REGENERATION.md` records fifteen `vehicleState` fields we subscribe to that
appear in **zero** of 3.15.0's 32,941 files, measured by whole-word grep over
every file. This sweep measures something narrower — depth-1 names in the
compiled documents — so the two are *not* the same metric. They coincide at 15
for 3.15.0, which is what makes the comparison meaningful: holding this sweep's
metric fixed and widening only the corpus,

| measured against | fields we subscribe to that the app never names |
|---|---|
| 3.15.0 alone | 15 |
| 26 versions | 2 |
| **all 54 versions** | **1 — `batteryCapacity`** |

`cabinHoldNotification` turns up in an intermediate build, which fits the
`CABIN_HOLD_*` naming era dated below. A claim that looked solid at one build,
and still looked solid at 26, is down to a single field at 54.

## Commands — the ledger

70 distinct command names. Transport is the union across every version that
named the command.

| command | versions | n | cohorts | transport |
|---|---|---|---|---|
| `ACTIVATE_EXTERNAL_SOUND` | 2.19.1–3.16.0 | 24 | C | cloud |
| `CABIN_HOLD_OFF` **(not in enum)** | 3.3.0 | 1 | C | cloud |
| `CABIN_HOLD_ON` **(not in enum)** | 3.3.0 | 1 | C | cloud |
| `CABIN_HVAC_3RD_ROW_REAR_LEFT_SEAT_HEAT` | 2.10.0–3.16.0 | 26 | C | cloud |
| `CABIN_HVAC_3RD_ROW_REAR_RIGHT_SEAT_HEAT` | 2.10.0–3.16.0 | 26 | C | cloud |
| `CABIN_HVAC_DEFROST_DEFOG` | 1.9.0–3.16.0 | 43 | A, B, C | cloud |
| `CABIN_HVAC_LEFT_SEAT_HEAT` | 1.9.0–3.16.0 | 43 | A, B, C | cloud |
| `CABIN_HVAC_LEFT_SEAT_VENT` | 1.10.0–3.16.0 | 42 | A, B, C | cloud |
| `CABIN_HVAC_REAR_LEFT_SEAT_HEAT` | 1.9.0–3.16.0 | 43 | A, B, C | cloud |
| `CABIN_HVAC_REAR_RIGHT_SEAT_HEAT` | 1.9.0–3.16.0 | 43 | A, B, C | cloud |
| `CABIN_HVAC_RIGHT_SEAT_HEAT` | 1.9.0–3.16.0 | 43 | A, B, C | cloud |
| `CABIN_HVAC_RIGHT_SEAT_VENT` | 1.10.0–3.16.0 | 42 | A, B, C | cloud |
| `CABIN_HVAC_STEERING_HEAT` | 1.9.0–3.16.0 | 43 | A, B, C | cloud |
| `CABIN_PRECONDITIONING_SET_TEMP` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `CHARGING_LIMITS` | 1.8.0–3.16.0 | 44 | A, B, C | cloud |
| `CLIMATE_HOLD_OFF` | 3.4.0–3.16.0 | 17 | C | cloud |
| `CLIMATE_HOLD_ON` | 3.4.0–3.16.0 | 17 | C | cloud |
| `CLOSE_ALL_WINDOWS` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `CLOSE_CHARGE_PORT_DOOR` | 2.19.1–3.16.0 | 24 | C | cloud |
| `CLOSE_FRUNK` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `CLOSE_LIFTGATE` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `CLOSE_TONNEAU_COVER` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `DISABLE_GEAR_GUARD` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `DISABLE_GEAR_GUARD_VIDEO` | 1.8.0–3.16.0 | 44 | A, B, C | cloud |
| `ENABLE_GEAR_GUARD` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `ENABLE_GEAR_GUARD_VIDEO` | 1.8.0–3.16.0 | 44 | A, B, C | cloud |
| `FLASH_EXTERNAL_LIGHTS` | 2.19.1–3.16.0 | 24 | C | cloud |
| `HONK_AND_FLASH_LIGHTS` | 1.0.3–3.4.0 | 38 | A, B, C | cloud+ble |
| `INVALID_COMMAND` **(not in enum)** | 1.5.1–3.16.0 | 48 | A, B, C | cloud |
| `LOCK_ALL_CLOSURES_FEEDBACK` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `OPEN_ALL_WINDOWS` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `OPEN_CHARGE_PORT_DOOR` | 2.19.1–3.16.0 | 24 | C | cloud |
| `OPEN_FRUNK` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `OPEN_LIFTGATE` | 2.10.0–3.16.0 | 26 | C | cloud |
| `OPEN_LIFTGATE_UNLATCH_TAILGATE` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `OPEN_TAILGATE` | 2.10.0–3.16.0 | 26 | C | cloud |
| `OPEN_TONNEAU_COVER` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `OTA_INSTALL_NOW_ACKNOWLEDGE` | 1.2.1–3.16.0 | 53 | A, B, C | cloud+ble |
| `PANIC_OFF` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `PANIC_ON` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `PAUSE_FRUNK` **(not in enum)** | 1.0.3–2.6.1 | 26 | A, B, C | ble-only |
| `PAUSE_LIFTGATE` **(not in enum)** | 1.0.3–2.6.1 | 26 | A, B, C | ble-only |
| `PAUSE_TONNEAU_COVER` **(not in enum)** | 1.0.3–2.6.1 | 26 | A, B, C | ble-only |
| `PET_COMFORT_OFF` | 3.14.0–3.16.0 | 3 | C | invalid-wrapper |
| `PET_COMFORT_ON` | 3.14.0–3.16.0 | 3 | C | invalid-wrapper |
| `RELEASE_LEFT_SIDE_BIN` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `RELEASE_RIGHT_SIDE_BIN` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `START_CHARGING` | 1.8.0–3.16.0 | 44 | A, B, C | cloud |
| `START_GEAR_GUARD_MASTER_SESSION` | 2.10.0–3.16.0 | 26 | C | cloud |
| `START_VIDEO_DOWNLOADING_SESSION` | 3.6.0–3.16.0 | 14 | C | invalid-wrapper |
| `STOP_CHARGING` | 1.8.0–3.16.0 | 44 | A, B, C | cloud |
| `TWO_FACTOR_DRIVE_ALLOW` | 3.1.0–3.16.0 | 20 | C | invalid-wrapper |
| `TWO_FACTOR_DRIVE_DENY` | 3.1.0–3.16.0 | 20 | C | invalid-wrapper |
| `TWO_FACTOR_DRIVE_DISABLE` | 3.7.0–3.16.0 | 12 | C | invalid-wrapper |
| `TWO_FACTOR_DRIVE_ENABLE` | 3.7.0–3.16.0 | 12 | C | invalid-wrapper |
| `UNLOCK_ALL_AND_OPEN_WINDOWS` | 1.5.1–3.4.0 | 32 | A, B, C | cloud+ble |
| `UNLOCK_ALL_CLOSURES` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `UNLOCK_DRIVER_DOOR` | 1.5.1–3.4.0 | 32 | A, B, C | cloud+ble |
| `UNLOCK_PASSENGER_DOOR` | 1.5.1–3.4.0 | 32 | A, B, C | cloud+ble |
| `UNLOCK_USER_PREFERENCES_AND_DISABLE_ALARM` | 1.0.3–3.4.0 | 38 | A, B, C | cloud+ble |
| `VEHICLE_CABIN_PRECONDITION_DISABLE` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `VEHICLE_CABIN_PRECONDITION_ENABLE` | 1.0.3–3.16.0 | 54 | A, B, C | cloud+ble |
| `WAKE_VEHICLE` | 1.0.3–3.16.0 | 54 | A, B, C | cloud |
| `WINCH_ACCEPT_CONTROLLER_ROLE` **(not in enum)** | 1.3.0–1.4.1 | 4 | A | ble-only |
| `WINCH_CANCEL` **(not in enum)** | 1.0.3–1.4.1 | 6 | A | ble-only |
| `WINCH_FREE_SPOOL` **(not in enum)** | 1.0.3–1.4.1 | 6 | A | ble-only |
| `WINCH_IN` **(not in enum)** | 1.0.3–1.4.1 | 6 | A | ble-only |
| `WINCH_OUT` **(not in enum)** | 1.0.3–1.4.1 | 6 | A | ble-only |
| `WINCH_REENGAGE` **(not in enum)** | 1.3.0–1.4.1 | 4 | A | ble-only |
| `WINCH_REJECT_CONTROLLER_ROLE` **(not in enum)** | 1.3.0–1.4.1 | 4 | A | ble-only |

## The command-side result is still negative

The only cloud-sendable name absent from `VehicleCommand` is `INVALID_COMMAND`,
a sentinel class. **Fifty-four versions yielded no new cloud-sendable command to
probe.** Every other app-only command is BLE-only and appears in the appendix.

**A rename, caught in a single build.** `CABIN_HOLD_ON` / `CABIN_HOLD_OFF` exist
in **3.3.0 and nowhere else**; from 3.4.0 onward the app says
`CLIMATE_HOLD_ON` / `CLIMATE_HOLD_OFF`, which is what the enum already carries.
So these are a superseded spelling, not a missing capability — and a
one-version transitional name is invisible to any sampling stride and to 3.15.0
alone. It is likely also why the integration subscribes to a field named
`cabinHoldNotification`.

Two enum members appear in **no version at all**:
`CABIN_HVAC_THIRD_ROW_LEFT_SEAT_HEAT` and `CABIN_HVAC_THIRD_ROW_RIGHT_SEAT_HEAT`.
`rivian_client/const.py` speculated these might belong to an older app; across 54
versions, none has ever named them. They stay — the app is a lower bound.

## Sensor surfaces

| surface | app | ours | app-only | ours-only | floor |
|---|---|---|---|---|---|
| `vehicleState` (depth-1) | 159 | 149 | 11 | 1 | 157 |
| Parallax RVM | 80 | 33 | 47 | 0 | 58 |
| `VehicleFeature` | 98 | 64 | 34 | 0 | 89 |
| charging / wallbox | 52 | 72 | 2 | 22 | 52 |

`vehicleState` uses the depth-1 metric of
`scripts/gates/helpers/apk_vehicle_state_fields.py`, not a union at any depth —
only depth-1 names are comparable to `VEHICLE_STATE_API_FIELDS`. A test pins the
two implementations together so they cannot drift.

**Parallax draws on 24 versions, from 2.19.1 onward** — not 3.x only, as an
earlier revision of this file said. **80 RVM types against 33 decoded.**

### But "47 undecoded" is not 47 decodable things (s33)

A decoder needs a **topic → message class** binding, and the app supplies those in
eleven dispatch files (`scripts/gates/helpers/topic_map.py` reads them). Running
it over 3.15.0:

| | |
|---|---|
| RVM names in the table | 80 |
| topics the dispatch binds | 21 |
| of those, already decoded | **21 — all of them** |
| **bound but not decoded** | **0** |
| named with no binding at all | 59 |

An earlier revision of this row said the queue was **8**. That was wrong, and so
was a later correction to **1**: both compared dotted topic names against
CONST-form names through a transform that silently mismatched
(`comfort.cabin.cabin_preconditioning_status` normalises to
`COMFORT_CABIN_CABIN_PRECONDITIONING_STATUS`, the dispatch says
`COMFORT_CABIN_PRECONDITIONING_STATUS`). `PARALLAX_DECODERS.md:139-166` settles
it from the other direction: the search over every base64-parse site in all
32,941 files is **closed**, and every bound topic is already decoded.

The eight are `OTA_DEPLOYMENT_STATE`, `SECURITY_VAS_FAULT`,
`SECURITY_IMMOBILIZER_STATE`, `DYNAMICS_VEHICLE_KNOWN_LOCATION`,
`BODY_TRAILER_STATES`, `COMFORT_CABIN_PRECONDITIONING_STATUS`,
`SECURITY_PASSIVE_ENTRY_DEBUG` and `SECURITY_BTM_DIAGNOSIS`.

A missing binding is not proof a topic is undecodable — 20 of our 33 decoders
were built from live capture rather than the dispatch. It does mean those 59 cost
a vehicle capture each rather than a read of the decompilation.

**Capture does not require an outage.** An earlier revision of this file said the
gateway permits one active subscription per user session and that capture
therefore needs the Home Assistant config entry disabled. That claim was
**RETRACTED on 2026-08-20** after measurement (`RVM_FIXTURES.md:21-29`,
`WS_CONTENTION.md` claim C8): a second connection received `connection_ack` in
0.0 s with production up, and the full topic set arrived with production
subscribed. Repeating it here told a maintainer to take a production outage
nobody needs, which is worse than a wrong count.

Capture instead runs against the live instance —
`scripts/capture_rvm_frames.py`. A survey on 2026-09-01 subscribed to all 80
topics for 180 s parked: **51 published a non-empty frame, 5 published an empty
payload, 24 were silent.** Silence is a recorded outcome, not a failure.

So the honest shape of this gap: 8 topics readable from the decompilation but
still needing a frame to confirm their value vocabulary, and 59 that need a frame
before anything can be read at all. Picking targets by reading topic names is
guessing — the dispatch is the evidence, and it disagreed with four of five names
chosen that way.

Each surface carries its own floor; a union below it is an error and exits 1.

### `vehicleState` fields the app names and we do not

| field | seen |
|---|---|
| `chargingDisabledAC` | 2.7.0–2.10.1 |
| `cloudConnection` | 1.5.1–2.0.0_beta |
| `otaPreconditionFailActiveMode` | 1.5.1 |
| `otaPreconditionFailFastCharging` | 1.5.1 |
| `otaPreconditionFailHVBattLow` | 1.5.1 |
| `otaPreconditionFailLVBatt` | 1.5.1 |
| `otaPreconditionFailNotParked` | 1.5.1 |
| `otaPreconditionFailOther` | 1.5.1 |
| `passiveEntryUnlockFailReason` | 3.7.0–3.16.0 |
| `vasAccessCanFaulted` | 3.8.0–3.16.0 |
| `vasSecureElementFaulted` | 3.8.0–3.16.0 |

### charging / wallbox names the vendored schema does not declare

| field | seen |
|---|---|
| `activated` | 1.0.3 |
| `updatedAt` | 1.8.0–2.19.1 |

## Appendix — BLE-only commands

No cloud path in any version, so none is sendable by this integration, which
sends via cloud after pairing.

| command | versions | n |
|---|---|---|
| `PAUSE_FRUNK` | 1.0.3–2.6.1 | 26 |
| `PAUSE_LIFTGATE` | 1.0.3–2.6.1 | 26 |
| `PAUSE_TONNEAU_COVER` | 1.0.3–2.6.1 | 26 |
| `WINCH_ACCEPT_CONTROLLER_ROLE` | 1.3.0–1.4.1 | 4 |
| `WINCH_CANCEL` | 1.0.3–1.4.1 | 6 |
| `WINCH_FREE_SPOOL` | 1.0.3–1.4.1 | 6 |
| `WINCH_IN` | 1.0.3–1.4.1 | 6 |
| `WINCH_OUT` | 1.0.3–1.4.1 | 6 |
| `WINCH_REENGAGE` | 1.3.0–1.4.1 | 4 |
| `WINCH_REJECT_CONTROLLER_ROLE` | 1.3.0–1.4.1 | 4 |

## Probe queue — a prioritised view over the ledger

Rows with a recorded live rejection are **held out with a re-entry condition**,
not foreclosed: `REMAINING_APK_GAPS.md` is explicit that a `CONFLICT` is not a
capability failure.

### Probed and accepted, 2026-08-31

All three current-build candidates were live-ACCEPTED with real values, which is
what promoted them in the catalog. Details in `COMMAND_COVERAGE.md`.

| field | result |
|---|---|
| `passiveEntryUnlockFailReason` | ACCEPTED, delivered `AT_HOME_DISABLE` |
| `vasAccessCanFaulted` | ACCEPTED, delivered `no_failure` |
| `vasSecureElementFaulted` | ACCEPTED, delivered `no_failure` |

Their value vocabularies are one sample from one R1T: `no_failure` is the healthy
arm of a fault enum whose other arms are unobserved, so a sensor mapping only
seen values would mis-render every unseen state.

### Next candidates

| # | target | kind | promotes on |
|---|---|---|---|
| 1 | `chargingDisabledAC` | name-probe | now corpus-confirmed as a real app name; a live accept |
| 2 | 6 Parallax RVMs with a named `.proto` schema | decode | the schema is already in `rivian_client/proto/*.proto`, bound by `// RVM:` comment, and a captured frame confirms the vocabulary. No outage needed. |
| 3 | `activated`, `updatedAt` (wallbox) | name-probe | a live accept |
| 4 | 34 `VehicleFeature` members we do not gate on | inspect | evidence the server emits the `featureName` |

Historical-only names (`cloudConnection`, the six `otaPreconditionFail*`) are
recorded but not queued: the app dropped them, so a probe tests nothing current.

## Corpus gaps

APKMirror lists 30 versions and carries nothing older than 2.5.1. `3.2.x`,
`2.9`, and `2.11`–`2.18` are absent from every source checked, so the ledger has
real holes. A name first appearing at, say, 2.19.1 may have arrived any time
after 2.10.1 — the windows above are bounds, not birthdates.
