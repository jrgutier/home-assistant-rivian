# Binary sensor audit against the app's value vocabulary

Read-only analysis. Audits all 35 `RivianBinarySensorEntityDescription` in `const.py:1501+`
against the decompiled app, and the inverse: which of the 127 `RivianSensorEntityDescription`
should be binary sensors instead.

Rule applied: **if the app's vocabulary for a field has exactly two non-invalid states, a binary
sensor is correct.** More than two, and the entity is judged case by case.

## The functionality question, answered

**Converting a `binary_sensor` to a `sensor` does lose real HA capability.** A `binary_sensor`
carrying `device_class` `door` / `window` / `garage_door` / `opening` / `motion` / `occupancy` /
`smoke` / `moisture` is exposed to HomeKit, Google and Alexa as a genuine contact/door/window
accessory. A `sensor` whose state is the string `"opening"` is not mappable to any such trait and
degrades to an unusable text readout. Nothing recovers this from the sensor side.

**But it is mostly a false choice.** Two properties of the existing code make it so:

1. `binary_sensor.py:121-138` already publishes the raw string as a `value` attribute on every
   non-aggregate binary sensor. Richer state is not being destroyed today, only kept out of the
   state machine. `state_attr('binary_sensor.x', 'value')` reads it now.
2. `data_classes.py:89` types `on_value` as `bool | float | int | str | list[str]`, and
   `tests/test_binary_sensor_invalid_states.py:130` already exercises `["open", "ajar"]`. A
   three-state field can stay binary by widening `on_value` — no retyping needed.

So the remedy for almost every finding below is a wider `on_value`, not a different platform.

The reverse direction has no equivalent symmetry, and its gain is **not uniform**: `problem` and
`connectivity` device classes get no HomeKit/Google accessory at all. A fault flag converted from
`sensor` to `binary_sensor` buys clean on/off state, correct styling, and simpler automations —
not voice exposure. Every row below says which applies.

## Evidence base

| Source | What it gives |
|---|---|
| `com.rivian.android.consumer/` (31,105 files, apktool) | The tree itself. Gitignored, proprietary, pre-flight only |
| `java_src/com/rivian/android/consumer/data/model/*.java` | 84 enum-like model classes — the per-field vocabularies |
| `smali_classes2/com/rivian/android/consumer/data/model/VehicleStateKt.smali` | The predicates the app applies to the GraphQL `VehicleState` |
| `java_src/p069Ci/EnumC0996d.java` | The flat value vocabulary and the Parallax int->string decode maps |

`VehicleStateKt` is the load-bearing source: its predicates take the **GraphQL** `VehicleState`,
so they are directly comparable to our `field=` names. `EnumC0996d`'s members are **Parallax/VAS
attribute** names (`frunkStatus`, `vehiclePowerMode`, `chargePortControlState`) — a different
namespace. Do not bind an `EnumC0996d` decode map to one of our GraphQL fields without a
corroborating model class.

### The app's closure/lock vocabulary

`VehicleStateKt` declares exactly six string constants: `OPEN`, `OPENED`, `CLOSED`, `LOCKED`,
`UNLOCKED`, `UNKNOWN`. Extracted per predicate:

| App predicate | Accepts as "open" |
|---|---|
| `isFrunkOpen` | `open`, `opened`, **`ajar`** |
| `isLeftFrontDoorOpen`, `isLeftRearDoorOpen`, `isRightFrontDoorOpen`, `isRightRearDoorOpen` | `open`, `opened` |
| `isLiftGateOpen`, `isTailGateOpen`, `isTonneauCoverOpen` | `open`, `opened` |
| `isLeftSideBinOpen`, `isRightSideBinOpen` | `open`, `opened` |
| `isLeftFrontWindowOpen`, `isRightFrontWindowOpen`, `isLeftRearWindowOpen`, `isRightRearWindowOpen` | `open`, `opened` |
| `areWindowsOpen` | `open`, `opened` |
| `areDoorsLocked` | `locked` |

