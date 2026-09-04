# Vehicle commands: what ships, what does not, and why

## The rule

**A command is kept unless a live test failed.** Absence from the current app is
not evidence of absence — `OPEN_TONNEAU_COVER` and `CLOSE_TONNEAU_COVER` appear in
zero of the app's 32,941 decompiled files and both physically move the tonneau
cover on the owner's R1T.

## Every sendable command the app declares is now in the enum

`VASCommand` has 57 subclasses. 46 build their `cloudData` through
`generateCloudDataWrapper`; one of those is the `INVALID_COMMAND` sentinel, so
**45 are sendable**. All 45 are in `VehicleCommand`, asserted in
`tests/test_apk_transcription.py`.

f2 added `CABIN_HVAC_3RD_ROW_REAR_{LEFT,RIGHT}_SEAT_HEAT`; f6 added
`OPEN_LIFTGATE`, `OPEN_TAILGATE` and `START_GEAR_GUARD_MASTER_SESSION`.

## In the enum but deliberately not wired to an entity

HA-shaped remaining-gap dispositions live in [`REMAINING_APK_GAPS.md`](REMAINING_APK_GAPS.md). This table remains the probe record.

| Command | Why |
|---|---|
| `OPEN_LIFTGATE` | Wired as `button.open_liftgate`, **disabled by default** — it moves a closure and has not been actuated (f7) |
| `OPEN_TAILGATE` | Wired as `button.open_tailgate`, **disabled by default**, same reason |
| `CABIN_HVAC_THIRD_ROW_*` | **ANSWERED by f7, 2026-08-19: REJECTED** (`CONFLICT/VEHICLE_COMMAND_ERROR`) on an R1T with `params={"level": 0}` |
| `CABIN_HVAC_3RD_ROW_REAR_*` | **ANSWERED by f7, 2026-08-19: ACCEPTED**, terminal in ~1.5 s, same params, same truck, seconds apart |
| `HONK_AND_FLASH_LIGHTS` | **ANSWERED by f7, 2026-08-22: REJECTED** (`CONFLICT/VEHICLE_COMMAND_ERROR`), same R1T. See "f7 results, 2026-08-22" below -- this one is NOT one of the seven `generateInvalidCloudDataWrapper` commands, so the "wrong envelope" theory below does not cover it |

The two closure-openers ship `entity_registry_enabled_default=False`. Shipping an
untested opener enabled puts it one tap away.

## START_GEAR_GUARD_MASTER_SESSION (wired s28)

Wired as `camera.gear_guard_live`. The app's live-view path, not a control
button: VAS `START_GEAR_GUARD_MASTER_SESSION` with `params.camera` (APK
default `"left"`), subscribe `gearGuardLiveConfig`, then Amazon KVS WebRTC
signaling as `role=viewer`. Tear-down is local; there is no stop VASCommand.
Clip download (`START_VIDEO_DOWNLOADING_SESSION`) is a different path and
stays unwired.

**Live measurement gate, 2026-08-26, 2022 R1T …002984, `camera=left`:**

- Gateway accepted (`command_id` `04-38b7b303ee1d25fc0830`).
- `vehicleCommandState` 2 → 3 → 0, `responseCode` 490.
- **GATE PASS:** `gearGuardLiveConfig` arrived with `endpoint` (host
  `kinesisvideo.us-east-1.amazonaws.com`), `channelArn` present,
  `role=viewer`, 3 `iceServers`, credentials present.
- Secrets are not recorded: no full endpoint URL, no `channelArn` value, no
  ICE username/credential.

Same day, send **without** `params.camera`: terminal state 4 / `responseCode`
1031, no live-config frame. The camera param is required.

## The seven built with `generateInvalidCloudDataWrapper`

| Command | Class:line |
|---|---|
| `PET_COMFORT_OFF` | `VASCommand.java:476` |
| `PET_COMFORT_ON` | `VASCommand.java:562` |
| `START_VIDEO_DOWNLOADING_SESSION` | `VASCommand.java:1409` |
| `TWO_FACTOR_DRIVE_ALLOW` | `VASCommand.java:1484` |
| `TWO_FACTOR_DRIVE_DENY` | `VASCommand.java:1500` |
| `TWO_FACTOR_DRIVE_DISABLE` | `VASCommand.java:1516` |
| `TWO_FACTOR_DRIVE_ENABLE` | `VASCommand.java:1539` |

