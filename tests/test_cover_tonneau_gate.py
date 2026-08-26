"""The tonneau cover's gate, twice wrong and now fixed: TONNEAU_CMD, then
`required_field`, now `option_code`.

Round 1 -- `cover.py` used to gate the tonneau on `TONNEAU_CMD`. That string
appears in **none** of the 32,941 decompiled files of the Rivian app, and in
no vehicle's `supported_features` -- so the control was never created for
anyone. The commands themselves are fine: tested live on an R1T,
`OPEN_TONNEAU_COVER` was accepted and the cover physically opened
(`binary_sensor.*_tonneau_cover` off -> on), and `CLOSE_TONNEAU_COVER`
returned it to closed and locked. The gate was wrong; the capability is real.

Round 2 -- the replacement was `required_field="closureTonneauClosed"`: key
presence in `coordinator.data`, not its value. This file used to carry a
SYNTHETIC negative test for it (`data={"closureFrunkClosed": ...}`, omitting
`closureTonneauClosed` entirely) with a comment saying the field is "among
the fields subscribed for every vehicle" and the negative branch would only
be reached by "a vehicle that genuinely does not have the closure". That
comment was wrong, provably: `closureTonneauClosed` is in
`VEHICLE_STATE_SUBSCRIPTION_FIELDS` (const.py) -- the ONE wire document sent
identically to every vehicle regardless of model -- so the key is present in
`coordinator.data` for every vehicle, tonneau or not. Two real R1S fixtures
(`tests/fixtures/community/issue-222.json`, `issue-245.json`; an R1S has no
tonneau option in any configuration) both carry `closureTonneauClosed` WITH
an SNA value (`docs/development/GATE_FIELD_EVIDENCE.md`). The synthetic
test's premise -- that omitting the key from `data` is what a real
non-tonneau vehicle looks like -- never happens on real hardware. `required_field`
was not a rare-edge-case bug; the branch it needed to work was unreachable,
and this file's own synthetic test masked that by constructing the
unreachable case directly instead of a reachable one.

Round 3 (this file, current) -- `option_code="TON-P01"`, matched by
containment against `vehicle["option_codes"]`
(`coordinator.py`'s `_extract_option_codes()`, built from
`mobileConfiguration.tonneauOption`), the vehicle's actual factory option for
a powered tonneau -- what the app itself checks
(`java_src/.../UserVehicle.java:616-618`). The negative test below is no
longer synthetic in the way Round 2's was: it replays a REAL R1S vehicle's
`coordinator.data` (loaded from `issue-222.json`, unmodified) to show the
field-presence gate would have wrongly created the cover on this real
vehicle, and the option_code gate correctly does not.  `option_codes` itself
IS still synthetic in that same test: the community fixtures predate the
`mobileConfiguration` fetch this integration added in s19, so no fixture
carries a real reading for it -- an empty list is what a real R1S is
expected to report once the fetch lands, not something already observed.

That is the general lesson these tests keep encoding: absence from the app,
or from `supportedFeatures`, is not evidence of absence -- but neither is
"the vehicle reports SOME value for this field", when that field is one
every vehicle reports regardless of hardware. Removal or re-gating needs
evidence that actually discriminates, not merely evidence that looks like it
does.
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock

import pytest

from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.cover import COVERS, RivianCoverEntity, async_setup_entry
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

COMMUNITY_FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "community"

# Every gate string cover.py and button.py use, checked against the app's own
# VehicleFeature enum. These are FEATURE NAMES -- the value the server emits --
# not member names; 19 of the 64 differ, and CHARGE_PORT_DOOR_COMMAND (member) vs
# CHARG_PORT_DOOR_COMMAND (featureName) is one of them. The full transcription and
# the lint that enforces this belong to f1; this list is the subset f3b-a swept.
KNOWN_FEATURE_NAMES = {
    "TAILGATE_CMD",
    "LIFTGATE_CMD",
    "SIDE_BIN_NXT_ACT",
    "CHARG_PORT_DOOR_COMMAND",
    "WINDOWS_CMD",
}


def _vehicle(
    features: list[str] | None = None, option_codes: list[str] | None = None
) -> dict:
    return {
        "id": "veh-1",
        "vin": "TESTVIN0000000001",
        "name": "Test R1T",
        "model": "R1T",
        "phone_identity_id": "phone-1",
        "supported_features": features if features is not None else [],
        "option_codes": option_codes if option_codes is not None else [],
    }


async def _setup(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    data: dict,
    features: list[str] | None = None,
    option_codes: list[str] | None = None,
) -> list[RivianCoverEntity]:
    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator.data = data
    hass.data[DOMAIN] = {
        entry.entry_id: {
            ATTR_VEHICLE: {"veh-1": _vehicle(features, option_codes)},
            ATTR_COORDINATOR: {ATTR_VEHICLE: {"veh-1": coordinator}},
        }
    }
    added: list[RivianCoverEntity] = []
    await async_setup_entry(hass, entry, added.extend)
    return added


def _keys(entities: list[RivianCoverEntity]) -> set[str]:
    return {e.entity_description.key for e in entities}


async def test_no_cover_is_keyed_on_tonneau_cmd_any_more(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The dead flag is gone from the gate table entirely."""
    assert "TONNEAU_CMD" not in COVERS


