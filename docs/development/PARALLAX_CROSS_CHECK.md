# Parallax cross-check: ours vs bretterer vs the app vs the wire

> A dated audit. Its `parallax.py:NN` citations are to the single hand-rolled
> module as it stood then; s49 replaced that module with the `parallax/` package
> ([PARALLAX_SCHEMAS.md](PARALLAX_SCHEMAS.md)). The findings stand; the line
> numbers no longer resolve.

Three sources compared, one topic at a time:

| | what it is | how it was read |
|---|---|---|
| **ours** | `custom_components/rivian/rivian_client/parallax.py`, hand-rolled wire decoders, 37 topics | by hand, decoder by decoder, plus running every decoder on the fixtures |
| **bretterer** | `bretterer/rivian-python-client` @ `37b75a0431a8aceb4bf73e73b33f3470a381ea75`, `src/rivian/parallax/proto/`, generated `_pb2` decoders, **73** topics | mechanically, from the compiled protobuf descriptors (`RVMDecoder.messages`), not by regex |
| **APK** | app 3.15.0 (4804) and 3.16.0 (4884), `docs/development/apk/schema/` (s42) | the committed JSON; 3.16.0 is quoted, 3.15.0 agrees on every finding below |
| **wire** | the 45 live captures in `tests/client/fixtures/parallax/` | decoded raw, then through both clients |

An APK schema is one of two strengths, and every row below says which:

- **bound** — the app parses the topic with this class (`apk_parallax_schema_<ver>.json`). Authoritative.
- **name-match** — the class has a parse entry point nobody calls (`uncalled_parse_wrappers_<ver>.json`, or a unique shape match in `message_index_<ver>.json`), and its field names say which topic it is. Strong, but not a binding.

## Headline

| | ours | bretterer |
|---|---|---|
| decoders that return **nothing** on their own live capture | 2 (`time_estimation`, `seat_conditioning_status`) | 1 (`seat_conditioning_status`) |
| decoders that return a **wrong value** on their own live capture | 2 (`charge_session_breakdown` power, Gear Guard consent†) | 6 (preconditioning, alarm, passive-entry debug, remote-command, `isActive`, Gear Guard consent†) |
| enum maps that mislabel values not in a capture | 4 | 5 |
| topics the APK binds that the client does not decode | 7 | 0 |

† name-match evidence, not bound; see the finding.

Where the two clients disagree on a captured value of a bound topic, **ours matches the APK every time** except
`time_estimation`.
bretterer's schema is mostly reverse-engineered from live payloads (`field_4 // unmapped; possibly speed`), so
its field *numbers* are almost always right and its *meanings* are where it drifts. Ours was transcribed from
the APK for the f5 set and is right there; the decoders that predate f5 are where ours drifts.

## Status (s43)

