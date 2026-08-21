# s13 — E2E acceptance against the real vehicle

**Run:** 2026-08-18, local Home Assistant 2026.8.2 / Python 3.14.6, config seeded by
`scripts/seed_config_entry.py` from `.env`. Vehicle: R1T, MY2022.
**Verdict: pass**, with one threshold deliberately not exercised (below).

This run found five defects that 1244 passing unit tests did not, because every one
of them only appears when talking to the real gateway. That is the entire argument
for this story existing.

## Thresholds

| Threshold | Result |
|---|---|
| Parallax decodes to real dicts, never `{"raw": …}` | **13 topics, 0 raw** |
| GraphQL field rejections | **0** |
| `sensor.*_odometer` holds a value | **`vehicleMileage: 152031000`** |
| All four tire pressures hold values | **3.4 / 3.38 / 3.4 / 3.4** |
| Door and lock binary sensors hold values | **6 doors/closures, 6 locks, all decoded** |
| Live charging sensors update more than once | **3–4 updates per run** |
| Zero `TypeError` from `get()` | **0** |
| Zero `KeyError` from any select | **0** |
| Zero tracebacks / ERROR lines | **0** |
| Climate hold write round-trips | **0 → 300 → 0 s, reflected in ~3 s** |

Topics decoded: `body.closures.states`, `body.locks.states`,
`comfort.cabin.cabin_preconditioning_status`, `comfort.cabin.cabin_temperatures`,
`comfort.cabin.climate_hold_setting`, `comfort.cabin.climate_hold_status`,
`comfort.cabin.defrost_defog_status`, `dynamics.tires.state`,
`dynamics.vehicle.gnss`, `dynamics.vehicle.odometer`,
`energy.high_voltage.battery_state`, `vehicle.power.state`,
`vehicle.wheels.vehicle_wheels`.

## The climate hold write

Exercised, with the owner's explicit approval and on their conditions: restore
steady state afterwards, and abort if anyone is in the vehicle.

**Occupancy gate before writing.** All six closures `closed`
(`doorFrontLeft/Right`, `doorRearLeft/Right`, `closureFrunk`,
`closureSideBinLeft`), `powerState: ready` — awake and parked, not `go`. Doors were
re-checked throughout and never changed.

**Round trip**, observed through the live Parallax subscription:

| Step | `climateHoldDurationSeconds` |
|---|---|
| baseline | `0` |
| `set_climate_hold(duration_minutes=5)` | `300` |
| `set_climate_hold(duration_minutes=0)` | `0` |

Both writes returned `SendVehicleOperationSuccess / success: true`, and the change
was reflected back through the subscription in about three seconds — well inside
the one-update threshold. 5 minutes encoding to exactly 300 seconds confirms the
hand-rolled varint encoder that replaced protobuf in s10 against the real vehicle,
which the golden-bytes tests could only assert against the old generated code.

The 16-raw-byte `phone_id` (`uuid.UUID(vasPhoneId).bytes`, not the 36-character
string) was resolved from the enrolled phone matching the configured public key —
the detail most likely to be got wrong, now confirmed end to end.

`climateHoldStatus` stayed `off` throughout, which is consistent: the write sets
the hold *duration*; the hold itself does not become active merely because a
duration is stored.

**The vehicle was left exactly as found**: duration `0`, status `off`.

## Defects found, all fixed in this session

1. **The response envelope was never unwrapped.** `_async_update_data` returned
   `_fetch_data()` directly, but every client method returns an aiohttp
   `ClientResponse`. Setup died immediately with
   `'HassClientResponse' object has no attribute 'get'`. Upstream checks the
   status, awaits `.json()` and returns `data["data"][key]`; the s05 merge dropped
   that and nothing failed, because the tests mock `self.api.get_*()` as already
   returning the inner dict. `self.key` sat on four coordinator classes with
   nothing reading it — the tell. **This is precisely the take-ours-silently-drops-
   upstream failure the plan's s05 review checkpoint predicted.**

2. **A Parallax-only field poisoned the GraphQL subscription.**
   `VEHICLE_STATE_API_FIELDS` is derived from every sensor's `field`, so the
   `wheels_installed` sensor added in s09b put `wheelsInstalled` into the
   subscription query. Rivian rejected it —
   `Cannot query field "wheelsInstalled" on type "VehicleState"` — and the whole
   subscription then delivered nothing: no battery level, no odometer, no tire
   pressures. Every reading in the table above was absent before this fix.

3. **`Off` missing from the preconditioning enum.** `decode_preconditioning` emits
   `"active" | "initiate" | "off"`; the options list was written for the GraphQL
   vocabulary. Logged an error and self-appended on every start.

4. **`SNA` not recognised as an invalid state.** `INVALID_SENSOR_STATES` listed
   only the long form `signal_not_available`; the vehicle sends `SNA`.

5. **Invalid states leaked whenever a key was seen for the first time.** The
   fallback was guarded by `and key in prev_items`, which fails both on the very
   first update and — the case that survived the first fix — whenever Parallax has
   already populated *other* keys, making `prev_items` truthy while this key is
   still new. Both rear seat heating sensors published a literal `SNA`, which an
   ENUM sensor then appends to its own options, making the bad value permanently
   valid for the life of the process.

## Note on the single-subscription constraint

H4 says one Parallax subscription per user session token. This run obtained a full
subscription without the production integration being disabled, so either
production was not subscribed at the time or the constraint is narrower than
measured. Worth re-checking before relying on it — but the safe reading stands: if
two instances contend, the second gets nothing rather than both degrading.

## f3b-b — tonneau cover, 2026-08-19 ~05:15 CDT