`generateInvalidCloudDataWrapper` passes `appName=""`, where
`generateCloudDataWrapper` defaults it to `rshell` (the literal appears **once**
in the whole app, so do not grep for it). These are also `isParallaxRequestOnly`.

**SUPERSEDED (2026-08-19): provenance, `isParallaxRequestOnly`, and the `appName=""` half.**

The seven-command table above was measured against the **3.15.0 pre-flight artifact**
`docs/development/apk/VASCommand.java`, and reproduces there today at the exact lines cited
(`:476`, `:562`, `:1409`, `:1484`, `:1500`, `:1516`, `:1539`).

The 18/6/0/8/91 counts in "How the app reads a command's result" were measured against the
**3.6.0** tree (versionCode 3989, 31,097 `.java` files), re-reproduced 2026-08-19. They are a
different extraction.

`:47`'s "These are also `isParallaxRequestOnly`" is **wrong**. `isParallaxRequestOnly` is true only for `TWO_FACTOR_DRIVE_ENABLE` and `TWO_FACTOR_DRIVE_DISABLE` (`VASCommandKt.java:117-119`). The predicate does not mention the other five.

The `appName=""` half of the claim does not survive either. The two wrappers differ in
`appName` alone — `"rshell"` by default (`VASCommand.java:157-165`) versus `""` — and
`send_vehicle_command` (`rivian.py:596-609`) sends no `appName` field at all. The
invalid-wrapper grouping is a real property *of the app*; it is not a property our client's
requests can express, so it does not explain the f7 rejections.

**Not wired blind, and not declared dead.** This is an *app-side routing* choice —
a weaker signal than absence from the server's own `supportedFeatures`, which the
tonneau already falsified. Each needs testing the way the tonneau was tested:
send it, read `vehicleCommandState`, observe the vehicle. That moves the vehicle,
so it is **f7's** work, not something to decide from the decompilation.

Seven, not eight. An earlier extraction bounded each subclass at the next
`extends VASCommand`, which swallowed the `Companion` class whose body *defines*
`generateInvalidCloudDataWrapper`, and so misread `CloseTonneauCover` — one of the
two live-proven tonneau commands — as invalid-wrapped.

## The seven commands this integration sends that app 3.15.0 does not name

```
CABIN_HVAC_THIRD_ROW_LEFT_SEAT_HEAT     UNLOCK_ALL_AND_OPEN_WINDOWS
CABIN_HVAC_THIRD_ROW_RIGHT_SEAT_HEAT    UNLOCK_DRIVER_DOOR
HONK_AND_FLASH_LIGHTS                   UNLOCK_PASSENGER_DOOR
                                        UNLOCK_USER_PREFERENCES_AND_DISABLE_ALARM
```

**Kept, and not deprecated.** The app ships one version; features get added and
removed, and the server accepts more than the current app asks for — measured
three separate ways now:

1. the tonneau commands, in no file, physically move the cover;
2. fifteen `vehicleState` fields we subscribe to are in no file, and three carry
   live data;
3. the server emits **seven** `supportedFeatures` names app 3.15.0 declares no
   member for.

Stamping a dated "deprecated" note on these would write false provenance and
defeat the next person's instinct to re-check. Removal requires a recorded live
failure.

**Unlock-family live probes, 2026-08-26 ~11:53 UTC** (power Ready, Park, closures
locked, windows closed; `OPEN_TAILGATE` not sent). Same session style as the
cheap-candidate run: HMAC working — other commands on this account accept.

| Command | Result | Restore |
|---|---|---|
| `UNLOCK_DRIVER_DOOR` | **REJECTED** `CONFLICT/VEHICLE_COMMAND_ERROR` (no command id, 0.77 s) | not needed |
| `UNLOCK_PASSENGER_DOOR` | **REJECTED** same (0.63 s) | not needed |
| `UNLOCK_USER_PREFERENCES_AND_DISABLE_ALARM` | **REJECTED** same (0.79 s) | not needed |
| `UNLOCK_ALL_AND_OPEN_WINDOWS` | **REJECTED** same (0.72 s) | not needed |

