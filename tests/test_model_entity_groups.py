"""Optional-hardware gating for sensors and binary sensors.

Every vehicle receives every description that `vehicle_supports()` grants.
Ungated descriptions (no `feature=` / `option_code=`) are the floor: R2 still
gets entities, which is the f3a substring-map bug. Optional hardware is
created only when a live featureName or option code matches.

Counts are asserted NUMERICALLY, not as set equality. A set dedupes, so a
set-equality assertion passes vacuously against exactly the duplication an
`ALL` group would cause.

s19 inverted (accepted): R2/R1S without `LIFTGATE_CMD` lose liftgate *state*.
Liftgate control stays dict-key gated on that same flag in cover.py.
"""

from __future__ import annotations

import json
import pathlib
import sys
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
from custom_components.rivian.sensor import async_setup_entry as sensor_setup
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from dump_entity_sets import SCENARIOS, entity_keys_for_scenario

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "entity_sets.json"

# Flag-dependent, not model-dependent. Stated as literals so the numbers are
# reviewable here rather than recomputed from the same source they are checking
# (derived via `scripts/dump_entity_sets.py`, not guessed -- run it with
# --check to confirm these against tests/fixtures/entity_sets.json).
NO_FLAG_COUNTS = (110, 39)

R1T_FULL_FEATURES = (
    "WINDOWS_CMD",
    "TAILGATE_CMD",
    "TAILGATE_NXT_ACT",
    "SIDE_BIN_NXT_ACT",
    "CHARG_PORT_DOOR_COMMAND",
)

# Dump scenario labels after --write. Sensors/binaries only -- pairing does
# not change those two platforms.
FIXTURE_COUNTS = {
    "R1T": (110, 39),
    "R1S": (110, 39),
    "R2": (110, 39),
    "__absent__": (110, 39),
    "unpaired": (110, 39),
    # s40 added ten sensors and one binary sensor gated on AUTO_VENT / V_GGVS /
    # ENRG_MONTR_PARK, which dump_entity_sets.SOFTWARE_FEATURES now gives to all
    # three full-hardware scenarios: +10/+1 on each row below.
    "R1T_full_hardware": (123, 46),
    "R1S_full_hardware": (123, 42),
    "R2_full_hardware": (121, 42),
}

STAY_UNGATED_KEYS = frozenset(
    {
        # binary_sensor.py / BINARY_SENSORS
        "closure_tailgate_closed",
        "closure_tailgate_locked",
        "charge_port_state",
        "window_front_left_closed",
        "window_front_right_closed",
        "window_rear_left_closed",
        "window_rear_right_closed",
        "car_wash_mode",
        "alarm_sound_status",
        "gear_guard_locked",
        # sensor.py / SENSORS
        "charge_port_status",
        "windows_next_action",
        "trailer_status",
        "cabin_hold_status",
        "gear_guard_video_mode",
        "gear_guard_video_status",
        "gear_guard_video_terms_accepted",
        "seat_front_left_heat",
        "seat_front_left_vent",
        "seat_front_right_heat",
        "seat_front_right_vent",
        "seat_rear_left_heat",
        "seat_rear_right_heat",
        "pet_mode_status",
        "pet_mode_temperature_status",
        # cover.py COVERS[None]
        "frunk",
        # switch.py SWITCHES
        "cabin_climate_hold",
        "charging_enabled",
        "gear_guard_video",
        "alarm",
        # select.py SELECTS + FRONT_SEAT_SELECTS
        "seat_front_left_heat_vent",
        "seat_front_right_heat_vent",
    }
)

GATED_ABSENT_FROM_NO_FLAG_R1T = frozenset(
    {
        "closure_liftgate_next_action",
        "closure_liftgate_closed",
        "closure_liftgate_locked",
        "seat_third_row_left_heat",
        "seat_third_row_right_heat",
        "closure_side_bin_left_next_action",
        "closure_side_bin_right_next_action",
        "closure_side_bin_left_closed",
        "closure_side_bin_left_locked",
        "closure_side_bin_right_closed",
        "closure_side_bin_right_locked",
        "closure_tailgate_next_action",
        "closure_tonneau_closed",
        "closure_tonneau_locked",
        "windows",
        "charge_port",
        "liftgate",
        "tonneau",
        "open_gear_tunnel_left",
        "open_gear_tunnel_right",
        "drop_tailgate",
        "open_tailgate",
        "open_liftgate",
    }
)


def _r1t_no_flag_dump_keys() -> set[str]:
    scenario = next(s for s in SCENARIOS if s.label == "R1T")
    return {
        key
        for platform_keys in entity_keys_for_scenario(scenario).values()
        for key in platform_keys
    }


def _scenario(label: str):
    return next(s for s in SCENARIOS if s.label == label)


def _keys_with_feature(collection, *names: str) -> set[str]:
    wanted = set(names)
    out: set[str] = set()
    for d in collection:
        feat = d.feature
        if feat is None:
            continue
        have = {feat} if isinstance(feat, str) else set(feat)
        if have & wanted:
            out.add(d.key)
    return out