**Entity: CONFIRMED. Round trip: INCONCLUSIVE, and inconclusive is not a failure.**

Pre-flight: Park, speed 0, Gear Guard armed, no door or window open, vehicle on
the charger. Charge-port door excluded from the occupancy test — it is open
whenever the vehicle is plugged in, which is exactly when the vehicle is awake and
reachable, so counting it aborts every usable window. It is a closure, not an
occupancy signal.

### What was confirmed

`cover.r1t_r1t_tonneau_cover` **exists** and reads `closed`. That is f3b-a's whole
claim: the cover was gated on `TONNEAU_CMD`, a flag no server emits, so it had
never been created for anyone. Re-gated on the field, it is there.

(An earlier probe reported it absent. That probe looked for `cover.r1t_tonneau`;
the entity id is `cover.r1t_r1t_tonneau_cover`. The doubled `r1t_r1t` prefix is
cosmetic and also affects `button.r1t_r1t_open_tailgate`.)

### What was not confirmed, and why it is not a failure

| Command | Physical effect | `last_command_state` |
|---|---|---|
| `OPEN_TONNEAU_COVER` | none observed in 60 s | `TIMEOUT` |
| `OPEN_TONNEAU_COVER` (retry) | none observed in 84 s | `TIMEOUT` |
| `CLOSE_TONNEAU_COVER` (already closed — calibration) | n/a | `TIMEOUT` |
| `LOCK_ALL_CLOSURES_FEEDBACK` (already locked — calibration) | n/a | `TIMEOUT` |

**Every command times out, including two that move nothing.** `TIMEOUT` is not a
refusal: it means `vehicleCommandState` returned no result within 30 s, so we
learn nothing about whether the vehicle accepted the command. The calibration
commands are what make this readable — a tonneau-specific problem would not also
time out a lock.

Network was healthy at the time (`rivian.com` resolved and returned 200 in 0.26 s
from the HA host) and `binary_sensor.r1t_cloud_connected` was `on`, so this is not
a connectivity outage. There was one unrelated DNS timeout 33 minutes earlier.

**Under Principle -1 this changes nothing.** An inconclusive run is not a recorded
live failure, so no entity, field or command is removed on the strength of it.
The tonneau commands remain live-proven from the earlier successful test.

### f7 not attempted

f7's entire output is a per-command live result. With `vehicleCommandState`
returning nothing for every command, f7 would fire closure-openers and record
`TIMEOUT` against each — no evidence, and several closures opened at 05:20 with no
reliable feedback. Deferred until the command-state path reports again.

### RETRACTED: "two lock signals disagree"

**This finding was wrong. The two signals agree, and always did.**

What I filed: `binary_sensor.r1t_locked_state` read `on` before the run and `off`
after, while `lock.r1t_closures` read `unlocked` before and `locked` after —
therefore "at least one is wrong or stale".

What is actually true: `locked_state` carries `device_class=LOCK`, and Home
Assistant renders that class as **`on` = Unlocked, `off` = Locked** — the inverse
of the intuitive reading. Applying it, both observations were consistent:

| moment | `locked_state` | means | `lock.r1t_closures` | agree? |
|---|---|---|---|---|
| before | `on` | Unlocked | `unlocked` | yes |
| after `LOCK_ALL_CLOSURES_FEEDBACK` | `off` | Locked | `locked` | yes |

They cannot disagree by construction. Both read the same `LOCK_STATE_ENTITIES`
set (`const.py:55`) and are exact complements — `lock.py:26-28` is
`not any(v == "unlocked")`, the binary sensor is `"unlocked" in values`
(`binary_sensor.py:83-86`).

`TestLockSignalsAreComplements` in `tests/test_binary_sensor_invalid_states.py`
now pins this, including a standalone assertion that the device class is `LOCK` —
which is the single check that would have stopped me filing the finding.

The observed values above are kept rather than deleted: a retracted finding is
worth more than a vanished one, and the readings themselves were accurate. Only
my reading of them was not.

Final state: all closures closed except the charge-port door (plugged in), Park,
speed 0, Gear Guard armed, `lock.r1t_closures` locked.

## f7 — actuate the residue, 2026-08-19 ~12:31 CDT (beta6)

**Supersedes, does not replace, the "f7 not attempted" note above.** That note deferred f7 "until
the command-state path reports again". `ae06ee9` fixed it; beta6 deployed it; f7 ran.

Sent with `scripts/probe_vehicle_command.py` against the deployed beta6 client. `OPEN_TAILGATE` was
**never sent** — see the prohibition below.

### Pre-flight (from the production integration, not inferred)

`gear_selector` Park, `speed` 0.0, `power_state` Ready, `lock.r1t_closures` locked, all closures
closed, Gear Guard video enabled, alarm Inactive. `cover.r1t_charge_port_door` open — expected and
excluded, the truck is plugged in. `pet_comfort_status` **Disabled**, `pet_comfort_temperature_status`
**Default** — the pre-state for the one command whose reversal is verifiable.

### Results

**Column header corrected 2026-08-20 (was `Send→terminal`).** These are time-to-first-frame figures, not terminal latencies: none of the five commands below reached a terminal state — they sit at states 5, 2, 2, 2, 2, all inside the app's *continue* set. See the standing note at `:432`: *"Every latency number recorded before `f9b663e` should be read as time-to-first-frame."*