Post-run: lock still locked, windows still closed, alarm switch still off.
No lock restore ran because nothing unlocked. Same class as
`HONK_AND_FLASH_LIGHTS` (also APK-absent, also CONFLICT). Kept in the enum.
Tonneau's "absence from the app is not evidence of absence" still holds for
those two; it does not make these four sendable on this VAS path.


## f7 results, 2026-08-19 (beta6)

**The third-row spelling question is settled.** `CABIN_HVAC_3RD_ROW_REAR_LEFT/RIGHT_SEAT_HEAT` are
accepted; `CABIN_HVAC_THIRD_ROW_LEFT/RIGHT_SEAT_HEAT` are rejected. One variable: identical
`params={"level": 0}`, same vehicle, seconds apart. Sending them without `level` is uninterpretable —
`_validate_vehicle_command` (`rivian.py:524-548`) omits all four third-row spellings from its
`level`-requiring list while the `send_vehicle_command` docstring (`:576`) says `CABIN_HVAC_*` needs
one, so nothing raises locally and a rejection cannot be told from a missing parameter.

**All seven `generateInvalidCloudDataWrapper` commands were rejected identically**
(`CONFLICT/VEHICLE_COMMAND_ERROR`), including `PET_COMFORT_ON`/`OFF`, which a healthy vehicle should
accept. Ordinary commands were accepted on the same credentials minutes earlier. That uniformity is
consistent with the ordinary cloud VAS path being the **wrong envelope** for a family the app builds
with `appName=""` and marks `isParallaxRequestOnly` — a transport result, not a capability one.
**Nothing is removed on this evidence** (Principle -1): a rejection through a possibly-wrong
transport is not a recorded live failure of the command.

**`OPEN_TAILGATE` was not sent.** Owner prohibition, 2026-08-19: the vehicle is parked where the
tailgate strikes the garage. Disposition `not-sent-owner-prohibited-physical-hazard`, distinct from
`not-run`. `OPEN_LIFTGATE` was sent and accepted (terminal 2.77 s); on an R1T it moves nothing, so
this proves the send path and not a physical effect — which is why it was the cheapest candidate in
the pool and why excluding it would have left `button.open_liftgate`'s "has not been actuated (f7)"
justification permanently unresolvable.

## f7 results, 2026-08-22

`s19` set out to wire `HONK_AND_FLASH_LIGHTS` (button) and `PET_COMFORT_ON`/`OFF`
(switch) ungated, on the tonneau precedent: absence from `supportedFeatures` and
absence of a backing state field are not evidence a capability is absent. Both
were probed with `scripts/probe_vehicle_command.py` before either was wired past
review, on the same R1T as the 2026-08-19 run:

| Command | Result |
|---|---|
| `WAKE_VEHICLE` (control) | **ACCEPTED** — command id returned, polled to a terminal state normally |
| `PET_COMFORT_ON` | **REJECTED** (`CONFLICT/VEHICLE_COMMAND_ERROR`) — reproduces the 2026-08-19 result above |
| `HONK_AND_FLASH_LIGHTS` | **REJECTED** (`CONFLICT/VEHICLE_COMMAND_ERROR`) |
| `HONK_AND_FLASH_LIGHTS`, retried immediately after `WAKE_VEHICLE` succeeded | **REJECTED** again |

The `WAKE_VEHICLE` control run is what makes this conclusive rather than
ambiguous: credentials, HMAC signing and the session were all working seconds
apart from the two rejections, so both are **command-specific** refusals, not an
environmental or auth failure. The retry after a successful wake also rules out
"vehicle was asleep, not in a state to accept a command" as the explanation for
`HONK_AND_FLASH_LIGHTS`.

