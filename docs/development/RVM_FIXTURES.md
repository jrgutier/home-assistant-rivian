# Parallax RVM payload fixtures (s08a)

Captured from the live vehicle on 2026-08-18. Fixtures live in
`rivian-python-client/tests/fixtures/parallax/`.

## How they had to be captured

Two things were learned the hard way and both change the procedure:

1. **The payload does not come back from the mutation.** `sendVehicleOperation`
   selects only `{ success }` (`rivian.py:857-861`). `prd.json` s08a previously
   claimed the four RVMs were "verified-working QUERIES today, so the existing query
   path suffices" — that is false. The payload arrives *only* on the
   `parallaxMessages` websocket subscription.

2. ~~**The gateway permits exactly one active subscription per user session.** With
   Home Assistant running, a second `connection_init` on the same `u-sess` is
   accepted, never acknowledged, and closed at TTL with `4420 Connection TTL
   expired`. A *malformed* token by contrast gets `4403 Forbidden` in ~0.5 s. So
   capture must run as **sole subscriber**: disable the HA config entry
   (`config_entries/disable`, `require_restart: false`), capture, re-enable.~~

   **RETRACTED 2026-08-20 — FALSIFIED by measurement (claim C8).** Arm 3b received
   the **full 33-topic RVM set with production subscribed**, and arm 3c received a
   `connection_ack` on a second connection with Home Assistant up, in 0.0 s. The
   "accepted, never acknowledged" half is false. **Capture does NOT require sole
   subscriber and does NOT require an outage** — it can be scheduled against a
   running production instance. The `4420` TTL close is real but its *cause* was
   never established. See `WS_CONTENTION.md`, claims C8, C1s, C1c and C2.

Identifiers matter too. Three exist and they are not interchangeable:

| Identifier | Value shape | Used by |
|---|---|---|
| `vehicles[0].id` | `01-XXXXXXXXX` | `vehicleState`, `parallaxMessages` |
| `vehicles[0].vas.vasVehicleId` | 36-char UUID | — |
| HA options `vehicle_control[0]` | 32-char hex | HMAC vehicle commands |

`RIVIAN_VEHICLE_ID` in `.env` matched **none** of them and produced
`{"errors":[{"message":"Invalid vehicle ID"}]}`. `phone_id` is
`uuid.UUID(enrolledPhones[0].vas.vasPhoneId).bytes` — **16 bytes**, confirmed
against the live API, and requires `get_user_information(include_phones=True)`.

## Captured

| RVM | File | Bytes | Content |
|---|---|---|---|
| `comfort.cabin.climate_hold_status` | `climate_hold_status.bin` | 8 | `0802100118012200` — f1=2, f2=1, f3=1, f4=empty |
| `comfort.cabin.climate_hold_setting` | `climate_hold_setting.bin` | 3 | `08ac02` — `hold_time_duration_seconds = 300` |
| `vehicle.wheels.vehicle_wheels` | `vehicle_wheels.bin` | 74 | two repeated submessages (34B, 36B) |

`climate_hold_setting` was empty until a hold was written, because the vehicle had
none configured. It was captured by **setting a 5-minute hold and reading it back**,
then clearing it (`duration_minutes=0`) — verified afterwards as
`switch.r1t_climate_hold = off`. This is the plan's single server-verified *write*,
and the round trip validates it end to end:

```
set 5 minutes  -> 08ac02  -> ClimateHoldSetting(hold_time_duration_seconds=300)
clear (0)      -> empty payload
```

It also confirms the docstring's independent claim that 7200 s encodes as `08a038`.

## Not captured: `ota.user_schedule.ota_config`

A **signed GET was accepted** by the server —
`{"__typename": "SendVehicleOperationSuccess", "success": true}` — and returned a
**0-byte payload**, repeatedly, across three separate capture sessions. There is no
OTA install schedule configured on this vehicle.

It is *not* dropped because the RVM is broken. It is dropped because no fixture can
be obtained without one of:

- writing an OTA schedule via an **unverified** write path, which risks scheduling an
  actual software install on the vehicle; or
- a schedule set by hand in the Rivian app, which is an owner action.