| Command | Disposition | Send→first frame | state |
|---|---|---|---|
| `WAKE_VEHICLE` (calibration) | accepted | **1.68 s** | 5 |
| `LOCK_ALL_CLOSURES_FEEDBACK` (calibration, already locked) | accepted | **1.75 s** | 2 |
| `OPEN_LIFTGATE` | accepted | **2.77 s** | 2 |
| `CABIN_HVAC_3RD_ROW_REAR_LEFT_SEAT_HEAT` | accepted | **1.48 s** | 2 |
| `CABIN_HVAC_3RD_ROW_REAR_RIGHT_SEAT_HEAT` | accepted | **1.47 s** | 2 |
| `CABIN_HVAC_THIRD_ROW_LEFT_SEAT_HEAT` | **rejected** `CONFLICT/VEHICLE_COMMAND_ERROR` | — | — |
| `CABIN_HVAC_THIRD_ROW_RIGHT_SEAT_HEAT` | **rejected** `CONFLICT/VEHICLE_COMMAND_ERROR` | — | — |
| `PET_COMFORT_ON` | **rejected** `CONFLICT/VEHICLE_COMMAND_ERROR` | — | — |
| `PET_COMFORT_OFF` | **rejected** `CONFLICT/VEHICLE_COMMAND_ERROR` | — | — |
| `START_VIDEO_DOWNLOADING_SESSION` | **rejected** `CONFLICT/VEHICLE_COMMAND_ERROR` | — | — |
| `TWO_FACTOR_DRIVE_ALLOW` | **rejected** `CONFLICT/VEHICLE_COMMAND_ERROR` | — | — |
| `TWO_FACTOR_DRIVE_DENY` | **rejected** `CONFLICT/VEHICLE_COMMAND_ERROR` | — | — |
| `TWO_FACTOR_DRIVE_DISABLE` | **rejected** `CONFLICT/VEHICLE_COMMAND_ERROR` | — | — |
| `TWO_FACTOR_DRIVE_ENABLE` | **rejected** `CONFLICT/VEHICLE_COMMAND_ERROR` | — | — |
| `OPEN_TAILGATE` | **not sent — owner prohibited, physical hazard** | — | — |

**Why `OPEN_TAILGATE` was never sent.** Owner prohibition, 2026-08-19: the vehicle is parked where an
opening tailgate **strikes the garage**. This is not a reversal question and not a pre-flight
question — the command is never sent, in any phase, under any pre-flight result. Its disposition is
`not-sent-owner-prohibited-physical-hazard`, deliberately distinct from `not-run`, so that a later
reader cannot mistake it for something that was merely skipped.

Consequence worth recording: with `OPEN_TAILGATE` prohibited and `OPEN_LIFTGATE` a no-op on an R1T,
**f7 actuated no real closure at all**. The Pre-mortem 2 scenario — a closure left open overnight,
Gear Guard unable to arm — was not merely avoided, it was unreachable.

### The third-row spelling question is ANSWERED

`COMMAND_COVERAGE.md` recorded "two spellings exist and neither has been seen to work here; which one
a vehicle accepts is a live question". **`CABIN_HVAC_3RD_ROW_REAR_*` is accepted; `CABIN_HVAC_THIRD_ROW_*`
is rejected.** Identical `params={"level": 0}`, same truck, seconds apart — one variable.

This required adding `--params` to the probe first. `_validate_vehicle_command` (`rivian.py:524-548`)
lists eight `level`-requiring HVAC commands and **omits all four third-row spellings**, while
`send_vehicle_command`'s docstring (`:576`) says `CABIN_HVAC_*` needs `level`. Without the parameter
nothing raises locally and every rejection is uninterpretable — "wrong spelling" and "missing
parameter" look identical.

### All seven invalid-wrapper commands rejected identically — a TRANSPORT answer, not a capability one

Every one returned the same `CONFLICT / VEHICLE_COMMAND_ERROR`, including two that a healthy vehicle
should accept. `COMMAND_COVERAGE.md:45-47` records them as built with `generateInvalidCloudDataWrapper`
(`appName=""`) and `isParallaxRequestOnly`. The uniformity across all seven, against acceptance of
ordinary commands minutes earlier on the same credentials, is consistent with the ordinary cloud VAS
path being **the wrong envelope** for this family. The plan declared seven rejections a passing f7 in
advance, and that is what happened.

**SUPERSEDED: the `isParallaxRequestOnly` and `appName=""` claims in the paragraph above.** Both
halves are wrong as an explanation of these rejections.

- `isParallaxRequestOnly` (`VASCommandKt.java:117-119`, 3.15.0 artifact) is true only for
  `TWO_FACTOR_DRIVE_ENABLE` and `TWO_FACTOR_DRIVE_DISABLE`. The other five are not marked.
- The two wrappers differ in `appName` alone — `"rshell"` by default (`VASCommand.java:157-165`)
  versus `""` (`:395-405`). Our client sends no `appName` at all (`send_vehicle_command`,
  `rivian.py:596-609`). The `appName=""` marker is an app-side construction detail we never
  express, so the seven-way rejection is not attributable to the wrapper.

**Nothing is removed on this evidence.** Under Principle -1 a rejection through a possibly-wrong
transport is not a recorded live failure of the command.

### `TWO_FACTOR_DRIVE_*`: the unverifiable guardrail never came due

All four were rejected, so **no security posture changed**. There is no state surface for them
anywhere — not in the repo, and confirmed not in Home Assistant either (no entity matches
`two_factor`/`factor`). Had any been accepted there would have been nothing to read back. They were
sent last, individually, ordered ALLOW → DENY → DISABLE → ENABLE so that any command which did take
effect would leave the run on the *more secure* state.

### Command response latency — measured (owner ruling 14)

**Accepted commands answer in 1.47–2.77 s** (n=5; send ack 0.54–1.83 s, result 0.63–0.94 s after).