**This is a new data point, not a rerun of 2026-08-19's.** `PET_COMFORT_ON` is
one of the seven `generateInvalidCloudDataWrapper` commands above, so its
rejection was already explainable by the "wrong envelope" theory (`appName=""`,
`isParallaxRequestOnly`, possibly needing the Parallax path instead of ordinary
VAS). `HONK_AND_FLASH_LIGHTS` is **not** one of the seven, and it is genuinely
absent from `VAS_COMMANDS` — the app's own 57-entry cloud-command table
(`tests/apk/transcription.py`) has no entry for it. **Its only occurrences
anywhere in the decompile are `case HONK_AND_FLASH_LIGHTS_VALUE:` switch
labels** handling a protobuf enum value (`com.rivian.android.consumer/java_src/p950p5/C18463s.java:123`,
among many others across the tree, including ones in generic
library/protobuf switches unrelated to Rivian at all) — siblings in those
switches are ordinary status codes, not evidence of a cloud-command path. An
earlier revision of this section claimed it "builds its `cloudData` through
the ordinary `generateCloudDataWrapper`, the same wrapper `WAKE_VEHICLE`
uses" — that claim was **unsourced** and does not hold up: nothing in the
decompile ties `HONK_AND_FLASH_LIGHTS` to `generateCloudDataWrapper`,
`cloudData`, or any `VASCommand` subclass at all. **There is no evidence
anywhere in the decompile that the app sends `HONK_AND_FLASH_LIGHTS` as a
cloud command.**

**So absence from `VAS_COMMANDS` *was* the correct signal here — this is
narrower than "offline signals failed to predict the refusal."** The prior
framing (enum presence + app presence + ordinary wrapper, refused anyway)
mistook enum-membership and decompile-presence for evidence of sendability,
when the one signal that actually mattered — presence in `VAS_COMMANDS` — was
never checked. That keeps the tonneau precedent intact on its own axis:
"absence from `supportedFeatures` is not evidence a capability is absent"
remains true, and does not run in reverse here either, since the refusal is
explained by a real, checkable absence (`VAS_COMMANDS`), not by enum/app
presence turning out to be worthless. `button.honk_and_flash` (commit
`5059674`) was reverted (commit `e803e49`) on the live-probe evidence rather
than shipped disabled, since there is no live path by which it would ever
work for anyone — unlike `OPEN_LIFTGATE`/`OPEN_TAILGATE`, which are accepted
and simply unactuated.

`PET_COMFORT_ON`/`OFF` remain unwired, per the existing seven-command rule
above and `tests/test_apk_transcription.py`'s `INVALID_WRAPPER_COMMANDS` guard
tests — now with a second, independent rejection on file.

**State is not the same as control.** `pet_mode_temperature_status`
(`custom_components/rivian/const.py:692`) and `pet_mode_status` (`:699`) already
exist as sensors, so pet comfort *state* is surfaced regardless of this result.
What remains unavailable is the *write* side, not visibility into the feature.

## `ACTIVATE_EXTERNAL_SOUND` and `FLASH_EXTERNAL_LIGHTS` — gateway accept, 2026-08-22

> **Superseded for flash.** This section proved gateway acceptance and nothing
> about the vehicle. The 2026-08-30/31 probe below shows `FLASH_EXTERNAL_LIGHTS`
> is physically inert, and the cause is a feature gate the app evaluates before
> it ever offers the button. Read that section before treating a gateway accept
> in this one as evidence a command works.

Both are real `VAS_COMMANDS` entries for the same physical function
(`HonkHorn`/`FlashLights` in `VASCommand.java`), unlike `HONK_AND_FLASH_LIGHTS`
above. Probed live against the same R1T with `scripts/probe_vehicle_command.py`
in the same session as the `WAKE_VEHICLE` control run documented above, so the
same credentials/HMAC/session-soundness argument covers these too. Raw results:

```
FLASH_EXTERNAL_LIGHTS
  command id 04-7bc33137ecb7c043cf9b   createdAt 2026-08-22T15:49:36.779249
  state 3 at t+8.95s and t+9.66s -- still in flight when polling ended
  NO TERMINAL STATE after 9.66s
  no CONFLICT: the sendVehicleCommand mutation was accepted

ACTIVATE_EXTERNAL_SOUND
  command id 04-c50e5dd82c31611c004a   createdAt 2026-08-22T15:49:49.378817
  state 3 at t+2.81s, then state 0 / responseCode 412 / statusCode 0 at t+3.52s
  TERMINAL after 3.52s from send
  no CONFLICT: accepted by the gateway, then declined by the vehicle
```

Both **accepted** by the gateway (a command id was returned in both cases).
Compare against `HONK_AND_FLASH_LIGHTS`/`PET_COMFORT_ON`'s refusals above,
which never got a command id at all — they raised `RivianApiException` with
`{'code': 'CONFLICT', 'reason': 'VEHICLE_COMMAND_ERROR'}` from the
`sendVehicleCommand` mutation itself.

