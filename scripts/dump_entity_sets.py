#!/usr/bin/env python3
"""Print (or write) the entity_sets.json fixture, derived from source.

s19 SECTION A follow-up: this used to cover only `sensor.py`/`binary_sensor.py`
(the `SENSORS`/`BINARY_SENSORS` collections). That is roughly half the entity
surface, and the half that has never had a creation bug -- the tonneau bug
this story fixed lived in `cover.py`, which this script did not watch.
Extended to every platform that builds entities from a static description
collection: `covers`, `buttons`, `switches`, `locks`, `selects`, `numbers`,
`climate`, `time`, `device_tracker`, `update`, alongside the original
`sensors`/`binary_sensors`.

Excluded, and why -- not an oversight:

  * `button.py`'s pairing button (`RivianPairPhoneButtonEntity`). It depends
    on live BLE pairing state read from `drivers_coordinator
    .get_device_details()`, not on anything a static `Scenario` below can
    express. No description collection backs it either.
  * `image.py` entirely. It fetches real vehicle images over the network via
    a live `VehicleImageCoordinator` refresh -- there is no static
    description collection to enumerate, and doing so would require a real
    API response.

Two platforms genuinely differ in shape from "a dict or tuple of
descriptions gated by feature/option_code, behind `phone_identity_id`":

  * `select.py`'s front-seat entities (`FRONT_SEAT_SELECTS`) are a `list[dict]`,
    not `RivianSelectEntityDescription` instances -- keyed by `"key"` like
    the rest, but built with a dedicated `RivianFrontSeatSelectEntity` class.
  * `switch.py`'s `CHARGING_SCHEDULE_ENABLED_SWITCH` and `number.py`'s
    `CHARGING_SCHEDULE_AMPERAGE_NUMBER`, plus `time.py`'s `TIME_ENTITIES`,
    `device_tracker.py`'s `LOCATION_DESCRIPTION`, and `update.py`'s
    `UPDATE_DESCRIPTION`, are all created **regardless of
    `phone_identity_id`** -- switch.py's own comment says so explicitly
    ("no pairing needed"), and the other three simply never check it. Every
    other platform below (`covers`, `buttons`, the rest of `switches`,
    `locks`, `selects`, `numbers`, `climate`) requires it, matching each
    platform's own `if vehicle.get("phone_identity_id")` guard.

A second, quieter gap found while extending this: `sensor.py` and
`binary_sensor.py` ALSO each build one vehicle-scoped collection outside
`SENSORS`/`BINARY_SENSORS` -- `CHARGING_SENSORS` + `DRIVER_SENSORS`
(sensor.py) and the hardcoded `cloud_connected` binary sensor
(`RivianCloudConnectionBinarySensor`, binary_sensor.py). None of the three
are gated by model, feature, option_code, or `phone_identity_id` -- created
for every vehicle unconditionally, same as the platforms above. The
ORIGINAL (pre-s19) version of this script covered `sensors`/
`binary_sensors` and still missed these; they were never part of `SENSORS`/
`BINARY_SENSORS`. Recorded as their
own `sensor_extras` / `binary_sensor_extras` keys rather than folded into
`sensors`/`binary_sensors`, because those two keys are numerically pinned
elsewhere (`tests/test_model_entity_groups.py`'s `NO_FLAG_COUNTS` /
`FIXTURE_COUNTS`) against `SENSORS`/`BINARY_SENSORS` specifically --
widening their contents would break a working, narrower invariant to
express a different, also-true one.

Deliberately NO `known_fields` axis on `Scenario`. No CREATION gate anywhere
in this codebase reads field presence any more: s19's tonneau fix was the
last one (`required_field`), removed for exactly this reason -- a field
in `VEHICLE_STATE_SUBSCRIPTION_FIELDS` is present in `coordinator.data`
for every vehicle regardless of hardware, so it never discriminated
anything (`docs/development/GATE_FIELD_EVIDENCE.md`). Adding an axis
nothing reads would be scaffolding for a gate this project just finished
arguing against; if a field-presence creation gate is ever reintroduced
deliberately, add the axis then, with the same evidence bar
GATE_FIELD_EVIDENCE.md set.

Read-only against the source of truth -- it does not reach the network, mock
a coordinator, or need a live vehicle -- so it stays usable as a committed
regenerator even though it does not build actual entities. Sensors,
binary sensors, SELECTS, and cameras import `vehicle_supports` (the same
predicate the platforms call). Covers and buttons still reproduce their
dict-key loops here. Kept in sync by tests/test_full_entity_sets.py, which runs the
REAL `async_setup_entry()` for every scenario in SCENARIOS and asserts it
returns exactly what this script computed -- so a predicate drifting from
its platform file fails a test, not just this docstring's claim.

Usage:
    python scripts/dump_entity_sets.py            # print to stdout
    python scripts/dump_entity_sets.py --write     # overwrite tests/fixtures/entity_sets.json
    python scripts/dump_entity_sets.py --check     # exit 1 if the committed fixture is stale
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.rivian.button import BUTTONS
from custom_components.rivian.climate import CLIMATE
from custom_components.rivian.const import BINARY_SENSORS, SENSORS
from custom_components.rivian.cover import COVERS
from custom_components.rivian.device_tracker import LOCATION_DESCRIPTION
from custom_components.rivian.gear_guard import CAMERAS
from custom_components.rivian.helpers import vehicle_supports
from custom_components.rivian.lock import LOCKS
from custom_components.rivian.number import CHARGING_SCHEDULE_AMPERAGE_NUMBER, NUMBERS
from custom_components.rivian.select import FRONT_SEAT_SELECTS, SELECTS
from custom_components.rivian.sensor import CHARGING_SENSORS, DRIVER_SENSORS
from custom_components.rivian.switch import CHARGING_SCHEDULE_ENABLED_SWITCH, SWITCHES
from custom_components.rivian.time import TIME_ENTITIES
from custom_components.rivian.update import UPDATE_DESCRIPTION

FIXTURE = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "entity_sets.json"
)

# Feature-flag strings the dump may name: COVERS/BUTTONS dict keys, plus
# description.feature on sensors/binaries/SELECTS, plus an allowlist so a
# Scenario can name a flag before it is a dict key / description.feature.
# A typo in a Scenario below is caught by the assertion just under this
# constant.
EXTRA_FEATURE_ALLOWLIST = frozenset(
    {
        "WINDOWS_CMD",
        "TAILGATE_NXT_ACT",
        "HEATED_SEATS_THIRD",
    }
)


def _all_descriptions(collection):
    """SENSORS / BINARY_SENSORS / SELECTS are tuples. Dict branch is defensive."""
    if isinstance(collection, dict):
        return tuple(d for group in collection.values() for d in group)
    return tuple(collection)


def _features_from(collection) -> set[str]:
    out: set[str] = set()
    for d in _all_descriptions(collection):
        feat = getattr(d, "feature", None)
        if feat is None:
            continue
        if isinstance(feat, str):
            out.add(feat)
        else:
            out.update(feat)
    return out


ALL_KNOWN_FEATURES: frozenset[str] = frozenset(
    {f for f in COVERS if f is not None}
    | {f for f in BUTTONS if f is not None}
    | _features_from(SENSORS)
    | _features_from(BINARY_SENSORS)
    | _features_from(SELECTS)
    | _features_from(CAMERAS)
    | EXTRA_FEATURE_ALLOWLIST
)


@dataclass(frozen=True)
class Scenario:
    """One synthetic vehicle -- every input a creation gate anywhere reads.

    `option_codes=None` and `option_codes=()` are deliberately different:
    `None` means the mobileConfiguration fragment was rejected (the key is
    absent from a real vehicle dict); `()` means it was accepted and the
    vehicle has no matching options. Both currently behave identically
    against every gate (`vehicle.get("option_codes") or []`), but the
    distinction is kept here because coordinator.py's own
    `_extract_option_codes()` keeps it, and a scenario that erased it would
    not be able to represent the rejected case at all.
    """

    label: str
    model: str | None
    paired: bool = True  # vehicle.get("phone_identity_id") truthy
    features: frozenset[str] = field(default_factory=frozenset)
    option_codes: tuple[str, ...] | None = ()


SCENARIOS: tuple[Scenario, ...] = (
    # The floor: no feature flags, no option codes. Unchanged in shape and
    # values from before this extension for the sensor/binary_sensor half --
    # see tests/fixtures/entity_sets.json's own history via git blame.
    Scenario("R1T", model="R1T"),
    Scenario("R1S", model="R1S"),
    Scenario("R2", model="R2"),
    Scenario("__absent__", model=None),
    # Realistic MAXIMUM evidence per body style, not a combinatorial sweep --
    # each names only the feature flags and option codes that body style can
    # structurally report. R1S/R2 deliberately do NOT get TON-P01,
    # TAILGATE_CMD, or SIDE_BIN_NXT_ACT: no R1S or R2 configuration has a
    # powered tonneau, a tailgate, or gear tunnels. This is what would have
    # caught the tonneau bug -- an R1S given every feature flag and option
    # code it could plausibly have must still not receive `tonneau`.
    Scenario(
        "R1T_full_hardware",
        model="R1T",
        features=frozenset(
            {
                "TAILGATE_CMD",
                "TAILGATE_NXT_ACT",
                "SIDE_BIN_NXT_ACT",
                "CHARG_PORT_DOOR_COMMAND",
                "WINDOWS_CMD",
                "LIVE_CAM",
                "MOTION_CAM",
            }
        ),
        option_codes=("TON-P01",),
    ),
    Scenario(
        "R1S_full_hardware",
        model="R1S",
        features=frozenset(
            {
                "LIFTGATE_CMD",
                "CHARG_PORT_DOOR_COMMAND",
                "HEATED_SEATS_THIRD",
                "LIVE_CAM",
                "MOTION_CAM",
            }
        ),
        option_codes=(),
    ),
    Scenario(
        "R2_full_hardware",
        model="R2",
        features=frozenset({"LIFTGATE_CMD", "CHARG_PORT_DOOR_COMMAND"}),
        option_codes=(),
    ),
    # Vehicle-control never set up (no BLE pairing / phone_identity_id): every
    # control platform below yields nothing, but sensors/binary_sensors and
    # the "no pairing needed" entities (see module docstring) are unaffected.
    Scenario("unpaired", model="R1T", paired=False),
)

for _s in SCENARIOS:
    assert _s.features <= ALL_KNOWN_FEATURES, (
        f"{_s.label} names a feature COVERS/BUTTONS no longer gate on: "
        f"{_s.features - ALL_KNOWN_FEATURES}"
    )
del _s


def entity_keys_for_scenario(s: Scenario) -> dict[str, list[str]]:
    """The full entity-key surface one Scenario produces, platform by platform.

    Sensors, binary sensors, SELECTS, and cameras go through vehicle_supports.
    Covers and buttons stay dict-key loops.
    """
    vehicle = {
        "model": s.model,
        "supported_features": list(s.features),  # NOT "features"
        "option_codes": list(s.option_codes or []),
    }
    option_codes = list(s.option_codes or [])

    covers: list[str] = []
    buttons: list[str] = []
    paired_switches: list[str] = []
    locks: list[str] = []
    selects: list[str] = []
    paired_numbers: list[str] = []
    climate: list[str] = []
    cameras: list[str] = []

    if s.paired:
        covers = sorted(
            d.key
            for feature, descriptions in COVERS.items()
            if feature is None or feature in s.features
            for d in descriptions
            if d.option_code is None or d.option_code in option_codes
        )
        buttons = sorted(
            d.key
            for feature, descriptions in BUTTONS.items()
            if feature is None or feature in s.features
            for d in descriptions
        )
        paired_switches = [d.key for d in SWITCHES]
        locks = sorted(d.key for d in LOCKS)
        cameras = sorted(d.key for d in CAMERAS if vehicle_supports(d, vehicle))
        selects = sorted(
            [d.key for d in SELECTS if vehicle_supports(d, vehicle)]
            + [seat["key"] for seat in FRONT_SEAT_SELECTS]
            + (["gear_guard_camera"] if cameras else [])
        )
        paired_numbers = [d.key for d in NUMBERS]
        climate = [CLIMATE.key]

    return {
        "sensors": sorted(
            d.key for d in _all_descriptions(SENSORS) if vehicle_supports(d, vehicle)
        ),
        "binary_sensors": sorted(
            d.key
            for d in _all_descriptions(BINARY_SENSORS)
            if vehicle_supports(d, vehicle)
        ),
        "covers": covers,
        "buttons": buttons,
        "switches": sorted(paired_switches + [CHARGING_SCHEDULE_ENABLED_SWITCH.key]),
        "locks": locks,
        "selects": selects,
        "numbers": sorted(paired_numbers + [CHARGING_SCHEDULE_AMPERAGE_NUMBER.key]),
        "climate": climate,
        "cameras": cameras,
        "time": sorted(d.key for d in TIME_ENTITIES),
        "device_tracker": [LOCATION_DESCRIPTION.key],
        "update": [UPDATE_DESCRIPTION.key],
        "sensor_extras": sorted(
            [d.key for d in CHARGING_SENSORS] + [d.key for d in DRIVER_SENSORS]
        ),
        "binary_sensor_extras": ["cloud_connected"],
    }


def build() -> dict[str, dict[str, list[str]]]:
    return {s.label: entity_keys_for_scenario(s) for s in SCENARIOS}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write", action="store_true", help="overwrite the committed fixture"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 (printing nothing to stdout) if the fixture is stale",
    )
    args = parser.parse_args()

    text = json.dumps(build(), indent=2, sort_keys=True) + "\n"

    if args.check:
        current = FIXTURE.read_text() if FIXTURE.is_file() else ""
        if current != text:
            print(
                f"{FIXTURE} is stale; run scripts/dump_entity_sets.py --write",
                file=sys.stderr,
            )
            return 1
        return 0

    if args.write:
        FIXTURE.write_text(text)
        print(f"wrote {FIXTURE}")
        return 0

    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