Under principle 3 — *no entity without a verified backing operation, and no decoder
for an RVM that does not ship* — the `ota_config` entity is **dropped**, and s08b
must not write `decode_ota_config` against an imagined layout. If an owner later
configures a schedule, re-run the capture and restore the entity.

## Reproducing

`scripts/gates/s08a.sh` asserts each fixture is non-empty, is valid protobuf wire
format, and that `climate_hold_setting` re-encodes byte-identically. The previous
version of that gate checked existence only — **four `touch`ed empty files passed
it**, which is why the non-empty and parse assertions exist.

## Capturing more (s34)

`scripts/capture_rvm_frames.py` subscribes to `parallaxMessages` and writes what
arrives. **It needs no outage.** The sole-subscriber claim above is retracted;
both surveys on 2026-09-01 ran against live production with Home Assistant up.

```sh
.venv/bin/python scripts/capture_rvm_frames.py --all <topic-file> --seconds 180 --write
```

A parked 180 s survey of all 80 topics returned **51 non-empty, 5 empty, 24
silent**. Silence is a recorded outcome, not a failure — `ota.user_schedule.
ota_config` returned 0 bytes across three sessions because no schedule existed.

### The re-run, while driving or charging

The 24 silent and 5 empty topics are in
[`scripts/rvm_topics_active_rerun.txt`](../../scripts/rvm_topics_active_rerun.txt),
derived from the 2026-09-01 survey log rather than transcribed, so it needs no
editing:

```sh
.venv/bin/python scripts/capture_rvm_frames.py \
    --all scripts/rvm_topics_active_rerun.txt --seconds 180 --write
```

The 5 empty are included deliberately: `charging.session.time_estimation`
publishing 0 bytes parked says nothing about what it publishes mid-charge.

**The script is additive.** It skips any topic already in `manifest.json`,
refuses to overwrite an existing `.bin`, and appends new entries to the manifest
itself. That was not true until 2026-09-01 — this section previously said "the
script skips topics already fixtured" while the code wrote
`topic.replace(".", "_") + ".bin"` unconditionally. Running it as documented
would have overwritten every frame the decoder tests assert against. The three
legacy-named fixtures still carry the scars: each has an `alias` recording a
duplicate written under the derived name by an earlier run, and
`comfort.cabin.climate_hold_setting`'s two copies **differ**
(`alias_identical: false`). `TestCaptureRerunIsAdditive` now pins the behaviour.

Afterwards, `git status` shows the new `.bin` files and the manifest change.
Read each frame by hand before committing — see below for why the guard is a
floor and not a proof.

`chargingDisabledAC` wants the same trip but a different tool: it is a
`vehicleState` field, not an RVM, so run
`.venv/bin/python scripts/probe_field_names.py chargingDisabledAC` while
plugged in and drawing AC. It delivered a bare `0` parked, which could be a
flag, a count or an enum's zero arm ([`REMAINING_APK_GAPS.md`](REMAINING_APK_GAPS.md)).

### Three decoders are silent on their own frames (2026-09-02)

The first active re-run added two frames and immediately exposed something the
fixture set had been hiding. Decoding all 32 committed frames through their own
registered decoders, **three return `{}`**:

| topic | why |
|---|---|
| `charging.session.time_estimation` | decoder reads field 1; frame carries field 2 = 64 |
| `security.access.passive_entry_debug` | decoder reads field 1; frame carries field 2 = 2 |
| `comfort.cabin.seat_conditioning_status` | structural — decoder expects the seat position as the OUTER field number (`SEAT_STATUS_FIELDS`, 7–12); the frame is `repeated {1: id, 2: value}` under field 1 |

Every decoder swallows exceptions so one bad frame cannot drop the subscription.
The price is that a decoder on the wrong field number looks exactly like a topic
the vehicle never publishes — both are silence. `TestDecodersProduceSomething`
`FromTheirOwnFrame` now makes it loud: a fourth silent decoder fails the suite.

**This corrects a claim in `const.py`.** `sensor.passive_entry_unlock_fail_reason`
is disabled by default with the reason "arrival UNWITNESSED … an absent value
cannot be told apart from the decoder never firing". The frame *does* arrive —
it is committed here. The decoder reads the wrong field. The entity is disabled
for a reason that turns out not to be the real one.

