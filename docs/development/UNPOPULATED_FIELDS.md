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

## f8 attempted 2026-08-19 — INCONCLUSIVE, and the instrument is why

**No verdict changes. Nothing is removed.** Under Principle -1 an inconclusive run is not a recorded
live failure, so all five fields keep their entities and their existing verdicts.

The integration was disabled (`ha core stop` -> edit `disabled_by` -> `ha core start`, that order
because HA flushes config entries on shutdown, `WS_CONTENTION.md:110-113`), making the probe the sole
subscriber. Outage 12:38-12:41:38 CDT, ~3.5 minutes. Re-enabled and verified recovered:
`disabled_by: None`, and fresh recorder rows at 12:41:38 for battery SoC, lock, gear and odometer.

**The probe never became a valid instrument.** It opens with a CONTROL of two known-good fields
(`batteryLevel`, `vehicleMileage`) precisely so that "the five are silent" can be told from "the probe
is not working". The control delivered **zero fields in 30 s** as sole subscriber, and again zero in
25.6 s after a `WAKE_VEHICLE` that returned terminal in 1.87 s. The run stopped there rather than
reporting five absent fields, which would have been false evidence.

**What the failure teaches, and it corrects an earlier reading of H4.** Home Assistant's own
subscription received a full snapshot within seconds of starting — recorder rows at 12:29:52 after the
beta6 restart and again at 12:41:38 after the f8 restore — while this probe, subscribing to a small
explicit property set, received nothing in either window. So:

- The earlier "accepted but silent" observation (2026-08-19 ~12:0x, with production running) was
  read as the `WS_CONTENTION.md:24` contention signature. **That reading is not safe.** The same
  silence appears with no competitor at all, so silence does not distinguish contention from
  "this probe does not receive what the integration receives".
- A Parallax subscription on the same credentials **did** deliver during the same period, so whatever
  the cause, it is specific to the GraphQL vehicle-state path as this probe drives it.

**The five fields, spelled out** — the tables above abbreviate three of them with a leading ellipsis,
which is unsearchable. In full: `tirePressureStatusValidFrontLeft`,
`tirePressureStatusValidFrontRight`, `tirePressureStatusValidRearLeft`,
`tirePressureStatusValidRearRight`, `cabinHoldNotification`. All five keep their existing verdicts;
f8 changed none of them.

**What f8 needs before it is re-run:** an instrument that reproduces the integration's subscription
rather than approximating it — the same property set the coordinator uses
(`VEHICLE_STATE_API_FIELDS`, `coordinator.py:958`) and the same setup path — verified by the control
delivering before any conclusion is drawn about the five. Bisection logic is written and ready
(`scripts/f8_probe.py`, committed with this correction; it previously pointed at an ephemeral session directory nobody else could reach); only the subscription setup is wrong.

SUPERSEDED: the instruction above previously named `VEHICLE_STATES_SUBSCRIPTION_PROPERTIES`. That
is only the client-library default (`rivian_client/rivian.py:626-627`), which the coordinator
never uses — it always passes the derived `VEHICLE_STATE_API_FIELDS` set. Following the old name
would rebuild the wrong instrument and f8 would fail a second time for a second reason.

## f8 COMPLETED 2026-08-19 ~19:00 CDT — all five delivered, all five null

**Verdict: PROBED. The five fields are accepted by the subscription and return `null`.** Not absent,
not rejected, not silent — *delivered, empty*. That is the hypothesis this document has carried since
"Why 'accepted but empty' is not 'invalid'", now confirmed against the vehicle.

```
=== ALL FIVE TARGETS + control ===
  [all-five] accepted; 7 field(s) in 0.4s
      batteryLevel                     = 84.099998
      vehicleMileage                   = 152031661
      tirePressureStatusValidFrontLeft  = None
      tirePressureStatusValidFrontRight = None
      tirePressureStatusValidRearLeft   = None
      tirePressureStatusValidRearRight  = None
      cabinHoldNotification             = None

  accepted as a document; 5/5 delivered
```

The control delivered **124 fields in 1.7 s** with real values (`wifiSignal -54`, all four windows
`closed`, `trailerStatus TRAILER_NOT_PRESENT`), so the instrument is proven before the result is
read — the discipline the first two attempts lacked.

**No entity or field is removed.** All five keep their entities: the server accepts the names, so
they are valid; it returns null, so this vehicle has no value for them today. A field that is
accepted and empty is exactly the case this document was written to protect.

### RETRACTION — both earlier f8 failures were my instrument, and so were two production outages

The probe's callback read `data["data"]["vehicleState"]`. The frame is
`{"id":…, "type":"next", "payload": {"data": {…}}}`, and `coordinator.py:580`, `:1074` and `:1223`
all unwrap `payload` first. The probe was one level too shallow, so `got` stayed empty **no matter
what arrived** and every field reported NOT DELIVERED.

That single defect produced:

- the first f8 run's "inconclusive — the control delivered nothing";
- the second run's identical failure *after* the property set was corrected to
  `VEHICLE_STATE_API_FIELDS`, which was a real fix for a real documentation error but not the cause;
- **the reading that H4 contention was real**, filed from a subscription that was "accepted but
  silent" — it was never silent, it was unparsed;
- **two production outages**, taken to make the probe the sole subscriber for a contention that does
  not exist.

With the parsing fixed, the probe delivers 124 fields **while production is subscribed**. There is no
contention on this path, f8 needs no outage, and `WS_CONTENTION.md`'s retraction notice should be read
as covering this too: silence in that record was this bug, not the gateway.

The lesson is the one this project already writes down and I failed to apply to my own tooling: an
instrument is proved before its result is read. The control existed precisely to catch this, and it
did catch it — twice — and twice I corrected something else.
