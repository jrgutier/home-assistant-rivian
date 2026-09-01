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
| `apj.java` | `defpackage/` | `vehicleState(id:)` document — carries the eight tire fields |
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

## Which extraction is which

This repo has referenced two decompilations of two different app versions. They
are not interchangeable. Findings rest on one or the other; mixing them is how
the seven-command table would lose its provenance.

| | source | on disk today | findings resting on it |
|---|---|---|---|
| the **artifacts** — the nine `.java` beside this file | `jadx` of **3.15.0** build 4804, 32,941 files | the nine files, yes; **and the tree they came from, at `.apk/3.15.0/jadx/sources`** (corrected 2026-08-31, s32) | the seven invalid-wrapper commands; `isParallaxRequestOnly`; the two wrapper generators; `VehicleFeature`; the five `vehicleState` documents |
| the **tree** `com.rivian.android.consumer/` | **3.6.0**, versionCode 3989 | yes | the command-state terminality vocabulary; the client-side cancellation of the command-state stream; the 18/6/0/8/91 subscription-vs-poll counts; `ParallaxAttributes` |

The section above ("The app") describes how the **artifacts** were produced and
is the only provenance the seven-command table has. It is not rewritten to say
3.6.0.

File counts, each with the command that produced it:

| figure | source | reproduces? |
|---|---|---|
| 32,941 | `jadx` run on 3.15.0, per this file's "The command" section | **yes, 2026-08-31** — `find .apk/3.15.0 -name '*.java' \| wc -l` returns exactly 32,941. An earlier revision said "not re-runnable — that tree is not on disk"; it is on disk and gitignored (`.apk/`) |
| **31,097** | `find com.rivian.android.consumer/java_src -name "*.java" \| wc -l` | **yes, 2026-08-19** |
| **71,735** | `find com.rivian.android.consumer -type f \| wc -l` | **yes, 2026-08-19** |
| 31,105 | this file's opening paragraph, "the 31,105-file apktool tree" | **no — unreproduced, source unknown** |

The 8-file gap between 31,105 and 31,097 is **not explained** and is not guessed
at. Naming 31,105 as unreproduced is the correction.

## Locating the command-state vocabulary (names change per build)

The four classes that carry the integer `state` vocabulary have obfuscated,
build-specific names (`C4171i`, `C2225j`, `C21098D1`, `C19503Ib` in 3.6.0). The
recipe, not the filename, is what gets committed. Each step was run against the
3.6.0 tree:

```sh
# 1. the subscription document -- its mo83d() returns the vehicleCommandState query
grep -rl "GetVehicleCommandState" java_src/
# 2. the fragment model -- the class whose toString() is "VehicleCommandStateFields(...)"
grep -rl "responseCode" java_src/ | xargs grep -l "statusCode"
# 3. the switch -- the single file that both imports the model and switches on its int field
grep -rn "switch (.*\.f[0-9]*[a-z]*) {" <file importing the model>
# 4. the terminality rule -- the file importing EXACTLY the continue-set classes
grep -n "^import p588Y9" <handler>
# 5. the cancellation -- confirm it is CLIENT-side, not a server close
grep -n "m20706p\|onComplete()" <handler>   # then read m20706p's definition
```

Step 5 exists so the next reader does not read `onComplete()` as a server close.
In 3.6.0 it looks the command id up in the app's own map and cancels a local
coroutine `Job`.

Copy the four resolved files here under **stable, meaningful names**, matching
how `l6e.java` and `wcm.java` are already renamed-by-role. These four are
**3.6.0**, unlike the nine above them:

| stable name | role | this tree (3.6.0) |
|---|---|---|
| `CommandStateSubscription.java` | the `vehicleCommandState` document | `java_src/sh/C19503Ib.java` |
| `CommandStateFields.java` | the fragment model; `state` is a non-null `int` | `java_src/p1050uh/C21098D1.java` |
| `CommandStateSwitch.java` | the nine-arm switch | `java_src/p245Jl/C4171i.java` |
| `CommandStateTerminality.java` | the continue-set test **and** `m20706p` | `java_src/p143Fi/C2225j.java` |

## Re-acquiring the corpus (s33)

The 54 trees under `.apk/` are gitignored, so a clean checkout has none of them.
The `.apkm`/`.apk` bundles they came from are **not retained** — re-acquisition
means re-downloading. What follows is what actually worked, including the parts
that did not.

**APKMirror's real listing is `/uploads/?appcategory=rivian`.** The app page's
"All versions" widget shows only the 10 most recent, and `?page=N` on it is
ignored — every page returns the same 10. Reading only that widget is how an
earlier revision of this work concluded that APKMirror carried nothing before
3.8.0, which was wrong by 20 versions. The uploads listing carries 30, back to
2.5.1. Nothing older than 2.5.1 exists there; `3.2.x`, `2.9` and `2.11`-`2.18`
exist on no source checked.

**Three automated routes do not work, and the reasons differ:**

| route | why not |
|---|---|
| `apkeep -d apk-mirror` | no such source exists; apkeep offers apk-pure, google-play, f-droid, huawei-app-gallery |
| `apkeep -d apk-pure` | APKPure does not carry this app — empty listing, while a control app returns 130+ versions |
| `apkeep -d google-play` | works, but Google Play serves **only the current version** by design, so it cannot backfill |

Google Play is still the way to get a *new frontier* build (3.16.0 came from it),
and needs an aas token obtained by exchanging an oauth token
(`apkeep --oauth-token <t> -e <email>`). An oauth token is not an aas token; passing
the former to `-t` fails with "Invalid payload".

**`tanishqmanuja/apkmirror-downloader` (APKMD) works, with two traps.** It ships
only Linux and Windows binaries, but `bun src/cli.ts` runs fine on macOS arm64
from a source clone. Its dpi filter drops any variant whose dpi is not matched
exactly, so `-d '*'` is required or every download fails "Could not find any
suitable variant":

```sh
bun src/cli.ts download rivian rivian -v <VERSION> -a universal -t bundle -d '*' --outdir <dir>
```

It is Cloudflare-blocked after a handful of requests at any spacing, and fails
permanently on some versions with "Could not find final download url". A browser
succeeds where it does not.

**The browser flow.** Navigate to
`/apk/rivian-llc/rivian/rivian-<v-with-dashes>-release/rivian-<v-with-dashes>-android-apk-download/`
and click the download control. **Wait after each click before navigating away** —
navigating immediately aborts the pending download, silently, which cost four
versions before it was noticed.

3.x releases are `.apkm` bundles (base plus 34 splits); **2.x releases are single
`.apk` files** of 433-467 MB. A pipeline globbing only `*.apkm` skips every 2.x
download without saying so.

Decompile with `jadx` (not apktool, per the distinction above); the 29 trees from
2.6.1 onward were produced with jadx 1.5.6.