**The distinction that must survive**: `ACTIVATE_EXTERNAL_SOUND`'s
`responseCode 412` is a **vehicle-level decline after gateway acceptance** —
categorically different from `CONFLICT`, which is a **gateway refusal** before
the command ever reaches the vehicle. Conflating the two would flatten this
finding into "everything fails," which is not what happened here: the gateway
accepted both, and the vehicle either kept acting on one (`FLASH_EXTERNAL_LIGHTS`,
still in flight when polling ended) or explicitly declined the other after
acceptance (`ACTIVATE_EXTERNAL_SOUND`, `412`).

**What is verified**: both are accepted by the gateway, on the same
credentials and session that also verified `HONK_AND_FLASH_LIGHTS`'s refusal
as command-specific. **What is not verified**: that these two explain
`HONK_AND_FLASH_LIGHTS`'s refusal, or that any succession or retirement
occurred between it and this pair — consistent with that reading, not
evidence for it.

## Cheap-candidate probes, 2026-08-26 ~11:18 UTC

Sent with `scripts/probe_vehicle_command.py` against this 2022 R1T (`…002984`).
Pre-flight (HA entities via supervisor core socket): `powerState` Sleep,
`gearGuardLocked` unlocked, climate-hold switch off / status Available, Park,
closures locked. `WAKE_VEHICLE` first as a control (command id `04-4d83cdd16f8b8b23d10c`,
state 5 / continue, no terminal in 11.18 s). HMAC/session were working: the
climate-hold pair and `START_GEAR_GUARD_MASTER_SESSION` returned command ids
on the same credentials seconds around the Gear Guard lock refusals.

| Command | Result |
|---|---|
| `WAKE_VEHICLE` (control) | **ACCEPTED** — command id, state 5 (continue), no terminal in 11 s |
| `CLIMATE_HOLD_ON` | **ACCEPTED** by gateway; terminal state **0** / `responseCode` **417** / `statusCode` 0 at t+8.97 s |
| `CLIMATE_HOLD_OFF` | **ACCEPTED** by gateway; terminal state **0** / `responseCode` **417** / `statusCode` 0 at t+9.28 s |
| `DISABLE_GEAR_GUARD` | **REJECTED** `CONFLICT/VEHICLE_COMMAND_ERROR` — no command id. Retried after `ENABLE` rejected the same way |
| `ENABLE_GEAR_GUARD` | **REJECTED** `CONFLICT/VEHICLE_COMMAND_ERROR` — no command id |
| `START_GEAR_GUARD_MASTER_SESSION` | **ACCEPTED** by gateway (id `04-9adefad40f5ff1e78f74`); terminal **state 4** / `responseCode` **1031** at t+4.37 s |

Post-run HA: power Ready; climate-hold still off / Available; Gear Guard still
unlocked. No closure moved. `417` and `1031` are recorded as integers; the
decompile artifacts under `docs/development/apk/` do not name them.

**Climate-hold VAS is the same class as `ACTIVATE_EXTERNAL_SOUND`:** gateway
accept, then a vehicle-level decline. The working write remains Parallax
(`switch.py:69-93`). Hold state did not change. Already-at-parity stays.

**Gear Guard lock is the same class as `HONK_AND_FLASH_LIGHTS` / `PET_COMFORT_ON`:**
gateway `CONFLICT` with no command id, on a session that accepted other commands
seconds apart. Video (`ENABLE_GEAR_GUARD_VIDEO`) stays the wired path. Catalog:
listed-not-built until a live accept — Principle -1, a VAS CONFLICT is not a
capability failure.

