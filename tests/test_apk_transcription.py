"""What the Rivian app declares, checked against what this integration does.

`tests/apk/transcription.py` is the data: `VehicleFeature` (64), the `l6e` RVM
table (56), `VASCommand` (57) and `VASCommandKt` (24), transcribed class by class
rather than grepped. Four flat greps preceded it and all four were lossy.

The tests here compare that transcription to the integration. They deliberately
do **not** compare it to the decompiled files -- those are gitignored, so a clean
checkout could not run such a test, and a skipped test is worse than an absent
one. `scripts/gates/f1.sh` does that half, when pre-flight has run.

## The one rule that governs every assertion below

**The app is a lower bound, never the schema.** Three independent measurements
now say so:

  1. `TONNEAU_CMD` gates a cover whose two commands physically move the tonneau,
     and appears in zero of 32,941 decompiled files.
  2. Fifteen `vehicleState` fields we subscribe to appear in zero of them, and
     three carry live data right now.
  3. The server emits **seven** `supportedFeatures` names for this account that
     no `VehicleFeature` member contains (`CHARG_CLEAN_NRG`, `CLM_HOLD_AUTO_VENT`,
     `CONNECT_PLUS`, `PIN_KEY_DRIVE`, `PREMIUM_SPEAKER`, `TRIP_ADD_STOP`,
     `WATCH_GEN1_PAIRING`).

So no test here asserts that something we ship must be present in the app. Where
we exceed the app, that is recorded as a finding, not a failure.
"""

from __future__ import annotations

import inspect
import json
import pathlib
import re

import pytest

from custom_components.rivian.button import BUTTONS
from custom_components.rivian.cover import COVERS
from custom_components.rivian.rivian_client import VehicleCommand
from custom_components.rivian.rivian_client.parallax import RVM_DECODERS

from tests.apk.transcription import (
    COMMAND_STATE_CONTINUE,
    COMMAND_STATE_TERMINAL,
    INVALID_CLOUD_WRAPPER_APP_NAME,
    INVALID_WRAPPER_COMMANDS,
    PARALLAX_REQUEST_ONLY_COMMANDS,
    RVM_NAMES,
    RVM_TOPICS,
    SENDABLE_COMMANDS,
    SENTINEL_COMMAND,
    VAS_COMMAND_KT_CONSTANTS,
    VAS_COMMAND_KT_NAMES,
    VAS_COMMANDS,
    VEHICLE_FEATURE_NAMES,
    VEHICLE_FEATURES,
)

REPO = pathlib.Path(__file__).parents[1]
OBSERVED = REPO / "tests/fixtures/supported_features_observed.json"

# Names the server emitted for this account. Union'd with the app's enum to form
# the set the gate-string lint accepts, because the app's enum is demonstrably
# not the whole vocabulary.
OBSERVED_FEATURE_NAMES = frozenset(
    name
    for vehicle in json.loads(OBSERVED.read_text())["vehicles"]
    for name in vehicle["features"]
)
KNOWN_FEATURE_NAMES = VEHICLE_FEATURE_NAMES | OBSERVED_FEATURE_NAMES

# Commands this integration sends that app 3.15.0 does not name. KEPT, and not
# deprecated: an app-side absence is the weakest of the three signals above.
COMMANDS_ABSENT_FROM_THIS_APK = frozenset(
    {
        "CABIN_HVAC_THIRD_ROW_LEFT_SEAT_HEAT",
        "CABIN_HVAC_THIRD_ROW_RIGHT_SEAT_HEAT",
        "HONK_AND_FLASH_LIGHTS",
        "UNLOCK_ALL_AND_OPEN_WINDOWS",
        "UNLOCK_DRIVER_DOOR",
        "UNLOCK_PASSENGER_DOOR",
        "UNLOCK_USER_PREFERENCES_AND_DISABLE_ALARM",
    }
)


