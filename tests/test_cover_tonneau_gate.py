"""The tonneau cover is keyed on the field the vehicle reports, not on a flag.

`cover.py` used to gate the tonneau on `TONNEAU_CMD`. That string appears in
**none** of the 32,941 decompiled files of the Rivian app, and in no vehicle's
`supported_features` -- so the control was never created for anyone.

The commands themselves are fine. Tested live on an R1T:
`OPEN_TONNEAU_COVER` was accepted and the cover physically opened
(`binary_sensor.*_tonneau_cover` off -> on), and `CLOSE_TONNEAU_COVER` returned it
to closed and locked. The gate was wrong; the capability is real.

That is the general lesson these tests encode: absence from the app, or from
`supportedFeatures`, is not evidence of absence. Removal needs a recorded live
failure.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.cover import COVERS, RivianCoverEntity, async_setup_entry
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

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
}


def _vehicle(features: list[str] | None = None) -> dict:
    return {
        "id": "veh-1",
        "vin": "TESTVIN0000000001",
        "name": "Test R1T",
        "model": "R1T",
        "phone_identity_id": "phone-1",
        "supported_features": features if features is not None else [],
    }


async def _setup(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    data: dict,
    features: list[str] | None = None,
) -> list[RivianCoverEntity]:
    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator.data = data
    hass.data[DOMAIN] = {
        entry.entry_id: {
            ATTR_VEHICLE: {"veh-1": _vehicle(features)},
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


async def test_a_vehicle_reporting_the_field_gets_the_cover(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Field presence is the gate -- and it needs no capability flag at all."""
    added = await _setup(
        hass,
        mock_config_entry,
        data={"closureTonneauClosed": {"value": "closed", "history": {"closed"}}},
        features=[],
    )
    assert "tonneau" in _keys(added)


async def test_a_vehicle_not_reporting_the_field_does_not(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The negative branch.

    Be plain about what this proves: `closureTonneauClosed` is among the fields
    subscribed for every vehicle, and the owner's R1T reports it, so on real
    hardware this branch is reached only by a vehicle that genuinely does not
    have the closure. It is asserted synthetically here because no R1S is
    available to the test suite -- not because it was verified on one.
    """
    added = await _setup(
        hass,
        mock_config_entry,
        data={"closureFrunkClosed": {"value": "closed", "history": {"closed"}}},
        features=[],
    )
    assert "tonneau" not in _keys(added)


async def test_the_flag_alone_no_longer_conjures_the_cover(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """A vehicle advertising the old flag but not reporting the field gets nothing.

    This is the inverse of the bug and matters just as much: the gate must key on
    what the vehicle reports, not on a string.
    """
    added = await _setup(hass, mock_config_entry, data={}, features=["TONNEAU_CMD"])
    assert "tonneau" not in _keys(added)


async def test_the_unconditional_covers_are_unaffected(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """frunk and windows stay unconditional; this story adds a third case, not a
    new filter over the existing two."""
    added = await _setup(hass, mock_config_entry, data={}, features=[])
    assert _keys(added) == {"frunk", "windows"}


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
    assert tonneau.required_field == "closureTonneauClosed"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({}, False),
        ({"closureTonneauClosed": {"value": "open"}}, True),
        ({"closureTonneauClosed": {"value": "closed"}}, True),
        # Present but valueless still counts as reported: the vehicle named the
        # field. Availability, not creation, is what handles an unusable value.
        ({"closureTonneauClosed": {}}, True),
    ],
)
async def test_creation_tracks_field_presence_not_field_value(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
    data: dict,
    expected: bool,
) -> None:
    added = await _setup(hass, mock_config_entry, data=data, features=[])
    assert ("tonneau" in _keys(added)) is expected