## Part 1 — the 35 binary sensors

No description in `BINARY_SENSORS` uses `negate`. All five distinct `on_value`s are bare strings,
never lists: `"open"` x17, `"unlocked"` x11, `"invalid"` x4, `"go"` x1, `"on"` x1.

### Verdict summary

| Verdict | Count |
|---|---|
| Correct as binary, no change | 12 |
| Correct as binary, `on_value` too narrow — **fix** | 18 |
| More than 2 states, needs a decision | 1 |
| No evidence in the app — leave alone | 4 |

### A. Locks — 11 sensors. **Correct. No change.**

`closure_frunk_locked`, `closure_tailgate_locked`, `door_front_left_locked`,
`door_front_right_locked`, `door_rear_left_locked`, `door_rear_right_locked`, `gear_guard_locked`,
`closure_side_bin_left_locked`, `closure_side_bin_right_locked`, `closure_tonneau_locked`,
`closure_liftgate_locked`

Vocabulary: `locked`, `unlocked` (+ `unknown`, already filtered by `INVALID_SENSOR_STATES`).
Exactly two non-invalid states. `on_value="unlocked"` with `device_class=LOCK` is right.
The aggregate `locked_state` shares this vocabulary and is also correct.

### B. Car wash — 1 sensor. **Correct. No change.**

`car_wash_mode` — `CarWashModeStatus` is `{ON, OFF}`. Exactly two states. `on_value="on"` is right.

### C. Open/closed closures — 16 sensors. **`on_value` too narrow. Fix.**

`closure_frunk_closed`, `closure_tailgate_closed`, `door_front_left_closed`,
`door_front_right_closed`, `door_rear_left_closed`, `door_rear_right_closed`,
`window_front_left_closed`, `window_front_right_closed`, `window_rear_left_closed`,
`window_rear_right_closed`, `closure_side_bin_left_closed`, `closure_side_bin_right_closed`,
`closure_tonneau_closed`, `closure_liftgate_closed`, plus the aggregates `door_state` and
`closure_state`.

All use `on_value="open"`. The app accepts `open` **and** `opened`. `closure_frunk_closed`
additionally must accept **`ajar`** — `isFrunkOpen` is the one predicate that tests all three.

**Live defect.** An ajar frunk renders as a confident **Closed** today. Not `unknown` — `off`.
A "close the frunk before leaving" automation does not fire, and the HomeKit contact sensor
reports closed on a frunk that is not.

Remedy: widen to `["open", "opened"]`, and `["open", "opened", "ajar"]` for the frunk.
Stays a binary sensor; voice exposure preserved.

### D. Charge port — 1 sensor. **More than 2 states. Needs a decision.**

`charge_port_state`, `field="chargePortState"`, `on_value="open"`, `device_class=DOOR`.

`ChargePortStatus` is `{OPEN, CLOSE, IN_TRANSITION, FAULT, OPENING, CLOSING, UNKNOWN}` —
**five non-invalid states**, corroborated by `EnumC0996d`'s `CHARGE_PORT_CONTROL_STATE_MAP`
(line 302), which carries the same seven values.

Two problems today:
- The closed value is **`close`**, not `closed`. Confirmed in fixtures (5 occurrences).
- `opening`, `closing` and `in_transition` all fall to **off**, reported as Closed.
- Unlike `powerState`, there is **no companion regular sensor** — `chargePortState` appears only
  at `const.py:1506`. The five-state vocabulary reaches the user nowhere except the `value`
  attribute.

Recommended: keep the binary sensor with `on_value=["open", "opening", "in_transition"]`
(a port mid-travel is not closed), **and** add a companion `sensor` exposing the raw state, the
way `powerState` already has both. Do not convert — that would surrender the DOOR accessory.

### E. Power state — 1 sensor. **More than 2 states, but already handled. No change.**

`use_state`, `field="powerState"`, `on_value="go"`, `device_class=MOVING`.