class TestVehicleFeatureTranscription:
    def test_sixty_four_members(self) -> None:
        assert len(VEHICLE_FEATURES) == 64

    def test_members_are_unique(self) -> None:
        members = [m for m, _ in VEHICLE_FEATURES]
        assert len(members) == len(set(members))

    def test_nineteen_members_differ_from_their_feature_name(self) -> None:
        """The count that makes the two-column transcription necessary.

        Gating on a member name where the server emits a featureName silently
        never matches -- a control that is never created, with nothing logged.
        """
        differing = [(m, f) for m, f in VEHICLE_FEATURES if m != f]
        assert len(differing) == 19

    def test_the_charge_port_pair_is_one_of_them(self) -> None:
        """The one this codebase actually depends on getting right."""
        assert ("CHARGE_PORT_DOOR_COMMAND", "CHARG_PORT_DOOR_COMMAND") in (
            VEHICLE_FEATURES
        )

    def test_tonneau_cmd_is_not_a_feature_at_all(self) -> None:
        """Neither a member nor a featureName, in either direction."""
        assert "TONNEAU_CMD" not in VEHICLE_FEATURE_NAMES
        assert "TONNEAU_CMD" not in {m for m, _ in VEHICLE_FEATURES}


class TestGateStringLint:
    """Every capability gate must name something a server actually emits.

    This is the test that would have caught `TONNEAU_CMD` -- a gate string that
    matched nothing, so the control was never created for anyone, silently.

    The deliberately ungated `None` groups are skipped rather than flagged:
    cover.py's frunk and windows and button.py's wake are unconditional on
    purpose, because gating the frunk behind FRUNK_NXT_ACT left vehicles that do
    not advertise the flag with no frunk control at all.
    """

    @staticmethod
    def _gates() -> set[str]:
        return {f for f in COVERS if f is not None} | {
            f for f in BUTTONS if f is not None
        }

    def test_every_gate_string_is_a_name_something_emits(self) -> None:
        unknown = self._gates() - KNOWN_FEATURE_NAMES
        assert not unknown, (
            f"gate strings matching no known capability name: {sorted(unknown)}. "
            "Check the featureName column of VehicleFeature -- 19 of 64 differ "
            "from the member name -- or add it to the observed fixture if the "
            "server emits it."
        )

    def test_no_gate_uses_a_member_name_where_the_feature_name_differs(self) -> None:
        """The specific typo class this lint exists for."""
        member_only = {
            m for m, f in VEHICLE_FEATURES if m != f and f not in {m}
        } - VEHICLE_FEATURE_NAMES
        wrong = self._gates() & member_only
        assert not wrong, (
            f"gates use MEMBER names; the server emits featureNames: {sorted(wrong)}"
        )

    def test_the_ungated_groups_are_skipped_not_flagged(self) -> None:
        assert None in COVERS
        assert None in BUTTONS

    def test_the_current_gates_are_what_we_expect(self) -> None:
        """A whitelist, so a new gate has to come past this test."""
        assert self._gates() == {
            "TAILGATE_CMD",
            "LIFTGATE_CMD",
            "SIDE_BIN_NXT_ACT",
            "CHARG_PORT_DOOR_COMMAND",
        }

    def test_switch_py_is_deliberately_ungated(self) -> None:
        """Recorded as a decision, not left as an oversight.

        switch.py applies no capability filter at all. That is consistent with
        defaulting to keeping a control, and it is why switch.py is out of this
        lint's scope. If it ever grows a gate, this test fails and the gate has to
        be added to the lint above rather than sliding in unchecked.
        """
        source = (REPO / "custom_components/rivian/switch.py").read_text()
        assert "supported_features" not in source