Against that: `entity.py` waits **30 s**, roughly 11-20x the observed latency, and the coordinator's
`_poll_command_state` first polls at **5 s** — about 3x the time an answer is actually available. The
subscription still delivers nothing, so that 5 s poll is the real feed and it is what bounds
perceived latency. A first poll at ~1 s with a ~10 s ceiling would match the vehicle's measured
behaviour; the current values were never measured, and are recorded here so the next change to them
is evidence-based. **Not changed in this run** — it is a live-path change and belongs behind its own
gate.

**State vocabulary widened.** `ae06ee9` calibrated only `state 0`. Observed here: **2** for
lock/liftgate/seat-heat, **5** for wake. Still no meaning assigned — `entity.py` treats any `int` as
terminal, which is why every one of these reported correctly.

### Vehicle left as found

Pet mode `Disabled` / `Default` (unchanged — both commands rejected). Park, speed 0, all closures
closed, `lock.r1t_closures` locked, charge-port door open because it is plugged in.

### Recorded limitations the table above does not carry

**`OPEN_LIFTGATE` — accepted, and that is a send-path result only.** An R1T has no liftgate, so
nothing could move and no reversal was required or performed. The recorder confirms nothing did:
`binary_sensor.r1t_tailgate` stayed `off` across 12:29-12:38. Acceptance proves the command is
routable and the signing material is good; it says nothing about a physical effect, and cannot on
this vehicle.

**`START_VIDEO_DOWNLOADING_SESSION` — rejected, and its reversal is undefined regardless.** There is
no stop command in `VehicleCommand` and no state field anywhere for it, so had it been accepted there
would have been no way to end the session or observe that it had started. It is grouped with the four
`TWO_FACTOR_DRIVE_*` commands as a no-state-surface command, not with the reversible ones.

## CORRECTION to the race table below — run 1's "state 2" was NOT terminal

`scripts/probe_vehicle_command.py` tested `state not in (None, "in_progress", "pending")` — a
**string** test against a server that answers with an **integer**. Every integer therefore read as
terminal, so run 1's `state 2` was printed as `TERMINAL` and recorded here as one. It is not:
**2 is in the app's continue set** `{1,2,3,5}` (`C4171i`'s switch, `C2225j`'s terminality test).

This is the same defect class the integration itself carried until this release — an instrument
built to investigate a bug, carrying the bug. The probe now uses the app's integer vocabulary.

**What survives the correction:** runs 2 and 3 returned **state 0**, which IS terminal. Those two
observations — both `WAKE_VEHICLE`, both via the poll — are the only genuine terminal command states
ever recorded in this project. The subscription has never been observed delivering one. That is
recorded as the accepted risk of removing the poll, and it is answerable by one probe run rather
than by field data.

## The command-state subscription DOES deliver — `ae06ee9`'s premise corrected, 2026-08-19

`ae06ee9` recorded: *"the vehicleCommandState SUBSCRIPTION never delivers, so nothing populates
`_command_states`"*, citing a debug log showing it *"established and torn down with no message in
between"*, and added `_poll_command_state` alongside it. **Measured three times on beta7, it
delivers every time.**

Method: pre-warm the websocket (so subscribe latency is not dominated by connect), send
`WAKE_VEHICLE`, subscribe to the returned `command_id`, and race the subscription against the same
poll the coordinator runs.

| Run | subscribe established | poll terminal | subscription frame |
|---|---|---|---|
| 1 | t+2.02 s | t+2.75 s (state 2) | **t+3.86 s** |
| 2 | t+1.80 s | t+2.64 s (state 0) | delivered |
| 3 | t+0.85 s | t+1.56 s (state 0) | delivered |

**What the race table does not record.** The fourth column, *"subscription frame"*, carries
`t+3.86 s` for run 1 and the bare word **"delivered"** for runs 2 and 3. **It never records the
`state` the delivered frames carried.** The `state` values in the table — `2`, `0`, `0` — are all
in the **poll terminal** column, and the poll is what this plan removes. Do not read "delivered"
as "delivered a terminal state".

- **run 1's poll terminal is mislabelled.** `2` is in the continue set {1,2,3,5}. The probe's
  string test called it terminal. Runs 2 and 3, at state `0`, are genuinely terminal — and are
  the only observations of a terminal command state anywhere in this repository. Both came from
  the poll.
- therefore **no terminal state has ever been observed on the subscription**, on any run, by
  any instrument.

The raw logs do not survive. There is no race script in the tree, none in git history, and no
captured output among the untracked/ignored files. The frames were observed by an ad-hoc script
whose output went to a terminal that is gone. The state must be re-measured, not recovered.

The frame carries the full `vehicleCommandState` payload — `id`, `command`, `state`, `responseCode`,
`statusCode`.

**What this means for the fix.** `ae06ee9` found two defects and said either alone would time out
every command. The second — the wait loop testing `state in ["COMPLETED_SUCCESS", …]`, strings,
against an **integer** — is now the one that carries the whole explanation: the subscription was
populating `_command_states` all along, and the loop simply never recognised what it held. The
polling added alongside is **redundant for correctness**. It is not useless — it answers ~0.7-1.1 s
sooner than the subscription in every run measured — but "the subscription never delivers" is not
why commands timed out, and should not be relied on as a reason to keep the poll.

Not changed here. Removing or retuning the poll touches the live command path and wants its own
gate, its own beta and its own live confirmation. Recorded so the next change to that path starts
from a measurement rather than from a claim that no longer holds.

### The integer states are not all terminal — the latency figures above measure the wrong thing.

