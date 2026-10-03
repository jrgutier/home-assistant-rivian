# s45 follow-up: five questions only the decompiled trees can answer

Read off `.apk/3.16.0/jadx/sources` (build 4884), cross-checked against 3.15.0
(build 4804) and, where a question is about a class that might have been
stripped, against all 54 trees. Sites are `defpackage/<file>:<line>` in 3.16.0
unless marked. Nothing here is a capture; it is what the app's code says.

## 1. `otaInstallReady` — `"ota_available"` is the install-ready member

The mapping is in `xqm.java:1312-1318` and again at `2303-2309` (3.15.0:
`i0m.java:1312` and `2301`). The value read is the stored `otaInstallReady` string
(`fqm.N0`, named by `fqm.toString()` at `fqm.java:1028`):

| raw string | `OverTheAirInstallReady` |
|---|---|
| `"ota_available"` | `AVAILABLE` |
| `"ota_not_available"` | `NOT_AVAILABLE` |
| anything else | `NOT_AVAILABLE` |

`"available"` is not a string the app compares against anywhere, so a binary sensor
whose on-value is `"available"` never turns on. `BINARY_SENSOR_AUDIT.md` has the
enum members right and the wire strings wrong.

The app also *produces* the same two strings from Parallax: `uf7.java:1778`
(3.15.0: `ds6.java:15757`), inside the `ota.deployment.state` handler, writes
`"ota_available"` when its `OtaActiveStatusDto.installReady` is true and
`"ota_not_available"` otherwise. The message has a matching bool,
`available_ota.ota_progress.install_ready` (field 7); the step from that field
into the DTO was not traced line by line.

## 2. The `"enum": null` fields

**The enum classes are not in the app.** Protobuf-lite stores an enum field as an
`int`; the enum class is only linked through a typed accessor, and R8 removes both
the accessor and the class when nothing reads the field. Searched for the
constants by prefix in all 54 trees (`UNEXPECTED_STOP_REASON_*`, `OTA_TYPE_*`,
`DOWNLOAD_POLICY_*`, `PAUSE_REASON_*`, `STATUS_ACKNOWLEDGE_*`,
`TRIP_TARGET_STATUS_*`, `WCC_VERSION_*`, `DEV_TYPE_*`), and by listing every enum
beside the owning message in 3.13.1, where package structure survives. Only the
`*_FIELD_NUMBER` constants exist.

| field | number → constant | evidence |
|---|---|---|
| `uql` #3–#7 `pet_mode`, `camp_mode`, `transport_mode`, `climate_keep`, `factory_mode` | **not recoverable** | only `in_service` and `car_wash` have accessors, both `nad` = `MODE_STATUS_UNSPECIFIED(0)`, `MODE_STATUS_ON(1)`. Nothing links #3–#7 to `nad` or to anything else |
| `wwd` #1 `unexpected_stop_reason` | **not recoverable** | no accessor, no enum class in any version. The app reads only #2 and #3 |
| `d5l` #3 `status` | **not recoverable** | no accessor; the app reads only #1 and #2 |
| `r1e` … `ota_type`, `download_policy`, `pause_reason`, `status_acknowledge` | **not recoverable** | no accessor on `t01`, `i1e`, `k1e`, `o1e`; no enum class in any version |
| `y5b` `display.devtype`, `display.wccversion`, `key_device_cloud.vehicle_response_required` | **not recoverable** | `y5b` is referenced nowhere outside its own file; in 3.13.1 the device-table package has two enums, device OEM and device status, and no others |

Two things the search did turn up:

- **`MODE_STATUS` changed shape.** In 3.9.0 and 3.10.0 it is
  `UNSPECIFIED(0)`, `OFF(1)`, `ON(2)`, `DISABLED(3)`, used by a two-field message
  (`car_wash_mode_status` = 1, `service_mode_status` = 2). From 3.11.0 on it is
  `UNSPECIFIED(0)`, `ON(1)` and the message is the six-field one (seven, with
  `factory_mode`, in 3.15.0 and 3.16.0). So `1` meant *off* in the old message and means *on*
  in the current one.
- **`wwd` #2 `derate_status` is what the app turns into the `chargerDerateStatus`
  strings** (`c97.java:296-333`): `none`, `nearing_toc`, `evse_derating`,
  `battery_cooling`, `battery_heating`, `ac_warm_plug`,
  `near_toc_lfp_batt_calibrating`; the other eleven members leave the previous
  value in place. `fault_chime` is reduced to one test,
  `== FAULT_CHIME_CHARGING_DISABLED_ALL`.