class TestRvmTopicTranscription:
    def test_fifty_six_topics(self) -> None:
        assert len(RVM_TOPICS) == 56

    def test_indices_are_contiguous_from_zero(self) -> None:
        """The assertion that proves the static block was read.

        Five members -- indices 9, 19, 29, 39 and 49 -- are declared bare at the
        top of the class and initialised in a static block, because jadx could not
        restore the enum. Reading only the inline declarations yields 51 entries
        with five gaps, and every gap is a topic that silently does not exist.
        """
        indices = sorted(t["index"] for t in RVM_TOPICS)
        assert indices == list(range(56))

    @pytest.mark.parametrize("index", [9, 19, 29, 39, 49])
    def test_each_static_block_member_is_present(self, index: int) -> None:
        (topic,) = [t for t in RVM_TOPICS if t["index"] == index]
        assert topic["rvm_name"]

    def test_rvm_names_are_unique(self) -> None:
        assert len({t["rvm_name"] for t in RVM_TOPICS}) == 56

    def test_subscription_scope_defaults_to_app_not_none(self) -> None:
        """`null` in the scope position means fug.App.

        The synthetic constructor substitutes `fug.App` when the default-argument
        mask has bit 4 set. Transcribing the literal would record 55 nulls and
        lose the single entry that actually differs.
        """
        assert {t["subscription_scope"] for t in RVM_TOPICS} == {"App", "Feature"}
        feature_scoped = [
            t["member"] for t in RVM_TOPICS if t["subscription_scope"] == "Feature"
        ]
        assert feature_scoped == ["DYNAMICS_TIRES_STATE"]

    def test_climate_hold_status_is_the_only_double_consumer_topic(self) -> None:
        """f5 has to honour this; recording it here is what makes that checkable."""
        doubled = [
            t["member"] for t in RVM_TOPICS if t["need_double_consumer_subscription"]
        ]
        assert doubled == ["CLIMATE_HOLD_STATUS"]

    def test_every_decoder_we_ship_decodes_a_topic_the_app_names(self) -> None:
        """One-directional on purpose.

        A decoder for a topic the app does not name would be worth investigating,
        not deleting -- but there are none, so the assertion is free. The reverse
        direction is NOT asserted: 38 topics the app names have no decoder here,
        and that is f5's work queue, not a failure.
        """
        assert set(RVM_DECODERS) <= RVM_NAMES

    def test_the_undecoded_remainder_shrank_by_exactly_what_f5_transcribed(
        self,
    ) -> None:
        """38 when f1 measured it. f5 transcribed 14 from the app's protobuf
        classes, and vehicle.network.state was added afterwards on an inference
        rather than a read binding (see TestNetworkState), so 23 remain. Pinned
        rather than left as "fewer", so adding or losing a decoder is a deliberate
        diff."""
        assert len(RVM_NAMES - set(RVM_DECODERS)) == 23
        assert len(RVM_DECODERS) == 33

    def test_the_two_already_decoded_topics_are_not_mistaken_for_candidates(
        self,
    ) -> None:
        """Naming these in f5's queue would send someone to rewrite working code."""
        for name in ("dynamics.tires.state", "vehicle.wheels.vehicle_wheels"):
            assert name in RVM_DECODERS