Read off the app, 2026-08-19, from the 3.6.0 tree. `C4171i.java:524-554` switches on the integer
`state` from the `vehicleCommandState` subscription and builds one of nine result objects.
`C2225j.java:147-167` then decides whether the command is finished: it keeps subscribing on
states **1, 2, 3, 5** (continue set) and completes on states **0, 4, 6, 7** and anything
outside 0-7 (terminal set).

`entity.py:196` returns on any integer, so the integration reports a command complete on the
first frame it catches, including the four the app keeps waiting on.

**All five of the f7 latency rows are continue-set frames** — states 5, 2, 2, 2, 2 — so
**zero of five reached a terminal state**. The existing f7 results table and its numbers are
left unedited. Those "Send→terminal" figures measure time-to-first-frame, not time-to-terminal,
and **terminal latency is unmeasured**.

The only recorded state-0 observations in this document are the poll's terminal reads on
`WAKE_VEHICLE` in the three-run race above. No name is assigned to any integer: the
obfuscated class names carry no words. Terminality is asserted; meaning is not.

The app special-cases `WAKE_VEHICLE` and completes on the first frame whatever the state
(`C4171i.java:559-569`). Under the shape that ships, the integration returns on the first
frame for every command, so that special case is subsumed rather than replicated.

## Step 13 — terminal latency MEASURED on beta8, 2026-08-19 ~18:55 CDT

**The subscription delivers terminal frames. The open question this release shipped with is
answered, and the answer vindicates removing the poll.**

Measured against deployed beta8, `WAKE_VEHICLE`, websocket pre-warmed so the race is fair:

| Run | poll terminal | subscription frames | state | subscription terminal at |
|---|---|---|---|---|
| 1 | t+1.59 s (state 0) | 2 | **0 — TERMINAL** | **t+2.35 s** (second frame t+8.99 s) |
| 2 | t+1.50 s (state 0) | 1 | **0 — TERMINAL** | **t+3.38 s** |

Before this, no terminal command state had ever been observed on the subscription — the only two in
the whole project came from the poll, and the risk accepted under ruling 15 was that removing the
poll removed the only thing that had ever seen one. **It did not.** The subscription carries the
terminal state, 0.8-1.9 s behind the poll.

### The corrected probe changed what a measurement means

The same run shows why the instrument had to be fixed first. A `WAKE_VEHICLE` on a sleeping truck:

```
t+14.66s  state 5   <- CONTINUE. The old string test printed "TERMINAL" here.
t+15.64s  state 0   <- actually terminal
```

The old `state not in (None, "in_progress", "pending")` test would have stopped at 14.66 s and
recorded a continue-state as the answer — off by a second, and wrong about what it had seen. Every
latency number recorded before `f9b663e` should be read as time-to-first-frame.

### What this does and does not license

**Does:** it retires the accepted risk of ruling 15. The subscription is a sufficient source; the
poll was redundant, as the app's own design implied (`vehicleCommandState` in 18 APK files,
`getVehicleCommand` in zero).

**Does not:** license lowering the 30 s ceiling. All five observations here are `WAKE_VEHICLE`, and
the app **special-cases** exactly that command — `C4171i` completes on the first frame when the
command is `WAKE_VEHICLE`, whatever the state. No non-wake command has been observed reaching
terminal. The ceiling stays until one is. `f9.sh` enforces this mechanically rather than by
convention.

---

## Step 7 — ruling 25 VERIFIED: the read-through is live, measured through Home Assistant

Run date **2026-08-20**, all times UTC, production instance. Gate 5A was taken as **option (a)** by the
owner — the truck was unlocked, and the send locks it. Every value below is from the run, not from a plan.

### Gate 5A, re-measured

| | |
|---|---|
| `lock.r1t_closures` re-measured | `unlocked` @ **`11:07:14Z`** |
| Send | **`11:07:14Z`** — **delta 0 s** against the 600 s rule |
| `usable_closure_count` / `total_closure_count` | **10 / 10** |
| `state_is_partial` | **`false`** — no pre-existing partial-lock finding |

The `unavailable` hazard was real and was dodged rather than designed away: the same entity was
`unavailable` at `09:14:17Z`, ~1 h 50 m before the gate.

### Route B, proved for the first time

`GET /api/states/lock.r1t_closures` @ `11:05:11Z` → HTTP **200**, state `unlocked`, and all five seeded
attributes present at their seeds (`response_code`, `status_code`, `state_frames_seen`, `state_is_lifecycle`,
`final_command_state`). §6.2 recorded this instrument as **NEVER EXERCISED**; it is now proved, and §6.3
row 6's Route A/Route B disagreement check was available for the first time.

### The control — and the accident that made it the real evidence

`button.r1t_wake` pressed through Home Assistant @ `11:05:48.609Z`, truck **asleep**
(`powerState: 'sleep'` confirmed live @ `11:05:32Z`). Command id **`04-309bfe26c94e9a8fe2c3`**, three
`Command <id> state update:` lines carrying that id. **Log instrument PROVED.**

The control was only supposed to prove the log instrument. It proved the entire read-through:

| Time | `state_frames_seen` | `state_is_lifecycle` | `final_command_state` | |
|---|---|---|---|---|
| `11:05:50.648` | 1 | `true` | 2 | ← **service call returns here** |
| `11:05:51.346` | 2 | `true` | 5 | *after* the call returned |
| `11:06:02.369` | **3** | **`false`** | **0** | *after* the call returned — **terminal** |

This is ruling 22's design observed end to end: return on the first frame, track terminality in the
background, attributes settle after the call returns, `state_is_lifecycle` flipping `true → false` exactly
when the terminal state arrives.