async def test_a_vehicle_with_the_option_code_gets_the_cover(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The current gate: option_code membership, not field presence."""
    added = await _setup(
        hass,
        mock_config_entry,
        data={"closureTonneauClosed": {"value": "closed", "history": {"closed"}}},
        option_codes=["TON-P01"],
    )
    assert "tonneau" in _keys(added)


async def test_a_vehicle_without_the_option_code_does_not(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The straightforward negative case: no TON-P01, no cover."""
    added = await _setup(
        hass,
        mock_config_entry,
        data={"closureTonneauClosed": {"value": "closed", "history": {"closed"}}},
        option_codes=[],
    )
    assert "tonneau" not in _keys(added)


async def test_a_real_r1s_reporting_the_field_still_gets_no_cover(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The bug this round fixed, replayed against a REAL vehicle's data.

    `issue-222.json` is a real R1S diagnostics attachment
    (`tests/fixtures/community/PROVENANCE.md`); an R1S has no tonneau option
    in any factory configuration. Its `closureTonneauClosed` reads
    `signal_not_available` -- present, not absent -- which is exactly what
    made `required_field` wrong: this vehicle would have received
    `cover.tonneau` under the old gate. `option_codes=[]` here IS synthetic
    (see this module's docstring -- no fixture predates the mobileConfiguration
    fetch), everything else in `data` is the unmodified fixture.
    """
    fixture = json.loads((COMMUNITY_FIXTURES / "issue-222.json").read_text())
    real_r1s_data = fixture["data"]["vehicle"][0]
    assert real_r1s_data["closureTonneauClosed"]["value"] == "signal_not_available"

    added = await _setup(hass, mock_config_entry, data=real_r1s_data, option_codes=[])
    assert "tonneau" not in _keys(added)


async def test_field_presence_or_absence_no_longer_affects_creation(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The replacement for Round 2's (wrong) `test_creation_tracks_field_presence`.

    With `option_codes` fixed, whether `closureTonneauClosed` appears in
    `data` at all -- or what it reads -- must make no difference to
    creation. `is_closed`'s own field read still depends on the value; only
    ENTITY CREATION is asserted here.
    """
    for data in (
        {},
        {"closureTonneauClosed": {"value": "open"}},
        {"closureTonneauClosed": {"value": "closed"}},
        {"closureTonneauClosed": {"value": "signal_not_available"}},
    ):
        added = await _setup(
            hass, mock_config_entry, data=data, option_codes=["TON-P01"]
        )
        assert "tonneau" in _keys(added), data
        added = await _setup(hass, mock_config_entry, data=data, option_codes=[])
        assert "tonneau" not in _keys(added), data


async def test_the_flag_alone_no_longer_conjures_the_cover(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """A vehicle advertising the old flag but lacking the option code gets nothing.

    This is the inverse of the original bug and matters just as much: the
    gate must key on what the vehicle actually has, not on a string.
    """
    added = await _setup(
        hass, mock_config_entry, data={}, features=["TONNEAU_CMD"], option_codes=[]
    )
    assert "tonneau" not in _keys(added)


async def test_the_unconditional_covers_are_unaffected(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """frunk stays unconditional; windows now requires WINDOWS_CMD."""
    added = await _setup(hass, mock_config_entry, data={}, option_codes=[])
    assert _keys(added) == {"frunk"}


async def test_the_other_gates_are_real_feature_names(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The sweep, recorded.

    TAILGATE_CMD, LIFTGATE_CMD, SIDE_BIN_NXT_ACT and CHARG_PORT_DOOR_COMMAND are
    all genuine `VehicleFeature` featureNames, so unlike TONNEAU_CMD they are left
    alone. "Real member" is still not "this server emits it" -- confirming that is
    f3b-b's job, on the vehicle -- but there is no offline evidence against them,
    and Principle -1 forbids removing a control on silence.
    """
    from custom_components.rivian.button import BUTTONS

    gates = {f for f in COVERS if f is not None} | {f for f in BUTTONS if f is not None}
    assert gates == KNOWN_FEATURE_NAMES, (
        "a gate string changed; check it against VehicleFeature's featureName "
        "column (NOT the member name -- 19 of 64 differ)"
    )


async def test_the_tonneau_still_uses_the_live_proven_commands(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Re-gating must not quietly change what is sent.

    OPEN_TONNEAU_COVER and CLOSE_TONNEAU_COVER are the two that were confirmed to
    physically move the cover.
    """
    from custom_components.rivian.rivian_client import VehicleCommand

    (tonneau,) = [d for group in COVERS.values() for d in group if d.key == "tonneau"]
    assert tonneau.command_open == VehicleCommand.OPEN_TONNEAU_COVER
    assert tonneau.command_close == VehicleCommand.CLOSE_TONNEAU_COVER
    assert tonneau.option_code == "TON-P01"
    assert not hasattr(tonneau, "required_field")


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        # All True: with the option code present, closureTonneauClosed's
        # presence, absence, or value make no difference to CREATION.
        ({}, True),
        ({"closureTonneauClosed": {"value": "open"}}, True),
        ({"closureTonneauClosed": {"value": "closed"}}, True),
        ({"closureTonneauClosed": {"value": "signal_not_available"}}, True),
    ],
)
async def test_creation_tracks_the_option_code_not_the_field(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
    data: dict,
    expected: bool,
) -> None:
    """Same shape as Round 2's field-presence table, proving the opposite result:
    with the option code present, creation succeeds regardless of what
    `closureTonneauClosed` reads, or whether it is even in `data`."""
    added = await _setup(hass, mock_config_entry, data=data, option_codes=["TON-P01"])
    assert ("tonneau" in _keys(added)) is expected
