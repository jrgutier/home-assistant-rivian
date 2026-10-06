# s47 follow-up: does the app treat trip-target 65535 minutes as "no estimate"?

Read off `.apk/3.16.0/jadx/sources` (build 4884); sites are `defpackage/<file>:<line>`
there unless marked 3.15.0. The captured frame is `10ffff03`: #2 = 65535, no #1.

## Verdict

**No. Nothing in the app compares the minutes against 65535, `0xFFFF`, `-1` or any
maximum.** The only test on the minutes anywhere is `> 0`, and one of the three
screens does not even have that. A frame like the captured one is never shown for
a different reason: **every reader hides the whole trip-target indicator unless
the SOC is between 1 and 100**, and the captured frame has no SOC.

So suppressing 65535 is an inference the app does not back. What the app does
back is: no trip-target SOC, no trip target.

## The path

`c97.java:591` stores #1 and #2 unmodified as `chargingTripTargetSoc` and
`chargingTripTargetMinsRemaining` (`qp2.java:130-131`). Both are plain `int`;
an absent field is 0. From there the pair is read in three places, plus a
push-notification path that does not go through Parallax.

| reader | gate on the indicator | test on the minutes |
|---|---|---|
| Edit charge limit (`np4.java:68-88` → `a63.java:526-528` → `h17.java:147`) | `np4.java:81`: feature flag `CHARGING_TRIP_TARGET` **and** `soc > 0 && soc <= 100` | `h17.java:272`: `else if (mins > 0)` formats; otherwise the subtitle is the empty string and is not drawn (`h17.java:295`) |
| Charging session card (`y13.java:356`, `f`) | `y13.java:391` feature flag; `y13.java:397` `soc <= 0 \|\| soc > 100` → hidden; then the charging state must be active or stopped | **none** — `y13.java:420-421` divides by 60 unconditionally |
| Charging settings (`j23.java:1046-1048` → `cv5.java:2343`, `h`) | `j23.java:1146`: feature flag **and** `soc > 0 && soc <= 100` **and** charger state is `ChargingActive` | not readable in 3.16.0: the lambda that consumes it, `ku2.invoke`, failed to decompile ("Method dump skipped"). In 3.15.0 the same screen is readable at `fr2.java:801` and `1184` and tests `mins > 0`, inside an `if (flag)` block |
| Push notification (`MessagingService.java:167-171` → `je0.java:301-304`) | — | parses the strings `tripTargetSoc` and `tripTargetMinsRemaining` to `int`, defaulting to 0; no comparison |

`y13.java:479-480` (`g`, the title beside `f`) and `ea3.java:157`, `lz2.java:79`
(the SOC bar marker) read only the SOC, with the same 1–100 gate at `y13.java:480`.

## The questions, one by one

- **Is 65535 / `0xFFFF` / `-1` / `Integer.MAX_VALUE` / `UShort.MAX` compared
  anywhere?** No. `65535` and `0xFFFF` occur in none of `h17`, `np4`, `j23`,
  `a63`, `y13`, `c97`, `qp2`, nor in 3.15.0's `fr2` or `ry2`. `MAX_VALUE` occurs
  in `h17` and `a63` only as `Float.MAX_VALUE` in unrelated layout code, outside
  the trip-target function (`h17.java:147-352`).
- **Does the UI hide the value when the SOC is absent or 0?** Yes, on every
  reader: `np4.java:81`, `y13.java:397`, `j23.java:1146`. Over 100 is hidden too.
- **Is any other value treated as "no estimate"?** Only `mins <= 0`, and only on
  two of the three screens (`h17.java:272`; 3.15.0 `fr2.java:801`). It blanks the
  "resume trip in …" subtitle and leaves the title showing.
- **What would 65535 look like if the SOC were valid?** It would be formatted as
  written: 65535 / 60 = 1092 h, 65535 % 60 = 15 min, through
  `R.string.duration_hr_min`. The app has no guard against it.

## Order of the subtitle branches

The minutes are the last of three, so they are also unreachable whenever an
earlier branch fires (`h17.java:263-292`, same order at `y13.java:414-434`):

1. battery level ≥ trip-target SOC → "ready to resume trip";
2. charge limit < trip-target SOC → "limit below target";
3. otherwise the minutes.

## Not established

- Which flag the `if (flag)` block around 3.15.0 `fr2.java:801` is. It was not
  matched to the `j23.java:1146` gate by name, only by position.
- Whether the vehicle sends 65535 deliberately as "unknown". The app is silent
  on it; that is a question for a capture taken during a trip with a charging
  target, where #1 is present.
