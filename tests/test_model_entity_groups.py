"""Which entity groups a vehicle gets, decided by an exact map rather than `in`.

The predicate was `if model in vehicle["model"]` -- a SUBSTRING test over the
group keys `R1`, `R1T`, `R1S`. It works by accident for the two models it was
written against and fails silently for everything else:

    "R1"  in "R1T"  -> True     (intended)
    "R1"  in "R2"   -> False    <-- an R2 receives ZERO entities
    "R1T" in "R1S"  -> False    (intended)

An R2 owner gets no sensors and no binary sensors at all, with nothing logged.

The replacement is an explicit map. Two things it deliberately does not do:

  * It adds no `"ALL"` key populated from `"R1"`. The platform comprehensions
    build LISTS, and every description shares `unique_id = f"{vin}-{key}"`
    (entity.py:49), so giving R1T the groups ALL, R1 and R1T would add 87 sensors
    and 27 binary sensors twice -- 114 duplicate-unique-id errors per vehicle.

  * It does not raise on an unknown model. An exact map is less forgiving than
    the substring test it replaces, and a KeyError here removes every entity for
    that vehicle. Unknown falls back to the shared `R1` group.

The counts below are asserted NUMERICALLY, not as set equality. A set dedupes,
so a set-equality assertion passes vacuously against exactly the duplication the
first bullet is about.

s19 follow-up: fixing the empty-group bug did not fix R2 fully. Liftgate STATE
(closure_liftgate_closed, closure_liftgate_locked, closure_liftgate_next_action)
lived only in "R1S", so an R2 -- an SUV with a liftgate -- got the liftgate
CONTROL (gated separately on the LIFTGATE_CMD feature flag) with none of the
state to go with it: it could open a liftgate it couldn't see the position of.
Those three descriptions moved to their own "LIFTGATE" group in const.py, and
both "R1S" and "R2" now include it. Rejected: `R2 -> ("R1", "R1S")`, which
would also hand the R2 the two third-row seat heaters in "R1S" -- no R2
configuration has a third row. See helpers.py's VEHICLE_MODEL_GROUPS comment.
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock

import pytest

from custom_components.rivian.binary_sensor import (
    async_setup_entry as binary_sensor_setup,
)
from custom_components.rivian.const import (
    ATTR_COORDINATOR,
    ATTR_VEHICLE,
    ATTR_WALLBOX,
    BINARY_SENSORS,
    DOMAIN,
    SENSORS,
)
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.cover import async_setup_entry as cover_setup
from custom_components.rivian.entity import RivianVehicleEntity
from custom_components.rivian.helpers import groups_for_model
from custom_components.rivian.sensor import async_setup_entry as sensor_setup
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "entity_sets.json"

# Sensors and binary sensors per model. Stated as literals so the numbers are
# reviewable here rather than recomputed from the same source they are checking
# (derived via `scripts/dump_entity_sets.py`, not guessed -- run it with
# --check to confirm these against tests/fixtures/entity_sets.json).
#
# Deliberately raised by f5's follow-up, which added nine sensors -- the fields
# the new Parallax decoders are the ONLY source for. Without them the decoders
# wrote into the coordinator and nothing read the result: fourteen new decoders
# and not one new entity. All nine are entity_registry_enabled_default=False.
# Shared group 87 -> 96.
#
# Raised again by the field-parity release's 25 new sensors (const.py's §E),
# all landing in the shared "R1" group -- every model gains all 25. Shared
# group 96 -> 121. Binary sensors are untouched throughout.
#
# s19: R2 raised again, from the "LIFTGATE" group fix above -- 121 -> 122
# sensors (closure_liftgate_next_action), 27 -> 29 binary sensors
# (closure_liftgate_closed, closure_liftgate_locked). R1T, R1S, and the
# no-model fallback are unchanged: R1S's liftgate entries only relabeled from
# "R1S" membership to "LIFTGATE" membership, same keys either way.
EXPECTED_COUNTS = {
    "R1T": (124, 33),
    "R1S": (124, 29),
    "R2": (122, 29),
    None: (121, 27),
    "": (121, 27),
    "R3X": (121, 27),
}


class TestGroupsForModel:
    """The map itself."""

    @pytest.mark.parametrize(
        ("model", "expected"),
        [
            ("R1T", ("R1", "R1T")),
            ("R1S", ("R1", "R1S", "LIFTGATE")),
            ("R2", ("R1", "LIFTGATE")),
        ],
    )
    def test_known_models(self, model: str, expected: tuple[str, ...]) -> None:
        assert groups_for_model(model) == expected

    @pytest.mark.parametrize("model", [None, "", "R2T", "R3X", "unknown"])
    def test_unknown_or_missing_falls_back_to_the_shared_group(
        self, model: str | None
    ) -> None:
        """Never raise. A KeyError here removes every entity for that vehicle."""
        assert groups_for_model(model) == ("R1",)

    def test_r2_is_not_empty_which_is_the_bug_being_fixed(self) -> None:
        assert groups_for_model("R2") == ("R1", "LIFTGATE")
        assert "R1" in groups_for_model("R2")

    def test_r2_gets_liftgate_state_which_is_the_s19_bug_being_fixed(self) -> None:
        """R2 is an SUV with a liftgate; it must not be state-blind for it."""
        assert "LIFTGATE" in groups_for_model("R2")
        # And it must not gain the third-row seat heaters that come bundled
        # with "R1S" -- no R2 configuration has a third row.
        assert "R1S" not in groups_for_model("R2")

    def test_no_all_group_exists(self) -> None:
        """An `ALL` key would double-add the shared group -- 114 duplicates."""
        assert "ALL" not in SENSORS
        assert "ALL" not in BINARY_SENSORS
        for model in ("R1T", "R1S", "R2", None):
            assert "ALL" not in groups_for_model(model)

    def test_groups_are_returned_without_repeats(self) -> None:
        """The comprehensions build lists; a repeated group is a duplicate entity."""
        for model in ("R1T", "R1S", "R2", None, "", "nonsense"):
            groups = groups_for_model(model)
            assert len(groups) == len(set(groups)), model

    def test_every_returned_group_actually_exists(self) -> None:
        for model in ("R1T", "R1S", "R2", None, "nonsense"):
            for group in groups_for_model(model):
                assert group in SENSORS or group in BINARY_SENSORS, group


async def _setup(
    hass: HomeAssistant, entry: ConfigEntry, model: str | None
) -> tuple[list, list]:
    """Run both platforms for one vehicle and return (sensors, binary sensors)."""
    vehicle = {
        "id": "veh-1",
        "vin": "TESTVIN0000000001",
        "name": "Test Vehicle",
        "phone_identity_id": "phone-1",
        "supported_features": [],
    }
    if model is not None:
        vehicle["model"] = model

    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator.get = MagicMock(return_value=None)
    coordinator.data = {}
    # Set explicitly: these are instance attributes assigned in __init__, so a
    # spec'd mock raises AttributeError for them rather than auto-creating one.
    coordinator.charging_coordinator = MagicMock()
    coordinator.charging_coordinator.get = MagicMock(return_value=None)
    coordinator.drivers_coordinator = MagicMock()
    coordinator.drivers_coordinator.get = MagicMock(return_value=None)

    wallbox = MagicMock()
    wallbox.data = {}

    hass.data[DOMAIN] = {
        entry.entry_id: {
            ATTR_VEHICLE: {"veh-1": vehicle},
            ATTR_COORDINATOR: {
                ATTR_VEHICLE: {"veh-1": coordinator},
                ATTR_WALLBOX: wallbox,
            },
        }
    }

    sensors: list = []
    binaries: list = []
    await sensor_setup(hass, entry, sensors.extend)
    await binary_sensor_setup(hass, entry, binaries.extend)
    return sensors, binaries


def _vehicle_only(entities: list) -> list:
    """Drop the charging/wallbox/cloud entities the model map does not govern."""
    return [
        e
        for e in entities
        if type(e).__name__ in ("RivianSensorEntity", "RivianBinarySensorEntity")
    ]


@pytest.mark.parametrize("model", sorted(EXPECTED_COUNTS, key=lambda m: str(m)))
async def test_entity_counts_per_model(
    hass: HomeAssistant, mock_config_entry: ConfigEntry, model: str | None
) -> None:
    """Numeric list lengths -- NOT set equality, which dedupes."""
    sensors, binaries = await _setup(hass, mock_config_entry, model)
    want_sensors, want_binaries = EXPECTED_COUNTS[model]
    assert len(_vehicle_only(sensors)) == want_sensors, model
    assert len(_vehicle_only(binaries)) == want_binaries, model


@pytest.mark.parametrize("model", ["R1T", "R1S", "R2"])
async def test_no_duplicate_unique_ids(
    hass: HomeAssistant, mock_config_entry: ConfigEntry, model: str
) -> None:
    """The failure an `ALL` group would cause, asserted directly.

    A set-equality gate cannot see this: the set is identical either way.
    """
    sensors, binaries = await _setup(hass, mock_config_entry, model)
    for entities in (_vehicle_only(sensors), _vehicle_only(binaries)):
        ids = [e.unique_id for e in entities]
        assert len(ids) == len(set(ids)), sorted({i for i in ids if ids.count(i) > 1})


async def test_an_r2_gets_entities_at_all(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The bug, stated as its own test so a regression is unmissable."""
    sensors, binaries = await _setup(hass, mock_config_entry, "R2")
    assert _vehicle_only(sensors), "an R2 received ZERO sensors"
    assert _vehicle_only(binaries), "an R2 received ZERO binary sensors"


