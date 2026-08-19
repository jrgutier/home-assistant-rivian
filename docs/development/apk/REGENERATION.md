# Regenerating the decompiled classes

The nine `.java` files beside this one are **not tracked in git**. They are
decompiled proprietary sources and this is a public HACS repository, so they are
gitignored (`.gitignore`) exactly as the 31,105-file apktool tree was. They are a
pre-flight artifact: a clean checkout has this file and nothing else, and
pre-flight must re-run before any story that cites them.

What *does* ship is the transcription. Every claim these classes support is
asserted in a test under `tests/`, so the shipped repository can be checked
without the sources present.

## The app

`com.rivian.android.consumer` **3.15.0** (build 4804), obtained as an `.apkm`
bundle from APKMirror.

## The command

```sh
unzip -o <bundle>.apkm -d apkm/          # yields base.apk plus split APKs
jadx -d src --no-res --no-debug-info apkm/base.apk
```

`jadx`, not `apktool`. The distinction is load-bearing: an apktool run of the same
app produces smali-derived Java that **does not contain `l6e.java` or `wcm.java`**,
which is how a reader can find three of the nine classes, conclude the other two do
not exist, and lose the five-document union below.

That run yields 32,941 `.java` files. Copy these nine out of it:

| File | Path under `src/sources/` | What it carries |
|---|---|---|
| `VehicleFeature.java` | `com/rivian/android/consumer/data/model/` | 64 capability members. **Two columns** — member name and `featureName`; 19 differ, and the server emits the `featureName` |
| `VASCommand.java` | `com/rivian/android/core/modules/` | Command subclasses, their `cloudData`, and which wrapper builds each |
| `VASCommandKt.java` | `com/rivian/android/core/modules/` | The command-name constants |
| `l6e.java` | `defpackage/` | The Parallax RVM table — names, and `subscriptionScope` |
| `wcm.java` | `defpackage/` | `vehicleState(id:)` document (128 fields) |
| `cdm.java` | `defpackage/` | `vehicleState(id:)` document |
| `apj.java` | `defpackage/` | `vehicleState(id:)` document — carries the eight tyre fields |
| `h9l.java` | `defpackage/` | `vehicleState(id:)` document — carries `activeDriverName` |
| `lel.java` | `defpackage/` | `vehicleState(id:)` document — carries the GNSS consent block |

## All five documents, not just `wcm.java`

The app's field set is the **union of five** Apollo-compiled `vehicleState(id:)`
documents, not one of them. Measured against our subscribed set:

- `ours − wcm` = **24**
- `ours − (all five)` = **15**

The nine-field difference is entirely live, working sensors. Taking `wcm.java` as
the app's whole field set therefore manufactures nine phantom "fields the app does
not know about" — which is precisely the pressure to delete working code that the
plan's f4 exists to disarm.

## The app is a lower bound, not the schema

Fifteen fields we subscribe to appear in **zero** of the 32,941 files, matched
whole-word. They are not invalid: the live subscription carries all of them, and a
single unknown name is fatal to the entire subscription — so the server's
`type VehicleState` demonstrably contains every one. Three carry real data on the
owner's R1T as of this writing (`batteryCapacity`, `gearGuardLocked`,
`wiperFluidState`).

Match **whole-word, not substring**. `wiperFluidState` occurs only inside the Room
column name `wiperFluidStateUpdatedTimestamp`, so a substring grep yields 14 and a
whole-word grep yields 15.
