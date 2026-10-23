from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.button import BUTTONS
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.cover import COVERS
from custom_components.rivian.entity import RivianVehicleControlEntity
from custom_components.rivian.lock import LOCKS
from custom_components.rivian.rivian_client import VehicleCommand
from custom_components.rivian.switch import SWITCHES
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import EntityDescription

VEHICLE = {"id": "v1", "vin": "VIN1", "name": "Test R1T", "model": "R1T"}

ACTIONS = [
    *(
        (d, command, fallback)
        for descriptions in COVERS.values()
        for d in descriptions
        for command, fallback in (
            ("command_close", "close_cover"),
            ("command_open", "open_cover"),
        )
    ),
    *(
        (d, command, fallback)
        for d in LOCKS
        for command, fallback in (
            ("command_lock", "lock"),
            ("command_unlock", "unlock"),
        )
    ),
    *(
        (d, command, fallback)
        for d in SWITCHES
        for command, fallback in (
            ("command_on", "turn_on"),
            ("command_off", "turn_off"),
        )
    ),
    *(
        (d, "command", "press_fn")
        for descriptions in BUTTONS.values()
        for d in descriptions
    ),
]


def _entity(mock_config_entry: ConfigEntry) -> RivianVehicleControlEntity:
    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator.data = {}
    entity = RivianVehicleControlEntity(
        coordinator=coordinator,
        config_entry=mock_config_entry,
        description=EntityDescription(key="test"),
        vehicle=VEHICLE,
    )
    entity._execute_command = AsyncMock(return_value=None)
    return entity


async def test_run_action_prefers_command_over_fallback(
    mock_config_entry: ConfigEntry,
) -> None:
    entity = _entity(mock_config_entry)
    fallback = AsyncMock()

    await entity._run_action(VehicleCommand.OPEN_FRUNK, {"a": 1}, fallback)

    entity._execute_command.assert_awaited_once_with(
        VehicleCommand.OPEN_FRUNK, {"a": 1}
    )
    fallback.assert_not_awaited()


async def test_run_action_calls_fallback_without_command(
    mock_config_entry: ConfigEntry,
) -> None:
    entity = _entity(mock_config_entry)
    fallback = AsyncMock()

    await entity._run_action(None, None, fallback)

    fallback.assert_awaited_once_with(entity.coordinator)
    entity._execute_command.assert_not_awaited()


@pytest.mark.parametrize(
    ("description", "command", "fallback"),
    ACTIONS,
    ids=[f"{d.key}-{command}" for d, command, _ in ACTIONS],
)
def test_every_control_action_has_a_command_or_a_callable(
    description, command: str, fallback: str
) -> None:
    assert getattr(description, command) is not None or callable(
        getattr(description, fallback)
    )


def test_no_cover_description_sets_feature() -> None:
    assert [
        d.key for descriptions in COVERS.values() for d in descriptions if d.feature
    ] == []