**`START_GEAR_GUARD_MASTER_SESSION` is a real cloud command**, and s28 went on to
wire it as `camera.gear_guard_live` — see
[`## START_GEAR_GUARD_MASTER_SESSION (wired s28)`](#start_gear_guard_master_session-wired-s28)
above. State 4 is terminal (`{0,4,6,7}`).

This run is the negative control for that section's claim that `params.camera` is
required, and it is worth keeping for exactly that reason. It sent **no**
`params.camera` and got state 4 / `1031` with no live-config frame; the s28 gate
run sent `camera=left` and got a full `gearGuardLiveConfig`. Two runs, one
variable, opposite outcomes — which makes "the camera param is required" a
measurement rather than an inference.

**`FLASH_EXTERNAL_LIGHTS` reproduced 2026-08-26 ~11:26 UTC** (power Ready, same
credentials as the table above). Command id `04-678b1c2506540fd2bdee`, send ack
0.69 s, state 2 then 3 (continue set). **No terminal state in 26.35 s**, same
shape as 2026-08-22 (then in-flight at 9.66 s). Gateway accept is confirmed a
second time. Vehicle decline (`412`) did **not** appear. Candidate-to-build.

## `FLASH_EXTERNAL_LIGHTS` — accepted by the gateway, does NOTHING. 2026-08-30/31

Three sends with `scripts/probe_vehicle_command.py` against this 2022 R1T
(`…002984`), to close the gap the 2026-08-22 run above left open: that run
polled for 9.66 s, never saw a terminal state, and so proved gateway acceptance
and nothing about the vehicle.

```
WAKE_VEHICLE  (control)
  command id 04-59cc1368182a329b305c   sent 2026-08-30T16:24:01Z
  state 0 at t+2.06s -- TERMINAL, responseCode None

FLASH_EXTERNAL_LIGHTS  (run 1, --poll 60)
  command id 04-25b8ac71fe5527dfafeb   sent 2026-08-30T16:24:14Z
  state 3 from t+22.76s through t+52.32s, unchanged
  NO TERMINAL STATE after 52.32s   responseCode/statusCode None throughout

FLASH_EXTERNAL_LIGHTS  (run 2, --poll 24)
  command id 04-1854b1429bef4a5d5d18   sent 2026-08-30T16:26:52Z  (ack 0.82s)
  state 2 at t+1.64s, state 3 from t+3.29s     NO TERMINAL STATE

FLASH_EXTERNAL_LIGHTS  (run 3, --poll 30, AFTER DARK, owner watching)
  command id 04-c18b4a8053448cc7aff9   sent 2026-08-31T04:18:39Z  (ack 1.03s)
  state 2 at t+1.85s, state 3 from t+2.80s     NO TERMINAL STATE
  OBSERVED VEHICLE BEHAVIOUR: none. The lights did not flash.
```

**The finding: the gateway accepts this command and the vehicle does nothing.**
Run 3 was watched by the owner after dark, the condition under which a brief
exterior flash is unmistakable. Nothing happened.

Four things make that a measurement rather than a guess:

1. **Not asleep.** The `WAKE_VEHICLE` control went terminal in 2.06 s, thirteen
   seconds before the first send. Terminal states do come back on this session,
   on this HMAC material.
2. **Not a polling-window artefact.** Run 1 held `state 3` for 52.32 s — 5.4x
   the 2026-08-22 window — and never moved.
3. **Not dropped on arrival.** Runs 2 and 3 both caught `state 2` before
   `state 3`. The command advances through the pipeline and parks. Both values
   are in `COMMAND_STATE_CONTINUE` (`tests/apk/transcription.py:950`), so the
   app itself would still be waiting.
4. **Not a visibility failure.** Two earlier attempts were inconclusive because
   the owner could not see the truck; run 3 was not.

**This is a third failure mode, distinct from the two the 2026-08-22 section
draws.** That section's whole point was separating a gateway `CONFLICT` (refused
before reaching the vehicle) from a vehicle-level `412` (accepted, then
declined). `FLASH_EXTERNAL_LIGHTS` is neither: accepted by the gateway, never
refused by anything, never terminal, and physically inert. There is no
responseCode to read because no terminal state ever arrives.

**Consequence for `ACTIVATE_EXTERNAL_SOUND`.** It shares this section's
2026-08-22 heading and remains catalogued beside flash as a candidate, on the
strength of the same gateway acceptance. Its `412` was at least a *vehicle*
answer. Flash's result removes the reason to read either row's gateway
acceptance as evidence a button would work — do not build the horn button on
that basis without probing it the same way, after dark, with someone watching.

**Disposition: no `button` entity is wired.** This integration does not ship a
control whose effect is unobserved, and this one's effect has now been observed
to be nothing. See [`REMAINING_APK_GAPS.md`](REMAINING_APK_GAPS.md).