**A property of this control worth recording:** the wake button is **self-extinguishing on success.** At
`11:06:03.876Z` the truck was awake, so `button.py:44-46`'s `connectivity_state() is SLEEPING` availability went false and
the attributes collapsed to `{"friendly_name": "R1T Wake"}`. Its settled values were recoverable **only**
from Route A. A Route-B-only run would have lost them — which is the argument for two routes, arriving from
a direction §6.2 did not anticipate.

### The one send

`lock.lock` on `lock.r1t_closures` @ `11:07:14.446Z`. Command id **`04-882106fb781c57e63f88`**.

```
11:07:15.670  state 2   responseCode None  statusCode None
11:07:17.842  state 3   responseCode None  statusCode None
11:07:22.193  state 0   responseCode 264   statusCode 0     <- TERMINAL
```

Entity `locked` @ `11:07:21.676Z`. Settled: `state_frames_seen: 3`, `state_is_lifecycle: false`,
`final_command_state: 0`. Post-state **`usable_closure_count: 10`, `total_closure_count: 10`,
`state_is_partial: false`**; all ten `LOCK_STATE_ENTITIES` members `off`, **zero `unknown`** — no SNA member
on this run, and no partial-lock finding.

**Route A and Route B agree exactly** on every settled value. §6.3 row 6: no disagreement.

### Verdict — §6.3 row 1

`state_frames_seen ≥ 1`, `state_is_lifecycle ∈ {true,false}`, `final_command_state` an integer.
**CRITERION 4 PASSES. THE READ-THROUGH IS LIVE.** Ruling 25 is verified. This is the one part of beta8
whose runtime behaviour nobody had observed, and where the Critical lived — the read-through key that
would have shipped dead. It did not ship dead.

### Ruling 14 output — NON-CEILING-BEARING, n=1

| Command | Path | Power state at send | Send→first frame | Send→terminal | States |
|---|---|---|---|---|---|
| `LOCK_ALL_CLOSURES_FEEDBACK` | integration | awake | **1.224 s** | **7.747 s** | 2 → 3 → 0 |
| `WAKE_VEHICLE` (control) | integration | **asleep** | **1.584 s** | **13.758 s** | 2 → 5 → 0 |

`LOCK_ALL_CLOSURES_FEEDBACK` is the **first non-wake command ever observed reaching a terminal state** on
this integration; the previous record was 0 of 5, all continue states. It is **an input to nothing** and is
not cited in the ceiling decision.

### A new defect, found by this run: `response_code` and `status_code` are frozen at the first frame

The terminal frame carried `responseCode: 264, statusCode: 0`. The entity reported
**`response_code: null`, `status_code: null`** — verified on both routes.

Cause, traced: `entity.py:155-160`'s live block refreshes only `state_frames_seen`, `state_is_lifecycle`
and `final_command_state` from the coordinator record. `response_code` and `status_code` come from
`_last_command_status`, which `entity.py:209-217` writes **once, from the first frame** — and the first
frame is a continue state whose codes are always `None`. The background terminality tracking never
revisits them.

**The data is already present**: `coordinator.py:1538-1539` keeps `responseCode` and `statusCode` on every
frame, terminal included. The fix is two lines in the block at `entity.py:155-160`.

This defeats the stated purpose of the round-2 decision that added the two attributes — *"`responseCode 288`
vs `None` is what distinguished a real answer from silence when diagnosing `ae06ee9`"* — because on the
shipped code they are `null` for any command whose codes arrive after the first frame, which is every
command observed so far. **Not fixed here** (P1: Step 7 is a measurement step). Carried to
`.omc/plans/open-questions.md`.

### Instrument honesty note — a vacuous pass, caught

Criterion 9's first check returned "0 debug lines after the reset" from a window that contained **zero lines
of any kind**, because silencing `custom_components.rivian` silenced the entire log. The count was vacuous
and was nearly recorded as a pass. Re-proved on its positive case: the same filter returns **100** on a
pre-reset window and **0** on the post-reset window. Criterion 9 passes on the second, arm-proved reading.

This is the same failure shape as the `scripts/f8_probe.py` parsing defect that prompted ruling 23 — an
instrument returning a clean-looking answer without ever having been shown it can return a dirty one.

---

## Step 8 — the ceiling decision, from first principles

**Prerequisite was Step 6 only.** Ruling 27 decides this from `entity.py:180`, not from a measurement.

### The rule, proposed for ratification (§5.1), re-keyed to first-frame latency

The governed quantity is **first-frame arrival**, per `entity.py:180` — the timeout that waits for the
*"first well-formed frame"* — and `entity.py:227-238`, which returns on the first non-empty
`get_command_state`.

> **The first-frame ceiling — `COMMAND_TIMEOUT_AWAKE` / `COMMAND_TIMEOUT_SLEEPING` in
> `custom_components/rivian/entity.py`, 30 s at the time this rule was written — may be lowered only when
> all of the following hold:**
> 1. **n ≥ 5** first-frame observations of **non-`WAKE_VEHICLE`** commands from the shipped integration path.
> 2. across **≥ 2 distinct commands** — one command's server-side handling is not the population.
> 3. across **≥ 2 distinct vehicle power states** (asleep at send, awake at send).
> 4. the proposed ceiling is **≥ 4x the observed maximum first-frame latency across both power states**.
> 5. **zero** observations in the set failed to produce a first frame within the current ceiling.
>
> **If any condition fails, the ceiling stays where it is and the rule is not re-argued.**

### The five conditions against the record, after Step 7

