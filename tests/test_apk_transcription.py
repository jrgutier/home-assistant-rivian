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
    HONK_FLASH_GATE_EVALUATOR,
    HONK_FLASH_GATE_FIRST_SEEN,
    HONK_FLASH_GATE_ROLLOUT_FLAG,
    HONK_FLASH_GATE_UNAVAILABLE_ARM,
    HONK_FLASH_GATE_VEHICLE_FEATURE,
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

# featureNames present as a VehicleFeature member in the decompiled TREE
# (com.rivian.android.consumer/java_src/.../VehicleFeature.java, app 3.6.0,
# versionCode 3989 per apktool.yml) that do NOT appear anywhere in
# VEHICLE_FEATURE_NAMES -- the 3.15.0 TRANSCRIPTION. 60 members in the tree, 64
# in the transcription, 15 withdrawn. This is a documentary assertion, not the
# lint itself (see TestGateStringsUseOnlyTheCurrentVocabulary below): it exists
# so a reader can see the finding without reconstructing the diff, and so it
# fails loudly if someone regenerates the transcription without accounting for
# the skew.
#
# Two of the 15 are, confusingly, still emitted by the live server today:
# CLM_HOLD_AUTO_VENT and PREMIUM_SPEAKER both appear in
# tests/fixtures/supported_features_observed.json (see the seven names listed
# in this module's docstring). Server presence is NOT evidence a name is a
# safe gate -- it only says the *feature* exists, not that this build of the
# app has any control wired to it. That is the same asymmetry as TONNEAU_CMD
# in reverse: absence from the app didn't prove the tonneau command was dead,
# and presence on the server doesn't prove a withdrawn gate is safe to revive.
WITHDRAWN_IN_3_15_0 = frozenset(
    {
        "ADDR_SHR",
        "CHARG_CMD",
        "CHARG_SCHED",
        "CLM_HOLD_AUTO_VENT",
        "FRUNK_NXT_ACT",
        "HEATED_SEATS",
        "HEATED_WHEEL",
        "PRECON_CMD_RESP",
        "PRECON_SCRN_PROT",
        "PREMIUM_SPEAKER",
        "RENAME_VEHICLE",
        "SET_TEMP_CMD",
        "TRIP_PLANNER",
        "VENTED_SEATS",
        "WIN_NXT_ACT",
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
    cover.py's frunk and button.py's wake are unconditional on purpose, because
    gating the frunk behind FRUNK_NXT_ACT left vehicles that do not advertise
    the flag with no frunk control at all. windows is gated on WINDOWS_CMD.
    """

    @staticmethod
    def _gates() -> set[str]:
        from custom_components.rivian.const import BINARY_SENSORS, SENSORS
        from custom_components.rivian.select import SELECTS

        gates = {f for f in COVERS if f is not None} | {
            f for f in BUTTONS if f is not None
        }
        for collection in (SENSORS, BINARY_SENSORS, SELECTS):
            for description in collection:
                feat = getattr(description, "feature", None)
                if feat is None:
                    continue
                if isinstance(feat, str):
                    gates.add(feat)
                else:
                    gates.update(feat)
        return gates

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
            "WINDOWS_CMD",
            "TAILGATE_NXT_ACT",
            "HEATED_SEATS_THIRD",
        }

    def test_no_cover_or_button_has_both_a_dict_key_and_option_code(self) -> None:
        """tonneau in COVERS[None] + option_code is allowed; a keyed group is not."""
        dual = []
        for collection in (COVERS, BUTTONS):
            for feature, descriptions in collection.items():
                if feature is None:
                    continue
                for description in descriptions:
                    if getattr(description, "option_code", None) is not None:
                        dual.append((feature, description.key, description.option_code))
        assert not dual

    def test_switch_py_is_deliberately_ungated(self) -> None:
        """Recorded as a decision, not left as an oversight.

        switch.py applies no capability filter at all. That is consistent with
        defaulting to keeping a control, and it is why switch.py is out of this
        lint's scope. If it ever grows a gate, this test fails and the gate has to
        be added to the lint above rather than sliding in unchecked.
        """
        source = (REPO / "custom_components/rivian/switch.py").read_text()
        assert "supported_features" not in source


class TestGateStringsUseOnlyTheCurrentVocabulary:
    """`TestGateStringLint` above only asks that a gate name SOMETHING -- the
    union of the 3.15.0 transcription and the observed fixture. That union is
    too permissive for one specific mistake: gating a NEW control on a
    `VehicleFeature` member that the app withdrew between 3.6.0 and 3.15.0.

    Three facts, or this test will be misread later:

    1. The decompiled TREE (`com.rivian.android.consumer/`) is app 3.6.0,
       versionCode 3989 (`apktool.yml`). The TRANSCRIPTION
       (`tests/apk/transcription.py`, `VEHICLE_FEATURE_NAMES`) is app 3.15.0,
       64 members. The tree has 60, 15 of which do not appear in the
       transcription at all -- `WITHDRAWN_IN_3_15_0` above. The lint below
       exists BECAUSE of that skew: finding 2 established that the tree is
       control-flow evidence only, and the transcription -- not the tree, and
       not the observed fixture -- is the vocabulary a new gate must be drawn
       from.
    2. Gating on a withdrawn name reproduces the `TONNEAU_CMD` failure: a
       control that exists for nobody, because nothing this build of the app
       can send ever sets that flag, with nothing logged to say why.
    3. `CLM_HOLD_AUTO_VENT` and `PREMIUM_SPEAKER` -- two of the 15 withdrawn
       names -- are STILL emitted by the live server today (they are 2 of the
       7 names in `OBSERVED_FEATURE_NAMES` that `VEHICLE_FEATURE_NAMES` does
       not contain; see this module's docstring). Server presence is not
       evidence a withdrawn name is a safe gate to revive -- it says the
       *feature* still exists, not that this app build has any control wired
       to it. That is the same asymmetry as `TONNEAU_CMD` in reverse, and it
       is why the rule below is stated against the TRANSCRIPTION alone, not
       `KNOWN_FEATURE_NAMES`.

    The positive form subsumes the 15-name blocklist and needs no maintenance:
    it also catches the 16th name Rivian withdraws next release, which a
    hardcoded list never would.
    """

    def test_every_gate_string_is_in_the_current_transcription(self) -> None:
        stale = TestGateStringLint._gates() - VEHICLE_FEATURE_NAMES
        assert not stale, (
            f"gate strings not in the 3.15.0 transcription: {sorted(stale)}. "
            "A name that only the observed fixture or the 3.6.0 tree knows "
            "about is not safe to gate a NEW control on -- see this class's "
            "docstring."
        )

    def test_the_documentary_withdrawn_set_matches_the_actual_skew(self) -> None:
        """Proves WITHDRAWN_IN_3_15_0 isn't stale prose: every name in it is
        genuinely absent from the transcription, and the count is exactly 15."""
        assert len(WITHDRAWN_IN_3_15_0) == 15
        assert WITHDRAWN_IN_3_15_0.isdisjoint(VEHICLE_FEATURE_NAMES)

    def test_no_current_gate_names_a_withdrawn_feature(self) -> None:
        """The 15-name form of the same rule, kept as the documentary,
        directly-legible assertion described in this class's docstring."""
        withdrawn_gates = TestGateStringLint._gates() & WITHDRAWN_IN_3_15_0
        assert not withdrawn_gates, (
            f"gate strings name a feature app 3.6.0 had and 3.15.0 dropped: "
            f"{sorted(withdrawn_gates)}. This is the TONNEAU_CMD failure mode: "
            "a control that exists for nobody, with nothing logged."
        )


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
        # 23 and 33 before s34, which shipped four decoders written from the
        # named .proto schemas in rivian_client/proto/, each verified against a
        # captured frame rather than against the parse succeeding.
        assert len(RVM_NAMES - set(RVM_DECODERS)) == 19
        assert len(RVM_DECODERS) == 37

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

        The 3RD_ROW pair is wired to the HEATED_SEATS_THIRD selects. The
        THIRD_ROW spelling stays unwired: which spelling a given vehicle
        accepts was the live question, and wiring both blind is how eleven
        dead controls were shipped before.
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
                "camera.py",
            )
        )
        ours = {c.value for c in VehicleCommand}
        for wired in (
            "CABIN_HVAC_3RD_ROW_REAR_LEFT_SEAT_HEAT",
            "CABIN_HVAC_3RD_ROW_REAR_RIGHT_SEAT_HEAT",
        ):
            assert wired in ours
            assert wired in platforms, f"{wired} should back the third-row selects"
        for unwired in (
            "CABIN_HVAC_THIRD_ROW_LEFT_SEAT_HEAT",
            "CABIN_HVAC_THIRD_ROW_RIGHT_SEAT_HEAT",
        ):
            assert unwired in ours
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
                "camera.py",
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


class TestHonkAndFlashGate:
    """Why FLASH_EXTERNAL_LIGHTS is accepted by the gateway and does nothing.

    The measurement is in COMMAND_COVERAGE.md; the cause is a conjunction the app
    evaluates before it offers the button. The decompiled classes are gitignored,
    so the claim is asserted here rather than living only in a doc citation.
    """

    def test_the_app_knows_the_vehicle_flag(self) -> None:
        """If the app did not name it, the gate reading would be wrong."""
        assert HONK_FLASH_GATE_VEHICLE_FEATURE in VEHICLE_FEATURE_NAMES

    def test_no_vehicle_in_evidence_carries_the_vehicle_flag(self) -> None:
        """Four vehicles, four absences -- but only two of them are datable.

        issue-171 (2024-08-08) and issue-222 (2025-08-26) cannot be placed
        against the flag's 2.19.1 first sighting, because the corpus carries no
        release dates. They are asserted here for completeness; the CLAIM rests
        on issue-245 and this truck, both comfortably post-flag.
        """
        assert HONK_FLASH_GATE_VEHICLE_FEATURE not in OBSERVED_FEATURE_NAMES

        community = REPO / "tests/fixtures/community"
        seen = 0
        for name in ("issue-171.json", "issue-222.json", "issue-245.json"):
            path = community / name
            assert path.is_file(), name
            assert HONK_FLASH_GATE_VEHICLE_FEATURE not in path.read_text(), name
            seen += 1
        assert seen == 3

    def test_the_rollout_flag_is_old_and_the_vehicle_flag_is_not(self) -> None:
        """The two halves of the gate have different histories.

        The rollout flag is not the new thing -- it predates the command by a
        long way, so "behind a rollout" cannot rest on the flag being recent.
        """
        first = HONK_FLASH_GATE_FIRST_SEEN
        assert first[HONK_FLASH_GATE_ROLLOUT_FLAG] == "1.5.1"
        assert first[HONK_FLASH_GATE_VEHICLE_FEATURE] == "2.19.1"

    def test_the_vehicle_flag_first_appears_with_the_command(self) -> None:
        """Cross-check against a span this repo recorded independently."""
        sweep = (REPO / "docs/development/APK_HISTORICAL_SWEEP.md").read_text()
        row = next(
            line
            for line in sweep.splitlines()
            if line.startswith("| `FLASH_EXTERNAL_LIGHTS`")
        )
        assert HONK_FLASH_GATE_FIRST_SEEN[HONK_FLASH_GATE_VEHICLE_FEATURE] in row

    def test_the_unavailable_arm_is_recorded(self) -> None:
        """A named not-available arm makes a withheld button a designed state."""
        assert HONK_FLASH_GATE_UNAVAILABLE_ARM.endswith("NOT_AVAILABLE")
        assert HONK_FLASH_GATE_EVALUATOR == ("as7.a", "as7.b")

    def test_the_finding_is_recorded_where_a_reader_will_look(self) -> None:
        coverage = (REPO / "docs/development/COMMAND_COVERAGE.md").read_text()
        assert HONK_FLASH_GATE_UNAVAILABLE_ARM in coverage
        # Normalised: the doc is hard-wrapped, so the phrase spans a newline.
        flat = " ".join(coverage.lower().replace("**", "").split())
        assert "per-vin exclusion is unproven" in flat

        gaps = (REPO / "docs/development/REMAINING_APK_GAPS.md").read_text()
        assert HONK_FLASH_GATE_VEHICLE_FEATURE in gaps
        assert "supportedFeatures" in gaps


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

    def test_the_validity_fields_ride_the_tpms_document_not_the_main_one(
        self,
    ) -> None:
        """The split is invisible to `test_all_five_are_still_subscribed` above:
        VEHICLE_STATE_API_FIELDS (149) is the UNION of two documents and is
        never itself sent on the wire, so all four validity fields staying in
        that union proves nothing about which actual document they ride. The
        wire symbols are VEHICLE_STATE_SUBSCRIPTION_FIELDS (137, the main
        document) and TIRE_PRESSURE_SUBSCRIPTION_FIELDS (12, the TPMS
        document) -- and the four tirePressureStatusValid* fields belong to
        the SECOND one. Without this, folding TPMS back into the main
        document (or the reverse) would leave every assertion in this class
        green."""
        from custom_components.rivian.const import (
            TIRE_PRESSURE_SUBSCRIPTION_FIELDS,
            VEHICLE_STATE_SUBSCRIPTION_FIELDS,
        )

        for field in self.VALIDITY_FIELDS:
            assert field in TIRE_PRESSURE_SUBSCRIPTION_FIELDS, field
            assert field not in VEHICLE_STATE_SUBSCRIPTION_FIELDS, field

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

        This has NOT been superseded by the TPMS split, and reads as if it might
        be: `subscribe_for_tire_pressure_updates` (rivian_client/rivian.py) now
        sends `"tirePressureState"` as the GraphQL `operationName` for our own
        TPMS subscription -- we adopted the OPERATION, deliberately, because
        that is what the app itself does. The assertion below is about
        something else entirely: whether `"tirePressureState"` is a FIELD name
        inside a selection set. It is not, on the app's side or ours, and never
        should be -- adopting the operation name changes nothing about that. Two
        different questions, one string; do not read this as stale because the
        operation got adopted.
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
        """Wired on camera.py (s28), not as a control button/switch/cover."""
        ours = {c.value for c in VehicleCommand}
        assert "START_GEAR_GUARD_MASTER_SESSION" in ours
        platforms = "".join(
            (REPO / "custom_components/rivian" / name).read_text()
            for name in ("button.py", "switch.py", "select.py", "cover.py", "number.py")
        )
        assert "START_GEAR_GUARD_MASTER_SESSION" not in platforms
        camera = (REPO / "custom_components/rivian/camera.py").read_text()
        assert "VehicleCommand.START_GEAR_GUARD_MASTER_SESSION" in camera

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
                "camera.py",
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


class TestGearGuardLiveConfigQuery:
    """The live-stream signaling subscription is the APK document, not a guess."""

    def test_query_matches_apk_dj8(self) -> None:
        from custom_components.rivian.rivian_client.rivian import (
            GEAR_GUARD_LIVE_CONFIG_QUERY,
        )

        # 3.15.0 defpackage/dj8.java:19
        assert GEAR_GUARD_LIVE_CONFIG_QUERY == (
            "subscription gearGuardRemoteConfig($vehicleId: String!, "
            "$commandId: String!) { gearGuardLiveConfig(vehicleId: $vehicleId, "
            "commandId: $commandId) { endpoint channelArn role iceServers { "
            "url username credential ttl } } }"
        )


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


class TestParallaxEnvelopeDerivation:
    """Step 5: the envelope is not derivable. These lock the negative so a
    guessed RVM cannot land as a silent fill-in of the transcription."""

    def test_no_rvm_is_bound_to_any_invalid_wrapper_command(self) -> None:
        from tests.apk.transcription import INVALID_WRAPPER_COMMAND_RVMS

        assert set(INVALID_WRAPPER_COMMAND_RVMS) == INVALID_WRAPPER_COMMANDS
        assert all(v is None for v in INVALID_WRAPPER_COMMAND_RVMS.values())

    def test_parallax_command_is_a_received_model(self) -> None:
        from tests.apk.transcription import PARALLAX_COMMAND_CONSTRUCTOR_FIELDS

        assert "commandId" in PARALLAX_COMMAND_CONSTRUCTOR_FIELDS
        assert "createdAt" in PARALLAX_COMMAND_CONSTRUCTOR_FIELDS
        assert PARALLAX_COMMAND_CONSTRUCTOR_FIELDS[0] == "commandId"
        assert PARALLAX_COMMAND_CONSTRUCTOR_FIELDS[1] == "createdAt"

    def test_the_3_15_0_accessor_is_getPxCmdName_not_getName(self) -> None:
        """N5: the 3.15.0 artifact calls getPxCmdName; the 3.6.0 class has
        getName. Recording both, labelled, is what stops a mapping across them.
        """
        from tests.apk.transcription import (
            PARALLAX_ATTRIBUTES_NAME_ACCESSOR_360_CONTEXT,
            PARALLAX_ATTRIBUTES_NAME_ACCESSOR_3150,
        )

        assert PARALLAX_ATTRIBUTES_NAME_ACCESSOR_3150 == "getPxCmdName"
        assert PARALLAX_ATTRIBUTES_NAME_ACCESSOR_360_CONTEXT == "getName"
        assert (
            PARALLAX_ATTRIBUTES_NAME_ACCESSOR_3150
            != PARALLAX_ATTRIBUTES_NAME_ACCESSOR_360_CONTEXT
        )


_PLATFORM_MODULES: tuple[str, ...] = (
    "button.py",
    "camera.py",
    "switch.py",
    "cover.py",
    "lock.py",
    "climate.py",
    "select.py",
    "number.py",
    "update.py",
)

_GAPS_HEADINGS: tuple[str, ...] = (
    "Candidate-to-build",
    "Listed-not-built (named non-goals)",
    "Listed-not-built until a live accept",
    "Already at parity via other transport",
    "Out of catalog",
)

_GAP_HEADINGS: tuple[str, ...] = _GAPS_HEADINGS[:3]

_UNPROVEN_GRAPHQL_NAMES: tuple[str, ...] = (
    "rearWindowStatus",
    "vehicleChargerDamaged",
    "driverOccupancyStatus",
    "driveAuthorizationUserInputRequestStatus",
    "chargingDisabledAC",
)


def _strip_hash_comments(src: str) -> str:
    """Drop `#` comments per line. Required: `\\b` matches CLIMATE_HOLD_ON in switch.py:72."""
    return "\n".join(re.sub(r"#.*", "", line) for line in src.splitlines())


def _platform_sources() -> str:
    return "".join(
        _strip_hash_comments((REPO / "custom_components/rivian" / name).read_text())
        for name in _PLATFORM_MODULES
    )


def _is_wired(name: str, sources: str) -> bool:
    return re.search(rf"VehicleCommand\.{re.escape(name)}\b", sources) is not None


def _gaps_sections() -> dict[str, str]:
    text = (REPO / "docs/development/REMAINING_APK_GAPS.md").read_text()
    parts = re.split(r"^## ", text, flags=re.MULTILINE)
    sections: dict[str, str] = {}
    for part in parts[1:]:
        title, _, body = part.partition("\n")
        title = title.strip()
        if title in _GAPS_HEADINGS:
            sections[title] = body
    return sections


def _backticks(section: str) -> set[str]:
    return set(re.findall(r"`([^`]+)`", section))


class TestRemainingApkGaps:
    """HA-shaped remaining-gap catalog. docs/development/REMAINING_APK_GAPS.md.

    Wiring is word-boundary VehicleCommand.{NAME} over nine platform modules
    with `#` comments stripped. Disposition tags are exact ATX `##` titles.
    """

    def test_the_five_headings_exist(self) -> None:
        assert set(_gaps_sections()) == set(_GAPS_HEADINGS)

    def test_platform_module_list_has_not_drifted(self) -> None:
        """_PLATFORM_MODULES is hand-maintained; s28 added camera.py and missed it.

        Every module that names a VehicleCommand must be in the list, or
        _is_wired() silently answers False and the whole catalog reasons from a
        stale premise. coordinator.py is the one deliberate exclusion: its only
        refs are two WAKE_VEHICLE sends (coordinator.py:1956,1966), which back no
        entity of their own.
        """
        naming = {
            path.name
            for path in (REPO / "custom_components/rivian").glob("*.py")
            if "VehicleCommand." in path.read_text()
        }
        assert naming - {"coordinator.py"} == set(_PLATFORM_MODULES)

    def test_there_is_no_second_test_module(self) -> None:
        assert not (REPO / "tests/test_remaining_apk_gaps.py").exists()

    def test_coverage_doc_points_at_the_catalog(self) -> None:
        text = (REPO / "docs/development/COMMAND_COVERAGE.md").read_text()
        assert "REMAINING_APK_GAPS.md" in text

    def test_gear_guard_lock_is_not_wired_because_video_is(self) -> None:
        """`ENABLE_GEAR_GUARD\\b` must not match ENABLE_GEAR_GUARD_VIDEO."""
        switch = _strip_hash_comments(
            (REPO / "custom_components/rivian/switch.py").read_text()
        )
        assert re.search(r"VehicleCommand\.ENABLE_GEAR_GUARD_VIDEO\b", switch)
        assert re.search(r"VehicleCommand\.DISABLE_GEAR_GUARD_VIDEO\b", switch)
        assert not re.search(r"VehicleCommand\.ENABLE_GEAR_GUARD\b", switch)
        assert not re.search(r"VehicleCommand\.DISABLE_GEAR_GUARD\b", switch)
        # The catalog claims the lock pair is unwired *anywhere*, not just here.
        sources = _platform_sources()
        assert not _is_wired("ENABLE_GEAR_GUARD", sources)
        assert not _is_wired("DISABLE_GEAR_GUARD", sources)

    def test_climate_hold_comment_is_not_wiring(self) -> None:
        raw = (REPO / "custom_components/rivian/switch.py").read_text()
        stripped = _strip_hash_comments(raw)
        assert re.search(r"VehicleCommand\.CLIMATE_HOLD_ON\b", raw)
        assert not re.search(r"VehicleCommand\.CLIMATE_HOLD_ON\b", stripped)
        assert not _is_wired("CLIMATE_HOLD_ON", stripped)
        assert not _is_wired("CLIMATE_HOLD_OFF", stripped)

    def test_sendable_commands_are_wired_or_catalogued(self) -> None:
        sources = _platform_sources()
        sections = _gaps_sections()
        tokens_by_heading = {
            heading: _backticks(body) for heading, body in sections.items()
        }
        wired = {name for name in SENDABLE_COMMANDS if _is_wired(name, sources)}
        candidate = tokens_by_heading["Candidate-to-build"]
        assert not (candidate & SENDABLE_COMMANDS & wired)

        for name in sorted(SENDABLE_COMMANDS):
            homes = [
                heading
                for heading, tokens in tokens_by_heading.items()
                if name in tokens
            ]
            assert _is_wired(name, sources) or homes, (
                f"{name} is sendable, not wired, and not backtick-named in the catalog"
            )
            if not _is_wired(name, sources):
                assert len(homes) == 1, f"{name} unwired with catalog homes {homes}"

        gap_tokens: set[str] = set()
        for heading in _GAP_HEADINGS:
            gap_tokens |= tokens_by_heading[heading]
        # A wired command is not a gap. s28 wired START_GEAR_GUARD_MASTER_SESSION
        # while it sat in "named non-goals" and nothing failed: the ban above
        # covers only Candidate-to-build, and the uniqueness check skips wired
        # names entirely. Ban wired sendables from all three gap sections so the
        # next s28 breaks a test instead of a claim.
        for name in sorted(gap_tokens & SENDABLE_COMMANDS & wired):
            homes = [h for h in _GAP_HEADINGS if name in tokens_by_heading[h]]
            raise AssertionError(f"{name} is wired but still catalogued in {homes}")
        assert "ENABLE_GEAR_GUARD_VIDEO" not in gap_tokens
        assert "DISABLE_GEAR_GUARD_VIDEO" not in gap_tokens

    def test_candidate_to_build_holds_no_command(self) -> None:
        """The command side of the catalog is closed; what remains is read-only.

        `FLASH_EXTERNAL_LIGHTS` and `ACTIVATE_EXTERNAL_SOUND` were pinned HERE
        until 2026-09-01, when the owner declined the live-write gate the
        section's own preamble names. They moved to named non-goals rather than
        being deleted, because the gateway accepts on this R1T are evidence and
        stay recorded.

        This asserts the *class*, not the two names: any future sendable that
        lands in this section is a live write nobody has approved.
        """
        sources = _platform_sources()
        candidate = _backticks(_gaps_sections()["Candidate-to-build"])

        assert not (candidate & SENDABLE_COMMANDS), sorted(
            candidate & SENDABLE_COMMANDS
        )
        for name in ("FLASH_EXTERNAL_LIGHTS", "ACTIVATE_EXTERNAL_SOUND"):
            assert name not in candidate, name
            assert not _is_wired(name, sources), f"{name} declined but wired"
        assert "ENABLE_GEAR_GUARD" not in candidate
        assert "DISABLE_GEAR_GUARD" not in candidate

    def test_candidate_rows_do_not_claim_a_missing_entity(self) -> None:
        """`HA today: none` was wrong for all three rows for thirteen days.

        The entities were added on 2026-08-19 (`744fe77`) from Parallax, and
        the catalog written on 2026-08-31 still said none existed. Nothing
        caught it, because the wiring checks read VehicleCommand names and
        these are sensor fields. This is that check.
        """
        from custom_components.rivian.const import SENSORS

        body = _gaps_sections()["Candidate-to-build"]
        fields = {description.field for description in SENSORS}

        for name in ("passiveEntryUnlockFailReason", "vasAccessCanFaulted"):
            assert name in _backticks(body), name
            assert name in fields, f"{name} has no sensor; the row's premise moved"
        assert "| none |" not in body, "a row claims no entity where one exists"

    def test_named_non_goal_pins(self) -> None:
        tokens = _backticks(_gaps_sections()["Listed-not-built (named non-goals)"])
        assert "HONK_AND_FLASH_LIGHTS" in tokens
        # Owner-declined 2026-09-01. Both were gateway-accepted on this R1T, so
        # they are not capability gaps -- they are a product decision, and this
        # is where the decision lives.
        assert "FLASH_EXTERNAL_LIGHTS" in tokens
        assert "ACTIVATE_EXTERNAL_SOUND" in tokens
        # INTERIOR_CAMERA is the camera gap that survived s28: it is a picker
        # option (gear_guard.py:37-38), never a gate source, so an interior-only
        # vehicle gets no camera entity at all.
        assert "INTERIOR_CAMERA" in tokens
        # s28 wired this and shipped the camera platform. Neither belongs in a
        # non-goals section again.
        assert "START_GEAR_GUARD_MASTER_SESSION" not in tokens
        assert "Platform.CAMERA" not in tokens

    def test_invalid_wrapper_seven_and_unproven_fields(self) -> None:
        tokens = _backticks(_gaps_sections()["Listed-not-built until a live accept"])
        for name in sorted(INVALID_WRAPPER_COMMANDS):
            assert name in tokens, name
        for name in _UNPROVEN_GRAPHQL_NAMES:
            assert name in tokens, name
        assert "ENABLE_GEAR_GUARD" in tokens
        assert "DISABLE_GEAR_GUARD" in tokens

    def test_climate_hold_is_already_at_parity(self) -> None:
        tokens = _backticks(_gaps_sections()["Already at parity via other transport"])
        assert "CLIMATE_HOLD_ON" in tokens
        assert "CLIMATE_HOLD_OFF" in tokens
        sources = _platform_sources()
        assert not _is_wired("CLIMATE_HOLD_ON", sources)
        assert not _is_wired("CLIMATE_HOLD_OFF", sources)

    def test_camera_platform_is_registered(self) -> None:
        """s28 shipped it (`__init__.py:52`); the catalog says so, so pin it.

        tests/test_camera.py calls async_setup_entry directly and never checks
        PLATFORMS, so nothing else covers the registration.
        """
        from custom_components.rivian import PLATFORMS
        from homeassistant.const import Platform

        assert Platform.CAMERA in PLATFORMS