class TestVasCommandTranscription:
    def test_fifty_seven_subclasses(self) -> None:
        assert len(VAS_COMMANDS) == 57

    def test_fifty_three_carry_a_literal_command_name(self) -> None:
        assert sum(1 for v in VAS_COMMANDS if v["command"]) == 53

    def test_forty_five_are_sendable(self) -> None:
        """Sendable is defined, not assumed.

        46 subclasses build cloudData through generateCloudDataWrapper; one of
        those is the INVALID_COMMAND sentinel, which is not a command anyone
        sends. 46 - 1 = 45.
        """
        assert len(SENDABLE_COMMANDS) == 45
        assert SENTINEL_COMMAND not in SENDABLE_COMMANDS

    def test_seven_use_the_invalid_wrapper(self) -> None:
        """Seven, not eight and not nine.

        An earlier extraction bounded each subclass at the next `extends
        VASCommand`, which swallowed the Companion class -- whose body DEFINES
        generateInvalidCloudDataWrapper -- and so misread CloseTonneauCover as
        invalid-wrapped. That is one of the two commands proven to physically move
        the tonneau.
        """
        assert INVALID_WRAPPER_COMMANDS == {
            "PET_COMFORT_OFF",
            "PET_COMFORT_ON",
            "START_VIDEO_DOWNLOADING_SESSION",
            "TWO_FACTOR_DRIVE_ALLOW",
            "TWO_FACTOR_DRIVE_DENY",
            "TWO_FACTOR_DRIVE_DISABLE",
            "TWO_FACTOR_DRIVE_ENABLE",
        }

    def test_both_tonneau_commands_use_the_ordinary_cloud_wrapper(self) -> None:
        """The pair the live test moved the cover with."""
        assert "OPEN_TONNEAU_COVER" in SENDABLE_COMMANDS
        assert "CLOSE_TONNEAU_COVER" in SENDABLE_COMMANDS

    def test_the_four_wrapperless_subclasses(self) -> None:
        assert {v["cls"] for v in VAS_COMMANDS if v["wrapper"] is None} == {
            "ParallaxCommand",
            "PauseFrunk",
            "PauseLiftgate",
            "PauseTonneauCover",
        }


class TestVasCommandKtTranscription:
    def test_twenty_four_constants(self) -> None:
        assert len(VAS_COMMAND_KT_CONSTANTS) == 24

    def test_eighteen_are_command_names(self) -> None:
        assert len(VAS_COMMAND_KT_NAMES) == 18

    def test_the_third_row_spellings_exist(self) -> None:
        """f2 adds these ALONGSIDE the existing THIRD_ROW spelling, not instead."""
        assert "CABIN_HVAC_3RD_ROW_REAR_LEFT_SEAT_HEAT" in VAS_COMMAND_KT_NAMES
        assert "CABIN_HVAC_3RD_ROW_REAR_RIGHT_SEAT_HEAT" in VAS_COMMAND_KT_NAMES


class TestWhatWeShipVersusWhatTheAppNames:
    """The comparison, stated as findings rather than as pass/fail on our side."""

    def test_the_commands_absent_from_this_apk_are_exactly_the_recorded_seven(
        self,
    ) -> None:
        """They STAY. An app-side absence is not a live failure."""
        app_names = {v["command"] for v in VAS_COMMANDS if v["command"]}
        ours = {c.value for c in VehicleCommand}
        assert ours - app_names == COMMANDS_ABSENT_FROM_THIS_APK

    def test_every_sendable_command_the_app_declares_is_in_our_enum(self) -> None:
        """f6 closed the queue. f2 added the 3RD_ROW pair; f6 added OPEN_LIFTGATE,
        OPEN_TAILGATE and START_GEAR_GUARD_MASTER_SESSION."""
        ours = {c.value for c in VehicleCommand}
        assert not SENDABLE_COMMANDS - ours

    def test_being_in_the_enum_is_not_the_same_as_being_wired(self) -> None:
        """A distinction f6 turns on.

        The four third-row commands exist as enum members and back no entity. That
        is deliberate: which spelling a given vehicle accepts is a live question,
        and wiring both blind is how eleven dead controls were shipped before.
        """
        # Entity tables reach VehicleCommand through lambdas, so membership is
        # read from the platform sources rather than from a `command` attribute.
        platforms = "".join(
            (REPO / "custom_components/rivian" / name).read_text()
            for name in (
                "select.py",
                "switch.py",
                "button.py",
                "cover.py",
                "number.py",
                "climate.py",
                "lock.py",
            )
        )
        for unwired in (
            "CABIN_HVAC_THIRD_ROW_LEFT_SEAT_HEAT",
            "CABIN_HVAC_THIRD_ROW_RIGHT_SEAT_HEAT",
            "CABIN_HVAC_3RD_ROW_REAR_LEFT_SEAT_HEAT",
            "CABIN_HVAC_3RD_ROW_REAR_RIGHT_SEAT_HEAT",
        ):
            assert unwired in {c.value for c in VehicleCommand}
            assert unwired not in platforms, f"{unwired} is now wired -- see f6"

    def test_the_invalid_wrapper_seven_are_members_and_wired_to_nothing(self) -> None:
        """INVERTED by owner ruling 11 (2026-08-19). Until then this asserted
        the seven were absent from the enum. They are members so f7 can send
        them; they back no entity -- wiring them blind is the defect that
        shipped eleven dead controls once.
        """
        ours = {c.value for c in VehicleCommand}
        assert INVALID_WRAPPER_COMMANDS <= ours
        platforms = "".join(
            (REPO / "custom_components/rivian" / name).read_text()
            for name in (
                "select.py",
                "switch.py",
                "button.py",
                "cover.py",
                "number.py",
                "climate.py",
                "lock.py",
            )
        )
        for command in sorted(INVALID_WRAPPER_COMMANDS):
            assert command not in platforms, f"{command} is now wired -- see f6"


