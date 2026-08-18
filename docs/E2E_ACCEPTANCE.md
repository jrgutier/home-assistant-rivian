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
| All four tyre pressures hold values | **3.4 / 3.38 / 3.4 / 3.4** |
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
   subscription then delivered nothing: no battery level, no odometer, no tyre
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
