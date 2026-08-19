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

Four of the fields these fill — `btmOcHardwareFailureStatus`,
`vasSecureElementFaulted`, `vasAccessCanFaulted`, `passiveEntryUnlockFailReason` —
are declared in the gateway schema and are **not** subscribed, so Parallax is
their only source.

**The tests are transcription tests, not captures.** The payloads are constructed
from the transcribed schema. They prove the decoder reads the field numbers and
enum values the app declares; they do not prove the vehicle emits them. Capture
needs sole-subscriber access to the websocket, which means stopping the production
integration (`WS_CONTENTION.md`) — that is f8's protocol.

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

## Two findings recorded rather than acted on

**`needDoubleConsumerSubscription` has no caller.** `CLIMATE_HOLD_STATUS` is the
only topic with the flag set, and its getter
`getNeedDoubleConsumerSubscription()` is called **nowhere in the 32,941
decompiled files**. App 3.15.0 sets it and acts on it nowhere. Duplicating the
topic in the `rvms` list would also contradict what the subscription code already
documents — a duplicated topic is delivered twice. So it is transcribed and left
alone.

**A second RVM enum exists.** `iol.java` declares two more topics that `l6e` does
not:

- `user_passcodes.passcode_types.drive_auth`
- `security.access.passive_entry` (as `PASSIVE_ENTRY_SETTING_V2`)

The second is a **third** spelling alongside `l6e`'s
`vehicle_access.state.passive_entry` and
`vehicle_access.passive_entry.passive_entry`. Recorded here so a future pass does
not treat `l6e` as the complete topic list — it is not.