class TestObservedCapabilities:
    def test_the_fixture_carries_no_vin(self) -> None:
        """A VIN in a public repository is exposure with no benefit."""
        text = OBSERVED.read_text()
        assert not re.search(r"\b[A-HJ-NPR-Z0-9]{17}\b", text)

    def test_the_server_emits_names_the_app_enum_does_not_contain(self) -> None:
        """The third independent measurement that the app is a lower bound.

        If this ever becomes empty, the claim weakens and the reasoning in this
        module's docstring needs revisiting -- so it is asserted, not narrated.
        """
        extra = OBSERVED_FEATURE_NAMES - VEHICLE_FEATURE_NAMES
        assert extra == {
            "CHARG_CLEAN_NRG",
            "CLM_HOLD_AUTO_VENT",
            "CONNECT_PLUS",
            "PIN_KEY_DRIVE",
            "PREMIUM_SPEAKER",
            "TRIP_ADD_STOP",
            "WATCH_GEN1_PAIRING",
        }

    def test_tonneau_cmd_is_emitted_by_nobody(self) -> None:
        """And the cover works anyway. This is the whole argument, in one line."""
        assert "TONNEAU_CMD" not in OBSERVED_FEATURE_NAMES

    def test_the_matrix_is_committed(self) -> None:
        matrix = REPO / "docs/development/CAPABILITY_MATRIX.md"
        assert matrix.is_file()
        text = matrix.read_text()
        assert "TONNEAU_CMD" in text
        assert "CHARG_PORT_DOOR_COMMAND" in text


