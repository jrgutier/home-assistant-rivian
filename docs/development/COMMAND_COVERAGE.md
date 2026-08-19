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
| `START_GEAR_GUARD_MASTER_SESSION` | Starts a live camera session. A streaming feature, not a control; this integration has no surface for it |
| `CABIN_HVAC_THIRD_ROW_*` | **ANSWERED by f7, 2026-08-19: REJECTED** (`CONFLICT/VEHICLE_COMMAND_ERROR`) on an R1T with `params={"level": 0}` |
| `CABIN_HVAC_3RD_ROW_REAR_*` | **ANSWERED by f7, 2026-08-19: ACCEPTED**, terminal in ~1.5 s, same params, same truck, seconds apart |

The two closure-openers ship `entity_registry_enabled_default=False`. Shipping an
untested opener enabled puts it one tap away.

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
