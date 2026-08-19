# The Parallax subscription gateway allows one connection per user session

**Measured 2026-08-18** against `wss://api.rivian.com/gql-consumer-subscriptions/graphql`.

## Why this document exists

A long debugging session concluded that "the Parallax websocket is broken — it
connects but is never acknowledged, so the integration's entire real-time path is
dead." **That conclusion was wrong**, and the way it was wrong is worth recording,
because the same trap is still there for the next person.

The gateway permits **exactly one active subscription per user session token**.
Home Assistant holds it. Every local probe was therefore a *second* connection,
which the server accepts, never acknowledges, and closes at TTL.

## The experiment

The Rivian config entry was disabled through Home Assistant's websocket API
(`config_entries/disable`, `require_restart: false`), leaving no incumbent
subscriber, and the identical probe was re-run.

> **RETRACTION NOTICE, 2026-08-19.** The row below claiming `connection_ack` immediately
> followed by a `next` frame when no incumbent holds the subscription **was not reproduced by f8**.
> With the HA entry disabled and the probe as sole subscriber, `connection_ack` arrived but **no
> data frame followed** — zero fields in 30 s, and zero again after a `WAKE_VEHICLE` that returned
> terminal in 1.87 s. Consequently the "accepted but silent" signature does **not** distinguish
> contention from "this client does not receive what the integration receives". See
> `UNPOPULATED_FIELDS.md`, section "f8 attempted 2026-08-19". Do not rely on the table below to
> interpret silence.

| Condition | `connection_init` result |
|---|---|
| HA running (incumbent holds the subscription) | accepted, **no ack**, held ~180 s, `CLOSE 4420 Connection TTL expired` |
| HA entry disabled (no incumbent) | **`connection_ack` immediately**, then a `next` frame — twice, consecutively |

The entry was re-enabled in a `finally` block; it returned to `state=loaded` and
telemetry resumed within ~25 s.

## What was ruled out first

Twenty variants, all still unacknowledged while HA held the subscription:

- a freshly minted `a-sess` from `create_csrf_token`, plus `csrf-token`
- reusing the same `aiohttp` session so cookies carried over
- `BASE_HEADERS`, `User-Agent`, `Apollographql-Client-Name` on the upgrade
- `client-version` removed, and bumped to a much newer value
- `client-name` set to the Android app's identifier
- `dc-cid` removed; `u-sess` capitalised; `u-sess` alone; an **empty** payload

The `u-sess` in `.env` is byte-identical (SHA-256) to the one the working
instance uses, so credentials were never the discriminator.

## Close codes, measured rather than assumed

| Code | Reason | Meaning |
|---|---|---|
| 4401 | `Unauthorized` | something was sent before `connection_ack` |
| 4403 | `Forbidden` | malformed `u-sess`, ~0.5 s after init |
| 4408 | `Connection initialization timeout` | no `connection_init` arrived |
| 4420 | `Connection TTL expired` | routine recycling of a healthy connection |

Two of these misled the original diagnosis:

- **4401 was read as "our credentials are rejected."** It is the
  graphql-transport-ws response to sending any message before the ack — which the
  probe deliberately did. It carried no information at all.
- **A *malformed* token gets 4403 in half a second, while a valid-but-duplicate
  connection gets silence.** That asymmetry is what made "expired credentials"
  look plausible. It is really "the session resolves, but it already has a
  subscriber."

## Consequences

**Fixture capture must run as sole subscriber.** `s08a` cannot be done from a dev
machine while Home Assistant is running. Disable the entry, capture, re-enable.

**`sendVehicleOperation` does not return the payload.** Its mutation selects only
`{ success }` (`rivian.py:866-870`), so the RVM payload arrives *only* on the
`parallaxMessages` subscription. `prd.json` s08a previously claimed the four RVMs
were "verified-working QUERIES today, so the existing query path suffices"; that
was false and has been corrected.

**Identifiers are not interchangeable.** Three exist:

| Identifier | Shape | Used by |
|---|---|---|
| `vehicles[0].id` | `01-XXXXXXXXX` | `vehicleState`, `parallaxMessages` |
| `vehicles[0].vas.vasVehicleId` | 36-char UUID | — |
| HA options `vehicle_control[0]` | 32-char hex | HMAC vehicle commands |

`RIVIAN_VEHICLE_ID` in `.env` matched none of them and produced
`{"errors":[{"message":"Invalid vehicle ID"}]}`. `phone_id` is
`uuid.UUID(enrolledPhones[0].vas.vasPhoneId).bytes` — **16 bytes** — and requires
`get_user_information(include_phones=True)`; the default query omits
`enrolledPhones` entirely, which briefly looked like "no phone enrolled".

## What the client does about it

`ws_monitor.py` now distinguishes these codes: 4401/4403 stop the monitor and log
at error, because reconnecting walks into the same rejection; 4420 is treated as
the routine recycling it is. Previously only the reason string `"Unauthenticated"`
was recognised — none of the real codes — so an auth rejection was retried
forever, and because the backoff counter reset whenever the socket merely
*opened*, it was retried with no backoff at all.

## Reproducing

Disable the entry, probe, re-enable, and confirm recovery by `state=loaded` **and**
fresh recorder rows — not by the API result alone. If the re-enable fails: retry,
then `config_entries/reload`, then as a last resort `ha core stop` → edit
`disabled_by: null` in `/config/.storage/core.config_entries` → `ha core start`.
That order matters: Home Assistant holds config entries in memory and flushes them
on shutdown, so a graceful restart would overwrite a hand-edit before reading it.
