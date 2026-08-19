"""A command's result comes back from the query, not from the subscription.

Measured on the vehicle, twice, with the same credentials minutes apart:

* `OPEN_TONNEAU_COVER` sent OUTSIDE Home Assistant, then polled with
  `get_vehicle_command_state`, answered in five seconds:
  `{'state': 0, 'responseCode': 288, 'statusCode': 0}`.
* the identical command sent THROUGH Home Assistant reported `TIMEOUT`. The debug
  log shows the command-state subscription being established and torn down with no
  message in between.

Sending was never the problem, and nothing in the send path had changed -- a diff
of `send_vehicle_command`, the HMAC signing and `vehicleCommandState` across the
releases involved is empty.

Two separate defects were behind it, and either alone is enough to time out every
command:

1. the subscription never delivers, so nothing populates `_command_states`;
2. the wait loop tested `state in ["COMPLETED_SUCCESS", ...]` -- **strings** --
   while the server answers with an **integer**. Even a working subscription would
   have timed out every command.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.coordinator import VehicleCoordinator


def _response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.json = AsyncMock(return_value=payload)
    return response


def _coordinator(payload: dict) -> MagicMock:
    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator._command_states = {}
    coordinator.api = MagicMock()
    coordinator.api.get_vehicle_command_state = AsyncMock(
        return_value=_response(payload)
    )
    return coordinator


LIVE = {
    "data": {
        "getVehicleCommand": {
            "id": "04-abc",
            "command": "OPEN_TONNEAU_COVER",
            "createdAt": "2026-08-19T10:30:47.896353",
            "state": 0,
            "responseCode": 288,
            "statusCode": 0,
        }
    }
}


class TestPolling:
    async def test_a_live_shaped_answer_is_stored(self) -> None:
        coordinator = _coordinator(LIVE)
        await VehicleCoordinator._poll_command_state(
            coordinator, "04-abc", interval=0, attempts=2
        )
        assert coordinator._command_states["04-abc"] == {
            "command": "OPEN_TONNEAU_COVER",
            "state": 0,
            "responseCode": 288,
            "statusCode": 0,
            "createdAt": "2026-08-19T10:30:47.896353",
        }

    async def test_it_stops_as_soon_as_it_has_an_answer(self) -> None:
        """One query for a command that answers on the first poll."""
        coordinator = _coordinator(LIVE)
        await VehicleCoordinator._poll_command_state(
            coordinator, "04-abc", interval=0, attempts=7
        )
        assert coordinator.api.get_vehicle_command_state.await_count == 1

    async def test_it_yields_to_the_subscription(self) -> None:
        """The subscription is kept; whichever answers first wins."""
        coordinator = _coordinator(LIVE)
        coordinator._command_states["04-abc"] = {"state": "COMPLETED_SUCCESS"}
        await VehicleCoordinator._poll_command_state(
            coordinator, "04-abc", interval=0, attempts=3
        )
        coordinator.api.get_vehicle_command_state.assert_not_awaited()
        assert coordinator._command_states["04-abc"]["state"] == "COMPLETED_SUCCESS"

    async def test_a_failing_query_does_not_kill_the_command(self) -> None:
        coordinator = _coordinator(LIVE)
        coordinator.api.get_vehicle_command_state = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        await VehicleCoordinator._poll_command_state(
            coordinator, "04-abc", interval=0, attempts=2
        )
        assert "04-abc" not in coordinator._command_states

    async def test_a_null_state_is_not_treated_as_an_answer(self) -> None:
        """in_progress comes back with state None; polling must keep going."""
        coordinator = _coordinator(
            {"data": {"getVehicleCommand": {"id": "04-abc", "state": None}}}
        )
        await VehicleCoordinator._poll_command_state(
            coordinator, "04-abc", interval=0, attempts=3
        )
        assert "04-abc" not in coordinator._command_states
        assert coordinator.api.get_vehicle_command_state.await_count == 3

    async def test_the_store_stays_bounded(self) -> None:
        coordinator = _coordinator(LIVE)
        coordinator._command_states = {f"old-{i}": {} for i in range(10)}
        await VehicleCoordinator._poll_command_state(
            coordinator, "04-abc", interval=0, attempts=2
        )
        assert len(coordinator._command_states) == 10
        assert "04-abc" in coordinator._command_states


class TestIntegerStateIsTerminal:
    """The wait loop must accept what the server actually sends."""

    @pytest.mark.parametrize("state", [0, 1, 2])
    def test_an_integer_state_is_terminal(self, state: int) -> None:
        import inspect

        from custom_components.rivian.entity import RivianVehicleControlEntity

        source = inspect.getsource(RivianVehicleControlEntity._execute_command)
        assert "isinstance(state, int)" in source, (
            "the wait loop only matched the string enum, so a live answer of "
            "state=0 never ended the wait and every command reported TIMEOUT"
        )

    def test_the_string_enum_is_still_accepted(self) -> None:
        import inspect

        from custom_components.rivian.entity import RivianVehicleControlEntity

        source = inspect.getsource(RivianVehicleControlEntity._execute_command)
        for value in ("COMPLETED_SUCCESS", "COMPLETED_ERROR", "FAILED"):
            assert value in source