class TestUnpopulatedFields:
    """The five fields the server accepts and never fills. All five stay.

    See docs/development/UNPOPULATED_FIELDS.md for the recorded finding behind
    each. "Never carried a value" is silence, not a live failure, and silence is
    exactly what the tonneau cover falsified.
    """

    VALIDITY_FIELDS = (
        "tirePressureStatusValidFrontLeft",
        "tirePressureStatusValidFrontRight",
        "tirePressureStatusValidRearLeft",
        "tirePressureStatusValidRearRight",
    )

    def test_all_five_are_still_subscribed(self) -> None:
        from custom_components.rivian.const import VEHICLE_STATE_API_FIELDS

        for field in (*self.VALIDITY_FIELDS, "cabinHoldNotification"):
            assert field in VEHICLE_STATE_API_FIELDS, field

    def test_none_of_them_is_named_by_the_app(self) -> None:
        """Which is why each needed a recorded finding rather than a deletion."""
        app_fields = {v["command"] for v in VAS_COMMANDS if v["command"]} | RVM_NAMES
        for field in (*self.VALIDITY_FIELDS, "cabinHoldNotification"):
            assert field not in app_fields

    def test_no_offline_candidate_exists_for_the_validity_fields(self) -> None:
        """There is no aggregate to adopt. An earlier draft said there was.

        `tirePressureState` is the OPERATION NAME of apj.java's subscription, not
        a field it selects, and it appears nowhere else except two retired flat
        extracts. Parsing the selection set shows apj selects exactly eight tire
        fields: the four pressures and the four statuses. No validity field, no
        aggregate.

        It was briefly adopted on that misreading and reverted before anything
        shipped. Subscribing to a name the server does not know takes the ENTIRE
        subscription down -- that is what wheelsInstalled did -- so this asserts
        the absence rather than leaving it to a comment.
        """
        from custom_components.rivian.const import VEHICLE_STATE_API_FIELDS

        for field in (
            "tirePressureStatusFrontLeft",
            "tirePressureStatusFrontRight",
            "tirePressureStatusRearLeft",
            "tirePressureStatusRearRight",
        ):
            assert field in VEHICLE_STATE_API_FIELDS
        assert "tirePressureState" not in VEHICLE_STATE_API_FIELDS

    def test_each_field_has_a_recorded_finding(self) -> None:
        doc = REPO / "docs/development/UNPOPULATED_FIELDS.md"
        assert doc.is_file()
        text = doc.read_text()
        for field in (*self.VALIDITY_FIELDS[:1], "cabinHoldNotification"):
            assert field in text
        assert "tirePressureState" in text
        assert "Left in place" in text

    def test_both_third_row_spellings_exist_side_by_side(self) -> None:
        """Added alongside, never renamed. The older spelling may serve older
        firmware, and an app-side absence is the weakest evidence there is."""
        ours = {c.value for c in VehicleCommand}
        assert "CABIN_HVAC_THIRD_ROW_LEFT_SEAT_HEAT" in ours
        assert "CABIN_HVAC_THIRD_ROW_RIGHT_SEAT_HEAT" in ours
        assert "CABIN_HVAC_3RD_ROW_REAR_LEFT_SEAT_HEAT" in ours
        assert "CABIN_HVAC_3RD_ROW_REAR_RIGHT_SEAT_HEAT" in ours


class TestCommandCoverage:
    """f6: every sendable command is in the enum, and the rest are recorded.

    See docs/development/COMMAND_COVERAGE.md.
    """

    def test_the_two_new_closure_openers_are_wired(self) -> None:
        from custom_components.rivian.button import BUTTONS

        keys = {d.key for group in BUTTONS.values() for d in group}
        assert {"open_tailgate", "open_liftgate"} <= keys

    def test_both_ship_disabled_by_default(self) -> None:
        """They move a closure and have not been actuated on the vehicle.

        f7 does that. Shipping an untested opener enabled puts it one tap away.
        """
        from custom_components.rivian.button import BUTTONS

        for group in BUTTONS.values():
            for description in group:
                if description.key in ("open_tailgate", "open_liftgate"):
                    assert description.entity_registry_enabled_default is False

    def test_the_dedicated_commands_are_distinct_from_the_combined_one(self) -> None:
        """OPEN_LIFTGATE_UNLATCH_TAILGATE does both; these do one each."""
        from custom_components.rivian.button import BUTTONS

        by_key = {d.key: d for group in BUTTONS.values() for d in group}
        assert by_key["open_tailgate"].command == VehicleCommand.OPEN_TAILGATE
        assert by_key["open_liftgate"].command == VehicleCommand.OPEN_LIFTGATE
        assert (
            by_key["drop_tailgate"].command
            == VehicleCommand.OPEN_LIFTGATE_UNLATCH_TAILGATE
        )

    def test_both_have_a_translation(self) -> None:
        translations = json.loads(
            (REPO / "custom_components/rivian/translations/en.json").read_text()
        )
        buttons = translations["entity"]["button"]
        assert buttons["open_tailgate"]["name"] == "Open Tailgate"
        assert buttons["open_liftgate"]["name"] == "Open Liftgate"

    def test_start_gear_guard_master_session_is_declared_but_unwired(self) -> None:
        """A streaming feature, not a control. Declared so the name is recorded."""
        ours = {c.value for c in VehicleCommand}
        assert "START_GEAR_GUARD_MASTER_SESSION" in ours
        platforms = "".join(
            (REPO / "custom_components/rivian" / name).read_text()
            for name in ("button.py", "switch.py", "select.py", "cover.py", "number.py")
        )
        assert "START_GEAR_GUARD_MASTER_SESSION" not in platforms

    def test_the_invalid_wrapper_seven_are_still_unwired(self) -> None:
        """INVERTED by owner ruling 11 (2026-08-19). Name kept: f6.sh lists it.
        "Still unwired" is the surviving half -- they are members so f7 can
        send them, and they back no entity.
        """
        ours = {c.value for c in VehicleCommand}
        assert INVALID_WRAPPER_COMMANDS <= ours
        platforms = "".join(
            (REPO / "custom_components/rivian" / name).read_text()
            for name in (
                "select.py",
                "switch.py",
                "button.py",
                "cover.py",
                "number.py",
                "climate.py",
                "lock.py",
            )
        )
        for command in sorted(INVALID_WRAPPER_COMMANDS):
            assert command not in platforms, f"{command} is now wired -- see f6"

    def test_the_seven_apk_absent_commands_are_still_here(self) -> None:
        """Kept. Stamping a dated "deprecated" note on a working command writes
        false provenance and defeats the next person's instinct to re-check."""
        ours = {c.value for c in VehicleCommand}
        assert COMMANDS_ABSENT_FROM_THIS_APK <= ours

    def test_the_coverage_decisions_are_written_down(self) -> None:
        doc = REPO / "docs/development/COMMAND_COVERAGE.md"
        assert doc.is_file()
        text = doc.read_text()
        for command in sorted(INVALID_WRAPPER_COMMANDS):
            assert command in text, command
        for command in sorted(COMMANDS_ABSENT_FROM_THIS_APK):
            assert command in text, command
        assert "START_GEAR_GUARD_MASTER_SESSION" in text


