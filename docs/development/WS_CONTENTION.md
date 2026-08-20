# Parallax websocket contention — and two superseded accounts of it

**Measured 2026-08-18** against `wss://api.rivian.com/gql-consumer-subscriptions/graphql`,
re-measured 2026-08-20.

> **This document's own title used to read "The Parallax subscription gateway allows one
> connection per user session."** That is claims **C1s** and **C1c**, and the register
> below **FALSIFIES both** — see their rows in §"the claim register". The gateway does
> *not* limit a user session to one subscription, and a second connection is *not*
> silently dropped. The title is corrected here rather than deleted, because a document
> whose headline asserts what its own table refutes is worse than one that says it
> changed its mind.
>
> Cited by claim ID, not line number, deliberately: this edit moved every row below it,
> which is the failure mode `scripts/gates/f9.sh` was re-keyed to avoid.

## Why this document exists

A long debugging session concluded that "the Parallax websocket is broken — it
connects but is never acknowledged, so the integration's entire real-time path is
dead." **That conclusion was wrong**, and the way it was wrong is worth recording,
because the same trap is still there for the next person.

The replacement account was:

> The gateway permits **exactly one active subscription per user session token**.
> Home Assistant holds it. Every local probe was therefore a *second* connection,
> which the server accepts, never acknowledges, and closes at TTL.

**That account is also wrong.** It is the second superseded explanation, not the
answer — and the claim register below falsifies both of its halves:

- **C1s** — *one active subscription per user-session token*. **FALSIFIED, statically.**
  `rivian.py:145` runs a single monitor multiplexing `rivian.py:146` `_subscriptions`, and
  `subscribe_for_vehicle_updates`, `subscribe_for_parallax_messages` and `subscribe_for_cloud_connection` in `coordinator.py` open three concurrent subscriptions on one
  `u-sess` every day this integration runs.
- **C1c** — *every local probe was a second connection, accepted, never acked, closed at
  TTL*. **FALSIFIED live.** Arm 3a: a second `vehicleState` subscription was **accepted**
  and control passed (≥100 fields, `batteryLevel` and `vehicleMileage` non-null) with
  production still subscribed. Arm 3c: init **acked in-session**, elapsed 0.0 s.

Both are kept visible above rather than rewritten away, because the point of this document
is how the reasoning went wrong.

**And the way it went wrong is not subtle: the instrument was broken.** From `759123d`:

> Both earlier f8 failures were a single defect in the probe: the callback read
> `data["data"]["vehicleState"]` while the frame is `{"payload": {"data": {…}}}`, which
> `coordinator.py:580/:1074/:1223` all unwrap. One level too shallow, so nothing was ever
> parsed and every field reported NOT DELIVERED regardless of what arrived.
>
> That defect also produced the H4 contention reading — **the subscription was never silent,
> it was unparsed** — and the **two production outages** taken to escape a contention that
> does not exist. … The control caught this twice and twice I corrected something else.

So the trap is not "a subtle server behaviour". It is this: **a broken instrument produced a
false reading, and each time the false reading was explained by inventing a server-side
policy instead of checking the instrument.** Twice. Past a control that flagged it both
times. At a cost of two real outages.

Two things would each have ended it immediately, and neither needed the network:

- **C1s was refutable statically.** `subscribe_for_vehicle_updates`, `subscribe_for_parallax_messages` and `subscribe_for_cloud_connection` in `coordinator.py` open three
  concurrent subscriptions on one `u-sess` every day this integration runs. Reading the
  client we already ship refutes "one subscription per session" without connecting to
  anything.
- **The control was already failing.** It said the instrument was wrong. It was believed
  about the vehicle and disbelieved about itself.

The lesson, in the commit's own words: **"Prove the instrument before reading the result."**

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

| Condition | `connection_init` result | Verdict |
|---|---|---|
| HA running (incumbent holds the subscription) | ~~accepted, **no ack**, held ~180 s, `CLOSE 4420 Connection TTL expired`~~ | **C2 — no-ack half FALSIFIED.** Arm 3c received `connection_ack` with production up, elapsed 0.0 s. The `4420` TTL close is real; its *cause* was never established |
| HA entry disabled (no incumbent) | ~~**`connection_ack` immediately**, then a `next` frame — twice, consecutively~~ | **C3 — UNVERIFIED, and retracted below.** f8 did not reproduce the `next` frame: ack arrived, zero data frames in 30 s |

Neither row survives as written. Both are kept because the point of this document is
the reasoning, and both readings were produced by the same broken probe (`759123d`).

