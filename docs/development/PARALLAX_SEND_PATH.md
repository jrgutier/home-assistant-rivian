# Parallax send path — envelope derivation

**Date: 2026-08-19.** Branch `post-beta6`. Step 5 of
`.omc/plans/open-questions-resolution.md`. Anchored on the **3.15.0 artifacts**
alone. The 3.6.0 tree is cited only as labelled context, never as a mapping.

Closed verdicts, so a stub cannot pass:

- **RVM: NOT DERIVABLE**
- **payload mapping: NOT DERIVABLE**
- **two-factor state surface: NOT FOUND**

No builder is written. `custom_components/rivian/rivian_client/` is untouched.
Steps 6 and 7 do not run.

---

## Anchoring rule (N5)

`ParallaxAttributes` exists only in the **3.6.0 tree**. The seven invalid-wrapper
commands exist only in the **3.15.0 artifact** `docs/development/apk/VASCommand.java`.
The shapes differ:

| | 3.15.0 artifact | 3.6.0 tree |
|---|---|---|
| `ParallaxAttributes.java` | **absent** (not one of the nine pre-flight copies; not next to `VASCommand.java`) | present, `com.rivian.android.core.modules.ParallaxAttributes` |
| command-name accessor | `VASCommand.name()` calls `parallaxAttributes.getPxCmdName()` | `getName()` (returns `"parallax_" + rvm`) |
| `getPxCmdName` in that extraction | the call site above | **0 files** |

These are two different classes with the same name. A payload mapping taken from
the 3.6.0 class and applied to a 3.15.0 command would be an unlabelled
cross-version inference — the N5 defect. This document does not do that.

The 3.6.0 class is recorded below as **context**, under its own heading, so a
reader who takes Follow-up 2 (re-extract 3.15.0 with apktool) has the contrast.
It is not evidence for a mapping.

---

## Stop 1 — the RVM for each of the seven

**RVM: NOT DERIVABLE**

The seven (`PET_COMFORT_ON`, `PET_COMFORT_OFF`,
`START_VIDEO_DOWNLOADING_SESSION`, `TWO_FACTOR_DRIVE_ALLOW`,
`TWO_FACTOR_DRIVE_DENY`, `TWO_FACTOR_DRIVE_DISABLE`,
`TWO_FACTOR_DRIVE_ENABLE`) live in the 3.15.0 artifact as ordinary
`VASCommand` subclasses. Each builds `cloudData` with
`generateInvalidCloudDataWrapper` and a command-name string. None of them
overrides `getParallaxAttributes`. None of them names an RVM.

`VASCommand.ParallaxCommand` is a different subclass. Its constructor is:

```
ParallaxCommand(String commandId, long createdAt,
                CloudDataWrapper cloudData,
                ParallaxAttributes parallaxAttributes,
                boolean isPxRequestOnly)
```

It takes a **commandId** and a **createdAt** timestamp. That is the signature of
a command the app **received** at runtime, with `parallaxAttributes` supplied
from outside and stored. There is no literal construction site to find, because
in this class there was never going to be one.

Searches run against the 3.15.0 artifacts (`docs/development/apk/*.java`):

| probe | result |
|---|---|
| `new ParallaxCommand(` besides the constructor itself | **0** |
| `new ParallaxAttributes(` | **0** (the class is not in the artifacts) |
| `getPxCmdName` | **1** — `VASCommand.name()`, a read of a supplied object, not a bind |
| `getRvm()` | **2** — `VASCommand.equals` / `hashCode`, comparing supplied objects |
| any of the seven command-name strings next to an RVM-shaped `a.b.c` topic | **0** |
| `PET_COMFORT` / `TWO_FACTOR` / `VIDEO_DOWNLOADING` in `l6e.java` | **0** command bindings. `l6e` has a **read** topic `comfort.cabin.pet_mode_status` (`COMFORT_CABIN_PET_MODE_STATUS`). That is the pet-mode *status* RVM this integration already decodes; it is not a write RVM for `PET_COMFORT_ON` / `_OFF`. |
| `user_passcodes` / `drive_auth` in `l6e.java` | **0** |

`VehicleFeature` names `TWO_FACTOR_DRIVE` and `PET_COMFORT_CONTROL` as
capabilities. A capability is not an RVM and is not a send envelope.

`isParallaxRequestOnly` is true for `TwoFactorDriveEnable` and
`TwoFactorDriveDisable` only (`VASCommandKt.isParallaxRequestOnly`). The
predicate does not name an RVM either.

**Stop.** Without an RVM name bound to a command, `send_vehicle_operation`
cannot be aimed. The send path is not built.

---

## Stop 2 — the payload mapping

**payload mapping: NOT DERIVABLE**