### Why it is inert: the app gates the button on a conjunction, and nothing we can see passes it

The measurement above says the command does nothing. The decompilation says why,
and it is not a per-vehicle fault.

**The gate is an AND, proven in the app's own evaluator.**
`.apk/3.16.0/jadx/sources/defpackage/rn8.java:8` binds the rollout flag
`wr7.HONK_AND_FLASH` to `VehicleFeature.HONK_AND_FLASH_COMMAND`. `as7.java:16-37`
evaluates that pair: `a()` returns false unless **every** `wr7` rollout flag on
the descriptor is enabled, and `b()` returns false unless `a()` passes **and**
the `VehicleFeature` check (`uhc.a.J(...)`) passes. Both must hold.
`mdm.java:88` consumes the result and picks between `is7.LOCATION_MICRO_APP` and
a constant named `is7.LOCATION_MICRO_APP_HONK_FLASH_NOT_AVAILABLE` — the app
ships a dedicated not-available arm for exactly this gate.

**The two flags have very different histories** (swept across all 54 corpus
versions, 2026-09-03):

| flag | kind | first appears | span |
|---|---|---|---|
| `honkAndFlash` (`wr7.java:31`) | app-side rollout | `1.5.1` | continuous to `3.16.0` |
| `HONK_AND_FLASH_COMMAND` (`VehicleFeature.java:51`) | vehicle capability | `2.19.1` | all 24 versions to `3.16.0` |

The vehicle flag arrives with the command itself —
[`APK_HISTORICAL_SWEEP.md`](APK_HISTORICAL_SWEEP.md) records
`FLASH_EXTERNAL_LIGHTS` spanning `2.19.1–3.16.0` across the same 24 versions, and
the sweep reproduces that span from a different query. Note the corpus jumps
`2.10.1 → 2.19.1`, so `2.19.1` is where the flag **first appears in the corpus**,
not necessarily where it was introduced.

**No vehicle we can see carries the vehicle flag.** Not this 2022 R1T
(55 features, `tests/fixtures/supported_features_observed.json`), and none of the
three community captures: `issue-171.json` (R1T, 2024-08-08), `issue-222.json`
(2024 R1S, 2025-08-26), `issue-245.json` (2023 R1S, 2026-03-09) —
[`PROVENANCE.md`](../../tests/fixtures/community/PROVENANCE.md), zero hits each.

**Two of those four absences are load-bearing; two are not.** The corpus cannot
date its own versions — every `base.apk` zip entry normalises to `1981-01-01` —
so `issue-171` and `issue-222` cannot be placed against `2.19.1` and are **not**
counted as evidence here. What remains is `issue-245` (2026-03-09, comfortably in
the 3.x era) and this truck's own current list. **Two confirmed post-flag
absences, not four.**

**So this is a third failure mode.** A gateway `CONFLICT` is a refusal before the
vehicle. A vehicle-level `412` is an acceptance then a decline. This is neither:
the gateway accepts because it validates session and HMAC, not capability; the
vehicle never actuates; no terminal state ever arrives. The app would not have
offered the button either.

**What this does NOT establish.** These flags gate the app's UI. Nothing in the
tree shows the VAS command path itself consulting them, so a firmware-side
explanation for the inertness is not excluded. And an absent flag is not proof of
an absent capability — `coordinator.py:916` records `TONNEAU_CMD` appearing in no
vehicle's `supportedFeatures` while both tonneau commands physically move the
cover, and `helpers.py:30-42` records this same R1T advertising none of
`LIFTGATE_CMD`, `FRUNK_NXT_ACT` or `HEATED_SEATS` while all three work. Per-VIN
exclusion is **unproven**; "not rolled out to anything we can observe" is what the
evidence supports.

## How the app reads a command's result — it SUBSCRIBES, it does not poll

Read off the decompilation, 2026-08-19, because `ae06ee9` added a poll on the belief that the
subscription never delivers and that belief turned out to be false.

| Field | Files in `com.rivian.android.consumer` |
|---|---|
| `vehicleCommandState` — the SUBSCRIPTION field | **18** |
| `GetVehicleCommandState` — the payload `__typename` | 6 |
| `getVehicleCommand` — the QUERY field our poll uses | **0** |