None of the three is fixed. `charging.session.time_estimation` has no named
schema and 64 is not obviously seconds; `seat_conditioning_status` shows ids 5
and 7 twice with different values, so field 2 is not one level per seat and the
message is not what the decoder models. A decoder built on a guess renders wrong
values as confidently as right ones. Resolving them needs a capture taken
mid-charge and with seat heaters actually running.

### Two classes of personal data, not one

A capture on 2026-09-01 wrote a child's school name, a home wifi SSID, MAC
addresses and account UUIDs to disk. Ten files were deleted. `--write` now
refuses any frame carrying identifier-shaped **text**.

**That guard is not sufficient on its own.** `charging.schedule.time_window`
carried a GPS coordinate as two f64 doubles inside a nested `WindowData.location`
submessage. IEEE-754 has no printable run, so every text-shaped check passed it,
and the fixture reached a pushed commit on a public repository before anyone
noticed. It was removed by history rewrite.

So a capture run has to expect both:

| class | looks like | caught by |
|---|---|---|
| text | place names, SSIDs, MACs, UUIDs | `carries_identifiers()`, and the ship-time string tests |
| binary | coordinates as f64 pairs | the negative-f64-beyond-90° test in `test_parallax_fixture_manifest.py` |

The numeric guard keys on a **negative** double beyond 90°, not on magnitude:
magnitude alone flagged `energy_high_voltage_battery_state`, whose 45.6 and
124.695 are state of charge and range. It does not catch eastern-hemisphere
longitudes, which are positive. Treat both guards as a floor. **Before committing
any new fixture, decode it and look at what the fields actually mean** — the
schema in `rivian_client/proto/` will name a `location` field if one is there.

## Decoding is not wiring — the s34 follow-up, closed 2026-09-03

s34 shipped four decoders and deliberately no entities, leaving "whether any
decoded RVM becomes an entity" as an open question. **Answered: all four are
wired**, as eleven entities (s40).

| decoder | entities | gate |
|---|---|---|
| `comfort.cabin.cabin_ventilation_setting` | 1 binary_sensor + 4 sensors | `AUTO_VENT` |
| `gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent` | 1 sensor | `V_GGVS` |
| `gearguard_streaming.privacy.gearguard_streaming_daily_limit` | 2 sensors | `V_GGVS` |
| `energy_edge_compute.graphs.parked_energy_distributions` | 3 sensors | `ENRG_MONTR_PARK` |

All eleven ship **enabled by default**, because the convention here is arrival,
not churn: five of the older Parallax-only fields ship enabled and the line
between them is whether the message is proven to arrive. All four of these have
committed fixtures captured from the live truck.

`parked_energy_distributions` emits three nested window dicts of ten keys each.
Thirty entities would invent thirty names for ten concepts, so it ships as three
sensors — one per window — each reading `totalKwh` directly (it is field 1 of
`_ENERGY_DISTRIBUTION`, never a sum of the components) with the other nine keys
as attributes.

**This changed no subscription.** `SUBSCRIBED_RVMS` derives from `RVM_DECODERS`,
and s40 added no decoder: 37 before, 37 after, byte-identical. That is what
separates this from s34, which was a live-behaviour change.

### The residual risk, recorded rather than assumed away

Gating is the convention — every entity-creating platform except `switch.py`
already filters through `vehicle_supports` — but `helpers.py` records two ways it
misfires, and one of them is live here.

**No community vehicle advertises `AUTO_VENT`.** `issue-222` and `issue-245` both
carry `V_GGVS` and `ENRG_MONTR_PARK`; `issue-171` carries none of the three; none
carries `AUTO_VENT`. Our own truck does, which is the only reason this is not
already the `TONNEAU_CMD` pattern — a flag nobody advertises, hiding a feature
that works for everybody.

So: **if cabin ventilation turns out to work on a vehicle that does not advertise
`AUTO_VENT`, the cabin-vent gate is wrong and should be removed.** That is a
falsifiable claim and `TestGatingMeasuredOnOtherVehicles` pins the flag
distribution so the day it changes, a test says so.

A planning note said `issue-245` carried all three flags. It does not; it carries
two. Measured, not assumed — which is why the number is in a test.