async def test_r2_is_the_shared_group_plus_liftgate(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Explicit membership, not non-emptiness.

    Before s19 this compared R2 against "R1T minus R1T-only", which happened
    to hold because R2 was exactly the shared "R1" group. It no longer holds:
    R2 now also carries "LIFTGATE", which R1T never had at all. R2's actual
    definition is the shared group plus liftgate state -- assert that
    directly instead.
    """
    r2_s, r2_b = await _setup(hass, mock_config_entry, "R2")

    def keys(entities: list) -> set[str]:
        return {e.entity_description.key for e in _vehicle_only(entities)}

    want_sensors = {d.key for d in SENSORS["R1"]} | {d.key for d in SENSORS["LIFTGATE"]}
    want_binaries = {d.key for d in BINARY_SENSORS["R1"]} | {
        d.key for d in BINARY_SENSORS["LIFTGATE"]
    }
    assert keys(r2_s) == want_sensors
    assert keys(r2_b) == want_binaries

    # Still no R1T-only or R1S-only (third-row seat heater) entities.
    r1t_only_sensors = {d.key for d in SENSORS["R1T"]}
    r1t_only_binaries = {d.key for d in BINARY_SENSORS["R1T"]}
    r1s_only_sensors = {d.key for d in SENSORS["R1S"]}
    assert not (keys(r2_s) & r1t_only_sensors)
    assert not (keys(r2_b) & r1t_only_binaries)
    assert not (keys(r2_s) & r1s_only_sensors)


async def test_r2_gets_liftgate_state_paired_with_liftgate_control(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The actual s19 bug: control without state.

    An R2 with LIFTGATE_CMD in supported_features got a `cover.liftgate` it
    could open and close, but (before this fix) none of the three sensors that
    say whether the liftgate is open or locked. Model-gated state (sensor.py /
    binary_sensor.py) and feature-flag-gated control (cover.py) are two
    independent gates; this test is the only one in the suite that exercises
    both together for the same vehicle, which is what the bug needed to hide.

    SYNTHETIC: no R2 fixture exists anywhere in tests/fixtures/community/ --
    only R1T (issue-171.json) and R1S (issue-222.json, issue-245.json)
    captures do. This vehicle dict and its LIFTGATE_CMD flag are constructed,
    not a recorded diagnostics payload.
    """
    vehicle = {
        "id": "veh-1",
        "vin": "TESTVIN0000000001",
        "name": "Test Vehicle",
        "model": "R2",
        "phone_identity_id": "phone-1",
        "supported_features": ["LIFTGATE_CMD"],
    }

    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator.get = MagicMock(return_value=None)
    coordinator.data = {}
    coordinator.charging_coordinator = MagicMock()
    coordinator.charging_coordinator.get = MagicMock(return_value=None)
    coordinator.drivers_coordinator = MagicMock()
    coordinator.drivers_coordinator.get = MagicMock(return_value=None)

    wallbox = MagicMock()
    wallbox.data = {}

    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            ATTR_VEHICLE: {"veh-1": vehicle},
            ATTR_COORDINATOR: {
                ATTR_VEHICLE: {"veh-1": coordinator},
                ATTR_WALLBOX: wallbox,
            },
        }
    }

    sensors: list = []
    binaries: list = []
    covers: list = []
    await sensor_setup(hass, mock_config_entry, sensors.extend)
    await binary_sensor_setup(hass, mock_config_entry, binaries.extend)
    await cover_setup(hass, mock_config_entry, covers.extend)

    sensor_keys = {e.entity_description.key for e in _vehicle_only(sensors)}
    binary_keys = {e.entity_description.key for e in _vehicle_only(binaries)}
    cover_keys = {e.entity_description.key for e in covers}

    assert "closure_liftgate_next_action" in sensor_keys
    assert {"closure_liftgate_closed", "closure_liftgate_locked"} <= binary_keys
    assert "liftgate" in cover_keys


