# Parallax decoders: what was transcribed, and what was not

## The method

R8 renames `GeneratedMessageLite` to `com.google.protobuf.e` and every message
class to two or three letters (`hk8`, `gxf`, `xq`). A grep of the decompilation
for `GeneratedMessageLite`, `ProtoAdapter` or `parseFrom` therefore finds nothing
outside Google's own code, and the app looks as though it carries no protobuf
schema at all. **It carries 326 message classes.** This was nearly recorded as
"the schema is not in the APK"; it is, and the first reading was wrong.

What R8 leaves alone is exactly what a decoder needs:

| Survives | Example |
|---|---|
| `<FIELD>_FIELD_NUMBER` constants | `GEAR_FIELD_NUMBER = 1` |
| `<field>_` instance members and their Java types | `private int gear_;` |
| protobuf enum constants and numbers | `GEAR_PARK(1)` |

The **topic → message** binding comes from the app's own decoder dispatch:
`b7h.java` and ten sibling files each hold methods of the shape

```java
if (j6e.a(str) != l6e.DYNAMICS_VEHICLE_GEAR) return null;
...
hk8.E(Base64.decode(payload, 0))
```

so topic and message class sit in one method body and can be read off
mechanically. `scripts/gates/helpers/topic_map.py`, `proto_index.py` and
`proto_schema.py` do that.

The **value vocabulary** is the app enum's name with its common prefix stripped
and lowercased: `GEAR_PARK` → `park`, `DRIVE_MODE_OFF_ROAD_AUTO` →
`off_road_auto`. That is not a guess — it is how `GEAR_STATUS_MAP` and
`DRIVE_MODE_MAP` in `const.py` were already built, from live subscription values.
Emitting the same strings is what lets these topics feed the **existing** sensors
rather than appending new options to them.

## Transcribed (14, plus one inference)

`body.trailer.state`, `comfort.cabin.pet_mode_status`,
`dynamics.vehicle.drive_mode`, `dynamics.vehicle.gear`,
`dynamics.vehicle.location`, `dynamics.vehicle.range`,
`energy.high_voltage.battery_characteristics`, `energy.low_voltage.battery_state`,
`security.access.btm`, `security.access.immobilizer_state`,
`security.access.passive_entry_debug`, `security.access.vas_fault`,
`security.alarm.state`, `security.video_monitoring.state`.

18 decoders → **32**, and → **33** with `vehicle.network.state` below. `SUBSCRIBED_RVMS` is the intersection of the wanted topics
with the ones that have a decoder, so writing the decoder is what subscribes the
topic; no subscription code changed.

Three of the fields these fill — `vasSecureElementFaulted`,
`vasAccessCanFaulted`, `passiveEntryUnlockFailReason` — are declared in the
gateway schema and are **not** subscribed, so Parallax is their only source. A
fourth, `btmOcHardwareFailureStatus`, was in that category too until the T3
reversal below moved it onto the main subscription.

**The tests are transcription tests, not captures.** The payloads are constructed
from the transcribed schema. They prove the decoder reads the field numbers and
enum values the app declares; they do not prove the vehicle emits them. Capture
needs sole-subscriber access to the websocket, which means stopping the production
integration (`WS_CONTENTION.md`) — that is f8's protocol.

### T3 (2026-08-21) — `PARALLAX_ONLY_FIELDS` shrinks 10 → 7, and the reason it was 10 was wrong

`batteryCellType` (`decode_battery_characteristics`, `energy.high_voltage.
battery_characteristics`), `coldRangeNotification` (`decode_range`, `dynamics.
vehicle.range`) and `btmOcHardwareFailureStatus` (`decode_btm_diagnosis`,
`security.access.btm`, above) are now requested on the main `vehicleState`
subscription (`VEHICLE_STATE_SUBSCRIPTION_FIELDS`, `const.py`) as well as being
decoded here. All three are in the app's own document (`sh/C19779dc.java:59`)
and are schema-declared, so subscribing to them is exactly what the app does.