`PowerState` is `{GO, READY, SLEEP, STANDBY, UNKNOWN}` — four non-invalid states, corroborated by
`VEHICLE_POWER_MODE_MAP` (`EnumC0996d:300`). So `ready`, `standby` and `sleep` all collapse to off.

That collapse is correct here: `MOVING` asks one boolean question and `go` is the only value that
answers it yes. And the richer vocabulary is **already exposed** — `power_state` is a regular
sensor on the same field at `const.py:693`. Both platforms already exist for this field. Nothing
to do; this is the pattern D should copy.

### F. Tire pressure validity — 4 sensors. **No evidence in the app. Leave alone.**

`tire_pressure_status_valid_front_left`, `…front_right`, `…rear_left`, `…rear_right`,
`on_value="invalid"`, `device_class=PROBLEM`.

`docs/development/UNPOPULATED_FIELDS.md` already settles these: **0 files in the app**, all four
read `unavailable` live, and the app requests no validity field of any kind. There is no
vocabulary to audit against. Verdict unchanged from that document — left in place, live probe
deferred. Marked **insufficient evidence**, not guessed.

## Part 2 — inverse: sensors that should be binary sensors

127 `RivianSensorEntityDescription` across `R1` / `R1T` / `R1S` / `LIFTGATE`; 31 already use
`SensorDeviceClass.ENUM`. Sweeping all 84 app model enums for exactly-2-member vocabularies and
cross-referencing against our sensor fields yielded 15 candidates. Verifying each enum against
its actual field binding in `VehicleState.java` / `VehicleState2.java` cut that to **12**. The
three rejected rows are recorded below — a keyword match is not a binding.

| Sensor key | Field | App enum | Vocabulary | Suggested device_class | Gains voice exposure? |
|---|---|---|---|---|---|
| `btm_ff_hardware_failure_status` | `btmFfHardwareFailureStatus` | `BtmFaultStatus` | `DETECTED` / `NOT_DETECTED` | `PROBLEM` | no |
| `btm_oc_hardware_failure_status` | `btmOcHardwareFailureStatus` | `BtmFaultStatus` | same | `PROBLEM` | no |
| `btm_rf_hardware_failure_status` | `btmRfHardwareFailureStatus` | `BtmFaultStatus` | same | `PROBLEM` | no |
| `btm_ic_hardware_failure_status` | `btmIcHardwareFailureStatus` | `BtmFaultStatus` | same | `PROBLEM` | no |
| `btm_rfd_hardware_failure_status` | `btmRfdHardwareFailureStatus` | `BtmFaultStatus` | same | `PROBLEM` | no |
| `btm_lfd_hardware_failure_status` | `btmLfdHardwareFailureStatus` | `BtmFaultStatus` | same | `PROBLEM` | no |
| `battery_hv_thermal_event` | `batteryHvThermalEvent` | `BatteryThermalEvent` | `DETECTED` / `UNDETECTED` | `PROBLEM` | no |
| `battery_hv_thermal_event_propagation` | `batteryHvThermalEventPropagation` | `BatteryThermalEvent` | same | `PROBLEM` | no |
| `alarm_sound_status` | `alarmSoundStatus` | `SoundAlarm` | `ACTIVE` / `INACTIVE` | `SOUND` or `PROBLEM` | no |
| `twelve_volt_battery_health` | `twelveVoltBatteryHealth` | `TwelveVoltBatteryHealth` | `OK` / `LOW` | `PROBLEM` | no |
| `service_mode` | `serviceMode` | `ServiceModeStatus` | `ON` / `OFF` | none | no |
| `ota_install_ready` | `otaInstallReady` | `OverTheAirInstallReady` | `AVAILABLE` / `NOT_AVAILABLE` | `UPDATE` | no |

