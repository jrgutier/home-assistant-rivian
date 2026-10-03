# Parallax schema, read off two app builds

Derived JSON only — field names, field numbers, wire kinds, enum constants, and the
obfuscated class/site names that locate them. No decompiled `.java` is committed
here or anywhere else in the repo (`docs/development/apk/*.java` is gitignored).

## The builds

| version | versionCode | source | sha256 of the base APK / bundle | jadx tree |
|---|---|---|---|---|
| 3.15.0 | 4804 | APKPure XAPK | `f5e672e04cdc11a780ed798e56d4679a1f4191bc3fecdc713d0e276f375ed81d` | `.apk/3.15.0/jadx/sources`, 32,941 files |
| 3.16.0 | 4884 | Google Play (`base.apk`) | `49bd631513cf9e78421e618c70c978f7cf2d291affe2fdbf4c10983dd80bc24a` | `.apk/3.16.0/jadx/sources`, 34,052 files |

3.16.0 is the newest of the 54 trees under `.apk/`. Both were decompiled with
jadx 1.5.6, `--no-res --no-debug-info`, per `../REGENERATION.md`. The 3.16.0
versionCode was read with `apkanalyzer manifest version-code .apk/3.16.0/base.apk`.

## The commands

```sh
for v in 3.15.0 3.16.0; do
  python scripts/gates/helpers/apk_parallax_schema.py \
    .apk/$v/jadx/sources $v docs/development/apk/schema \
    docs/development/apk/schema/topics_checked.txt
done
```

`topics_checked.txt` is the 20 topics in question plus the 24 rows of the
"Not transcribed" table in `../../PARALLAX_DECODERS.md`, deduplicated: 35 names,
because 9 are on both lists.

`apk_parallax_schema.py` is new. It replaces the pairing in `topic_map.py` for this
purpose because that pairing — and the grep the "exhaustive search" section of
`PARALLAX_DECODERS.md` rests on — only sees `X.M(Base64.decode(...))` on one line.

## What the files are

| file | contents |
|---|---|
| `apk_parallax_schema_<ver>.json` | `{topic: {class, dispatch_site, binding, fields}}` for every topic with a parse site. Nested messages are inlined under a field's `message` key |
| `bindings_check_<ver>.json` | `topics`: each of the 35 as `bound` / `referenced_only` / `absent`. `rvm_enums`: every member of both RVM enums |
| `unbound_parse_sites_<ver>.json` | parse sites with no topic binding, with the parsed message's schema |
| `uncalled_parse_wrappers_<ver>.json` | message classes that have a `byte[]` parse entry point and **no caller anywhere in the tree**, with their schema |
| `message_index_<ver>.json` | every protobuf message class: `{field: [number, wire_kind]}` |

`wire_kind` comes from the protobuf-lite RawMessageInfo string in each class, so it
is exact where `java_type` is not (`int` covers int32, uint32, sint32 and enum).

`binding` says how the topic was tied to the parse site: `direct` (the method that
parses also guards on exactly one RVM member), `via_caller` (the guard is one call
up), or `lambda_registry` (the parse is one `case` of a synthetic lambda, and the
`new Lambda(N)` selecting it is registered against an RVM member; `registry_site`
says where).

## Results

| | 3.15.0 | 3.16.0 |
|---|---|---|
| protobuf message classes | 339 | 341 |
| parse call sites | 84 | 84 |
| **topics bound** | **30** | **30** |
| RVM enum members | `l6e` 56 + `iol` 2 | `nne` 57 + `ifm` 2 |
| uncalled parse wrappers | 24 | 25 |

The only RVM-enum change is `VEHICLE_ACTIVE_USER` = `vehicle.profiles.active_user`,
new in 3.16.0 and not parsed anywhere in it.

### The 35 checked topics

Identical in both builds except where marked.

**bound (6)** — class names are 3.15.0 / 3.16.0:

| topic | class | site (3.15.0) |
|---|---|---|
| `charging.session.notification` | `yfd` / `wwd` | `mz6.java:284` |
| `charging.session.remote_command` | `v6g` / `dsg` | `mz6.java:353` |
| `charging.session.soc_slider` | `sug` / `hgh` | `mz6.java:395` |
| `charging.session.trip_target` | `fgk` / `d5l` | `mz6.java:581` |
| `ota.deployment.state` | `vkd` / `r1e` | `ds6.java:15640` |
| `security.access.passive_entry` | `w9e` / `gre` | `t8.java:72`, registered at `apl.java:25` |

