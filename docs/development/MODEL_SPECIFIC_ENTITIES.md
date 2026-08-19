# Entities that do not apply to every model

## The rule

**Default to keeping an entity. Remove one only on a recorded live failure.**

Absence from the Rivian app, from a vehicle's `supportedFeatures`, or from a
hardware inference is *not* evidence that a capability does not exist. That was
established the expensive way: `cover.py` gated the tonneau cover on
`TONNEAU_CMD`, a flag that appears in **none** of the app's 32,941 decompiled
files and in **no** vehicle's `supportedFeatures`. Every offline reading said the
capability was absent. Tested on the owner's R1T instead, `OPEN_TONNEAU_COVER`
was accepted and the cover **physically opened**; `CLOSE_TONNEAU_COVER` returned
it to closed and locked. The gate was wrong and the capability was real, so the
control had simply never been created for anyone.

Silence is not evidence. Deleting an entity needs a live failure, written down.

## `closure_tailgate_closed` and `closure_tailgate_locked`

These two live in the **shared `R1` group**, so an R1S gets them as well as an
R1T. An R1S has a liftgate, not a tailgate.

**They stay.** The argument for removing them was that an R1S would show a
confident `Closed` for hardware it does not have. That argument is now spent: as
of f0, a binary sensor whose field reports `fault` / `sna` /
`signal_not_available` / `undefined` returns `None` from `is_on`, so the state is
**`unknown`** rather than a confident `Closed`. Note `unknown`, not
`unavailable` -- availability keys on the field being present, and the raw value
still flows so the matching control stays operable.

What is left is a cosmetic argument, and the cost on the other side is concrete:
moving them into an R1T-only group takes two entities away from **every R1S
owner**, on a hardware inference, with no recorded live failure. That is the same
inference the tonneau falsified, and it fails on an R1S that reports the field
for some reason nobody here has anticipated.

There is a second reason to be careful. The owner drives an R1T, so an R1T-only
test pin is structurally blind to an R1S regression. `test_model_entity_groups.py`
therefore carries a synthetic R1S case rather than relying on live observation.

**Removing them requires a recorded owner decision amending the rule at the top
of this file**, plus a live failure from an R1S. Neither exists.

## R1T-only and R1S-only groups today

| Group | Sensors | Binary sensors |
|---|---|---|
| `R1` (shared) | 87 | 27 |
| `R1T` | 3 | 6 |
| `R1S` | 3 | 2 |

Totals per model, asserted in `tests/fixtures/entity_sets.json`:

| Model | Sensors | Binary sensors |
|---|---|---|
| R1T | 90 | 33 |
| R1S | 90 | 29 |
| R2, or `model` absent | 87 | 27 |

An R2 receives the shared group only. Before f3a it received **nothing**: the
predicate was a substring test, and `"R1" in "R2"` is `False`.