**`d5l` #2 `time_estimate` is minutes.** `c97.java:591` passes it unmodified into
the charging model field named `chargingTripTargetMinsRemaining`
(`qp2.toString()`, `qp2.java:131`); `soc` goes to `chargingTripTargetSoc`.

## 3. Units

**The app does nothing with any of these four messages.** `pak`, `u3l`, `ugm` and
`jx3` are each referenced in exactly one file, their own. The same holds for
their 3.15.0 counterparts, and in 3.13.1, where package names survive, the
equivalent classes are imported by no class outside their own package. There is no multiply, no formatter, no display string to read a
unit from. What the schema itself says:

| field | type | unit evidence |
|---|---|---|
| `pak.window_data.start_time`, `end_time`, `duration` | int32 | **none**; the name carries no unit and nothing consumes it |
| `pak.window_data.start_day_of_week`, `end_day_of_week` | uint32 | **none**; no enum, no consumer, so the numbering (0- or 1-based, Sunday or Monday first) is unknown |
| `pak.window_data.amps` | uint32 | name only |
| `u3l.legremainingdurationseconds` | double | name only: seconds |
| `u3l.legremainingdistancemeters` | double | name only: metres |
| `u3l.legetautc`, `tripetautc` | `google.protobuf.Timestamp` (`seconds` int64, `nanos` int32) | type |
| `ugm.install_time_epoch` | `google.protobuf.Timestamp` | type; not a bare integer, despite the name |
| `jx3.soc_perc_green`, `soc_perc_blue` | uint32 | name only: percent |
| `jx3.cold_range_impact_km` | uint32 | name only: km |

Two neighbours that *are* consumed, for scale: `hold_time_duration_seconds` is
built as `minutes * 60 + hours * 3600` (`vm3.java:53`), and the OTA schedule's
`startsatmin` (`rfe`, uncalled) is named in minutes.

## 4. `vehicle_access.passive_entry.passive_entry` — the message is `fre`

`fre` (3.15.0: `v9e`): `allowpassiveentryviabluetoothwhileinccc` = 1 bool,
`cccpassivepermissionstatus` = 2 enum
(`CCC_PASSIVE_PERMISSION_STATUS_SNA(0)`, `_DISABLED(1)`, `_ENABLED(2)`).

It is bound on the **request** side, which is why a search for parse sites did
not find it. `wy9.java:2225-2234` (3.15.0: `nnb.java:1901-1910`) builds one of
two messages and sends it as a `PARALLAX_OPERATION_REQUEST`:

| branch | message built | field set | topic |
|---|---|---|---|
| V2 | `gre` | #1 status = `ENABLED` or `DISABLED` | `security.access.passive_entry` |
| otherwise | `fre` | #1 bool | `vehicle_access.passive_entry.passive_entry` |

The app never parses a `fre`; it only writes field 1. `hold_time_duration_seconds`
is `wl3`, as suspected, and belongs to `comfort.cabin.climate_hold_setting`
(section 5).

## 5. Callers of the uncalled wrappers

For each class, every file in the 3.16.0 tree that names it, whole-word.

| class | referenced outside its own file | binding |
|---|---|---|
| `ugm`, `rfe`, `pak`, `jx3`, `u3l`, `bvk`, `wq7`, `e9a`, `uql`, `y5b`, `g2i` | **nowhere** | none — no lambda registry, no `java.util.Base64` local, no Flow mapping. Not a missed pattern: the class name does not occur |
| `zzn` | only as an unrelated Google Maps method name | none |
| `fre` | `wy9.java:2225` | request payload for `vehicle_access.passive_entry.passive_entry` (section 4) |

The request side binds two more of the 25 uncalled classes that were not on the
list:

| class (3.16.0 / 3.15.0) | site | topic |
|---|---|---|
| `wl3` / `vh3` | `vm3.java:61-69` / `ui3.java:69` | `comfort.cabin.climate_hold_setting` |
| `iwn` / `b3n` | `ook.java:95-99` / `w3k.java:106` | `vehicle.wheels.vehicle_wheels` |

Those three, plus `gre`, are every typed message the app sends as a Parallax
request; the remaining request sites forward an already-serialised command.
