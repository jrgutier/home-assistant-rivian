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

| Command | Disposition | Send→terminal | state |
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
