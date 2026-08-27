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

## `ACTIVATE_EXTERNAL_SOUND` and `FLASH_EXTERNAL_LIGHTS` — accepted, live-probed, 2026-08-22

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
