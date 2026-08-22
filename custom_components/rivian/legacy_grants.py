"""The model -> entity-group map `helpers.py`'s `groups_for_model()` resolves.

PERMANENT FLOOR, not a migration shim. `helpers.py`'s `vehicle_supports()`
(s19 §A) treats this map's grants as one evidence source among several,
UNIONED with feature-flag and option-code evidence, never intersected: server
evidence may only ADD entities on top of what this map already grants, and
must never be read as a reason to REMOVE one. There is no release where this
module goes away -- it is the mechanism, not scaffolding standing in for one.

## The bug this map exists to prevent from coming back

Before this map existed, model gating was `if model in vehicle["model"]` -- a
SUBSTRING test over group names that happened to work for the two models it
was written against and failed silently for the third:

    "R1"  in "R1T"  -> True     (intended)
    "R1"  in "R2"   -> False    <-- an R2 got ZERO entities, silently
    "R1T" in "R1S"  -> False    (intended)

An R2 owner got no sensors and no binary sensors at all, with nothing logged.
An exact `dict.get(model, DEFAULT)` lookup cannot repeat that failure mode --
which is also why a KeyError on an unrecognised model must never be allowed to
propagate (see `DEFAULT_MODEL_GRANTS` below): that would just be the same
"vehicle silently gets nothing" bug wearing a different exception type.

## Why the map lives in its own module

Originally `VEHICLE_MODEL_GROUPS` inside `helpers.py`, alongside a dozen
unrelated utilities (diagnostics redaction, token-shaped log scrubbing, the
Rivian API client constructor). Extracted here so nobody reaches for this
specific, load-bearing map by habit while skimming `helpers.py` for something
else, and so its own docstring -- this one -- has room to say what it is
without competing for space with those other concerns.

## The R2 liftgate follow-up (s19)

`"LIFTGATE"` is a capability group, not a model group: both R1S and R2 are
SUVs with a liftgate, so both are granted it, while R1T (a tailgate, not a
liftgate) is not. See `helpers.py`'s comment on `VEHICLE_MODEL_GRANTS` below
for the full reasoning and the rejected one-line alternative.
"""

from __future__ import annotations

# Which entity groups a vehicle model receives.
#
# Deliberately no "ALL" key populated from "R1". The platform comprehensions
# build LISTS (binary_sensor.py:40, sensor.py:71-78) and every description
# shares unique_id = f"{vin}-{key}" (entity.py:54), so ALL + R1 + R1T would add
# the shared group twice: 114 duplicate-unique-id errors per vehicle.
#
# R2 also carries "LIFTGATE": an R2 is an SUV with a liftgate, but the three
# liftgate state descriptions (const.py:1460 SENSORS["LIFTGATE"],
# const.py:1845 BINARY_SENSORS["LIFTGATE"]) used to live in "R1S" only. R2 was
# ("R1",), so it got the liftgate CONTROL (cover.py:127, button.py:89 -- gated
# on the LIFTGATE_CMD feature flag, not on this map) with no way to read
# whether the liftgate was open or locked: it could open a door it couldn't
# see the state of.
#
# Rejected: folding R2 into the "R1S" group outright (R2 -> ("R1", "R1S")).
# One line, but "R1S" also carries the third-row seat heaters
# (seat_third_row_left_heat / seat_third_row_right_heat), and no R2
# configuration has a third row -- that would fabricate two entities no R2
# owns. Pulling the liftgate descriptions into their own "LIFTGATE" group and
# giving it to both "R1S" and "R2" grants exactly the capability that's
# shared (liftgate) without the one that isn't (third row). "R1S"'s and
# "R1T"'s entity sets are unchanged by this: R1S trades "R1S" membership in
# the liftgate keys for "LIFTGATE" membership in the same keys, a relabel,
# not a removal. Pinned by tests/fixtures/entity_sets.json.
VEHICLE_MODEL_GRANTS: dict[str, tuple[str, ...]] = {
    "R1T": ("R1", "R1T"),
    "R1S": ("R1", "R1S", "LIFTGATE"),
    "R2": ("R1", "LIFTGATE"),
}

# An exact map is less forgiving than the substring test it replaces, so an
# unrecognised or missing model must NOT raise: a KeyError here removes every
# sensor and binary sensor for that vehicle, which is a worse failure than
# handing it the shared group and letting per-field availability sort it out.
DEFAULT_MODEL_GRANTS: tuple[str, ...] = ("R1",)
