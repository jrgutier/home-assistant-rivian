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

## Transcribed (14)

`body.trailer.state`, `comfort.cabin.pet_mode_status`,
`dynamics.vehicle.drive_mode`, `dynamics.vehicle.gear`,
`dynamics.vehicle.location`, `dynamics.vehicle.range`,
`energy.high_voltage.battery_characteristics`, `energy.low_voltage.battery_state`,
`security.access.btm`, `security.access.immobilizer_state`,
`security.access.passive_entry_debug`, `security.access.vas_fault`,
`security.alarm.state`, `security.video_monitoring.state`.

18 decoders → **32**. `SUBSCRIBED_RVMS` is the intersection of the wanted topics
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

## Not transcribed (24)

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