**Why they were excluded in the first place, and why that reasoning does not
survive.** All ten original `PARALLAX_ONLY_FIELDS` were kept off the
subscription document on the theory that requesting a field would let
`VehicleCoordinator._subscription_keys` claim it and permanently lock Parallax
out of ever filling it — "a subscribed field is recorded in
`_subscription_keys`, which blocks Parallax's only source for it." That rests
on a misreading: `_subscription_keys` is populated from frames the gateway
actually **delivers** (`coordinator.py:1292`), never from the set of fields
*requested* — a subscribed-but-never-delivered field claims nothing, and
`tests/test_parallax_gap_fill.py::test_falsy_entries_are_not_recorded_as_supplied`
already pins that distinction. Subscribing to a field is not by itself a claim
on it.

**Nothing here says the decoders became redundant.** The gap-fill rule only
discards a Parallax value for a key already claimed by a *delivered* subscription
frame (`coordinator.py:1134`); until this integration has live evidence that the
gateway actually delivers non-null values for these three, the decoders remain
their working, verified fallback — exactly the same reasoning
`### UPDATE — field parity subscribes the other ten (T2b)` above applies to the
ten `wifi*`/`cellular*` names, and exactly why no decoder code changed here.

The remaining seven `PARALLAX_ONLY_FIELDS` — `consecutiveAlarmDisabledNotification`,
`knownLocation`, `passiveEntryUnlockFailReason`, `secureImmobilizerStatus`,
`vasAccessCanFaulted`, `vasSecureElementFaulted`, `wheelsInstalled` — have no
such document to point to: none of them is in the app's own `vehicleState`
request, so they stay excluded on solid ground, not the reversed one.

## Not transcribed (23)

No decoder for these appears in the app's dispatch files, so there is no
topic → message binding to read off. They are **not** dropped: they stay in the
`l6e` transcription, and the moment a binding is found the decoder follows and the
subscription picks the topic up automatically.

| Topic | Why not decoded |
|---|---|
| `body.windows.states` | no decoder in the app's dispatch files |
| `charging.schedule.time_window` | no decoder in the app's dispatch files |
| `charging.session.notification` | no decoder in the app's dispatch files |
| `charging.session.remote_command` | no decoder in the app's dispatch files |
| `charging.session.soc_slider` | no decoder in the app's dispatch files |
| `charging.session.trip_target` | no decoder in the app's dispatch files |
| `comfort.cabin.cabin_ventilation_setting` | no decoder in the app's dispatch files |
| `comfort.cabin.hvac_settings_status` | no decoder in the app's dispatch files |
| `comfort.user_modes.state` | no decoder in the app's dispatch files |
| `device_table.vas_keyper.devices` | no decoder in the app's dispatch files |
| `energy_edge_compute.graphs.cold_weather_soc` | no decoder in the app's dispatch files |
| `energy_edge_compute.graphs.parked_energy_distributions` | no decoder in the app's dispatch files |
| `gearguard_streaming.privacy.gearguard_streaming_daily_limit` | no decoder in the app's dispatch files |
| `gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent` | no decoder in the app's dispatch files |
| `geofence.geofence_service.favoriteGeofences` | no decoder in the app's dispatch files |
| `navigation.navigation_service.trip_info` | no decoder in the app's dispatch files |
| `navigation.navigation_service.trip_progress` | no decoder in the app's dispatch files |
| `ota.deployment.state` | no decoder in the app's dispatch files |
| `ota.ota_state.vehicle_ota_state` | no decoder in the app's dispatch files |
| `ota.user_schedule.ota_config` | no decoder in the app's dispatch files |
| `secure_file_transfer.pet_snapshot.secure_file` | no decoder in the app's dispatch files |
| `vehicle.network.state` | no decoder in the app's dispatch files |
| `vehicle_access.passive_entry.passive_entry` | no decoder in the app's dispatch files |
| `vehicle_access.state.passive_entry` | no decoder in the app's dispatch files |

<!-- 24 remaining -->

## The exhaustive search for the remaining 24 (result: none to be found)

The owner asked for a harder search rather than stopping at the 14. It was done
exhaustively and it came back empty, which is a result rather than a shrug.

**Method.** Every protobuf-parse-from-base64 site in all 32,941 files, found with
`grep -rE '\b[a-z0-9]{2,4}\.[A-Z]\(Base64\.decode'`. There are **25**, in 14
files. Not a sample — the whole set.