class TestCommandStateVocabulary:
    """§7 test 10: the transcribed integer sets, and where they are consumed."""

    def test_continue_and_terminal_are_disjoint_and_cover_zero_to_seven(self) -> None:
        assert not COMMAND_STATE_CONTINUE & COMMAND_STATE_TERMINAL
        assert COMMAND_STATE_CONTINUE | COMMAND_STATE_TERMINAL == frozenset(range(8))

    def test_coordinator_imports_the_continue_set_by_name(self) -> None:
        """The transcription is the source of truth; coordinator.py must not
        restated the literal inside the consumer. Production cannot import
        tests/, so the name is defined in coordinator.py and asserted equal.
        """
        from custom_components.rivian.coordinator import (
            COMMAND_STATE_CONTINUE as used,
            _command_state_is_lifecycle,
        )

        assert used == COMMAND_STATE_CONTINUE
        source = inspect.getsource(_command_state_is_lifecycle)
        assert "COMMAND_STATE_CONTINUE" in source
        assert "{1, 2, 3, 5}" not in source

    def test_entity_contains_no_terminality_vocabulary(self) -> None:
        source = (REPO / "custom_components/rivian/entity.py").read_text()
        assert "COMMAND_STATE_CONTINUE" not in source
        assert "isinstance(state, int) or state in" not in source

    def test_parallax_request_only_is_two_of_the_invalid_wrapper_seven(self) -> None:
        assert PARALLAX_REQUEST_ONLY_COMMANDS <= INVALID_WRAPPER_COMMANDS
        assert len(PARALLAX_REQUEST_ONLY_COMMANDS) == 2

    def test_our_client_never_sends_app_name(self) -> None:
        """N8: the two wrappers differ in appName alone, a field we never send."""
        hits = []
        root = REPO / "custom_components/rivian"
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if "appName" in path.read_text():
                hits.append(str(path.relative_to(REPO)))
        assert not hits
        assert INVALID_CLOUD_WRAPPER_APP_NAME == ""
