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

### Separate finding: two lock signals disagree

`binary_sensor.r1t_locked_state` read `on` before the run and `off` after, while
`lock.r1t_closures` read `unlocked` before and `locked` after. They disagree in
both directions, so at least one is wrong or stale. Recorded, not chased.

Final state: all closures closed except the charge-port door (plugged in), Park,
speed 0, Gear Guard armed, `lock.r1t_closures` locked.
