"""Command-state path, after rulings 15 and 22.

SUPERSEDED: this module originally recorded that a command's result comes
back from the query (`getVehicleCommand`), not the subscription. That was
ae06ee9's diagnosis, and it was why `_poll_command_state` existed. Ruling 15
drops the poll -- the app never had one: `vehicleCommandState` in 18 APK
files, `getVehicleCommand` in 0. Ruling 22 returns on the first well-formed
subscription frame and tracks terminality in the background.

TestPolling's six tests went with the function. The ae06ee9 record is kept
below so the diagnosis stays reconstructible.

---

A command's result comes back from the query, not from the subscription.

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

## What is broken, stated precisely

**The commands work.** The vehicle acts on them. Observed on the owner's R1T with
the code as shipped: `CLOSE_FRUNK` closed the hood, `CLOSE_ALL_WINDOWS` closed the
windows, `LOCK_ALL_CLOSURES_FEEDBACK` locked the vehicle, and
`OPEN_TONNEAU_COVER` unlocked the tonneau. What is broken is the **result
reporting** -- all four of those recorded `last_command_state: TIMEOUT` anyway.

That distinction matters and an earlier description of this got it wrong by
saying the defect would "time out every command", which reads as the controls not
working. They work. What fails is knowing that they did.

The cost is not cosmetic: `_execute_command` returns `None`, so callers cannot
tell success from failure; `EVENT_COMMAND_SUCCESS` and `EVENT_COMMAND_FAILED`
never fire, so anything keyed off them never runs; and every control permanently
advertises `TIMEOUT` in its attributes.

Two defects, either of which alone prevents a result from ever being recorded:

1. the subscription never delivers, so nothing populates `_command_states`;
2. the wait loop tested `state in ["COMPLETED_SUCCESS", ...]` -- **strings** --
   while the server answers with an **integer**, so even a working subscription
   would never have satisfied it.

Note what `state: 0` does NOT mean. The tonneau returned `state 0 / responseCode
288` and unlocked without opening, so 0 is not proof the physical action
completed. No meaning is assigned to it here beyond "the server answered".
"""

from __future__ import annotations

import inspect
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, PropertyMock, patch

import pytest

from custom_components.rivian.climate import DEFROST_DEFOG, RivianClimateEntity
from custom_components.rivian.coordinator import (
    COMMAND_STATE_CONTINUE,
    VehicleCoordinator,
)
from custom_components.rivian.entity import RivianVehicleControlEntity
from custom_components.rivian.rivian_client import VehicleCommand
from homeassistant.components.climate import ATTR_TEMPERATURE, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription

from tests.apk.transcription import COMMAND_STATE_CONTINUE as TRANSCRIBED_CONTINUE

REPO = Path(__file__).parents[1]
COORDINATOR_PY = REPO / "custom_components/rivian/coordinator.py"
ENTITY_PY = REPO / "custom_components/rivian/entity.py"

VEHICLE = {
    "id": "test_vehicle_123",
    "vin": "TEST123456789",
    "name": "Test R1T",
    "model": "R1T",
    "phone_identity_id": "test_phone_id",
}

FIRST_FRAME_STATES = [0, 1, 2, 3, 4, 5, 6, 7, 42, -1]
STRING_ENUM = ("COMPLETED_SUCCESS", "COMPLETED_ERROR", "FAILED")


def _frame(state, command="WAKE_VEHICLE", **extra) -> dict:
    return {
        "payload": {
            "data": {
                "vehicleCommandState": {
                    "command": command,
                    "state": state,
                    **extra,
                }
            }
        }
    }


