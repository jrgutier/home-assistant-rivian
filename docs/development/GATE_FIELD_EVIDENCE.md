# Gate field evidence: does a usable value mean the hardware exists?

## Why this file exists

`tests/fixtures/community/PROVENANCE.md` records three community diagnostics
fixtures gathered to test one premise: that the plan's gate rule — a field
counts as "reported" when its value is not in `INVALID_SENSOR_STATES =
{"fault", "signal_not_available", "sna", "undefined"}` (`const.py:89`) — is a
reliable stand-in for "this vehicle has the hardware". Two of those fixtures
are R1S vehicles reporting all five R1S-group gate fields usable, which looked
like it settled the question. The third — an R1T — did not, and that result
is the reason this file exists: it reports three usable values for hardware
(third-row seats, a liftgate) an R1T does not have.

This file checks the premise properly: every one of the **14 gated field
descriptions** the integration currently has (not just the five originally
sampled), across every source available, including the project's own live
R1T. No code change or plan edit is proposed here — this is evidence only.

## Summary answers

- **Does an R1S report usable values for hardware it lacks (tonneau, side
  bins)? No.** Both R1S fixtures read SNA on all eight R1T-group
  closure/lock fields, with no exceptions. See Finding 3.
- **Does an R1T report usable values for hardware it lacks (liftgate)? Yes,
  for one of three liftgate fields**, on two independent R1T vehicles. See
  Finding 1.
- **Does a usable value reliably mean the hardware is present? No** — the
  same live R1T reads SNA on two lock fields for hardware confirmed present
  and working. See Finding 2.
- **Can anything in this data tell a live reading from a hardcoded default?
  No** — the diagnostics dumps reflect masked coordinator state, not raw
  wire history, and every gated field's history is flat everywhere. See
  Findings 5a and 5.

## The 14 gated descriptions

Two model-scoped groups in `const.py` gate on field presence (not a
`supportedFeatures` flag — see `docs/development/MODEL_SPECIFIC_ENTITIES.md`
for why field-presence gating replaced flag gating after the `TONNEAU_CMD`
finding):

| Group | Sensors (`SENSORS[...]`, `const.py:1437-1559`) | Binary sensors (`BINARY_SENSORS[...]`, `const.py:1753-1812`) |
|---|---|---|
| `R1T` (3 + 6 = 9) | `closure_tailgate_next_action`, `closure_side_bin_left_next_action`, `closure_side_bin_right_next_action` | `closure_side_bin_left_closed`, `closure_side_bin_left_locked`, `closure_side_bin_right_closed`, `closure_side_bin_right_locked`, `closure_tonneau_closed`, `closure_tonneau_locked` |
| `R1S` (3 + 2 = 5) | `seat_third_row_left_heat`, `seat_third_row_right_heat`, `closure_liftgate_next_action` | `closure_liftgate_closed`, `closure_liftgate_locked` |

`closure_tailgate_closed`/`closure_tailgate_locked` are deliberately **not**
in this set — they live in the shared `R1` group and are out of scope here
(`MODEL_SPECIFIC_ENTITIES.md:19-43` covers why).

`sensor.py:184` and `binary_sensor.py:109` both filter on the same
`INVALID_SENSOR_STATES` set, so "usable" means the same thing on both
platforms for every field below.

## Data sources

1. **`issue-171.json`** — R1T, 2023, community diagnostics, 2024-08-08 (`tests/fixtures/community/`).
2. **`issue-222.json`** — R1S, 2024, community diagnostics, 2025-08-26.
3. **`issue-245.json`** — R1S, 2023, community diagnostics, 2026-03-09.
4. **Live production R1T** — the project's own 2022 R1T, `root@192.168.1.5`,
   captured **2026-08-19 12:31 CDT** on beta6. Not a new probe run for this
   file — cited from what the test suite already records:
   `tests/test_lock.py:522-598`, `tests/test_binary_sensor_invalid_states.py:408-435`.
   Covers the 10-member `LOCK_STATE_ENTITIES` set (`const.py:56-67`), which
   includes 6 of the 14 gated fields.

None of the three community fixtures carry raw `*_next_action` data for
`closureTailgateNextAction`, `closureSideBinLeftNextAction`, or
`closureSideBinRightNextAction` — those three keys are simply **absent** from
all three payloads (110-111 total vehicle-state keys each; verified by key
lookup, not by value). That is a genuine data gap, not a zero/SNA reading, and
it is called out as such in the table rather than folded into either column.

## Per-field, per-source table

`✓` = usable (not in `INVALID_SENSOR_STATES`). `SNA` = one of the four invalid
values, cited literally. `—` = key absent from that source (no data either
way). Live-R1T cells not covered by `LOCK_STATE_ENTITIES` are `n/a` — no
citable live record exists for them.

