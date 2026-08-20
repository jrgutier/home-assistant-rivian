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