The entry was re-enabled in a `finally` block; it returned to `state=loaded` and
telemetry resumed within ~25 s.

## What was ruled out first

> **C4 — UNFALSIFIABLE AS WRITTEN.** All twenty variants were judged by the probe whose
> callback read `data["data"]["vehicleState"]` against a `{"payload": {"data": {…}}}` frame
> and therefore parsed **nothing regardless of what arrived** (`759123d`). "Unacknowledged"
> was the instrument, not the server. The sweep cannot distinguish a rejected header from an
> accepted one, so it rules nothing out. Kept as a record of what was tried, not of what was
> learned.

Twenty variants, all reported unacknowledged while HA held the subscription:

- a freshly minted `a-sess` from `create_csrf_token`, plus `csrf-token`
- reusing the same `aiohttp` session so cookies carried over
- `BASE_HEADERS`, `User-Agent`, `Apollographql-Client-Name` on the upgrade
- `client-version` removed, and bumped to a much newer value
- `client-name` set to the Android app's identifier
- `dc-cid` removed; `u-sess` capitalised; `u-sess` alone; an **empty** payload

The `u-sess` in `.env` is byte-identical (SHA-256) to the one the working
instance uses, so credentials were never the discriminator.

## Close codes — the `Meaning` column is NOT measured

> **The heading here used to read "Close codes, measured rather than assumed."** It was
> wrong in the same way as everything above it. The **codes** were observed; the
> **`Meaning` column is interpretation**, and claims **C6** and **C7** — which cover this
> table and the two bullets under it — are both **UNVERIFIED**: the arms that would have
> tested them (3d/3e) were **dropped by ruling 28**, because provoking 4401/4403 puts
> `ws_monitor` into a permanent silent stop with no self-heal that the no-harm criteria
> could not have detected. Read the table as a hypothesis that has not been paid for.

| Code | Reason | Meaning (UNVERIFIED — C6) |
|---|---|---|
| 4401 | `Unauthorized` | something was sent before `connection_ack` |
| 4403 | `Forbidden` | malformed `u-sess`, ~0.5 s after init |
| 4408 | `Connection initialization timeout` | no `connection_init` arrived |
| 4420 | `Connection TTL expired` | routine recycling of a healthy connection |

Two of these misled the original diagnosis — **claim C7, also UNVERIFIED**:

- **4401 was read as "our credentials are rejected."** It is the
  graphql-transport-ws response to sending any message before the ack — which the
  probe deliberately did. It carried no information at all.
- **A *malformed* token gets 4403 in half a second, while a valid-but-duplicate
  connection gets silence.** That asymmetry is what made "expired credentials"
  look plausible. ~~It is really "the session resolves, but it already has a
  subscriber."~~

  **That last sentence is the FALSIFIED C1s policy restated.** There is no
  one-subscriber rule to resolve into: `subscribe_for_vehicle_updates`, `subscribe_for_parallax_messages` and `subscribe_for_cloud_connection` in `coordinator.py` open three
  concurrent subscriptions on one `u-sess` every day. And the "silence" it explains
  was not silence — the probe's callback read one level too shallow and parsed
  nothing (`759123d`). The asymmetry may well be real; the explanation attached to
  it is not, and no measurement of it survives.

## Consequences

> ~~**Fixture capture must run as sole subscriber.** `s08a` cannot be done from a dev
> machine while Home Assistant is running. Disable the entry, capture, re-enable.~~
>
> **FALSIFIED — claim C8.** Arm 3b received the **full 33-topic RVM set with production
> subscribed**. Capture requires neither a sole subscriber nor an outage; it can be
> scheduled against a running production instance. The two outages taken to obtain
> "sole subscriber" access bought nothing — see `UNPOPULATED_FIELDS.md` and `759123d`.

**`sendVehicleOperation` does not return the payload.** Its mutation selects only
`{ success }` (`rivian.py:857-861`), so the RVM payload arrives *only* on the
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

## Claim register

Every claim in this document, split, classified, and counted. Added 2026-08-19
per ruling 23; existing rows above are not edited (P1). Arithmetic is against
**fifteen** rows: C1 split into C1s (subscription) and C1c (connection) per
ruling 28. C1c, C8, C6 and C7 record the 2026-08-20 live run (Re-verification
below), not the plan-time OPEN / IN DOUBT predictions.

