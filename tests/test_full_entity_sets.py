"""s19 SECTION A follow-up: proves `dump_entity_sets.py` matches REALITY.

Every predicate in `entity_keys_for_scenario()` is a hand-reproduction of one
platform's `async_setup_entry` list comprehension -- necessarily, since there
is no shared function to import instead (see that script's module docstring).
A hand-reproduction can drift from the code it describes without either side
noticing. This file is the guard: for every `Scenario` the script defines, it
runs the REAL `async_setup_entry()` of all twelve platforms against an
equivalent mocked vehicle/coordinator and asserts the result is exactly what
the script computed. A predicate that drifts from its platform file fails a
test here, not just a claim in a docstring.

Also re-proves the fixture itself is current (`dump_entity_sets.py --check`,
run from inside the suite rather than trusted as something a human ran
before committing -- same pattern as test_vehicle_supports.py's inertness
proof).
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from custom_components.rivian.binary_sensor import (
    async_setup_entry as binary_sensor_setup,
)
from custom_components.rivian.button import async_setup_entry as button_setup
from custom_components.rivian.camera import async_setup_entry as camera_setup
from custom_components.rivian.climate import async_setup_entry as climate_setup
from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.cover import async_setup_entry as cover_setup
from custom_components.rivian.device_tracker import (
    async_setup_entry as device_tracker_setup,
)
from custom_components.rivian.lock import async_setup_entry as lock_setup
from custom_components.rivian.number import async_setup_entry as number_setup
from custom_components.rivian.select import async_setup_entry as select_setup
from custom_components.rivian.sensor import async_setup_entry as sensor_setup
from custom_components.rivian.switch import async_setup_entry as switch_setup
from custom_components.rivian.time import async_setup_entry as time_setup
from custom_components.rivian.update import async_setup_entry as update_setup
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dump_entity_sets import SCENARIOS, Scenario, entity_keys_for_scenario

REPO_ROOT = Path(__file__).resolve().parents[1]

PLATFORM_SETUP = {
    "sensors_and_extras": sensor_setup,
    "binary_sensors_and_extras": binary_sensor_setup,
    "covers": cover_setup,
    "buttons": button_setup,
    "switches": switch_setup,
    "locks": lock_setup,
    "selects": select_setup,
    "numbers": number_setup,
    "climate": climate_setup,
    "cameras": camera_setup,
    "time": time_setup,
    "device_tracker": device_tracker_setup,
    "update": update_setup,
}


async def _run_real_platforms(
    hass: HomeAssistant, entry: ConfigEntry, s: Scenario
) -> dict[str, list]:
    """Run every platform's REAL async_setup_entry for one Scenario."""
    vehicle: dict = {
        "id": "veh-1",
        "vin": "TESTVIN0000000001",
        "name": "Test Vehicle",
        "supported_features": sorted(s.features),
        "option_codes": list(s.option_codes) if s.option_codes is not None else None,
    }
    if s.model is not None:
        vehicle["model"] = s.model
    if s.paired:
        vehicle["phone_identity_id"] = "phone-1"

    coordinator = MagicMock(spec=VehicleCoordinator)
    # The four OTA fields specifically: RivianUpdateEntity.__init__ ->
    # _update_version_info() concatenates them directly (update.py), which
    # raises on None -- a construction-time requirement, not something this
    # Scenario/gate covers. "0.0.0"/"" are update.py's own documented
    # fallback-triggering sentinels (latest falls back to current when
    # otaAvailableVersion == "0.0.0"; latest hash likewise for ""), so this
    # is the shape update.py already expects a version-unknown vehicle to
    # report, not an arbitrary value chosen to dodge the crash.
    _OTA_FIELDS = {
        "otaCurrentVersion": "2024.01.0",
        "otaAvailableVersion": "0.0.0",
        "otaCurrentVersionGitHash": "",
        "otaAvailableVersionGitHash": "",
    }
    coordinator.get = MagicMock(side_effect=lambda key, *a, **kw: _OTA_FIELDS.get(key))
    coordinator.data = {}
    coordinator.charging_coordinator = MagicMock()
    coordinator.charging_coordinator.get = MagicMock(return_value=None)
    coordinator.drivers_coordinator = MagicMock()
    # None (falsy) => button.py's pairing-button generator expression adds
    # nothing. That entity is excluded from this fixture on purpose (module
    # docstring); if this ever started returning a paired device, the
    # pairing button would appear in the real result and this test's
    # per-platform comparison would catch the mismatch.
    coordinator.drivers_coordinator.get_device_details = MagicMock(return_value=None)

    wallbox = MagicMock()
    wallbox.data = {}

    hass.data[DOMAIN] = {
        entry.entry_id: {
            ATTR_VEHICLE: {"veh-1": vehicle},
            ATTR_COORDINATOR: {
                ATTR_VEHICLE: {"veh-1": coordinator},
                "wallbox": wallbox,
            },
        }
    }

    results: dict[str, list] = {}
    for name, setup_fn in PLATFORM_SETUP.items():
        added: list = []
        await setup_fn(hass, entry, added.extend)
        results[name] = added
    return results


