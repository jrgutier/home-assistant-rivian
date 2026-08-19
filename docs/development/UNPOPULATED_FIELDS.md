# Fields the server accepts but never populates

Five fields are subscribed for, accepted by the server, and have never carried a
value on the owner's 2022 R1T. **All five stay.** This file is the recorded
finding the rule demands: an entity is removed only on a live *failure*, and
"never carried a value" is not one — it is silence, which is exactly what the
tonneau cover falsified.

Method: whole-word grep across all 32,941 decompiled files of
`com.rivian.android.consumer` 3.15.0, plus the live state machine of the
production instance. Whole-word matters: `wiperFluidState` occurs only inside the
Room column name `wiperFluidStateUpdatedTimestamp`, so a substring grep
undercounts.

## The four `tirePressureStatusValid*`

| | |
|---|---|
| Fields | `tirePressureStatusValidFrontLeft`, `…FrontRight`, `…RearLeft`, `…RearRight` |
| Entities | `binary_sensor.*_{front,rear}_{left,right}_tire_pressure_validity` |
| In the app | **0 files** |
| Live | `unavailable`, all four |
| Verdict | **No source found in the app. Left in place. Live probe deferred to f8.** |

**Correction.** An earlier draft of this file said a source *had* been found:
`tirePressureState`, "the aggregate the app requests instead". That was wrong,
and it is worth recording how, because the mistake is the exact one this project
keeps having to unlearn.

`tirePressureState` is the **operation name** of `apj.java`'s subscription —
`subscription tirePressureState($vehicleID: String!) { vehicleState(id: …) { … } }`
— not a field it selects. A flat grep for `tirePressure[A-Za-z]*` returns it and
gives no hint which it is. The only other occurrences in the whole decompilation
are in two retired flat extracts, `apk_statefields.txt` and `apk_ops.txt`, which
is how it reached the plan in the first place. Parsing the selection set instead
of grepping the text shows `apj.java` selects exactly **eight** fields:

```
tirePressure{FrontLeft,FrontRight,RearLeft,RearRight}
tirePressureStatus{FrontLeft,FrontRight,RearLeft,RearRight}
```

It was briefly adopted into `VEHICLE_STATE_API_FIELDS` on the strength of that
misreading, and reverted before anything shipped. Subscribing to a name the
server does not know is not a harmless experiment: it is what `wheelsInstalled`
did, and it takes the **entire** subscription down (`const.py:1441-1455`).

So: the four `tirePressureStatus*` are already subscribed and already reporting —
all four read `OK` live — and the app requests **no** validity field of any kind
and **no** aggregate. There is no offline candidate. That is the third outcome:
no source found in the app, entities left in place, live probe deferred to f8.

They cost nothing and removing them needs a live failure nobody has recorded.

## `cabinHoldNotification`

| | |
|---|---|
| Field | `cabinHoldNotification` |
| Entity | `sensor.*_cabin_climate_hold_notification` |
| In the app | **0 files** |
| Live | `unavailable` |
| Verdict | **Left in place. Live probe deferred to f8.** |

**No source found in the app.** Its sibling `cabinHoldStatus` *is* populated —
live value `Available` — and is a different field with a different meaning, so it
is not a replacement. Nothing in the decompiled app names `cabinHoldNotification`
in any form, so there is no second candidate to try offline.

This is the outcome the offline evidence actually supports, and it is written
down rather than resolved: the field is accepted by the server (it is in the
subscription, which the server validates name by name and rejects wholesale), and
it has never carried a value here. Whether it carries one on other hardware is an
f8 question.

## Why "accepted but empty" is not "invalid"

The server validates the subscription document by name and rejects the **entire**
subscription if one name is unknown — that is how `wheelsInstalled` took the
whole thing down. The live subscription currently carries all 124 names and
works. So every one of these five is a name the server's `type VehicleState`
contains. They are empty, not wrong.

Fifteen of the 124 appear in **zero** decompiled files, and three of those fifteen
carry live data right now (`batteryCapacity` 124.99, `gearGuardLocked` on,
`wiperFluidState` Normal). The app is a lower bound on the schema, so its silence
about these five says nothing about the server.

## The `^` trap, now closed

`VEHICLE_STATE_SANS_TPMS_API_FIELDS` was built with `^` (symmetric difference),
not `-`. It behaved as subtraction only because all four tire-pressure names
happened to be in the base set. The moment one left — which is precisely what
editing the tire field set does — `^` would have **added it back**, producing the
unknown-field subscription kill described above.

Converted to `-`. The guard in `tests/test_init.py` asserts the operator's
behaviour directly rather than only its current result.

## The `3RD_ROW` spellings

`VehicleCommand` now carries both:

```
CABIN_HVAC_THIRD_ROW_LEFT_SEAT_HEAT      CABIN_HVAC_3RD_ROW_REAR_LEFT_SEAT_HEAT
CABIN_HVAC_THIRD_ROW_RIGHT_SEAT_HEAT     CABIN_HVAC_3RD_ROW_REAR_RIGHT_SEAT_HEAT
```

The `3RD_ROW` pair is what app 3.15.0 sends (`VASCommandKt`). The `THIRD_ROW`
pair appears in no file of this build.

**Added alongside, not renamed.** The older spelling may serve older firmware, and
neither pair is wired to an entity yet — which one a given vehicle accepts is a
live question, and f6 answers it by testing rather than by grepping.