**The APK is the authority** (owner's decision, 2026-10-03). Where a decoder and the app disagree, the app wins,
including where the APK evidence is a name-match rather than a binding (O5, O8).

| | fixed in s43 |
|---|---|
| O1 `time_estimation` | reads #2 minutes; INVALID / PACK_DISCHARGING suppress it |
| O2 `seat_conditioning_status` | decodes `c1i`'s repeated `levels`; a listed surface with no level is `Off` (the enum has no OFF member) |
| O3 preconditioning | full `p22` vocabulary; empty payload is `undefined`, not `off` |
| O4 `charge_session_breakdown` | `nl2`: #8 range added, #9 power, #10 range rate; no estimates |
| O5, O8 Gear Guard consent, daily limit | `vpl`, `uc5` numbering; live consent now reads `consented` |
| O6 defrost | `lv5`: Defog, Defrost, Defog_Defrost, Off |
| O7 power state | `qqf` 5–7 added; unknown values keep the deliberate `standby` fallback (`test_connectivity.py`) |
| O9 battery state | phantom `rangeKm` removed |
| proto | `rivian_security.proto` and `rivian_energy.proto`: seven 3.6.0-offset enums re-based on 3.16.0 |
| passive-entry debug | not a bug: the capture carries only #2 (`send_lock_fail_notification` = FALSE); the old "decoder reads the wrong field" diagnosis is withdrawn |

Pinned in `tests/test_parallax_s43_apk_authority.py`, against both the APK JSON and the captures.

## Status (s44)

The five APK-bound topics in the first table of "What bretterer has that we lack" are decoded, from the APK schema
rather than bretterer's (`tests/test_parallax_s44_decoders.py`):

| topic | emits | entity |
|---|---|---|
| `charging.session.soc_slider` | `batteryLimit` | existing `battery_limit` |
| `charging.session.remote_command` | `remoteChargingAvailable` (0/1 from START_AVAILABILITY) | existing; gates the charging switch |
| `charging.session.notification` | `chargerDerateStatus` (gateway casing), `chargingFaultChime` | existing `charger_derate_status`; **new** `charging_fault_chime` |
| `charging.session.trip_target` | `tripTargetSoc` | **new** `trip_target_soc`, disabled by default (no capture) |
| `ota.deployment.state` | `otaCurrentVersion*`, `otaAvailableVersion*`, `otaStatus`, `otaCurrentStatus`, `otaDownloadProgress`, `otaInstallProgress` (firmware category only, gateway casing) | existing OTA sensors and update entity |

Where the gateway names the value, the subscription still wins (gap-fill rule); Parallax only fills gaps. Not
decoded, because the app gives no unit or vocabulary: notification #1 stop reason, trip-target #2 time and #3
status, OTA install time / duration / type / install-ready.

## Status (s45)

Owner decisions: decode every name-matched topic (entities disabled where no frame is captured), and enable
trip-target sensors on the APK binding alone. `apk/schema/FOLLOWUP_S45.md` (from the APK) answered the open
questions.

| | |
|---|---|
| name-matched decoders | `body.windows.states` (`zzn` → `window*Calibrated`), `comfort.cabin.hvac_settings_status` (`e9a`), `comfort.user_modes.state` (`uql` #1/#2 → `serviceMode`/`carWashMode`), `geofence…favoriteGeofences` (`wq7`), `navigation…trip_progress` (`u3l`), `ota.ota_state.vehicle_ota_state` (`ugm`), `ota.user_schedule.ota_config` (`rfe`), `secure_file_transfer.pet_snapshot.secure_file` (`g2i`, metadata only), `vehicle_access.state.passive_entry` (`fre`), `energy_edge_compute.graphs.cold_weather_soc` (`jx3`) |
| request-side binding | `vehicle_access.passive_entry.passive_entry` → `fre` (the app sends it there) |
| `ota_install_ready` | **fixed**: on_value is `ota_available`, the wire string the app maps to AVAILABLE; `"available"` never arrived, so the binary sensor could never turn on. `ota.deployment.state` now also emits it from `install_ready` |
| derate status | only the seven members the app maps; the other eleven emit nothing (the app keeps the previous value) |
| trip target | `#2` is minutes → new `trip_target_time_remaining` |
| not decoded, no evidence anywhere | `uql` #3–#7, `wwd` #1, `d5l` #3, `r1e` ota_type / download_policy / pause_reason / status_acknowledge — their enums are in none of 54 app versions; `charging.schedule.time_window` (`pak`: no unit or day numbering), `navigation…trip_info` (`bvk`), `device_table.vas_keyper.devices` (`y5b`: key material and unrecoverable enums) |
| cold weather SOC | `jx3` decoded → `coldWeatherSocGreen` / `Blue` (%), `coldRangeImpact` (km); units from the field names, meaning of green/blue not in the app |

Pinned in `tests/test_parallax_s45_name_match.py`.

## Status (s46 capture)

A 300 s additive capture of the ten unwitnessed topics (`wt/rvm-captures`):

| topic | result | action |
|---|---|---|
| `charging.session.trip_target` | committed, `10ffff03`: #2 = 65535, no SOC | no trip target: the app shows one only for SOC 1–100 and has no minutes sentinel (`apk/schema/FOLLOWUP_S47.md`) |
| `geofence…favoriteGeofences` | arrived, withheld (place names); shape matches `wq7` | entity enabled |
| `navigation…trip_progress` | arrived, withheld (GPS); shape matches `u3l` | four entities enabled |
| `charging.schedule.time_window` | arrived, withheld (location); shape matches `pak` | still not decoded: no units |
| `ota.user_schedule.ota_config` | empty payload | entity enabled (reads `none`) |
| `navigation…trip_info` | empty payload | not decoded |
| both passive-entry topics, pet snapshot, `body.windows.states` | silent | entities stay disabled |

Withheld frames are checked by shape only, with invented values (`TestTheS46CaptureShapes`).

## Bugs in ours

### Confirmed (APK bound **and** the live capture agree)

| # | topic | ours | APK (3.16.0 class) | live capture | effect |
|---|---|---|---|---|---|
| O1 | `charging.session.time_estimation` | reads **field 1** as `timeToEndOfCharge` (`parallax.py:570`) | `o9k`: #1 `validity_flag` enum, **#2 `remaining_minutes`** uint32 | `1040` = #2 = 64 | decoder returns `{}` on every real frame. The sensor's unit is already minutes (`const.py:819`), so reading #2 needs no conversion. bretterer has this right |
| O2 | `comfort.cabin.seat_conditioning_status` | reads fields 7–12 as per-seat submessages (`SEAT_STATUS_FIELDS`, `parallax.py:807`) | `c1i`: one repeated #1 `levels` {#1 `instance`, #2 `device` HEAT/VENT, #3 `level` LEVEL1–3} | 9 × #1 {instance, device} | decoder returns `{}` on every real frame. Root cause: fields 7–12 are the layout of **`mtm`**, the vehicle-state *preconditioning* blob (`seat_heat_status_front_left = 7` …), not this topic's message. bretterer is also silent here (wrong enum, see T6) |
| O3 | `comfort.cabin.cabin_preconditioning_status` | 4 → `active`, **1 and 2 → `initiate`**, everything else → `off` (`parallax.py:560`) | `p22`: 1 INITIATE, **2 ACTIVE**, 3 ACTIVE_WARNING, 4 COMPLETE_MAINTAIN, 5–7 timeout/errors, 8 UNAVAILABLE, 9 TIMEOUT_COMPLETE | `0808` = 8 (UNAVAILABLE) → ours `off`, acceptable | 2 (actually running) reads `initiate`; 3 (running with a warning) reads `off` |

### Confirmed by name-match plus live capture

| # | topic | ours | APK | live | effect |
|---|---|---|---|---|---|
| O4 | `energy_edge_compute.graphs.charge_session_breakdown` | **field 10** read as "charge power integer (kW)" and used as `power` when #9 is absent (`parallax.py:245`); `rangeAddedThisSession` *estimated* as kWh × 3.5 | `nl2` (the only class in either build matching the capture's 9 fields): #8 `range_added_kms`, #9 `current_power`, **#10 `current_range_per_hour`**, #7 `time_remaining_mins`, #6 `session_duration_mins`, #13 `charging_state` | #10 = 2, #8 = 20, #13 = 4 (complete) | on a **completed** session ours reports 2.0 kW and 21.7 km added; the vehicle said 0 kW and 20 km. bretterer reads this one correctly |
| O5 | `gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent` † | 1 consented, **2 not_consented**, 3 not_applicable, 4 unknown (`_GEAR_GUARD_CONSENT`, `parallax.py:1419`) | `vpl` #1 `user_consent`: 0 UNKNOWN, 1 NOT_APPLICABLE, **2 CONSENTED**, 3 NOT_CONSENTED | `0802` = 2 | if `vpl` is this topic's message, the live entity shows `not_consented` for a consenting owner. bretterer has the identical map. **Owner can settle this in seconds**: is Gear Guard streaming consent granted in-vehicle? |

† The enum in `rivian_security.proto` came from the 3.6.0 transcription and is offset from the 3.16.0 wire numbers
in the same way for three messages (consent, daily limit, CCC passive permission). That is a systematic error, not a
one-off. The daily-limit capture (`2`) happens to decode to `not_hit` under both readings, which is why the offset
went unnoticed.

### Enum gaps, not in any capture (APK name-match or bound)

| # | topic | ours | APK | effect |
|---|---|---|---|---|
| O6 | `comfort.cabin.defrost_defog_status` | 2 → `Defrost`, **anything else → `Off`** (`parallax.py:417`) | `lv5`: 1 DEFOG, 2 DEFROST, 3 DEFOG_DEFROST, 4 OFF | defog (1) and defog+defrost (3) report `Off`. The sensor already has a `Defog` option (`const.py:281`) |
| O7 | `vehicle.power.state` | unknown values default to `standby` (`parallax.py:536`) | `qqf`: 5 VEHICLE_RESET, 6 OTA_UPDATE, 7 SHUTDOWN | an OTA install reads as `standby` |
| O8 | `gearguard_streaming_daily_limit` | 1 → `undefined`, 3 → `hit` (`_GEAR_GUARD_DAILY_LIMIT`) | `uc5`: 0 UNDEFINED, **1 HIT**, 2 NOT_HIT | a hit limit (1) reads `undefined`; same 3.6.0 offset as O5 |
| O9 | `energy.high_voltage.battery_state` | reads a `rangeKm` float at `charge_state.#3` (`parallax.py:184`) | `bc1.charge_state` has only #1, #2 | phantom field, never present on the wire. Harmless; ours also leaves #2 cell temperatures, #3 thermal event and #4 power output undecoded |

### Agree with the APK (no action)

`body.closures.states`, `body.trailer.state`, `charging.session.status` (raw ints), `comfort.cabin.climate_hold_status`,
`comfort.cabin.pet_mode_status`, `dynamics.vehicle.{drive_mode,gear,gnss,location,odometer,range}`,
`energy.high_voltage.battery_characteristics`, `energy.low_voltage.battery_state`, `security.access.{btm,immobilizer_state,
passive_entry_debug,vas_fault}`, `security.alarm.state`, `security.video_monitoring.state`, and, by name-match,
`dynamics.tires.state` (`ydk`/`xdk`), `vehicle.wheels.vehicle_wheels` (`iwn`), `comfort.cabin.climate_hold_setting`
(`wl3`), `energy_edge_compute.graphs.{charging_graph_global (qs2), parked_energy_distributions (hpe)}`.

Two things worth a look but not called bugs:

- `comfort.cabin.cabin_temperatures` #4 is `interior_display_temperature_celsius` (`d32`), which ours emits as
  `cabinClimateDriverTemperature`. In the capture it is 21.0 against an interior of 36.0 and an HVAC set point of
  21.0 (`hvac_settings_status`), so "driver temperature" is plausibly the display set point, which may be the
  gateway's meaning too. Not changed.
- `comfort.cabin.cabin_ventilation_setting`: ours (and bretterer) read #2–#5 from the 3.6.0 proto; `bm3` has only #1.
  They are never on the wire, so they never fire.

## Bugs in bretterer

Reported here, not upstream. Each is APK-bound unless marked.

| # | topic | bretterer | APK | live capture shows |
|---|---|---|---|---|
| T1 | `comfort.cabin.cabin_preconditioning_status` | 2 INITIATE_2, **4 ACTIVE**, **8 PET_COMFORT** | 2 ACTIVE, 4 COMPLETE_MAINTAIN, **8 UNAVAILABLE** | **`active` for an unavailable system** |
| T2 | `security.alarm.state` | #1 `consecutive_alarm_disabled_notification`, #2 `sound_status` enum — **fields swapped** | #1 `sound_alarm` enum (1 FALSE, 2 TRUE, 3 SNA), #2 `consecutive_alarm_disabled_notification` bool | `alarmSoundStatus: null`, `consecutiveAlarmDisabledNotification: 1` |
| T3 | `security.access.passive_entry_debug` | the 13 unlock-fail reasons on **#2** | reasons on **#1**; #2 is `send_lock_fail_notification` (0 SNA, 1 TRUE, 2 FALSE) | `at_home_disable` from a frame that says "send lock-fail notification: false" |
| T4 | `charging.session.remote_command` | 1 START, 2 STOP | `start_available`: 0 SNA, 1 FALSE, 2 TRUE | `start` from "start not available" |
| T5 | `charging.session.status` | #3 `is_active` bool | #3 `evse_type` enum | `isActive: false` derived from the EVSE type |
| T6 | `comfort.cabin.seat_conditioning_status` | level enum on #3 | #3 `level` 1–3 (LEVEL1–3) — shape right, but ids 2–4, 6, 9, 12, 14 missing | `{}` (same silence as O2) |
| T7 | `ota.deployment.state` | #1.#1 as `deploymentState`, `time_remaining` (#6), `update_cycle_count` (#8), `late_stage_flag` (#11); OTA status 8 = SCHEDULED_TO_INSTALL | #1.#1 `category`, #6 `countdown_timer`, #8 `status_acknowledge` enum, #11 `is_active`; status **8 READY_TO_INSTALL, 9 SCHEDULED_TO_INSTALL** | labels mislead; the version fields decode right |
| T8 | `user_passcodes.passcode_types.drive_auth` | 1 DISABLED, 2 ENABLED | 0 SNA, 1 NONE, 2 MOBILE_NOTIF | (no capture) |
| T9 | Gear Guard consent / daily limit † | same offset enums as ours (O5, O8) | `vpl`, `uc5` | same as ours |
| T10 | `comfort.cabin.defrost_defog_status` † | 2 DEFROST_ACTIVE only | `lv5` 1–4 as O6 | — |
| T11 | `energy.high_voltage.battery_state` | #3 as `string` | #3 `thermal_event` message {two bools} | empty on the capture, so no symptom yet |

Type-only differences (bretterer `int32`/`int64` where the APK has `uint32`/`enum`/`bool`) are wire-compatible
varints and are not listed; `theirs_vs_apk` in the method section below reproduces all 358 lines.

## What bretterer has that we lack

Of bretterer's 73 topics, 36 are not decoded here. Sorted by evidence:

**APK-bound, live-captured, and bretterer decodes correctly** — take these first:

| topic | APK | capture | value |
|---|---|---|---|
| `charging.session.soc_slider` | `hgh` #1 `user_soc_limit` | `0855` = 85 | charge limit |
| `ota.deployment.state` | `r1e` (large) | 54 B: `2026.31.0`, idle | current/available OTA; use the APK names, not T7's |
| `charging.session.notification` | `wwd` #1 stop reason, #2 derate status (16 values), #3 fault chime | `0801` | derate reason while charging |
| `charging.session.remote_command` | `dsg` #1 `start_available` | `0801` | use the APK meaning, not T4's |
| `charging.session.trip_target` | `d5l` #1 soc, #2 time estimate, #3 status | — | bretterer reads #2 only |

**Name-match, and bretterer's field numbers agree with the APK class:** `charging.schedule.time_window` (`pak`),
`comfort.cabin.hvac_settings_status` (`e9a`, capture: 21.0 °C), `comfort.user_modes.state` (`uql`: in_service,
car_wash, pet_mode, camp_mode, transport_mode, climate_keep, factory_mode; capture #4 = 2, #7 = 4),
`energy_edge_compute.graphs.cold_weather_soc` (`jx3`: also #2 `soc_perc_blue`, #3 `cold_range_impact_km`),
`navigation.navigation_service.{trip_info (bvk), trip_progress (u3l)}`, `ota.user_schedule.ota_config` (`rfe`),
`ota.ota_state.vehicle_ota_state` (`ugm`), `vehicle.profiles.active_user` (`mj`, new in 3.16.0),
`geofence.geofence_service.favoriteGeofences` (`wq7`), `device_table.vas_keyper.devices` (`y5b`).

**In neither app's RVM enums.** Nine are also absent from every `.java` file and from the dex in both builds
(s42's byte search): `body.wipers.fluid_level`, `charging.energy.state`, `charging.session.power`,
`departure.schedule.schedule`, `dynamics.brakes.fluid_level`, `dynamics.vehicle.{efficiency,mass_estimate}`,
`parallax.wakeup.heartbeat`, `vehicle.setting.network`. Seven more, `charging.smart_charging.*` (3) and
`holiday_celebration.*` (4), are not in either RVM enum, but s42 did not full-text search for them. Whatever bretterer knows about these came from live traffic
alone; the live capture is the only check available. `charging.energy.state` is captured here (10 B) and bretterer
reads `chargerStatus: chrgr_sts_not_connected` from it, with three fields it leaves unnamed.

## Not checked

- Topics with no capture **and** no APK schema: bretterer's decoders for them cannot be verified offline at all.
- The 18 bound enum fields the APK cannot attribute (`"enum": null`, s42 README), e.g. `charging.session.status`
  #3 `evse_type`, `charge_session_breakdown` #13: field numbers are verified, value names are not.
- Tire status values (`xdk.status`): the enum is not attributable, so ours `1 → OK, else Warning` is unverified.

## Proposed follow-ups

Each is its own `sNN` story with a test pinned to the capture or the APK JSON.

1. **O1 + O2 + O4** — the three decoders that are silent or wrong on their own capture. Highest value, smallest diff.
2. **O3 + O6 + O7** — complete the preconditioning, defrost and power-mode enums from the APK.
3. **O5 + O8** — ask the owner the one consent question, then re-base the three 3.6.0-transcribed enums
   (`rivian_security.proto`) on the 3.16.0 numbers.
4. **New decoders** from the first table of "What bretterer has that we lack", using the APK schema, not bretterer's.
5. Optionally, send T1–T5 to bretterer as an issue, with the APK class names and the capture bytes.

## Method

Done 2026-10-03, offline, against s42's committed schema. Reproduce with a venv carrying `protobuf`:

- **bretterer vs APK**: for each topic in both `RVMDecoder.messages` and the APK schema, walk the message
  descriptor and the APK field tree in parallel by field number, recursing into submessages, and compare wire
  type, type and every enum number→name.
- **ours vs APK**: by reading each decoder against `apk_parallax_schema_3.16.0.json`; the f5 enum maps were also
  compared value by value.
- **wire**: each fixture parsed as raw protobuf, then run through `RVM_DECODERS[topic]` and bretterer's
  `_decode_rvm_payload(payload, topic)`.
- **name-match**: each unbound capture's top-level `{field: wire type}` matched against every class in
  `message_index_3.16.0.json`; a match is only cited where it is unique or the field names name the topic.