def _keys_with_option(collection, code: str) -> set[str]:
    return {d.key for d in collection if d.option_code == code}


class TestUniqueKeys:
    """Keys unique across SENSORS and across BINARY_SENSORS.

    unique_id is vin-plus-key (entity.py). A repeated key is a duplicate
    entity regardless of which flag granted it.
    """

    def test_sensor_keys_are_unique(self) -> None:
        keys = [d.key for d in SENSORS]
        assert len(keys) == len(set(keys)), sorted(
            {k for k in keys if keys.count(k) > 1}
        )

    def test_binary_sensor_keys_are_unique(self) -> None:
        keys = [d.key for d in BINARY_SENSORS]
        assert len(keys) == len(set(keys)), sorted(
            {k for k in keys if keys.count(k) > 1}
        )


async def _setup(
    hass: HomeAssistant,
    entry: ConfigEntry,
    model: str | None,
    features: tuple[str, ...] = (),
    option_codes: tuple[str, ...] = (),
) -> tuple[list, list]:
    """Run both platforms for one vehicle and return (sensors, binary sensors)."""
    vehicle = {
        "id": "veh-1",
        "vin": "TESTVIN0000000001",
        "name": "Test Vehicle",
        "phone_identity_id": "phone-1",
        "supported_features": list(features),
        "option_codes": list(option_codes),
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


class TestStayUngatedAndGatedAbsent:
    """Stay-ungated keys must remain; gated keys must leave no-flag R1T."""

    def test_stay_ungated_keys_are_in_no_flag_r1t_dump(self) -> None:
        assert STAY_UNGATED_KEYS <= _r1t_no_flag_dump_keys()

    async def test_stay_ungated_sensor_binary_keys_are_in_no_flag_r1t_setup(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        sensors, binaries = await _setup(hass, mock_config_entry, "R1T", features=())
        keys = {
            e.entity_description.key
            for e in (*_vehicle_only(sensors), *_vehicle_only(binaries))
        }
        sensor_or_binary = {d.key for d in SENSORS} | {d.key for d in BINARY_SENSORS}
        assert STAY_UNGATED_KEYS & sensor_or_binary <= keys

    def test_gated_absent_disjoint_from_no_flag_r1t_dump(self) -> None:
        assert GATED_ABSENT_FROM_NO_FLAG_R1T.isdisjoint(_r1t_no_flag_dump_keys())


def _vehicle_only(entities: list) -> list:
    """Drop the charging/wallbox/cloud entities the creation predicate does not govern."""
    return [
        e
        for e in entities
        if type(e).__name__ in ("RivianSensorEntity", "RivianBinarySensorEntity")
    ]


@pytest.mark.parametrize("model", ["R1T", "R1S", "R2", None, "", "R3X"])
async def test_entity_counts_per_model(
    hass: HomeAssistant, mock_config_entry: ConfigEntry, model: str | None
) -> None:
    """Numeric list lengths -- NOT set equality, which dedupes.

    Default `_setup(features=())` is the floor. Every model, including R2,
    gets the ungated counts.
    """
    sensors, binaries = await _setup(hass, mock_config_entry, model)
    want_sensors, want_binaries = NO_FLAG_COUNTS
    assert len(_vehicle_only(sensors)) == want_sensors, model
    assert len(_vehicle_only(binaries)) == want_binaries, model


async def test_r1t_full_hardware_counts(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    sensors, binaries = await _setup(
        hass,
        mock_config_entry,
        "R1T",
        features=R1T_FULL_FEATURES,
        option_codes=("TON-P01",),
    )
    assert len(_vehicle_only(sensors)) == 113
    assert len(_vehicle_only(binaries)) == 45


async def test_liftgate_cmd_only_counts(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    sensors, binaries = await _setup(
        hass, mock_config_entry, "R2", features=("LIFTGATE_CMD",)
    )
    assert len(_vehicle_only(sensors)) == 111
    assert len(_vehicle_only(binaries)) == 41


async def test_heated_seats_third_only_counts(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    sensors, binaries = await _setup(
        hass, mock_config_entry, "R1S", features=("HEATED_SEATS_THIRD",)
    )
    assert len(_vehicle_only(sensors)) == 112
    assert len(_vehicle_only(binaries)) == 39


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
    """The f3a bug, stated as its own test so a regression is unmissable."""
    sensors, binaries = await _setup(hass, mock_config_entry, "R2")
    assert _vehicle_only(sensors), "an R2 received ZERO sensors"
    assert _vehicle_only(binaries), "an R2 received ZERO binary sensors"


async def test_r2_is_the_shared_group_plus_liftgate(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """With-flag liftgate state: ungated floor plus LIFTGATE_CMD descriptions."""
    r2_s, r2_b = await _setup(hass, mock_config_entry, "R2", features=("LIFTGATE_CMD",))
    floor_s, floor_b = await _setup(hass, mock_config_entry, "R2")

    def keys(entities: list) -> set[str]:
        return {e.entity_description.key for e in _vehicle_only(entities)}

    liftgate_sensors = _keys_with_feature(SENSORS, "LIFTGATE_CMD")
    liftgate_binaries = _keys_with_feature(BINARY_SENSORS, "LIFTGATE_CMD")
    assert keys(r2_s) == keys(floor_s) | liftgate_sensors
    assert keys(r2_b) == keys(floor_b) | liftgate_binaries

    r1t_sensors = _keys_with_feature(
        SENSORS, "SIDE_BIN_NXT_ACT", "TAILGATE_CMD", "TAILGATE_NXT_ACT"
    )
    r1t_binaries = _keys_with_feature(BINARY_SENSORS, "SIDE_BIN_NXT_ACT") | (
        _keys_with_option(BINARY_SENSORS, "TON-P01")
    )
    third_row = _keys_with_feature(SENSORS, "HEATED_SEATS_THIRD")
    assert not (keys(r2_s) & r1t_sensors)
    assert not (keys(r2_b) & r1t_binaries)
    assert not (keys(r2_s) & third_row)


async def test_r2_without_liftgate_cmd_has_no_liftgate_state(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """s19 inverted, accepted: no LIFTGATE_CMD means no liftgate *state*."""
    sensors, binaries = await _setup(hass, mock_config_entry, "R2")
    keys = {
        e.entity_description.key
        for e in (*_vehicle_only(sensors), *_vehicle_only(binaries))
    }
    assert "closure_liftgate_next_action" not in keys
    assert not {"closure_liftgate_closed", "closure_liftgate_locked"} & keys


async def test_r2_gets_liftgate_state_paired_with_liftgate_control(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Control and state share LIFTGATE_CMD; both appear together.

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
    """No-flag models share the ungated floor; optional hardware stays off both."""
    r1t_s, r1t_b = await _setup(hass, mock_config_entry, "R1T")
    r1s_s, r1s_b = await _setup(hass, mock_config_entry, "R1S")

    def keys(entities: list) -> set[str]:
        return {e.entity_description.key for e in _vehicle_only(entities)}

    r1t_sensors = _keys_with_feature(
        SENSORS, "SIDE_BIN_NXT_ACT", "TAILGATE_CMD", "TAILGATE_NXT_ACT"
    )
    r1t_binaries = _keys_with_feature(BINARY_SENSORS, "SIDE_BIN_NXT_ACT") | (
        _keys_with_option(BINARY_SENSORS, "TON-P01")
    )
    r1s_sensors = _keys_with_feature(SENSORS, "HEATED_SEATS_THIRD", "LIFTGATE_CMD")
    r1s_binaries = _keys_with_feature(BINARY_SENSORS, "LIFTGATE_CMD")
    assert not (keys(r1s_s) & r1t_sensors)
    assert not (keys(r1s_b) & r1t_binaries)
    assert not (keys(r1t_s) & r1s_sensors)
    assert not (keys(r1t_b) & r1s_binaries)
    assert keys(r1t_s) == keys(r1s_s)
    assert keys(r1t_b) == keys(r1s_b)


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
    """The baseline every later story is checked against."""

    def test_fixture_exists(self) -> None:
        assert FIXTURE.is_file(), f"missing committed fixture: {FIXTURE}"

    @pytest.mark.parametrize("label", sorted(FIXTURE_COUNTS))
    async def test_entity_sets_match_the_fixture(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry, label: str
    ) -> None:
        scenario = _scenario(label)
        expected = json.loads(FIXTURE.read_text())[label]
        sensors, binaries = await _setup(
            hass,
            mock_config_entry,
            scenario.model,
            features=tuple(scenario.features),
            option_codes=tuple(scenario.option_codes or ()),
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
        for label, (n_sensors, n_binaries) in FIXTURE_COUNTS.items():
            assert len(data[label]["sensors"]) == n_sensors, label
            assert len(data[label]["binary_sensors"]) == n_binaries, label


class TestTailgateStaysShared:
    """`closure_tailgate_*` has no `feature=` / `option_code=`, and stays that way.

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

    def test_the_tailgate_entities_have_no_feature_or_option_code(self) -> None:
        found = {d.key: d for d in BINARY_SENSORS if d.key in self.TAILGATE_KEYS}
        assert set(found) == self.TAILGATE_KEYS
        for description in found.values():
            assert description.feature is None, description.key
            assert description.option_code is None, description.key

    def test_they_appear_under_no_flags(self) -> None:
        """Static: they are on the tuple with both gates None, so features=() grants them."""
        found = [d for d in BINARY_SENSORS if d.key in self.TAILGATE_KEYS]
        assert {d.key for d in found} == self.TAILGATE_KEYS
        assert all(d.feature is None and d.option_code is None for d in found)

    @pytest.mark.parametrize("model", ["R1T", "R1S", "R2"])
    async def test_every_model_still_receives_them(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry, model: str
    ) -> None:
        _, binaries = await _setup(hass, mock_config_entry, model, features=())
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
            d for d in BINARY_SENSORS if d.key == "closure_tailgate_closed"
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