The 3.15.0 artifacts do not contain `ParallaxAttributes`. The only mentions are
field types and accessors on `VASCommand` / `ParallaxCommand` (`getRvm()`,
`getPxCmdName()`). There is no field list, no constructor with named payload
arguments, and no literal `parallaxCommonPayload` / `parallaxOpPayload` /
`rvm` value.

A mapping shown only from the 3.6.0 class is **not adopted**. See context
below. Our `send_vehicle_operation` carries one `payload`
(`rivian_client/rivian.py`); guessing that the two 3.6.0 strings concatenate,
or that one is `Metadata` and one is `Operation`, would be the guess this step
exists to refuse.

---

## Stop 3 — whether the server accepts the RVM at all

Gated on stop 1. There is no RVM to ask about for the seven.

`SENDVEHICLEOPERATION_TEST_RESULTS.md` is the record that justified pruning
`RVMType` from 18 to 4. **The file is absent** (N7): `ls` returns "No such file
or directory"; `git log --all --diff-filter=A --name-only` never added it;
`git show 28de279:docs/development/SENDVEHICLEOPERATION_TEST_RESULTS.md` is
`fatal: path does not exist`. The citations are in this repository; the
document they point at is not and appears never to have been committed here.

### What the six citing files still say

Nine occurrences, six files, reconstructed rather than guessed:

| file | what it records |
|---|---|
| `scripts/gates/s09a.sh` | Removed entities targeted RVMs that return `INTERNAL_SERVER_ERROR` to `sendVehicleOperation` **in both directions**. `build_*` count pinned at **4** (was 21). `RVMType` pinned at **4** (was 18). Client methods `set_halloween_settings`, `set_cabin_ventilation`, `set_vehicle_geofences`, `set_gear_guard_consents`, `set_passive_entry_settings` must stay gone. |
| `custom_components/rivian/rivian_client/parallax.py` `RVMType` | "Rivian's Android app (`EnumC6207c.java`) declares 18. Only four are accepted … the rest return `INTERNAL_SERVER_ERROR` in BOTH directions, recorded in `docs/development/SENDVEHICLEOPERATION_TEST_RESULTS.md`." The four that ship: `comfort.cabin.climate_hold_setting` (the one verified **write**), `comfort.cabin.climate_hold_status`, `vehicle.wheels.vehicle_wheels`, `ota.user_schedule.ota_config`. |
| `tests/client/test_parallax_commands.py` | "**Ten of the fourteen tested** return `INTERNAL_SERVER_ERROR` in BOTH directions." The four that remain are the four in `RVMType` above. |
| `tests/test_parallax_controls.py` | Halloween switch/select/number tests deleted with their entities for the same ISE reason. |
| `tests/client/test_climate_hold_encoder.py` | `08a038` is 7200 s (two-hour hold), "recorded in `SENDVEHICLEOPERATION_TEST_RESULTS.md`". Independently, `08ac02` is a live 5-minute hold captured from the vehicle. |
| `tests/client/test_fork_rvm_decoders.py` | Same `08a038` == 7200 s citation. |
| `parallax.py` `encode_climate_hold_setting` | Repeats both hex values. |

**Unreconciled, and not guessed at:** `RVMType`'s docstring says the rest of 18
(fourteen) return ISE in both directions. `test_parallax_commands.py` says
"**Ten of the fourteen tested**". Those are different claims. The missing file
is what would settle which four of the fourteen were untested, if any. This
document does not pick one.

**Also cannot be reconstructed:** the per-RVM table, the request/response
bodies, whether "both directions" means GET+SET or two payload shapes, dates,
vehicle, firmware.

Re-add an RVM only after a live test shows the server accepts it — `s09a.sh`
and `RVMType`'s docstring already say so. This step does not add one.

---

## Two-factor state surface

**two-factor state surface: NOT FOUND**

The question is whether a GraphQL field or a Parallax RVM feeds the boolean
that selects `TWO_FACTOR_DRIVE_ENABLE` vs `_DISABLE`, such that Step 7 could
read it back from this integration. It cannot.

### 3.15.0 artifacts

No GraphQL field named for the enable/disable setting. `l6e.java` has no
`drive_auth` / `user_passcodes` / `two_factor` topic. `VehicleFeature` has
`TWO_FACTOR_DRIVE` as a capability, not a state field. This integration's
`const.py` / coordinators / sensors carry `petModeStatus` and
`petModeTemperatureStatus` (pet comfort) and nothing for two-factor drive.

`EnumC4141a` (3.6.0 tree, listed here only because the plan named it) is a
**request-code** enum: `ALLOW=1000`, `DENY=1001`, `ENABLE=1002`,
`DISABLE=1003`. A BLE/request code is not a GraphQL field and not an RVM.