| Parser | Bound to | Status |
|---|---|---|
| 21 sites in `b7h` and ten siblings | a topic, via a guarded method | all already decoded here |
| `vj3` (in `ipf`, called from `lra`) | `CLIMATE_HOLD_STATUS` | already decoded |
| `rsb` (in `cqf`, "ProtobufVehicleStateParserHelper") | `BODY_CLOSURES_STATES` | already decoded |
| `pol` (in `cfl`) | not a topic payload at all — `REF_UUID`, `REF_MODEL`, `PROGRESS`, `OPERATION_ERROR`, `DATA` is the Parallax **operation-response envelope** | n/a |
| `opl` (in `ipf`) | see below | **no caller** |

The other four files that reference the undecoded topics — `k6e` (all 24), `zuf`,
`nnb`, `sn4` — contain **zero** base64 decodes. They handle subscription
management, not parsing.

**Conclusion: the 24 have no topic-to-message binding anywhere in this build.**
The app subscribes to them and this version contains no decoder for them. There
is nothing further to read off a parse site, so the search is finished rather
than paused.

### The one candidate, deliberately not taken

`opl` is parsed at `ipf`, and its fields are `default_link` (1), `routes` (2),
`default_link_quality` (3), `wifi` (4) and `cellular` (5). That is
`vehicle.network.state` and nothing else in the topic list — the integration's own
schema already carries `wifiSignal`, `cellularSignalStrength`, `wifiSsid` and six
more siblings.

**Written, on the owner's decision, and flagged as the one inference here.** Its
parser `ipf.e` has **no caller in the decompilation**, so nothing says which topic
feeds it — this is not a binding read off a dispatch.

What raised it above a guess is corroboration from a second independent source.
Its nested submessages land one-to-one on the gateway schema f4 rebuilt from the
app's own `vehicleState` documents:

| `opl` field | schema field | | `opl` field | schema field |
|---|---|---|---|---|
| `wifi.wpa_status` | `wifiWpaStatus` | | `cellular.carrier` | `cellularCarrier` |
| `wifi.ssid` | `wifiSsid` | | `cellular.network` | `cellularMode` |
| `wifi.signal_quality` | `wifiAntennaBars` | | `cellular.signal_quality` | `cellularAntennaBars` |
| `wifi.link_speed` | `wifiLinkSpeed` | | `cellular.signal_strength` | `cellularSignalStrength` |
| `wifi.frequency` | `wifiFreq` | | | |
| `wifi.security` | `wifiSecureStatus` | | | |

Ten names, every one declared in `type VehicleState`, on a topic literally called
`vehicle.network.state`.

**The cost of being wrong is bounded, and that is why it was takeable.** Every
field above except `wifiSignal` is declared but **not subscribed**, so a bad
decode mis-fills sensors that do not exist yet rather than corrupting a working
one. `wifiSignal` *is* subscribed, and the gap-fill rule means the subscription
keeps it — this decoder cannot touch it.

A captured `vehicle.network.state` payload from f8 would still settle it either
way, and the tests say plainly that they are transcription tests, not a capture.

### UPDATE — field parity subscribes the other ten (T2b)

The "cost of being wrong is bounded" claim above was true when the wire was the
derived `VEHICLE_STATE_API_FIELDS`: a name was requested only where this
integration had a sensor for it, and the only `wifi*`/`cellular*` sensor was
`wifiSignal`. T2's field-parity change replaced that with the app's literal
129-field document — the same one the `opl` corroboration table above was built
from — which requests the app's whole `wifi*`/`cellular*` list regardless of
whether an entity reads it. All eleven names `_WIFI_SPEC`/`_CELLULAR_SPEC` write
are now on the wire (`tests/client/test_f5_decoders.py::TestNetworkState::
test_the_wifi_and_cellular_overlap_with_the_subscription` pins the set); only
`wifiStaDisabledReason`, the twelfth app name, has no decoder and is sourced from
the subscription alone.