| # | Condition | Status | Evidence |
|---|---|---|---|
| 1 | n ≥ 5 non-wake | **MET — n = 5** | `:216` 1.75 s, `:217` 2.77 s, `:218` 1.48 s, `:219` 1.47 s, **+ Step 7's `LOCK_ALL_CLOSURES_FEEDBACK` 1.224 s** |
| 2 | ≥ 2 distinct commands | **MET** — 4 distinct | as above |
| 3 | ≥ 2 power states | **NOT MET** | all five non-wake observations are warm-path. Step 7's send was at `11:07:14Z`, ~70 s after the truck woke |
| 4 | proposed ≥ 4x observed max | **not evaluable** | condition 3 unmet, so the cross-power-state max is unknown |
| 5 | zero first-frame failures | **MET** for the warm set | — |

**Step 7 moved condition 1 from NOT MET to MET and did not touch condition 3, which is the one that binds.**

`NON-WAKE FIRST-FRAME LATENCY MEASURED: LOCK_ALL_CLOSURES_FEEDBACK` — 1.224 s, integration path,
2026-08-20. Recorded as the measurement only. The ceiling is **not** ratified, so `f9.sh`'s interlock
remains pinned; it needs both tokens and has only one.

### Conclusion

**CEILING UNCHANGED — 30 s, first-frame ceiling, n=5 non-wake warm + 1 cold-path observation.**

Stated on its ground, as a result and not as silence:

- the ceiling governs **first-frame arrival only** — `entity.py:180`, `:227-238`;
- warm-path first-frame latency is **1.224-2.77 s** across five non-wake observations;
- cold-path first-frame latency is observed at **14.66 s** (`:425-427`), giving the 30 s ceiling **~2.05x**
  headroom over the largest first-frame latency ever observed — *provenance limitation:* that figure is from
  `scripts/probe_vehicle_command.py`, not the integration path;
- therefore 30 s costs a user nothing except on a wholly silent subscription, where it is the only thing
  that ends the wait at all.

`custom_components/rivian/entity.py` is **not edited**; `timeout: int = 30` stands.

**Supersedes, visibly (ruling 9 house style):** `:285`'s *"roughly 11-20x the observed latency"* compares the
ceiling against the warm-path range alone and is wrong about the headroom. The correct figure is ~2.05x, and
a 10 s ceiling — floated at `:288` — would have timed out the cold-path command at 14.66 s.

### A cold-path datum from Step 7 that bears on the provenance limitation, n=1

Step 7's control was a `WAKE_VEHICLE` sent **through the integration path** to a **sleeping** truck — the
same command and same power state as the 14.66 s probe-path figure, differing only in path.

| Observation | Path | First frame |
|---|---|---|
| `:425-427` `WAKE_VEHICLE`, asleep | probe | **14.66 s** |
| Step 7 control `WAKE_VEHICLE`, asleep | **integration** | **1.584 s** |

**This is not entered into the ceiling decision and changes nothing above.** It is n=1 against n=1, and
condition 1 excludes `WAKE_VEHICLE` from the governing set precisely because the app special-cases it. It is
recorded because it is the first evidence that the cold-path 14.66 s may be a **probe-path artefact** rather
than a property of the vehicle — and §5.1 names "gather cold-path integration-path data and discover the
true maximum is much lower" as one of the two honest ways to make the rule satisfiable. If that holds up
under more observations, condition 4's implied `≥ 58.6 s` floor falls with it. **One observation is not that
evidence.** Carried to `.omc/plans/open-questions.md`.

---

## Step 9 — the ceiling raised to 60 s / 120 s

**This supersedes Step 8's "CEILING UNCHANGED — 30 s" conclusion, visibly (ruling 9 house style).** Step 8
answered the question it was asked — *may the ceiling be **lowered**?* — and the answer there stands: no,
condition 3 was never met and is not met now. This is a **raise**, which Step 8's rule does not govern. The
rule's *implementation* in `f9.sh` was a direction-blind fixed-string pin on `timeout: int = 30`, so it fired
on a raise anyway; it has been **re-keyed, not disarmed** (see the interlock note below).

`custom_components/rivian/entity.py` now declares:

```python
COMMAND_TIMEOUT_AWAKE: Final = 60
COMMAND_TIMEOUT_SLEEPING: Final = 120
```

resolved per the vehicle's derived connectivity state, with an explicit `timeout=` argument still winning.

### (a) These are not the same quantity, and the mapping is a decision, not a measurement

The quantity governed here is **first-frame arrival** inside a blocking Home Assistant service call — the
loop returns on the first well-formed frame, so the ceiling bites only on total silence. The app's 60 s /
120 s (`C5332Z.java:242` / `:254`, selected at `:821`; full table at `C5323P.java:110-114`) is a
**whole-command give-up timeout**, in a UI that shows its own live progress affordance while it runs. The
app is **silent** on first-frame ceilings.

So the numbers were carried across from a different quantity **by owner decision, to mirror the app**. That
is the whole justification and it is stated as such. No measurement in this document implies these values.

### (b) The honest worst case

| Path | Before | After |
|---|---|---|
| Awake | 30 s | **60 s** |
| Sleeping | 30 s wake-wait + 30 s ceiling = 60 s | **120 s** |

A user pressing a control against a wholly silent subscription now watches the entity spin for up to two
minutes instead of one. Step 8's own conclusion — that the ceiling *"is the only thing that ends the wait at
all"* — is what makes this a real cost rather than a theoretical one. It is accepted because the 30 s
blocking wake-wait at `coordinator.py` has been deleted in the same change: wake latency now lands *inside*
the first-frame window rather than in front of it, and the cold-path first-frame observation in this
document is 14.66 s.