def _coordinator(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> VehicleCoordinator:
    return VehicleCoordinator(
        hass=hass,
        config_entry=mock_config_entry,
        client=MagicMock(),
        vehicle_id="v1",
    )


def _entity(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
    coordinator: VehicleCoordinator,
) -> RivianVehicleControlEntity:
    entity = RivianVehicleControlEntity(
        coordinator=coordinator,
        config_entry=mock_config_entry,
        description=EntityDescription(key="test", name="Test"),
        vehicle=VEHICLE,
    )
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()
    return entity


class _Clock:
    """Advances only when sleep is awaited. Tests must not take 30 s each."""

    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps = 0

    def __call__(self) -> float:
        return self.t

    async def sleep(self, dt: float) -> None:
        self.sleeps += 1
        self.t += dt


def _deliver_on_send(
    coordinator: VehicleCoordinator, state, command_id: str = "cmd-1"
) -> None:
    async def send(command, params=None):
        coordinator._process_command_state(
            command_id, _frame(state, command=command.value)
        )
        return command_id

    coordinator.send_vehicle_command = send


# --- 1 / 2 / 2b [at-return] -------------------------------------------------


class TestFirstFrameReturns:
    """The property that carries the whole argument. [at-return]

    For any well-formed frame the user gets a non-TIMEOUT answer at the same
    speed as today -- within one sampling tick, not at the 30 s ceiling. This
    is the test that would have caught ae06ee9, and the timing half pins
    ruling 22 against a re-introduced blocking wait.
    """

    @pytest.mark.parametrize("state", [*FIRST_FRAME_STATES, *STRING_ENUM])
    async def test_a_well_formed_frame_returns_on_the_first_tick(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        state,
    ) -> None:
        coordinator = _coordinator(hass, mock_config_entry)
        entity = _entity(hass, mock_config_entry, coordinator)
        _deliver_on_send(coordinator, state)
        clock = _Clock()

        result = await entity._execute_command(
            VehicleCommand.WAKE_VEHICLE, _clock=clock, _sleep=clock.sleep
        )

        assert result is not None
        assert entity._last_command_status["state"] is not None
        assert entity._last_command_status["state"] != "TIMEOUT"
        assert entity._last_command_status["state"] == state
        assert clock.sleeps == 0
        assert clock.t < 0.5


class TestTimeoutMeansZeroWellFormedFrames:
    """TIMEOUT is reachable only from zero well-formed frames. [at-return]"""

    async def test_no_frame_is_timeout_with_zero_frames(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        coordinator = _coordinator(hass, mock_config_entry)
        entity = _entity(hass, mock_config_entry, coordinator)
        coordinator.send_vehicle_command = AsyncMock(return_value="cmd-1")
        clock = _Clock()

        result = await entity._execute_command(
            VehicleCommand.WAKE_VEHICLE, _clock=clock, _sleep=clock.sleep
        )

        assert result is None
        assert entity._last_command_status["state"] == "TIMEOUT"
        assert entity.extra_state_attributes["state_frames_seen"] == 0
        assert clock.t >= 30

    @pytest.mark.parametrize("state", [*FIRST_FRAME_STATES, *STRING_ENUM])
    async def test_any_well_formed_frame_is_never_timeout(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry, state
    ) -> None:
        coordinator = _coordinator(hass, mock_config_entry)
        entity = _entity(hass, mock_config_entry, coordinator)
        _deliver_on_send(coordinator, state)
        clock = _Clock()

        result = await entity._execute_command(
            VehicleCommand.WAKE_VEHICLE, _clock=clock, _sleep=clock.sleep
        )

        assert result is not None
        assert entity._last_command_status["state"] != "TIMEOUT"

    async def test_a_malformed_payload_is_timeout_and_logs_error(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry, caplog
    ) -> None:
        coordinator = _coordinator(hass, mock_config_entry)
        entity = _entity(hass, mock_config_entry, coordinator)
        with caplog.at_level(logging.ERROR):
            coordinator._process_command_state("cmd-1", {"payload": {}})
        coordinator.send_vehicle_command = AsyncMock(return_value="cmd-1")
        clock = _Clock()

        result = await entity._execute_command(
            VehicleCommand.WAKE_VEHICLE, _clock=clock, _sleep=clock.sleep
        )

        assert result is None
        assert entity._last_command_status["state"] == "TIMEOUT"
        assert entity.extra_state_attributes["state_frames_seen"] == 0
        assert "Received unknown command state update" in caplog.text

    async def test_a_null_state_is_timeout_and_logs_warning(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry, caplog
    ) -> None:
        coordinator = _coordinator(hass, mock_config_entry)
        entity = _entity(hass, mock_config_entry, coordinator)
        with caplog.at_level(logging.WARNING):
            coordinator._process_command_state("cmd-1", {"state": None})
            coordinator._process_command_state(
                "cmd-1",
                {"payload": {"data": {"vehicleCommandState": {"state": None}}}},
            )
        coordinator.send_vehicle_command = AsyncMock(return_value="cmd-1")
        clock = _Clock()

        result = await entity._execute_command(
            VehicleCommand.WAKE_VEHICLE, _clock=clock, _sleep=clock.sleep
        )

        assert result is None
        assert entity._last_command_status["state"] == "TIMEOUT"
        assert entity.extra_state_attributes["state_frames_seen"] == 0
        assert "Received unknown command state update" in caplog.text
        assert "missing or null state" in caplog.text


# --- 3 / 4 [settled] --------------------------------------------------------


class TestBackgroundRecord:
    async def test_continue_set_does_not_truncate_the_record(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """State 2 at t=0, state 0 at t=1. [settled]

        _execute_command returns state 2 -- ruling 22 -- and once settled the
        coordinator record has frames_seen == 2. The == 2 is meaningful only
        because the counter lives in _process_command_state (N10).
        """
        coordinator = _coordinator(hass, mock_config_entry)
        entity = _entity(hass, mock_config_entry, coordinator)
        _deliver_on_send(coordinator, 2)
        clock = _Clock()

        result = await entity._execute_command(
            VehicleCommand.WAKE_VEHICLE, _clock=clock, _sleep=clock.sleep
        )

        assert result["state"] == 2
        assert entity._last_command_status["state"] == 2

        coordinator._process_command_state("cmd-1", _frame(0, command="WAKE_VEHICLE"))
        rec = coordinator.get_command_state("cmd-1")
        assert rec["frames_seen"] == 2
        assert rec["terminal_reached"] is True
        assert rec["state"] == 0
        assert rec["is_lifecycle"] is False
        assert rec["terminal_at"] is not None

    async def test_ceiling_with_only_continue_set_states(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Only continue-set frames: first state is kept, never TIMEOUT. [settled]"""
        coordinator = _coordinator(hass, mock_config_entry)
        entity = _entity(hass, mock_config_entry, coordinator)
        _deliver_on_send(coordinator, 2)
        clock = _Clock()

        result = await entity._execute_command(
            VehicleCommand.WAKE_VEHICLE, _clock=clock, _sleep=clock.sleep
        )
        assert result["state"] == 2

        coordinator._process_command_state("cmd-1", _frame(5))
        coordinator._process_command_state("cmd-1", _frame(3))
        await coordinator._unsubscribe_command_state("cmd-1")

        rec = coordinator.get_command_state("cmd-1")
        assert rec["is_lifecycle"] is True
        assert rec["terminal_reached"] is False
        assert rec["frames_seen"] == 3
        assert entity._last_command_status["state"] == 2
        assert entity._last_command_status["state"] != "TIMEOUT"


# --- 5a / 5b / 5c -----------------------------------------------------------


class TestAttributeSurface:
    async def test_5a_seeds_before_any_command(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """[at-return] seeded before any command has ever been sent."""
        coordinator = _coordinator(hass, mock_config_entry)
        entity = _entity(hass, mock_config_entry, coordinator)

        attrs = entity.extra_state_attributes
        assert "state_is_lifecycle" in attrs
        assert "state_frames_seen" in attrs
        assert "final_command_state" in attrs
        assert attrs["state_is_lifecycle"] is None
        assert attrs["state_frames_seen"] == 0
        assert attrs["final_command_state"] is None

    async def test_5b_read_through_after_the_call_has_returned(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """THE C1 TEST. Interpretation B is mandatory.

        1. _execute_command returns on one frame delivered during the call.
        2. The call has RETURNED -- entity.py:234 has run, _current_command_id
           is None.
        3. Only then deliver a second frame.
        4. Then read extra_state_attributes.

        Interpretation A (read during the wait) passes with C1 present and is
        forbidden. This fails against a read-through keyed on
        _current_command_id, which is None from the instant the call returns.
        """
        coordinator = _coordinator(hass, mock_config_entry)
        entity = _entity(hass, mock_config_entry, coordinator)
        _deliver_on_send(coordinator, 2)
        clock = _Clock()

        await entity._execute_command(
            VehicleCommand.WAKE_VEHICLE, _clock=clock, _sleep=clock.sleep
        )

        assert entity._current_command_id is None
        assert entity._last_command_id == "cmd-1"
        assert entity.extra_state_attributes["state_frames_seen"] == 1

        coordinator._process_command_state("cmd-1", _frame(0))

        attrs = entity.extra_state_attributes
        assert attrs["state_frames_seen"] == 2
        assert attrs["final_command_state"] == 0

    async def test_5c_evicted_record_falls_back_to_seeds(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """After the record is evicted (removed directly), attributes fall
        back to their seeds and do not raise. NOT by advancing 60 s: the
        record outlives the subscription. [settled]
        """
        coordinator = _coordinator(hass, mock_config_entry)
        entity = _entity(hass, mock_config_entry, coordinator)
        _deliver_on_send(coordinator, 2)
        clock = _Clock()

        await entity._execute_command(
            VehicleCommand.WAKE_VEHICLE, _clock=clock, _sleep=clock.sleep
        )
        assert entity._last_command_id == "cmd-1"

        coordinator._command_states.pop("cmd-1")

        attrs = entity.extra_state_attributes
        assert entity._last_command_id == "cmd-1"
        assert coordinator.get_command_state("cmd-1") is None
        assert attrs["state_frames_seen"] == 0
        assert attrs["state_is_lifecycle"] is None
        assert attrs["final_command_state"] is None


# --- 6 / 7 / 7b -------------------------------------------------------------


class TestPollIsGone:
    def test_poll_is_absent_from_subscribe(self) -> None:
        source = inspect.getsource(VehicleCoordinator._subscribe_to_command_state)
        assert "_poll_command_state" not in source
        assert "async_create_background_task" not in source
        assert "_poll_command_state" not in COORDINATOR_PY.read_text()
        assert "get_vehicle_command_state" not in COORDINATOR_PY.read_text()


class TestVocabularyLivesWhereTheFramesArrive:
    """The wait loop must accept what the server actually sends.

    That acceptance now lives in coordinator.py, where the frames arrive.
    """

    def test_an_integer_state_is_terminal(self) -> None:
        """Previously pinned the defect.

        Asserted `isinstance(state, int)` in `_execute_command`'s source, which
        is the N1 bug: returning on any integer including the continue set.
        4b deletes that expression; terminality is evaluated against
        COMMAND_STATE_CONTINUE in coordinator.py.
        """
        source = inspect.getsource(RivianVehicleControlEntity._execute_command)
        assert "isinstance(state, int)" not in source
        assert "COMMAND_STATE_CONTINUE" in COORDINATOR_PY.read_text()
        from custom_components.rivian.coordinator import _command_state_is_lifecycle

        helper = inspect.getsource(_command_state_is_lifecycle)
        assert "COMMAND_STATE_CONTINUE" in helper
        assert "{1, 2, 3, 5}" not in helper

    def test_the_string_enum_is_still_accepted(self) -> None:
        """The three string literals moved out of `_execute_command`.

        They are still accepted, now in coordinator.py's is_lifecycle rule
        (4b's table, row 3). Rewritten to inspect coordinator.py rather than
        deleted -- 4b would go red on a change that is working as designed.
        """
        source = COORDINATOR_PY.read_text()
        for value in STRING_ENUM:
            assert value in source
        execute = inspect.getsource(RivianVehicleControlEntity._execute_command)
        for value in STRING_ENUM:
            assert value not in execute

    async def test_an_unrecognised_string_is_unknown_not_terminal(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """4b's fourth row: unknown string => is_lifecycle is None, and does
        not set terminal_reached.
        """
        coordinator = _coordinator(hass, mock_config_entry)
        coordinator._process_command_state("cmd-1", _frame("SOME_NEW_VALUE"))
        rec = coordinator.get_command_state("cmd-1")
        assert rec["is_lifecycle"] is None
        assert rec["terminal_reached"] is False
        assert rec["frames_seen"] == 1


# --- 8 Scenario 3 -----------------------------------------------------------


class TestAgeInvariantEviction:
    async def test_forty_in_window_entries_are_not_evicted(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry, caplog
    ) -> None:
        """Drive 40 distinct ids, then a second frame for the first.

        Fails an insertion-order bound of 10 and a hard cap of 32. Scenario 3
        rule 1: the age invariant is absolute; 32 is a floor, not a cap.
        """
        coordinator = _coordinator(hass, mock_config_entry)
        with caplog.at_level(logging.WARNING):
            for i in range(40):
                coordinator._process_command_state(f"cmd-{i}", _frame(2))
            coordinator._process_command_state("cmd-0", _frame(2))

        assert len(coordinator._command_states) == 40
        assert coordinator.get_command_state("cmd-0")["frames_seen"] == 2
        assert "in-window entries" in caplog.text


# --- 10b / 10c refresh ------------------------------------------------------


class TestRefreshDoesNotDependOnTerminality:
    async def test_continue_set_frames_refresh_the_listeners(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Three continue-set frames, no terminal -- at least three refreshes,
        plus one more on unsubscribe. Revision 3's trigger would have been
        called zero times, which Scenario 2 argues is the likely production
        case.
        """
        coordinator = _coordinator(hass, mock_config_entry)
        coordinator.async_update_listeners = MagicMock()
        for state in (2, 2, 5):
            coordinator._process_command_state("cmd-1", _frame(state))
        assert coordinator.async_update_listeners.call_count >= 3
        count = coordinator.async_update_listeners.call_count
        await coordinator._unsubscribe_command_state("cmd-1")
        assert coordinator.async_update_listeners.call_count == count + 1

    async def test_end_of_tracking_refresh_fires_on_every_path(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """The refresh lives in _unsubscribe_command_state, which all four
        end-of-tracking paths call: 60 s auto, malformed-frame, string-terminal,
        and async_shutdown.
        """
        import asyncio

        coordinator = _coordinator(hass, mock_config_entry)
        coordinator.api.subscribe_for_command_state = AsyncMock(
            return_value=AsyncMock()
        )
        coordinator.async_update_listeners = MagicMock()

        # Path 1: 60 s auto-unsubscribe.
        real_sleep = asyncio.sleep

        async def instant_sixty(dt):
            if dt == 60:
                return
            await real_sleep(0)

        with patch("asyncio.sleep", instant_sixty):
            await coordinator._subscribe_to_command_state("auto")
            await real_sleep(0)
        assert "auto" not in coordinator._command_state_subscriptions
        assert coordinator.async_update_listeners.call_count >= 1

        # Path 2: malformed (null state) unsubscribe.
        coordinator.async_update_listeners.reset_mock()
        coordinator._process_command_state(
            "malformed",
            {"payload": {"data": {"vehicleCommandState": {"state": None}}}},
        )
        await real_sleep(0)
        coordinator.async_update_listeners.assert_called()

        # Path 3: string-terminal early-unsubscribe.
        coordinator.async_update_listeners.reset_mock()
        coordinator._process_command_state("str-term", _frame("COMPLETED_SUCCESS"))
        await real_sleep(0)
        coordinator.async_update_listeners.assert_called()

        # Path 4: async_shutdown.
        coordinator.async_update_listeners.reset_mock()
        coordinator._command_state_subscriptions["shut"] = AsyncMock()
        coordinator._unsubscribe = AsyncMock()
        await coordinator.async_shutdown()
        coordinator.async_update_listeners.assert_called()


# --- 11 / 12 / 13 / 14 integration ------------------------------------------


class TestRoundTrip:
    async def test_returns_on_the_first_frame_and_settles_on_the_terminal(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        coordinator = _coordinator(hass, mock_config_entry)
        entity = _entity(hass, mock_config_entry, coordinator)
        _deliver_on_send(coordinator, 2)
        clock = _Clock()

        result = await entity._execute_command(
            VehicleCommand.WAKE_VEHICLE, _clock=clock, _sleep=clock.sleep
        )
        assert result["state"] == 2
        assert clock.sleeps == 0

        coordinator._process_command_state("cmd-1", _frame(0))
        attrs = entity.extra_state_attributes
        assert attrs["final_command_state"] == 0
        assert attrs["state_is_lifecycle"] is False
        assert attrs["state_frames_seen"] == 2
        assert entity._last_command_status["state"] == 2

    async def test_ae06ee9_silence_is_now_timeout_with_zero_frames(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Ruling 15: the subscription delivers nothing.

        Before ruling 15 the poll answered and the command completed. Now the
        command must report TIMEOUT with state_frames_seen 0. This encodes the
        accepted risk as an assertion, so a quietly reintroduced fallback goes
        red.
        """
        coordinator = _coordinator(hass, mock_config_entry)
        entity = _entity(hass, mock_config_entry, coordinator)
        coordinator.send_vehicle_command = AsyncMock(return_value="cmd-1")
        clock = _Clock()

        result = await entity._execute_command(
            VehicleCommand.WAKE_VEHICLE, _clock=clock, _sleep=clock.sleep
        )

        assert result is None
        assert entity._last_command_status["state"] == "TIMEOUT"
        assert entity.extra_state_attributes["state_frames_seen"] == 0

    async def test_a_null_state_frame_is_timeout_without_raising(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry, caplog
    ) -> None:
        coordinator = _coordinator(hass, mock_config_entry)
        entity = _entity(hass, mock_config_entry, coordinator)
        with caplog.at_level(logging.WARNING):
            coordinator._process_command_state(
                "cmd-1",
                {"payload": {"data": {"vehicleCommandState": {"state": None}}}},
            )
        coordinator.send_vehicle_command = AsyncMock(return_value="cmd-1")
        clock = _Clock()

        result = await entity._execute_command(
            VehicleCommand.WAKE_VEHICLE, _clock=clock, _sleep=clock.sleep
        )

        assert result is None
        assert entity._last_command_status["state"] == "TIMEOUT"
        assert entity.extra_state_attributes["state_frames_seen"] == 0
        assert "missing or null state" in caplog.text

    async def test_subscribe_raising_does_not_propagate(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        coordinator = _coordinator(hass, mock_config_entry)
        entity = _entity(hass, mock_config_entry, coordinator)
        coordinator.api.subscribe_for_command_state = AsyncMock(
            side_effect=RuntimeError("boom")
        )

        async def send(command, params=None):
            await coordinator._subscribe_to_command_state("cmd-1")
            return "cmd-1"

        coordinator.send_vehicle_command = send
        clock = _Clock()

        result = await entity._execute_command(
            VehicleCommand.WAKE_VEHICLE, _clock=clock, _sleep=clock.sleep
        )
        assert result is None
        assert entity._last_command_status["state"] == "TIMEOUT"


# --- 15 climate chained calls -----------------------------------------------


class TestClimateChainedCalls:
    async def test_three_chained_calls_complete_in_three_first_frame_latencies(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """climate.set_temperature's three chained calls complete in ~3
        first-frame latencies, not ~3 ceilings. The concrete regression
        ruling 22 exists to prevent.
        """
        coordinator = _coordinator(hass, mock_config_entry)
        n = 0

        async def send(command, params=None):
            nonlocal n
            n += 1
            command_id = f"cmd-{n}"
            coordinator._process_command_state(
                command_id, _frame(2, command=command.value)
            )
            return command_id

        coordinator.send_vehicle_command = send
        entity = RivianClimateEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=Mock(key="cabin_climate"),
            vehicle=VEHICLE,
        )
        entity.hass = hass
        entity.async_write_ha_state = MagicMock()

        def values(key):
            if key == "defrostDefogStatus":
                return "On"
            if key == "cabinPreconditioningType":
                return "NONE"
            return None

        entity._get_value = MagicMock(side_effect=values)
        clock = _Clock()

        orig = entity._execute_command

        async def execute(command, params=None, timeout: int = 30, **kwargs):
            kwargs.setdefault("_clock", clock)
            kwargs.setdefault("_sleep", clock.sleep)
            return await orig(command, params, timeout, **kwargs)

        entity._execute_command = execute

        # Live properties couple these: defrost-on forces hvac HEAT, so the
        # three awaits in async_set_temperature are not all taken together.
        # Pin the two conditions independently so the test covers the chain
        # the plan named (climate.py:124, :129, :132).
        with (
            patch.object(
                RivianClimateEntity,
                "preset_mode",
                PropertyMock(return_value=DEFROST_DEFOG),
            ),
            patch.object(
                RivianClimateEntity,
                "hvac_mode",
                PropertyMock(return_value=HVACMode.OFF),
            ),
        ):
            await entity.async_set_temperature(**{ATTR_TEMPERATURE: 22})

        assert n == 3
        assert clock.sleeps == 0
        assert clock.t < 0.5


# --- transcribed continue set -----------------------------------------------


def test_coordinator_continue_set_matches_the_transcription() -> None:
    assert COMMAND_STATE_CONTINUE == TRANSCRIBED_CONTINUE


class TestCeilingInterlockKeysOnTheRightQuantity:
    """f9's ceiling interlock must key on FIRST-FRAME latency, not terminal.

    `entity.py`'s timeout docstring says the wait is for "the first well-formed
    frame", and the loop returns on the first non-empty `get_command_state`. So
    the 30 s ceiling bounds first-frame arrival and bites only at zero frames.

    The interlock previously keyed on a terminal-latency measurement -- a
    leftover from the design where `_execute_command` blocked until terminal,
    which was superseded and never re-derived. A gate outlived its own design.

    It also keyed on a lowercase English phrase that the record was expected to
    reproduce, and survived only because `grep -qF` is case-sensitive. Both
    replacement tokens are shaped so prose will not produce them, and relaxation
    requires the measurement AND a separate owner ratification.
    """

    def test_the_gate_requires_both_tokens(self) -> None:
        gate = (REPO / "scripts/gates/f9.sh").read_text()
        assert "NON-WAKE FIRST-FRAME LATENCY MEASURED:" in gate
        assert "CEILING RATIFIED BY OWNER" in gate

    def test_the_retired_marker_is_absent_from_the_gate(self) -> None:
        """Absent entirely -- quoting it even to explain it satisfies the grep.

        That happened on the first attempt at this change: the explanatory
        comment reintroduced the string and the acceptance criterion caught it.
        """
        gate = (REPO / "scripts/gates/f9.sh").read_text()
        assert "terminal latency measured" not in gate
        assert "terminal latency is unmeasured" not in gate
        assert "DOC_HAS_MEASURED" not in gate

    def test_the_gate_cites_the_docstring_that_fixes_the_quantity(self) -> None:
        """REWRITTEN from an address pin to a QUANTITY pin.

        This used to assert a `file:line` citation appeared in the gate. Adding the
        two ceiling constants above `_execute_command` shifted that line, and an
        address pin does not fail when the address goes stale -- it keeps passing
        while asserting the wrong thing, which is the worst failure mode a gate has.

        The phrase "first well-formed frame" is the governed quantity itself. It is
        already present in both the gate and the docstring it cites, so this is
        satisfiable today; it survives every future line shift; and it fails exactly
        when the quantity being bounded changes, which is what the citation was for.
        """
        gate = (REPO / "scripts/gates/f9.sh").read_text()
        entity = (REPO / "custom_components/rivian/entity.py").read_text()
        assert "first well-formed frame" in gate
        assert "first well-formed frame" in entity

    def test_the_ceiling_is_now_sixty_and_one_twenty(self) -> None:
        """INVERTED from `test_the_ceiling_is_still_thirty`, which pinned 30 s.

        The ceiling is now state-dependent: 60 s awake, 120 s while SLEEPING,
        mirroring the app's CLOUD-path give-up timeouts (`C5332Z.java:242`/`:254`,
        selected at `:821`). It is a RAISE, and the record's rule governs *lowering*
        -- the old pin was a direction-blind fixed string, so it fired anyway.

        What earns each half is not the same. The sleeping ceiling clears the
        record's own 4x-observed-max condition: cold first-frame max 14.66 s
        (`docs/E2E_ACCEPTANCE.md:610`) implies a 58.6 s floor, which 120 s clears and
        30 s did not. The awake raise does NOT come from a measurement -- the awake
        population's max is 2.77 s (`:216-219`), which 30 s already cleared about
        eleven times over. It is an owner decision to mirror the app, and saying so
        is the point: attributing it to the record would be inventing a
        justification the record does not give.

        The *lowering* interlock is untouched: both ratification tokens and the
        relaxation branch stay exactly as armed as before, pinned by
        `test_the_gate_requires_both_tokens`.
        """
        entity = (REPO / "custom_components/rivian/entity.py").read_text()
        assert entity.count("COMMAND_TIMEOUT_AWAKE: Final = 60") == 1
        assert entity.count("COMMAND_TIMEOUT_SLEEPING: Final = 120") == 1
        assert "timeout: int = 30" not in entity

        gate = (REPO / "scripts/gates/f9.sh").read_text()
        assert "COMMAND_TIMEOUT_AWAKE: Final = 60" in gate
        assert "COMMAND_TIMEOUT_SLEEPING: Final = 120" in gate

    def test_the_lowering_interlock_is_still_armed(self) -> None:
        """Re-keying the pin must not have ratified anything.

        `CEILING RATIFIED BY OWNER` means the owner ratified a *lowered* ceiling.
        Nobody did, and writing it would permanently relax the interlock for every
        future change including a genuine lowering. Raising the ceiling required
        editing this gate; it did not require disarming it.
        """
        doc = (REPO / "docs/E2E_ACCEPTANCE.md").read_text()
        assert "CEILING RATIFIED BY OWNER" not in doc


class TestTheCeilingFollowsTheConnectivityState:
    """60 s awake, 120 s while sleeping, and an explicit argument still wins.

    The app selects between two CLOUD-path give-up timeouts on exactly this state
    (`C5332Z.java:821`). Here the quantity is narrower -- the wait for the *first
    well-formed frame* -- but the reason for the split is the same one this change
    creates: the wake is dispatched and never awaited, so on the sleeping path the
    vehicle's wake latency now lands inside the first-frame window rather than in
    front of it.

    Each test drives the loop to exhaustion on a fake clock and asserts which side of
    the boundary the final time lands on, so a resolution wired to the wrong constant
    fails rather than merely running longer.
    """

    async def test_an_awake_vehicle_gets_sixty(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        coordinator = _coordinator(hass, mock_config_entry)
        coordinator._is_online = True
        coordinator.data = {"powerState": "ready"}
        entity = _entity(hass, mock_config_entry, coordinator)
        coordinator.send_vehicle_command = AsyncMock(return_value="cmd-1")
        clock = _Clock()

        await entity._execute_command(
            VehicleCommand.WAKE_VEHICLE, _clock=clock, _sleep=clock.sleep
        )

        assert 60 <= clock.t < 120

    async def test_a_sleeping_vehicle_gets_the_longer_ceiling(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        coordinator = _coordinator(hass, mock_config_entry)
        coordinator._is_online = False
        coordinator.data = {"powerState": "sleep"}
        entity = _entity(hass, mock_config_entry, coordinator)
        coordinator.send_vehicle_command = AsyncMock(return_value="cmd-1")
        clock = _Clock()

        await entity._execute_command(
            VehicleCommand.WAKE_VEHICLE, _clock=clock, _sleep=clock.sleep
        )

        assert 120 <= clock.t < 180

    async def test_an_explicit_timeout_still_wins(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """The seam callers and tests rely on is preserved.

        `timeout` moved from `int = 30` to `int | None = None` rather than being
        removed, so an explicit value -- positional or keyword -- still overrides the
        state-derived default. No production caller passes one today; the wrapper in
        this file's own timeout tests does, positionally.
        """
        coordinator = _coordinator(hass, mock_config_entry)
        coordinator._is_online = False
        coordinator.data = {"powerState": "sleep"}
        entity = _entity(hass, mock_config_entry, coordinator)
        coordinator.send_vehicle_command = AsyncMock(return_value="cmd-1")
        clock = _Clock()

        await entity._execute_command(
            VehicleCommand.WAKE_VEHICLE, None, 10, _clock=clock, _sleep=clock.sleep
        )

        # 10, not the 120 the SLEEPING state would otherwise have selected.
        assert 10 <= clock.t < 60