def _keys(entities: list, *, exclude_types: tuple[str, ...] = ()) -> set[str]:
    return {
        e.entity_description.key
        for e in entities
        if type(e).__name__ not in exclude_types
    }


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.label for s in SCENARIOS])
async def test_script_matches_the_real_platforms(
    hass: HomeAssistant, mock_config_entry: ConfigEntry, scenario: Scenario
) -> None:
    """For every Scenario, the script's computed set == what setup actually builds."""
    want = entity_keys_for_scenario(scenario)
    got = await _run_real_platforms(hass, mock_config_entry, scenario)

    # sensor.py mixes in RivianChargingSensorEntity/RivianDriverSensorEntity
    # (this Scenario's sensor_extras) and RivianWallboxSensorEntity (never
    # gated by a vehicle at all, so out of scope for every Scenario here).
    sensor_keys = {
        e.entity_description.key
        for e in got["sensors_and_extras"]
        if type(e).__name__ == "RivianSensorEntity"
    }
    extra_keys = {
        e.entity_description.key
        for e in got["sensors_and_extras"]
        if type(e).__name__
        in ("RivianChargingSensorEntity", "RivianDriverSensorEntity")
    }
    assert sensor_keys == set(want["sensors"]), scenario.label
    assert extra_keys == set(want["sensor_extras"]), scenario.label

    # binary_sensor.py mixes in RivianCloudConnectionBinarySensor
    # (this Scenario's binary_sensor_extras, always exactly {cloud_connected}).
    binary_keys = {
        e.entity_description.key
        for e in got["binary_sensors_and_extras"]
        if type(e).__name__ == "RivianBinarySensorEntity"
    }
    binary_extra_keys = {
        e.entity_description.key
        for e in got["binary_sensors_and_extras"]
        if type(e).__name__ == "RivianCloudConnectionBinarySensor"
    }
    assert binary_keys == set(want["binary_sensors"]), scenario.label
    assert binary_extra_keys == set(want["binary_sensor_extras"]), scenario.label

    assert _keys(got["covers"]) == set(want["covers"]), scenario.label
    assert _keys(got["buttons"]) == set(want["buttons"]), scenario.label
    assert _keys(got["switches"]) == set(want["switches"]), scenario.label
    assert _keys(got["locks"]) == set(want["locks"]), scenario.label
    assert _keys(got["selects"]) == set(want["selects"]), scenario.label
    assert _keys(got["numbers"]) == set(want["numbers"]), scenario.label
    assert _keys(got["climate"]) == set(want["climate"]), scenario.label
    assert _keys(got["cameras"]) == set(want["cameras"]), scenario.label
    assert _keys(got["time"]) == set(want["time"]), scenario.label
    assert _keys(got["device_tracker"]) == set(want["device_tracker"]), scenario.label
    assert _keys(got["update"]) == set(want["update"]), scenario.label


class TestNoDuplicateUniqueIds:
    """The failure an accidental double-grant would cause (mirrors f3a's own
    guard for sensors/binary_sensors, extended to every platform here)."""

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.label for s in SCENARIOS])
    async def test_no_platform_double_adds_an_entity(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry, scenario: Scenario
    ) -> None:
        got = await _run_real_platforms(hass, mock_config_entry, scenario)
        for name, entities in got.items():
            ids = [e.unique_id for e in entities]
            assert len(ids) == len(set(ids)), (scenario.label, name)


class TestCommittedFixtureIsCurrent:
    def test_dump_entity_sets_check_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/dump_entity_sets.py", "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


class TestTonneauStaysOffEverySuvScenario:
    """The regression guard this whole extension exists to add.

    Not redundant with tests/test_cover_tonneau_gate.py: that file tests the
    gate predicate directly with hand-built vehicles. This asserts it against
    the COMMITTED FIXTURE, so a future edit that regenerates the fixture
    without noticing a regression fails here even if nobody thinks to run
    the tonneau-specific suite.
    """

    def test_no_suv_scenario_has_tonneau(self) -> None:
        import json

        data = json.loads((REPO_ROOT / "tests/fixtures/entity_sets.json").read_text())
        for label in ("R1S", "R1S_full_hardware", "R2", "R2_full_hardware"):
            assert "tonneau" not in data[label]["covers"], label

    def test_r1t_full_hardware_does_have_it(self) -> None:
        """The positive control: the gate must still grant it somewhere."""
        import json

        data = json.loads((REPO_ROOT / "tests/fixtures/entity_sets.json").read_text())
        assert "tonneau" in data["R1T_full_hardware"]["covers"]
