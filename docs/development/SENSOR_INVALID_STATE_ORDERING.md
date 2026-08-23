# The two platforms must filter the same value at the same point

`sensor.py` and `binary_sensor.py` both drop values the vehicle flags as unusable —
`INVALID_SENSOR_STATES` (`const.py`) = `{fault, signal_not_available, sna, undefined}`. They
disagreed about *when*, and that disagreement was a bug.

## What went wrong

`binary_sensor.py` tests the **raw** value. `sensor.py` tested the **output of `value_lambda`**.

Most lambdas run `_to_title_case`, which converts underscores to spaces:

```
"signal_not_available"  ->  "Signal Not Available"  ->  .lower() == "signal not available"
```

Spaces, not underscores. That matches nothing in the set, so it slipped past the filter, failed
the ENUM `options` check below it, logged an error, and — the real damage —
**appended itself to that entity's own `options` list for the life of the process**. The vehicle's
error code became a permanently valid state for that entity.

Measured before the fix: **27 of the 31** options-carrying sensors leaked on
`signal_not_available`. Every `*_next_action` closure sensor, `charger_status`, `ota_status`,
`trailer_status`, `power_state`, and all nine seat heat/vent sensors. `sensor.py`'s own comment
notes the rear seat heaters report SNA whenever the vehicle is parked, so this was not exotic.

### 27 here, 36 in MIGRATION.md — both correct

They count different harms, so neither contradicts the other:

| | count | of what | what it counts |
|---|---|---|---|
| here | **27** | of the 31 options-carrying sensors | leaked `signal_not_available` into the ENUM check and **mutated their own `options` list** |
| MIGRATION.md | **36** | of the 38 lambda-carrying sensors | their **displayed state** changed, on any of the four spellings |

The nine in the gap are there for one of two reasons: six carry no `options` at all, so they
displayed a wrong string but had nothing to mutate; and `gear_status` and `charge_port_status`
changed on spellings beyond `signal_not_available` — all four, in their case.

## Why the constant was already right

The app is normative and it agrees with us. `java_src/p069Ci/EnumC0996d.java` declares all four as
distinct constants:

```java
public static final String FAULT                = "Fault";
public static final String SIGNAL_NOT_AVAILABLE = "signal_not_available";
public static final String SNA                  = "sna";
public static final String UNDEFINED            = "undefined";
```

So `signal_not_available` genuinely occurs on the wire — the leak was real, not theoretical — and
`INVALID_SENSOR_STATES` needs no members added or removed. Only the comparison point was wrong.

Note the app capitalizes `FAULT` as `"Fault"`. Our comparison lowercases first, so this is already
handled. Do **not** "fix" the constant to match the capitalization; that would be a deviation from
the app for no gain.

`VehicleStateKt.isSignalNotAvailable` compares against `"-1"`, but that is the numeric cellular
signal field, not the state vocabulary. Do not conflate the two.

## The fix

`sensor.py` now tests the raw value **before** `value_lambda` runs, mirroring `binary_sensor.py`.
The post-lambda test is kept as well — it costs nothing and still catches a lambda that
manufactures an invalid-looking string from a valid input.

## The behaviour change this causes

A lambda that *rescued* an invalid value no longer gets the chance. `charge_port_status` and
`power_state` both map `sna` to the literal string `"Unknown"`; they now return `None`, which
renders as Home Assistant's native `unknown` state.

That is the point — a vehicle error code should not be dressed up as a state — but it is visible
on a dashboard, so it is recorded in `docs/MIGRATION.md`.

## What pins this

`tests/test_sensor_invalid_state_ordering.py` walks **every** options-carrying description and
asserts each spelling resolves to `None` and that `options` is never mutated. It pins the class,
not the instance: a new ENUM sensor is covered without anyone remembering to add a case. It also
asserts the population size, so a sensor cannot quietly leave the guarantee.
