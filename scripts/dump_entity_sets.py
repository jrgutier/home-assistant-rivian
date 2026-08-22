#!/usr/bin/env python3
"""Print (or write) the entity_sets.json fixture, derived from const.py.

Computes exactly what `sensor.py`/`binary_sensor.py`'s async_setup_entry
comprehensions produce for one vehicle: for each model group
`groups_for_model` returns, every description key in SENSORS[group] /
BINARY_SENSORS[group]. Read-only against the source of truth -- it does not
reach the network, mock a coordinator, or need a live vehicle -- so it stays
usable as a committed regenerator even though it does not build actual
entities.

test_no_duplicate_unique_ids (tests/test_model_entity_groups.py) is what
guards against a REAL duplicate; this script does not need to, since the
model map's groups are pairwise key-disjoint by construction and this reports
what would be produced, not what a bug might produce.

Usage:
    python scripts/dump_entity_sets.py            # print to stdout
    python scripts/dump_entity_sets.py --write     # overwrite tests/fixtures/entity_sets.json
    python scripts/dump_entity_sets.py --check     # exit 1 if the committed fixture is stale
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.rivian.const import BINARY_SENSORS, SENSORS
from custom_components.rivian.helpers import groups_for_model

FIXTURE = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "entity_sets.json"
)

# Fixture label -> vehicle["model"] value. "__absent__" mirrors
# test_model_entity_groups.py's `None if model == "__absent__" else model`.
MODELS: dict[str, str | None] = {
    "R1S": "R1S",
    "R1T": "R1T",
    "R2": "R2",
    "__absent__": None,
}


def entity_keys(model: str | None) -> tuple[list[str], list[str]]:
    """The (sensors, binary_sensors) keys one vehicle of this model receives."""
    groups = groups_for_model(model)
    sensors = [d.key for group in groups for d in SENSORS.get(group, ())]
    binaries = [d.key for group in groups for d in BINARY_SENSORS.get(group, ())]
    return sorted(sensors), sorted(binaries)


def build() -> dict[str, dict[str, list[str]]]:
    data: dict[str, dict[str, list[str]]] = {}
    for label, model in MODELS.items():
        sensors, binaries = entity_keys(model)
        data[label] = {"sensors": sensors, "binary_sensors": binaries}
    return data


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