### (c) Condition 4 is cleared by the sleeping ceiling only

Run Step 8's condition 4 (`≥ 4x observed max first-frame`) **per power state**, which is exactly what
condition 3 exists to force:

| Path | Observed max first-frame | 4x floor | Before | After |
|---|---|---|---|---|
| Awake | **2.77 s** (`:216-219`, n=5, range 1.224–2.77 s) | **11.1 s** | 30 s (~11x headroom) | 60 s |
| Sleeping (cold) | **14.66 s** (`:610`, probe-path provenance) | **58.6 s** | 30 s (~2.05x) | 120 s |

**The sleeping raise is earned by the record**: 30 s did not clear its own 58.6 s floor and 120 s does.
**The awake raise is not.** 30 s already gave roughly 11x headroom over every awake observation in this
repo. Attributing the awake raise to condition 4 would mean applying the *cold* maximum to the *awake*
ceiling — the precise cross-population substitution condition 3 forbids. The awake raise is for symmetry
with the app, and nothing else.

The 14.66 s figure keeps its probe-path provenance limitation, and the n=1 integration-path counter-datum
above (1.584 s) still does not overturn it.

### The interlock

`f9.sh`'s ceiling interlock is **re-keyed to the new constants, never disarmed.** Both ratification-token
greps and the relaxation branch are untouched, so the *lowering* interlock is exactly as armed as it was
before this change: this document still does not contain the owner-ratification token, and it is not
supposed to — nobody has ratified a lowering. Pinned by
`tests/test_command_state.py::test_the_gate_requires_both_tokens` and
`::test_the_lowering_interlock_is_still_armed`.

---

# s17 — the sleeping-vehicle wake path, actuated live

**Run:** 2026-08-21 05:51 CDT, production Home Assistant at `root@192.168.1.5`, integration
`1.6.0-beta9` deployed from the published release artifact (md5 verified byte-identical to
the zip HACS installs). Vehicle: R1T, MY2022, genuinely asleep.

**Verdict: PASS.**

## Why this run had to happen

Every other claim in beta9 is proven in-process: 1735 unit tests, a 15-cell truth table for
`derive_connectivity_state`, and sixteen gates. **One was not.** That the cloud accepts a
command sent immediately behind an *unconfirmed* `WAKE_VEHICLE` rested entirely on
inference from the decompiled app (`C2150e.java:212-215`), never on observation. The code
shipped to beta users with that gap named and tracked rather than papered over.

## What was observed

Verbatim, `custom_components.rivian` at debug:

```
05:51:23.739  Sending command LOCK_ALL_CLOSURES_FEEDBACK with params: None
05:51:23.739  Sending command WAKE_VEHICLE with params: None
05:51:24.834  WAKE_VEHICLE command sent with ID: 04-244cc6e33394ca8012ea
05:51:25.658  Command 04-244cc6e33394ca8012ea state update: {...}
05:51:25.859  LOCK_ALL_CLOSURES_FEEDBACK command sent with ID: 04-5441431def843f24873e
05:51:26.188  Command 04-5441431def843f24873e state update: {...}
05:51:27.253  Command 04-5441431def843f24873e state update: {...}
05:51:38.656  Command 04-5441431def843f24873e state update: {...}
05:51:38.910  Vehicle 01-276948064 data update gap: 2.0 minutes (powerState: sleep)
05:51:39.766  Command 04-5441431def843f24873e state update: {...}
```

| Threshold | Result |
|---|---|
| The vehicle was actually asleep | **yes** — the coordinator's own watchdog line reads `(powerState: sleep)` |
| Connectivity resolved `SLEEPING`, not `ONLINE` | **yes** — otherwise no wake would have been dispatched at all |
| The wake is dispatched without blocking | **yes** — both `Sending command` lines carry the **identical** timestamp `05:51:23.739` |
| No ~30 s stall (the pre-beta9 blocking wait) | **confirmed absent** — press to command-on-the-wire was **2.1 s** |
| The cloud accepted the command behind an unconfirmed wake | **yes** — first state frame for the lock at `05:51:26.188`, four frames total |
| The vehicle woke | **yes** — `powerState` went `sleep` → `standby` (`10:51:35.899Z`) → `ready` (`10:51:41.100Z`) |

## The ordering, which is better than the app's

The wake's send *returned* at `05:51:24.834`; the lock went out at `05:51:25.859`. The Python
awaits the wake's own HTTP round trip before signing the requested command, so **the wake
provably reaches the cloud first**. `C2150e.java:212-219` builds the command flow, fires the
wake, and collects with no await between them — no ordering guarantee at all. This
implementation is strictly safer than the one it mirrors, a point raised in code review and
now confirmed on the wire.

## What this run does NOT establish

- The 120 s `COMMAND_TIMEOUT_SLEEPING` ceiling was never approached — the first frame arrived
  in 0.3 s, so the raised ceiling remains exercised only by unit tests. That is the expected
  outcome, not a gap: the ceiling exists for the slow case, and this was not one.
- One command, one vehicle, one sleep state. It is an existence proof that the cloud accepts
  the sequence, not a distribution.

## Incident during setup, recorded rather than omitted

The beta8 backup was first written to `/config/custom_components/rivian.beta8.bak`. Home
Assistant scans that directory and parsed the dots as a module path, so setup failed with
`ModuleNotFoundError: No module named 'custom_components.rivian.beta8'` and **the integration
was down from 21:07 to 21:19** (~12 minutes) on the production instance. Moving the backup to
`/config/rivian_backups/` and restarting restored it. A backup belongs outside any directory
Home Assistant enumerates; `custom_components/` is exactly such a directory.