**This does not mean the decoder is dead.** The gap-fill rule
(`coordinator.py:1134`) only discards a Parallax value for a key already in
`_subscription_keys`, which `_build_vehicle_info_dict` (`coordinator.py:1285-
1293`) populates from *delivered* frames — keyed on the outer dict's truthiness,
not on whether the frame's `"value"` is non-null, which is the separate bug
worker-4's value-based-provenance fix targets. So each of the ten depends on
which of three cases the gateway puts it in: delivered with a real value (the
subscription wins outright, decoder output for that field is unreachable),
named but delivered null (today, wrongly claims the key and blocks Parallax
too, until the provenance fix lands), or never named in a frame at all
(Parallax remains the only source, same as before field parity).

**Which case applies to these ten is not known from this repository.** The
`UNPOPULATED_FIELDS.md` precedent — four `tirePressureStatusValid*` names and
`cabinHoldNotification`, all schema-declared and subscribed, all delivered null
on the owner's R1T — makes the "named but null" case at least plausible here
too, but that is a hypothesis carried over by analogy, not evidence about these
specific fields. Settling it is an f8 question: capture a live `vehicleState`
frame after this change ships and check whether `wifiSsid`, `wifiWpaStatus`, and
the rest arrive with real values, arrive null, or are absent from the frame
entirely, the same way `UNPOPULATED_FIELDS.md` settled its five.

No decoder code changes on the strength of this finding — "the app's document
requests it" is exactly the weak evidence the tonneau-cover removal already
showed is not grounds to delete a decoder.

### UPDATE — live probe settles the ten, and they stay anyway (2026-08-22)

The "which case applies" question above is now answered for all ten. A live
probe against a real R1T — asleep, `powerState = sleep` — delivered every
`wifi*`/`cellular*` name in the main subscription's frame with a real, non-null
value:

```
wifiFreq = 5200      wifiLinkSpeed = 260        wifiSsid = <redacted>
wifiSecureStatus = WPA    wifiWpaStatus = COMPLETED
wifiAntennaBars = 3       wifiStaDisabledReason = 0
```

(`wifiSsid` is redacted here — it is in the diagnostics-redaction set and does
not belong in a committed file.)

That is the **first** of the three cases above, not the "named but null" one
`UNPOPULATED_FIELDS.md`'s tire-pressure precedent suggested by analogy: the
subscription delivers, `_build_vehicle_info_dict` records the key, and the
gap-fill rule (`coordinator.py:1134`) discards whatever the f5 decoders would
have produced for these ten. **The f5 `opl`/`vehicle.network.state` decoders
are now unreachable for these fields** — the subscription wins outright, same
as it already did for the eleventh, `wifiSignal`.

**They stay anyway. No decoder is deleted, and no test is weakened.** Three
reasons, in order of how much they've already cost this project to learn:

1. **This repository has been wrong before about what "unreachable" means.**
   `TONNEAU_CMD` appears in zero of app 3.15.0's 32,941 decompiled files and in
   no vehicle's `supportedFeatures` — every offline signal said the gate was
   dead weight — and both tonneau commands physically move the cover. Reasoning
   from absence-of-evidence to "this code no longer matters" is the exact
   mistake that produced a real regression once already; unreachable-by-current-
   evidence is not unreachable-by-construction.
2. **An idle decoder costs nothing.** It runs only when the gap-fill rule lets a
   Parallax value through, which for these ten it currently never does. There is
   no maintenance burden, no performance cost, and no behavior to regress by
   leaving it in place.
3. **The alternative is sensors going dark with no warning.** If the gateway
   ever stops filling one of these ten in the main document — a schema change,
   a feature flag, a vehicle without this hardware revision — the decoder is
   the only thing standing between that and a silently `unavailable` entity.
   Deleting it trades a live, working fallback for a bet that today's delivery
   behavior is permanent.

Deleting proven-unreachable code is the tempting move here, and it is the wrong
one for the same reason `UNPOPULATED_FIELDS.md`'s Principle -1 exists: silence
(or, here, redundancy) is not a live failure, and is never by itself grounds to
remove something that still works. **Documentation only — no decoder code
changed on the strength of this finding.**

## How the app avoids duplicate subscriptions

Worth recording because this integration solves the same problem differently, and
because it explains a flag that looked inert.