**None of the 12 gains voice-assistant exposure.** Every one lands in `problem` / `update` /
no-device-class, which HomeKit and Google do not surface as accessories. The gain is real but
narrower than the forward direction: correct on/off semantics, `problem` styling and the red
"Detected" badge, working `to: "on"` state triggers, and eligibility for HA's alert helpers.

Each conversion changes the entity ID from `sensor.x` to `binary_sensor.x` and breaks existing
automations, dashboards and templates naming it. That cost was accepted for this direction.

### The three rejected candidates

The keyword sweep that produced the shortlist matched on names. Checking what type each field
actually carries in `VehicleState.java` / `VehicleState2.java` overturned three of them:

| Sensor | Why the keyword match was wrong |
|---|---|
| `wiper_fluid_state` | Typed **`WiperFluidState`** = `{EMPTY, LOW, NORMAL}` — **three** states, not the two-member `FluidLevelLow` the name suggests. The existing three-option sensor was already correct. |
| `brake_fluid_low` | `brakeFluidLow` appears in **neither** `VehicleState` nor `VehicleState2`. No binding, no vocabulary, no verdict — same outcome as the four `tirePressureStatusValid*`. Left as a sensor rather than guessed into a boolean. |
| `ota_deployment_intent` | Binding confirmed, and `OverTheAirDeploymentIntent` really is two members — but `UNSPECIFIED` is not the negation of `PERFORMANCE_UPGRADE`, it is the absence of an answer. Two-state is a filter for candidates, not a conversion trigger. |

All three are pinned by `tests/test_apk_binary_sensor_vocabulary.py::TestFieldsDeliberatelyNotConverted`,
because the heuristic is easy to re-run and would propose them again.

The other 112 sensors are not candidates: numeric (`batteryLevel`, `distanceToEmpty`, pressures,
temperatures), version strings (`otaAvailableVersion*`), free text (`activeDriverName`,
`wifiSsid`), or genuinely multi-state (`chargerStatus`, `gearStatus`, `driveMode`,
`otaStatus`, `tirePressureStatus*` — which read `OK` live and carry more than two states).

## Evidence strength — read before acting

- **`ajar` on the frunk: strong.** A dedicated constant, and `isFrunkOpen` is the only predicate
  that tests it. `"ajar"` also appears twice in our own test corpus.
- **`opened` everywhere: medium.** Every app predicate accepts it, but no fixture or live capture
  in this repo has ever carried it. It may be defensive coding against a value the server no
  longer emits. Widening `on_value` to include it is free and cannot regress anything; do not
  claim it fixes an observed failure.
- **`chargePortState` five-state: strong.** Two independent sources agree (`ChargePortStatus`,
  `CHARGE_PORT_CONTROL_STATE_MAP`), and `"close"` appears in fixtures, proving the field really
  does use this vocabulary rather than `closed`.
- **The 15 inverse candidates: strong for the vocabulary, unproven for the wire.** The enum
  membership is direct evidence of what the app models. Whether our GraphQL field emits exactly
  those two strings, in that case, is not proven here.

## Recommended order

1. Widen the 16 open/closed descriptions to `["open", "opened"]`; frunk to
   `["open", "opened", "ajar"]`. Smallest change, fixes a shipped wrong state.
2. Fix `charge_port_state`: `on_value=["open", "opening", "in_transition"]`, and add the
   companion regular sensor so the five-state vocabulary is reachable.
3. Convert the 12 inverse candidates, accepting the entity-ID break. Land with a migration note.
4. Transcribe every vocabulary claim above into `tests/` so the repo stays checkable without the
   decompilation present, as `docs/development/apk/REGENERATION.md` requires.

## Not covered

- The aggregate descriptions (`locked_state`, `door_state`, `closure_state`) take a `set` of
  fields through a different `is_on` path (`binary_sensor.py:86-95`). They are included in the
  verdicts above on vocabulary grounds, but the widening has not been traced through that path.
- Whether the server ever emits `opened` on any field.
- `RivianCloudConnectionBinarySensor` — not field-driven, out of scope.