### 3.6.0 tree — CONTEXT, not a mapping, not a read-back

The chain the plan named is real and not obfuscated at the UI layer. Run
against `com.rivian.android.consumer/` (3.6.0, versionCode 3989):

`HighSecurityDriveSettingCardFragment.m8596S()` returns viewmodel `C15661S`.
`C15661S.f52773q` is a `MutableStateFlow<Boolean>` **seeded `Boolean.FALSE`**.

What writes it:

1. **The toggle itself** (`C14283D0`, case 8). The UI boolean is written into
   `f52773q` *before* the command is sent. Then
   `booleanValue3 ? "TWO_FACTOR_DRIVE_ENABLE" : "TWO_FACTOR_DRIVE_DISABLE"`
   and `C0080E.m22605n(...)`.
2. **Failure rollback** of that same toggle.
3. **A cloud-decoded `C8853e`** (`C15646K` case 2):
   `f52773q = (c8853e.driveAuthSetting != EnumC10498D.NONE)`.
   `C8853e` is built from protobuf `C23909f` (`DRIVEAUTHSETTING_FIELD_NUMBER = 1`;
   enum `SNA=0`, `NONE=1`, `MOBILE_NOTIF=2`) by `C6490l0` case 6, which is
   bound as the decoder for `EnumC2947c.USER_PASSCODES_DRIVE_AUTH`
   (`"user_passcodes.passcode_types.drive_auth"`). `C0080E.m22605n` **writes
   the same RVM** — so in 3.6.0 the app's toggle is a Parallax read/write of
   that topic, not a `sendVehicleCommand` of `TWO_FACTOR_DRIVE_ENABLE`.

`PARALLAX_DECODERS.md` already records this topic as living in a **second**
RVM enum (`iol.java` / `EnumC2947c`), not in `l6e`. It is absent from the
3.15.0 `l6e.java` artifact. It is absent from this integration's `RVMType`
(the four the server has accepted). There is no decoder and no entity for it
here.

`driveAuthorizationUserInputRequestStatus` / `twoFactorDriveAllow` /
`twoFactorDriveDeny` (GraphQL-shaped names in the 3.6.0 tree) are the
**ALLOW/DENY challenge**, event-shaped, not the enable/disable setting.

So: the 3.6.0 app has a Parallax surface for the toggle. That surface is a
different extraction, a different RVM table, and is not readable from this
integration or from Home Assistant. Adopting it as the 3.15.0 command's RVM
would be the N5 defect. It is a lead for Follow-up 2, not a mapping, and it
does not open Step 7. `_guardrails[7]` still cannot be discharged.

---

## 3.6.0 `ParallaxAttributes` — CONTEXT only

Present at `com.rivian.android.core.modules.ParallaxAttributes`. Three
`String` fields: `parallaxCommonPayload`, `parallaxOpPayload`, `rvm`.
`getName()` returns `"parallax_" + rvm`. **No `getPxCmdName`.**
`grep` for `new ParallaxAttributes` across the whole 3.6.0 tree: **0**.
Same received-object pattern as the 3.15.0 `ParallaxCommand` constructor.

This class is not used to derive a payload mapping for the seven.

---

## Consequences

- Steps 6 and 7 do not run. Their precondition is both stop-1 and stop-2
  recording the positive `derived` token; both recorded `NOT DERIVABLE`.
- Ruling 18's send path is not built, because there is nothing to aim
  `send_vehicle_operation` at. The transport that already exists
  (`send_parallax_command` → `send_vehicle_operation`) is unchanged.
- Follow-up 2 (re-extract 3.15.0 with apktool so `ParallaxAttributes` and
  the seven come from one build) is the strongest remaining way to reopen
  this. This step does not reopen ruling 20.
- The two-factor 3.6.0 RVM `user_passcodes.passcode_types.drive_auth` is
  recorded as a labelled lead, not as a sendable envelope.

---

## Commands that produced the counts

```
# 3.15.0 artifacts
grep -l 'new ParallaxCommand\|new ParallaxAttributes\|getPxCmdName' \
    docs/development/apk/*.java
#   VASCommand.java only; constructor definition + getPxCmdName at name()

grep -c getPxCmdName docs/development/apk/VASCommand.java
#   1

# 3.6.0 tree
grep -rl 'getPxCmdName' com.rivian.android.consumer/java_src | wc -l
#   0

grep -rl 'class ParallaxAttributes' com.rivian.android.consumer/java_src
#   .../core/modules/ParallaxAttributes.java

grep -rn 'new ParallaxAttributes' com.rivian.android.consumer --include='*.java' | wc -l
#   0

ls docs/development/SENDVEHICLEOPERATION_TEST_RESULTS.md
#   No such file or directory
```