Method validated against fields the app is known to use: `sendVehicleCommand` 8 files,
`vehicleState` 219, `currentUser` 91. The grep finds real operation field names, so a zero is
meaningful rather than an artefact.

**The app never polls for a command result.** `getVehicleCommand` is a real server-side query — our
poll works, and it answers 0.7-1.1 s sooner than the subscription frame — but it appears nowhere in
the app. The polling in `coordinator._poll_command_state` is ours, added in `ae06ee9` on the premise
that the subscription "never delivers". Measured three times on beta7, the subscription delivers
every time (`docs/E2E_ACCEPTANCE.md`, "The command-state subscription DOES deliver").

So the honest position is: the app's design is subscription-only, our subscription works, and the
poll is a redundant fallback that happens to be marginally faster. Whether to keep it is a real
trade-off — fidelity to the app and one fewer query per command, against ~1 s of perceived latency
and a fallback if the subscription ever regresses to the behaviour `ae06ee9` believed it had. Not
decided here; it is a live-command-path change and belongs behind its own gate.

## Name-probes, 2026-08-31 — the three s32 corpus candidates, all ACCEPTED

`docs/development/APK_HISTORICAL_SWEEP.md` found three `vehicleState` names in
3.15.0's compiled documents that `VEHICLE_STATE_API_FIELDS` does not carry. A
decompile does not promote a row, so they were probed.

`scripts/probe_field_names.py`, read-only: subscriptions only, no command sent
and nothing actuated. Each candidate rode **alone** with the two known-good
control fields rather than being added to the live document — the server rejects
the entire document on one unknown name, so a shared probe cannot say which name
killed it, and an unproven name inside `VEHICLE_STATE_API_FIELDS` would take out
every sensor at once instead of one probe. Control ran first and was accepted, so
the instrument was valid before any candidate was judged by it.

| Field | Result | Value observed |
|---|---|---|
| `passiveEntryUnlockFailReason` | **ACCEPTED**, delivered (0.2 s) | `AT_HOME_DISABLE` |
| `vasAccessCanFaulted` | **ACCEPTED**, delivered (0.4 s) | `no_failure` |
| `vasSecureElementFaulted` | **ACCEPTED**, delivered (0.3 s) | `no_failure` |

Three for three, each carrying a real value rather than an accepted silence. The
gateway knows all three names on this account today, which is what promotes them
in [`REMAINING_APK_GAPS.md`](REMAINING_APK_GAPS.md) from "unproven GraphQL name"
to candidate-to-build.

Two cautions before anything ships. The value vocabularies here are one sample
from one R1T at one moment: `no_failure` is plainly the healthy arm of a fault
enum whose other arms are unobserved, and `AT_HOME_DISABLE` is one of an unknown
number of passive-entry reasons. Building a sensor that maps only these values
would mis-render every state that has not been seen yet. And an accept on this
account is not an accept on every account — `supportedFeatures` gating still
applies, as `TONNEAU_CMD` established.

## Name-probe, 2026-09-01 — `chargingDisabledAC` ACCEPTED

The s33 corpus sweep confirmed `chargingDisabledAC` is a name the app itself
carries, not only a type declared in `rivian_client/schemas/gateway.graphql`.
`REMAINING_APK_GAPS.md` had it as "Name-probe required"; this settles that.

`scripts/probe_field_names.py chargingDisabledAC`, read-only, riding alone with
the two control fields. Control accepted first.

| Field | Result | Value observed |
|---|---|---|
| `chargingDisabledAC` | **ACCEPTED**, delivered (0.2 s) | `0` |

The gateway knows the name and has a value for it on this account.

**What the value means is not established.** One sample, and it is numeric rather
than the string vocabulary the neighbouring `chargingDisabledACFaultState` uses —
`0` could be a boolean-shaped flag, a count of disable reasons, or an enum whose
zero arm is "not disabled". A sensor built on the guess that `0` means "enabled"
would invert on any other reading. That needs either a second sample under a
different charging state or a schema type before anything ships.

Four of four name-probes from this sweep have now been accepted
(`passiveEntryUnlockFailReason`, `vasAccessCanFaulted`, `vasSecureElementFaulted`,
`chargingDisabledAC`). That is a point about the *corpus* being a good source of
candidate names, not evidence that any of them is ready to become an entity.