| Field | Hardware exists on... | issue-171 (R1T) | issue-222 (R1S) | issue-245 (R1S) | Live production R1T (2026-08-19) |
|---|---|---|---|---|---|
| `closureLiftgateClosed` | R1S | SNA (`signal_not_available`) | ✓ `closed` | ✓ `closed` | n/a |
| `closureLiftgateLocked` | R1S | **✓ `locked`** | ✓ `unlocked` | ✓ `unlocked` | **✓ usable** (one of the 7 non-SNA `LOCK_STATE_ENTITIES` members) |
| `closureLiftgateNextAction` | R1S | SNA (`SNA`) | ✓ `Open_Allowed` | ✓ `Open_Allowed` | n/a |
| `seatThirdRowLeftHeat` | R1S | **✓ `Off`** | ✓ `Off` | ✓ `Off` | n/a |
| `seatThirdRowRightHeat` | R1S | **✓ `Off`** | ✓ `Off` | ✓ `Off` | n/a |
| `closureTonneauClosed` | R1T | SNA | SNA | SNA | n/a |
| `closureTonneauLocked` | R1T | SNA | SNA | SNA | **SNA** (one of the 3 live members read invalid — `test_lock.py:522-528`) |
| `closureTailgateNextAction` | R1T | — (absent) | — (absent) | — (absent) | n/a |
| `closureSideBinLeftClosed` | R1T | SNA | SNA | SNA | n/a |
| `closureSideBinLeftLocked` | R1T | SNA | SNA | SNA | **✓ usable** (one of the 7 non-SNA `LOCK_STATE_ENTITIES` members) |
| `closureSideBinLeftNextAction` | R1T | — (absent) | — (absent) | — (absent) | n/a |
| `closureSideBinRightClosed` | R1T | SNA | SNA | SNA | n/a |
| `closureSideBinRightLocked` | R1T | SNA | SNA | SNA | **SNA** (one of the 3 live members read invalid — `test_lock.py:522-528`) |
| `closureSideBinRightNextAction` | R1T | — (absent) | — (absent) | — (absent) | n/a |

Bold cells are the ones that cut against the "usable value → hardware
present" premise in either direction.

## Finding 1 — a usable value does not mean the hardware exists

`closureLiftgateLocked` reads a usable value (`locked` or `unlocked`) on
**every single source in this table, including two independent R1T
vehicles that have no liftgate**: the community R1T (`issue-171.json`) and
the project's own live production R1T. This is not a single anomalous
reading — it is the *only* one of the three R1S-group liftgate fields that
does this, on two vehicles from two different owners, months apart, on
different integration/firmware versions. `closureLiftgateClosed` and
`closureLiftgateNextAction` both correctly read SNA on the R1T in
`issue-171.json` (no live-R1T citation exists for these two — `LOCK_STATE_ENTITIES`
does not cover them).

So within the same feature group, on the same vehicle, one field's "usable"
signal is corroborated as spurious by two independent vehicles, while its two
siblings' SNA readings are not contradicted anywhere in this evidence. A rule
that grants all three liftgate fields together because at least one read
usable would grant `closure_liftgate_locked` to R1T owners on the strength of
a value this evidence shows is not tied to the hardware at all.

## Finding 2 — SNA does not reliably mean the hardware is absent, either

The reverse failure also has direct evidence, and it does not require
comparing across vehicles: on the **same** live production R1T, at the
**same** timestamp, `closureTonneauLocked` and `closureSideBinRightLocked`
both read `signal_not_available` — and this R1T's tonneau is confirmed real,
working hardware (`MODEL_SPECIFIC_ENTITIES.md:9-15`: `OPEN_TONNEAU_COVER`
physically opened it; `CLOSE_TONNEAU_COVER` closed and locked it, tested on
this same vehicle). So SNA was read, live, for the *lock* signal on hardware
whose *existence and operability* were independently confirmed by command on
that same vehicle. SNA here means "this sub-signal isn't reporting right
now", not "this vehicle lacks a tonneau".

Between Finding 1 and Finding 2: on the one vehicle where independent,
non-diagnostics confirmation of real hardware exists (the live R1T), a gated
field's usability tracked neither direction reliably — a present, working
component (tonneau) read SNA on its lock signal, while an absent component
(liftgate) read usable on its lock signal.

## Finding 3 — does an R1S over-grant on hardware it lacks? (No, not in this evidence)

Team-lead's second question: does an R1S report usable defaults for
R1T-group hardware (tonneau, side bins) it does not have, the way the R1T
did for the liftgate? **Not in either R1S fixture.** All eight R1T-group
closure/lock fields (`closureTonneauClosed/Locked`,
`closureSideBinLeft/RightClosed/Locked`) read SNA on both `issue-222.json`
and `issue-245.json` — consistently, with no exceptions. The three
`*NextAction` fields in that group are absent from both, same as everywhere
else, so they contribute no data either way.

So the over-granting risk found here is **not symmetric**: it is confined, in
this evidence, to one specific sub-field (`closure_liftgate_locked`) inside
the group that *does* match the vehicle's actual body style, not to a
wholesale cross-model leak of R1T fields onto R1S vehicles or vice versa. That
is a narrower problem than "R1S owners get tonneau entities", but it is not a
smaller one for the R1T-group's own liftgate-lock analog — the mechanism
that produced it (a stable non-SNA default on missing hardware) is exactly
the one that would also produce it for other lock-class fields on other
model/hardware combinations this evidence does not cover.