| ID | Claim (line) | Verdict | Route |
|---|---|---|---|
| **C1s** | *(superseded account, §"Why this document exists")* gateway permits exactly one active **subscription** per user-session token | **FALSIFIED — STATIC.** `rivian.py:145` one monitor multiplexing `:146` `_subscriptions`; the three subscribe_for_* call sites in coordinator.py three concurrent subscriptions on one `u-sess`; shipped to users at `diagnostics.py's `subscribed` field`. Re-confirmed 2026-08-20 | Static, done |
| **C1c** | *(superseded account, ibid.)* every local probe was a *second* **connection**, accepted, never acked, closed at TTL | **FALSIFIED.** The claim is that a second connection is *never acked*. Arm 3a: a second `vehicleState` subscription was ACCEPTED; control passed (≥100 fields, `batteryLevel` and `vehicleMileage` non-null) with production subscribed. Arm 3c: INIT ACKED IN SESSION, elapsed 0.0 s. Both LIVENESS OK. The original "never acked, closed at TTL" half is false. | Live, arms 3a-3c — done |
| **C1b** | *(superseded account, ibid.)* *"Home Assistant holds it"* — that the gateway designates one connection as holder | **UNFALSIFIABLE AS WRITTEN.** No server-side introspection exists; the claim ascribes an internal policy observable only by its effects | Not testable — rewrite as observation, not mechanism |
| **C2** | `:33` HA running → accepted, **no ack**, held ~180 s, `CLOSE 4420` | **FALSIFIED (the no-ack half) — causal label still in doubt.** Arm 3c received `connection_ack` with production up. The TTL close is untouched; the *because* is not established | Live, arm 3c |
| **C3** | `:34` HA disabled → `connection_ack` immediately, then a `next` frame, twice | **UNVERIFIED — NEEDS AN OUTAGE.** | Not taken |
| **C3R** | `:22-29` the retraction: sole subscriber, ack but zero data frames in 30 s | **SUPERSEDED — reported by the broken parser, and its premise is falsified by C8.** | **NEEDS AN OUTAGE** — not taken; may be retired without one if C1c falls |
| **C4** | `:41-48` twenty header/token variants, all unacknowledged | **UNFALSIFIABLE AS WRITTEN.** (§4.0.4) | Supersede with a non-reproducibility note |
| **C5** | `:50-52` the `.env` `u-sess` is byte-identical (SHA-256) to the instance's | **VERIFIED — re-run 2026-08-19 at execution.** sha256[:16] `f24719019dbe68e0` both sides, length 36 (matches plan-time iteration 1; HA `/config/.storage/core.config_entries` and `/homeassistant/.storage/core.config_entries`) | Static, re-run |
| **C6** | `:55-60` close codes 4401 / 4403 / 4408 / 4420 and their meanings | **UNVERIFIED — arms dropped by ruling 28.** Arm 3e would provoke close codes 4401/4403, which `ws_monitor` turns into a permanent silent stop with no self-heal, and the no-harm criteria could not have detected it. | Live-testable in principle; **not this round** |
| **C7** | `:64-70` 4401 carried no information; malformed token → 4403 in ~0.5 s; valid-but-duplicate → silence | **UNVERIFIED — arms dropped by ruling 28.** Arms 3d/3e would provoke 4401/4403, which `ws_monitor` turns into a permanent silent stop with no self-heal, and the no-harm criteria could not have detected it. | Live-testable in principle; **not this round** |
| **C8** | `:74-76` *"Fixture capture must run as sole subscriber. `s08a` cannot be done from a dev machine while Home Assistant is running."* | **FALSIFIED.** The claim is that capture *requires* a sole subscriber. Arm 3b: PARALLAX CONCURRENT — sole subscriber NOT required. Full 33-topic RVM set received with production subscribed. LIVENESS OK. | Live, arm 3b — done |
| **C9** | `:77-81` `sendVehicleOperation` selects only `{ success }`; payload arrives only on `parallaxMessages` | **VERIFIED (SUBSTANCE) — CITATION STALE.** Selection at `rivian.py:857-861`; `:866-870` has no `success` | Static, done — fix three citations |
| **C10** | `:83-95` three non-interchangeable identifiers; `phone_id` from `vasPhoneId`; default user query omits `enrolledPhones` | **VERIFIED.** `probe_vehicle_command.py:105`, `:138` | Static, done |
| **C11** | `:99-104` `ws_monitor.py` distinguishes the codes; 4401/4403 stop the monitor, 4420 is routine | **VERIFIED.** `ws_monitor.py:37` `AUTH_CLOSE_CODES = frozenset({4401, 4403})`, `:41` `TTL_CLOSE_CODE = 4420`, `:165-176` | Static, done |
| **C12** | `:106-113` reproduction recipe; HA flushes config entries on shutdown so a graceful restart overwrites a hand-edit | **VERIFIED BY USE.** The f8 outage followed exactly this order (`UNPOPULATED_FIELDS.md:121-123`). *Iteration 1 left this row's route column blank; it is classified here; and its own line range was stale — the recipe block is `:106-113`, not `:106-112`.* | Verified by prior use; no re-test |