async def test_r1t_only_entities_do_not_reach_an_r1s_and_vice_versa(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The owner drives an R1T, so an R1T-only pin is blind to R1S regressions."""
    r1t_s, r1t_b = await _setup(hass, mock_config_entry, "R1T")
    r1s_s, r1s_b = await _setup(hass, mock_config_entry, "R1S")

    def keys(entities: list) -> set[str]:
        return {e.entity_description.key for e in _vehicle_only(entities)}

    assert not (keys(r1s_b) & {d.key for d in BINARY_SENSORS["R1T"]})
    # "R1S" no longer has binary sensor descriptions of its own -- both moved
    # to "LIFTGATE" (see const.py's SENSORS/BINARY_SENSORS["LIFTGATE"]) -- so
    # BINARY_SENSORS.get(..., ()) rather than a bare index, which would
    # KeyError on the now-absent key.
    assert not (keys(r1t_b) & {d.key for d in BINARY_SENSORS.get("R1S", ())})
    assert not (keys(r1s_s) & {d.key for d in SENSORS["R1T"]})
    assert not (keys(r1t_s) & {d.key for d in SENSORS["R1S"]})


class TestDeviceRegistration:
    """entity.py:54 read vehicle["model"] unguarded.

    That is the third site, and the one with the widest blast radius: DeviceInfo
    is built for EVERY platform, so a vehicle with no `model` key fails device
    registration everywhere, not merely in the two comprehensions.
    """

    @staticmethod
    def _entity(entry: ConfigEntry, vehicle: dict) -> RivianVehicleEntity:
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value=None)
        coordinator.data = {}
        return RivianVehicleEntity(
            coordinator=coordinator,
            config_entry=entry,
            description=EntityDescription(key="probe"),
            vehicle=vehicle,
        )

    async def test_absent_model_still_registers(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        entity = self._entity(
            mock_config_entry,
            {"id": "veh-1", "vin": "TESTVIN0000000001", "name": "Test Vehicle"},
        )
        assert entity.device_info is not None
        assert entity.device_info["name"] == "Test Vehicle"

    async def test_absent_model_and_name_falls_back_to_the_vin(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """A device must always have a name; None is not a valid one."""
        entity = self._entity(
            mock_config_entry,
            {"id": "veh-1", "vin": "TESTVIN0000000001", "name": None},
        )
        assert entity.device_info["name"] == "TESTVIN0000000001"

    async def test_the_model_is_still_reported_when_present(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        entity = self._entity(
            mock_config_entry,
            {
                "id": "veh-1",
                "vin": "TESTVIN0000000001",
                "name": None,
                "model": "R1T",
            },
        )
        assert entity.device_info["model"] == "R1T"
        assert entity.device_info["name"] == "R1T"


class TestCommittedFixture:
    """The baseline every later story is checked against.

    f0 took a transient snapshot deliberately: f3b-a adds the tonneau cover
    between f0 and here, so a snapshot committed then would have gone red at the
    very next story with no legal move under the stop rule. This is the one that
    is committed.
    """

    def test_fixture_exists(self) -> None:
        assert FIXTURE.is_file(), f"missing committed fixture: {FIXTURE}"

    @pytest.mark.parametrize("model", ["R1T", "R1S", "R2", "__absent__"])
    async def test_entity_sets_match_the_fixture(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry, model: str
    ) -> None:
        expected = json.loads(FIXTURE.read_text())[model]
        sensors, binaries = await _setup(
            hass, mock_config_entry, None if model == "__absent__" else model
        )
        assert (
            sorted(e.entity_description.key for e in _vehicle_only(sensors))
            == expected["sensors"]
        )
        assert (
            sorted(e.entity_description.key for e in _vehicle_only(binaries))
            == expected["binary_sensors"]
        )

    def test_the_fixture_records_lengths_too(self) -> None:
        """So a regression that swaps entities one-for-one is still caught."""
        data = json.loads(FIXTURE.read_text())
        for model, (n_sensors, n_binaries) in (
            ("R1T", EXPECTED_COUNTS["R1T"]),
            ("R1S", EXPECTED_COUNTS["R1S"]),
            ("R2", EXPECTED_COUNTS["R2"]),
        ):
            assert len(data[model]["sensors"]) == n_sensors, model
            assert len(data[model]["binary_sensors"]) == n_binaries, model


class TestTailgateStaysShared:
    """`closure_tailgate_*` is in the shared group, and stays there.

    An R1S has a liftgate, not a tailgate, so these two entities do not apply to
    it. That is not a reason to remove them. The functional argument -- that an
    R1S would show a confident `Closed` for hardware it lacks -- was answered by
    f0: a binary sensor whose field is unusable now reports `unknown`. What
    remains is cosmetic, while the cost is two entities taken from every R1S
    owner on a hardware inference with no recorded live failure. That is the same
    inference the tonneau cover falsified.

    See docs/development/MODEL_SPECIFIC_ENTITIES.md. Removing them requires a
    recorded owner decision, not a passing test.
    """

    TAILGATE_KEYS = {"closure_tailgate_closed", "closure_tailgate_locked"}

    def test_the_tailgate_entities_are_in_the_shared_group(self) -> None:
        shared = {d.key for d in BINARY_SENSORS["R1"]}
        assert self.TAILGATE_KEYS <= shared

    def test_they_are_not_in_an_r1t_only_group(self) -> None:
        """If they were, this file would be describing a removal that happened."""
        r1t_only = {d.key for d in BINARY_SENSORS["R1T"]}
        assert not (self.TAILGATE_KEYS & r1t_only)

    @pytest.mark.parametrize("model", ["R1T", "R1S", "R2"])
    async def test_every_model_still_receives_them(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry, model: str
    ) -> None:
        _, binaries = await _setup(hass, mock_config_entry, model)
        keys = {e.entity_description.key for e in _vehicle_only(binaries)}
        assert self.TAILGATE_KEYS <= keys, model

    def test_the_committed_fixture_records_them_for_the_r1s(self) -> None:
        """The fixture is the artefact a future removal would have to edit."""
        data = json.loads(FIXTURE.read_text())
        assert self.TAILGATE_KEYS <= set(data["R1S"]["binary_sensors"])
        assert self.TAILGATE_KEYS <= set(data["R2"]["binary_sensors"])

    async def test_an_unusable_tailgate_field_reads_unknown_not_closed(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """The behaviour this file documents, asserted rather than asserted-about.

        This is what removes the functional argument for deleting them, so it is
        checked here and not left to f0's module alone.
        """
        from custom_components.rivian.binary_sensor import RivianBinarySensorEntity

        (description,) = [
            d for d in BINARY_SENSORS["R1"] if d.key == "closure_tailgate_closed"
        ]
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value="signal_not_available")
        coordinator.data = {}
        entity = RivianBinarySensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle={
                "id": "veh-1",
                "vin": "TESTVIN0000000001",
                "name": "Test R1S",
                "model": "R1S",
            },
        )
        assert entity.is_on is None
        assert entity.available is True


def test_the_decision_is_written_down_where_it_will_be_found() -> None:
    """A decision that lives only in a commit message gets re-litigated."""
    doc = (
        pathlib.Path(__file__).parents[1]
        / "docs/development/MODEL_SPECIFIC_ENTITIES.md"
    )
    assert doc.is_file()
    text = doc.read_text()
    assert "closure_tailgate_closed" in text
    assert "recorded owner decision" in text