## Finding 4 — three fields have no data in any fixture

`closureTailgateNextAction`, `closureSideBinLeftNextAction`, and
`closureSideBinRightNextAction` are absent — not SNA, simply not present as
keys — in all three community diagnostics payloads (integration versions
1.3.1, 1.4.0, 1.5.1) and have no live-R1T citation available either
(`LOCK_STATE_ENTITIES` and `CLOSURE_STATE_ENTITIES` don't cover
`*NextAction` fields, and no test in this repo captures a live reading for
them). Whatever the union rule decides for these three, it is deciding it on
zero observations, not on a negative finding — this evidence cannot tell
whether the server ever populates them, on any model.

## Finding 5a — the instrument itself hides flicker (masking at `coordinator.py:1553-1572`)

Before reading the flat-history observation below at face value, it matters
that the diagnostics dump is not a raw wire capture — it is the coordinator's
*masked* state, and the masking is asymmetric by design.
`VehicleCoordinator._build_vehicle_info_dict` (`coordinator.py:1553-1572`)
folds each update into `self.data`: when an incoming value is one of
`INVALID_SENSOR_STATES` **and** the field already has a previous entry, the
whole previous `{"value": ..., "history": ...}` object is substituted in
unchanged (`coordinator.py:1557-1558`) — the invalid reading is not recorded
anywhere, not in `value`, not in `history`. Only a valid reading ever
extends `history` (`coordinator.py:1572`). The one documented exception is
the very first update for a field with no prior entry, which is published
as-is, invalid values included (`coordinator.py:1536-1549`) — that is how a
literal `SNA` was once observed on both rear seat heating sensors at a fresh
start (comment at `coordinator.py:1541`).

The consequence for this evidence: **once a field has produced one valid
reading, ever, every later invalid reading on that field becomes
permanently invisible** to anything reading `self.data` or a diagnostics
dump taken from it — including a field that flickers between a plausible
value and SNA on the wire indefinitely afterward. This is a plausible,
code-grounded mechanism for Finding 1, not just an analogy: if
`closureLiftgateLocked` produced one valid reading on an R1T at any point
(a boot-time race, a transient default before the vehicle's absent-hardware
state settled, or genuinely no such state ever being reported for that
one sub-signal), masking would lock that value in and hide any SNA
readings after it, on both the community R1T and the live production R1T,
indefinitely. This does not prove that is what happened — no earlier
capture of either vehicle exists to check — but it means "this field reads
a stable usable value" and "this field genuinely, permanently works on this
hardware" are not the same claim on this codebase, independent of anything
about the vehicle itself.

## Finding 5 — what would actually discriminate, and why this data can't

Every gated field in every community fixture carries `history` of length 1
(a single value, one timestamp) — no observed variation anywhere, on any of
the 14 fields, in any of the three fixtures. That is not a limitation of the
diagnostics format itself: in the same three files, `gnssBearing` carries 27,
38, and 208 *distinct* history values respectively, and `batteryLevel` shows
2 distinct values in `issue-171.json`. The tool records variation when a
field has any — it simply never observed any on these 14 fields, in any
fixture. Finding 5a is why that absence of variation cannot be read as
"this field never went invalid" either — masking would erase that evidence
just as effectively as genuine stability would produce it. A flat history is
consistent with both.

A single point-in-time snapshot with a flat history cannot distinguish "this
is a live sensor reading that happens not to have changed in this window"
from "this is a hardcoded/default value the API always returns for this
field on this vehicle". Nothing in the data collected for this sweep
resolves that ambiguity, and it should be said plainly rather than
gestured at: **no mechanism in this evidence set discriminates a real
reading from an inert default.**

What would discriminate, going by what has actually worked in this project
before:

- **A value that changes across two or more samples of the same vehicle**
  over time — the `gnssBearing`/`batteryLevel` contrast above shows the
  instrumentation is capable of catching this when it exists; none of the
  three community fixtures happen to be repeat captures of the same vehicle,
  so this sweep has no such pair to check. Given Finding 5a, this
  discriminator only works in one direction: two dumps showing *different*
  valid values is real proof the field is live, since masking cannot
  fabricate a second distinct valid reading. Two dumps showing the *same*
  value proves nothing either way — that is exactly what masking produces
  whether the field is genuinely stable or flickering to SNA in between
  samples.
- **An actuation test** — command the entity and observe a state or physical
  change, the same falsification that already overturned the `TONNEAU_CMD`
  premise (`MODEL_SPECIFIC_ENTITIES.md:9-15`): sending `OPEN_TONNEAU_COVER`
  to a vehicle believed to lack the flag and watching the cover move is
  direct evidence a static field reading cannot provide. No community
  fixture can supply this — it requires a live vehicle and an owner willing
  to run the command, which is exactly the constraint that made this
  diagnostics sweep necessary in the first place.

Neither exists in the evidence gathered here. This file's per-field table is
the ceiling of what a diagnostics-attachment sweep can establish; closing
Finding 1/Finding 2's ambiguity requires one of the two methods above, run
against a specific vehicle, which is outside this sweep's scope.