The census, which must add to fifteen:

| Category | Count | IDs |
|---|---|---|
| Static (falsified or verified without connecting) | **5** | C1s, C5, C9, C10, C11 |
| Live-testable with production up | **5** | C1c, C2, C6, C7, C8 |
| Needs an outage | **2** | C3, C3R |
| Unfalsifiable as written | **2** | C1b, C4 |
| Verified by prior use | **1** | C12 |
| **Total** | **15** | |

Answer to ruling 23's "which need an outage": **two** — C3 and C3R, and C3R is already retracted.

## Downstream citation map

What a failure invalidates downstream. First column is unbolded `If C1s falls` /
`If C1c falls` / `If C8 falls` / `If C1c and C8 both hold` so it cannot collide
with the register's row anchor (`| **C…** |`). Scoping the register parsers to
this document's `## Claim register` block is sufficient; the reformat is
redundancy.

| If this falls | These stop being true | Files |
|---|---|---|
| If C1s falls — already fallen, statically | the diagnostics comment shipped to users; the s06c gate's header reasoning; the `prd.json:153` narrative | `custom_components/rivian/diagnostics.py's `subscribed` field`, `scripts/gates/s06c.sh:7`, `tests/test_subscription_failures.py:7`, `prd.json:153`. **The subscription-failure-typing gap itself survives** — typed failures are justified independently of why the day was lost. Change the narrative, not the gap |
| If C1c falls | `WS_CONTENTION.md:13`'s "second connection" account of every past probe failure; C2, C7's second half, and C4's entire premise become explicable without gateway policy | `docs/development/WS_CONTENTION.md` only — the downstream files cite the *subscription* claim, which is C1s |
| If C8 falls | the s08a prerequisite; the RVM fixture protocol; the standing excuse that the f5 decoders are transcription-only | `prd.json:163`, `docs/development/RVM_FIXTURES.md:16-22`, `docs/development/PARALLAX_DECODERS.md:62-63` and `:158-162`, `tests/client/test_f5_decoders.py:26-28`. **Positive downstream effect:** a real captured `vehicle.network.state` payload becomes schedulable with no outage, which `docs/development/PARALLAX_DECODERS.md:161-162` says "would still settle it either way" |
| If C8 falls | **two** gates enforce the obsolete protocol, not one: `scripts/gates/f8.sh:39` requires the literal `sole subscriber` in the record, and `scripts/gates/f5.sh:14-16` states it as the reason the decoders are transcription tests | Both need rewording in the same commit that changes the protocol, never before |
| If C1c and C8 both hold | nothing changes downstream; the f8 result is then explained by something other than contention and **the parse bug's second explanation is still owed** | PM-1 |

Explicitly NOT invalidated by any outcome here: the f8 result itself (all five
delivered, null). It was measured with a proved control on the shipped code path.

The thirteen downstream citation sites across ten files (D1):

1. `prd.json:153`
2. `prd.json:163`
3. `custom_components/rivian/diagnostics.py's `subscribed` field`
4. `docs/development/RVM_FIXTURES.md:16-22`
5. `docs/development/PARALLAX_DECODERS.md:62-63`
6. `docs/development/PARALLAX_DECODERS.md:158-162`
7. `docs/development/UNPOPULATED_FIELDS.md:122` — drifted pointer, same failure mode as C9; Step 9 repairs it
8. `tests/client/test_f5_decoders.py:26-28`
9. `tests/test_subscription_failures.py:7`
10. `scripts/gates/s06c.sh:7`
11. `scripts/gates/f8.sh:8`
12. `scripts/gates/f8.sh:39`
13. `scripts/gates/f5.sh:14-16`

Note on `scripts/gates/f8.sh:36-41`. The `sole subscriber` requirement is
*conditional on the verdict containing `INCONCLUSIVE`*. `found` is built by
substring search over the whole document, and P1 keeps every retracted
`INCONCLUSIVE` verdict in the record permanently. So `INCONCLUSIVE` is in that
document forever, the branch is permanently taken, and the `sole subscriber`
requirement is permanently live.

---