**referenced_only (19; 20 in 3.16.0)** — in an RVM enum, no parse site:
`body.windows.states`, `charging.schedule.time_window`,
`comfort.cabin.cabin_ventilation_setting`, `comfort.cabin.hvac_settings_status`,
`comfort.user_modes.state`, `device_table.vas_keyper.devices`,
`energy_edge_compute.graphs.cold_weather_soc`,
`energy_edge_compute.graphs.parked_energy_distributions`,
`gearguard_streaming.privacy.gearguard_streaming_daily_limit`,
`gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent`,
`geofence.geofence_service.favoriteGeofences`,
`navigation.navigation_service.trip_info`,
`navigation.navigation_service.trip_progress`, `ota.ota_state.vehicle_ota_state`,
`ota.user_schedule.ota_config`, `secure_file_transfer.pet_snapshot.secure_file`,
`vehicle.network.state`, `vehicle_access.passive_entry.passive_entry`,
`vehicle_access.state.passive_entry`; plus `vehicle.profiles.active_user` in
3.16.0 only.

**absent (10; 9 in 3.16.0)** — the string is in no `.java` file, and a byte search
of the four `classes*.dex` in each APK finds none of them either:
`body.wipers.fluid_level`, `charging.energy.state`, `charging.session.power`,
`departure.schedule.schedule`, `dynamics.brakes.fluid_level`,
`dynamics.vehicle.efficiency`, `dynamics.vehicle.mass_estimate`,
`parallax.wakeup.heartbeat`, `vehicle.setting.network`; plus
`vehicle.profiles.active_user` in 3.15.0 only.

## What this corrects in `PARALLAX_DECODERS.md`

**"The 24 have no topic-to-message binding anywhere in this build" is wrong for
five of them**, and for `security.access.passive_entry` from the second enum. The
search behind that sentence grepped for `X.M(Base64.decode(`, i.e.
`android.util.Base64` inlined into the parse call. The charging dispatch in `mz6`
decodes with `java.util.Base64.getDecoder().decode(str)` into a local first and
then calls `yfd.F(bArrDecode)`, which that grep cannot match. `ota.deployment.state`
does use `android.util.Base64` (`ds6.java:15640`): it is among the 25 sites that
search listed, where it was counted as already decoded. It has no decoder here.

**The other 19 stay unbound, but the schema for most of them is in the APK.** The
uncalled-wrapper file lists message classes with a parse entry point that nothing
calls — `nzk` (`in_service`, `car_wash`, `pet_mode`, `camp_mode`, …), `lmj`
(`is_valid`, `window_data`), `xek` (`legetautc`, `tripetautc`, …), `uv9`
(`set_temperature_celsius`), `ai3` (`auto_cabin_ventilation_enabled`) and so on.
Their field names line up with referenced-only topics, which is presumably how
another client can decode a topic this app never parses. **That is a match on
names, not a binding**: nothing in either build says which topic feeds which of
these classes, so they are listed, not assigned.

## The special cases

| class (3.15.0 / 3.16.0) | finding |
|---|---|
| `vj3` / `xn3` | bound, `via_caller`, to `comfort.cabin.climate_hold_status` — agrees with `PARALLAX_DECODERS.md` |
| `opl` / `ngm` | parse site `ipf.java:159` / `v9g.java:159`, no caller in either build — agrees; still the one inference |
| `rsb` / `q7c` | parse site `cqf.java:17` / `oag.java:17`, **no caller in either build**. `PARALLAX_DECODERS.md` says it is bound to `BODY_CLOSURES_STATES`; the class that is bound to `body.closures.states` is `eq3` / `gu3` (`kbn.java:1044`). `rsb` has one field, repeated `states`, and its only parser maps a `LOCK_STATUS_*` enum |
| `tpj` / `ydk` | parsed in a coroutine lambda whose owner logs as `TirePressureStateRepository`; the topic is not named at the site or at its constructor, so it is left unbound |
| `pol`, `gyh` / `ofm`, `xki` | the Parallax operation-response envelope and its status, not topic payloads |

## Limits

- `"enum": null` on an enum field means the message class has no typed accessor
  for it (R8 strips unused getters), so nothing links the field to its enum class.
  18 of 72 enum fields in the bound topics are in that state in each build. The
  enum class usually still exists; it is just not attributable from the message.
- `lambda_registry` picks the nearest RVM member preceding the lambda's
  construction. Both uses were read by hand (`apl.java` / `ouh.java`) and are right.
- The remaining unbound sites are Tink key formats, the WebRTC download channel,
  and ten `ByteString`-parsed vehicle-state messages in `xpf` / `jag` that carry
  no topic.