**One shared subscription per (vehicle, RVM set).** `z5e.java` is a
process-wide registry whose logger tag names the design:
`PVMParallaxGroupSubscriptionCenter`. It holds a `ConcurrentHashMap` keyed on

```
"<vehicleId>|<rvms, sorted, comma-joined>"
```

`oue.java:240-266` builds that key with `nu3.Y0(...)` — Kotlin `sorted()` — so the
key is **order-independent**: two callers asking for the same set in different
orders share one subscription rather than opening two.

The flow is created with Kotlin's `shareIn`:

```java
on6.C0(flow, z5e.b, i9i.b(2, 2000L), 0)
```

`i9i.b(2, 2000L)` is the default-argument synthetic: mask `2` leaves the first
parameter untouched, so this is
`SharingStarted.WhileSubscribed(stopTimeoutMillis = 2000,
replayExpirationMillis = Long.MAX_VALUE)` with `replay = 0`. The subscription is
reference-counted by the Flow machinery and survives **2 seconds** after the last
consumer detaches — a grace window so moving between two screens that want the
same RVMs does not tear down and re-establish the websocket.

Insertion is `concurrentHashMap.putIfAbsent(key, flow)`, and the loser of a race
discards its own flow and takes the winner's. Two threads cannot create two
subscriptions for the same set.

**Duplicate *consumption* is then routed explicitly**, by the
`isVehicleState` / `needDoubleConsumerSubscription` pair described below.

### How ours differs

`SUBSCRIBED_RVMS` (`coordinator.py:303-305`) is
`sorted({*PARALLAX_RVMS, *CHARGING_RVMS} & set(RVM_DECODERS))` — sorted like the
app's key, and additionally **deduplicated** by set intersection, which the app
does not need because its input is already a set. We open one subscription for the
whole integration and have a single consumer, so neither the group centre nor the
double-consumer routing has an analogue here. The one thing worth borrowing is the
2-second teardown grace: when the config entry is disabled and re-enabled (f8's
protocol), the old subscription is not necessarily gone the instant it is closed.

## Two findings recorded rather than acted on

**CORRECTION — `needDoubleConsumerSubscription` does have callers, and it routes
duplicate consumption deliberately.** An earlier version of this file said the
getter is "called nowhere in the 32,941 decompiled files". That was wrong, and the
mistake is worth naming: the grep was for the lowercase field
`needDoubleConsumerSubscription`, which does not match the accessor
`getNeedDoubleConsumerSubscription` because of the capital `N`. Case-sensitive
greps for a Kotlin property miss its generated getter.

There are two call sites, and together they are the app's answer to duplicate
Parallax consumption:

`nem.java:330` — selecting which topics to subscribe to individually:

```java
if ((topic.getSubscriptionScope() == fug.App && !topic.isVehicleState())
    || topic.getNeedDoubleConsumerSubscription()) {
    arrayList.add(topic);
}
```

`acf.java:593` — the other consumer, dropping what the first one owns:

```java
if (l6eVarA != null && l6eVarA.isVehicleState()
    && !l6eVarA.getNeedDoubleConsumerSubscription()) {
    return hnkVar;   // drop: handled by the vehicle-state path
}
```

So each topic normally flows down exactly **one** of the two paths. The flag is
the explicit exception that makes a topic flow down **both** — hence "double
consumer". `CLIMATE_HOLD_STATUS` is the only topic in the enum that is both
`isVehicleState` and flagged, so it is the only one deliberately consumed twice:
20 topics match that selector, and it is the sole member admitted purely by the
flag.

Nothing here changes what this integration does — we have one consumer, so there
is no second path for a topic to be dropped from. It is recorded because the flag
is now understood rather than assumed inert.

**A second RVM enum exists.** `iol.java` declares two more topics that `l6e` does
not:

- `user_passcodes.passcode_types.drive_auth`
- `security.access.passive_entry` (as `PASSIVE_ENTRY_SETTING_V2`)

The second is a **third** spelling alongside `l6e`'s
`vehicle_access.state.passive_entry` and
`vehicle_access.passive_entry.passive_entry`. Recorded here so a future pass does
not treat `l6e` as the complete topic list — it is not.