# Re-verification, 2026-08-20 — owner ruling 23

Run with `scripts/ws_contention_probe.py`, production up throughout, **no outage taken**: the
`Starting Home Assistant` count was 6 before and 6 after, and `Web socket rejected by the server`
returned 0 at baseline and 0 after every arm. Arms 3d and 3e were dropped by ruling 28 — they
provoke close codes 4401/4403, which `ws_monitor` turns into a permanent silent stop with no
self-heal, and the no-harm criteria could not have detected it.

## What the arms found

| Arm | Claim | Verdict |
|---|---|---|
| **3a** | C1c — a second `vehicleState` subscription on one user session | **ACCEPTED.** Control passed: ≥100 fields delivered with `batteryLevel` and `vehicleMileage` non-null, while production was subscribed. `LIVENESS OK`. |
| **3b** | C8 — a Parallax subscription concurrent with production's | **PARALLAX CONCURRENT — sole subscriber NOT required.** Received the full RVM topic set (33 topics, `body.locks.states` through `vehicle.wheels.vehicle_wheels`) with production subscribed. `LIVENESS OK`. |
| **3c** | C1c vs client — a hand-rolled `connection_init` in the same session | **INIT ACKED IN SESSION**, elapsed 0.0 s. `LIVENESS OK`. |
| **C6, C7** | close-code behaviour | **UNVERIFIED — arms dropped by ruling 28.** Not omitted, not carried forward as verified. |

## C1 was two claims wearing one sentence, and the static half was already false

The superseded account in §"Why this document exists" says "exactly one active **subscription** per
user session token", then says "Every local probe was therefore a second **connection**." Those are different claims, and the conflation is the
original defect.

**C1-as-subscription (C1s) is FALSIFIED STATICALLY — no probe needed.** `rivian.py` builds one
`WebSocketMonitor` per client and multiplexes a `_subscriptions` dict over it; `coordinator.py` runs
`subscribe_for_vehicle_updates`, `subscribe_for_parallax_messages` and
`subscribe_for_cloud_connection` on that one client concurrently, and `diagnostics.py` ships
`"subscribed": coor._unsub_parallax is not None` — the code asserts a Parallax subscription
coexisting with the vehicle-state one. **Production has run three concurrent subscriptions on one
user session every day since the feature shipped.**

**C1-as-connection (C1c) is the claim that was actually open, and arms 3a and 3c answer it: a second
connection is accepted and acked.**

## What this retires

The **sole-subscriber prerequisite** — cited in `prd.json`, `RVM_FIXTURES.md` and the f8 outage plan
— **is retired for Parallax by arm 3b.** Capturing an RVM payload does not require stopping the
integration.

That matters beyond bookkeeping. Two production outages were taken this session to make a probe the
sole subscriber, for a contention that does not exist. The probe was never contended; its callback
read `data["data"]` where the frame is `{"payload": {"data": …}}`, so it parsed nothing and the
silence was read as contention. Arm 3b now shows the outages were unnecessary twice over: the
parsing was broken *and* the prerequisite was false.

## The retraction notice above is itself unreliable

It reports "no data frame followed" — from the same callback that could not see data frames at all.
It may be retracting a true row for a false reason. Treated as superseded by this section rather
than trusted.

## Correction to this document's own commit history, 2026-08-20

`3fe5eaa`'s message says a *crashed* worker left an uncommitted register draft and that **Step 4's**
commit swept it in. Both halves are false, and the record is the decision here, so the true sequence
is recorded rather than the tidy one:

- `17343e0` (Step 6) is where the first register block was committed — swept in by `git add -A` while
  a **live** worker had it in progress. Step 6's subject is the `f9.sh` interlock; the register had
  nothing to do with it.
- `610182f` (Step 4) added the re-verification section and **no** register block — verified: it adds
  zero `## Claim register` lines.
- `ebbaf39` was that worker committing its own Step 1, editing the register already in the tree.
- `3fe5eaa` then appended a second register, deleted the first, **and swept in the same worker's
  uncommitted `scripts/gates/f9.sh` and `scripts/ws_contention_probe.py` edits** — 75 insertions to
  the probe, including its dry-run document printer.

That is three `git add -A` collisions with a concurrently-running worker in one session. The
mechanism is always the same: stage everything, and another agent's half-finished work rides along
under an unrelated subject. `git add <paths>` is the fix and it was available every time.

The **content** of the register is unaffected — one block, fifteen rows, verdicts taken after the
arms ran, all three criteria arm-proved in both directions. Only the provenance narrative was wrong.
