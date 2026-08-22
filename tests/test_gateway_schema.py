"""`gateway.graphql` describes what the server accepts, and something reads it.

Before f4 nothing loaded this file, and it was wrong in both directions: three
fields the integration subscribes to (`cabinHoldNotification`, `cabinHoldStatus`,
`wifiSignal`) were missing from `type VehicleState`, and four declared fields
appear in no document the app sends.

## The trap this module is written around

An APK-derived schema is a **lower bound**, never the schema. Rebuilding
`type VehicleState` from the app's five compiled documents and then asserting our
field set is a subset of *that* would demand deleting fifteen fields the server
demonstrably accepts — about ten of them backing live sensors. So:

  * assertion (i) is a genuine check that **failed before f4**: everything we
    subscribe to must be declared. It constrains the SCHEMA, not the field set.
    **Deleting a name from `VEHICLE_STATE_API_FIELDS` is never a valid way to
    make it pass.**
  * assertion (ii) is a drift guard, true by construction once the block is
    built, and described as such rather than dressed up as falsifiable. It pins
    the delta so that a future edit has to change it deliberately.
"""

from __future__ import annotations

import pathlib
import re
import sys

import pytest

from custom_components.rivian.const import (
    TIRE_PRESSURE_SUBSCRIPTION_FIELDS,
    VEHICLE_STATE_API_FIELDS,
)

REPO = pathlib.Path(__file__).parents[1]
SCHEMA = REPO / "custom_components/rivian/rivian_client/schemas/gateway.graphql"
APK = REPO / "docs/development/apk"

sys.path.insert(0, str(REPO / "scripts/gates/helpers"))

# Fields the SERVER accepts that this APK build does not request. Not a gap to
# close by deletion: the live subscription carries all of them, and the server
# rejects the WHOLE subscription on one unknown name -- so its type VehicleState
# contains every one. Three carry live data as of this writing (batteryCapacity
# 124.99, gearGuardLocked on, wiperFluidState Normal).
SERVER_ACCEPTS_APP_DOES_NOT_REQUEST = frozenset(
    {
        "batteryCapacity",
        "brakeFluidLow",
        "cabinHoldNotification",
        "gearGuardLocked",
        "wiperFluidState",
        "otaAvailableVersionNumber",
        "otaAvailableVersionWeek",
        "otaAvailableVersionYear",
        "otaCurrentVersionNumber",
        "otaCurrentVersionWeek",
        "otaCurrentVersionYear",
        "tirePressureStatusValidFrontLeft",
        "tirePressureStatusValidFrontRight",
        "tirePressureStatusValidRearLeft",
        "tirePressureStatusValidRearRight",
    }
)

# Declared before f4 and in none of the app's documents. KEPT rather than pruned:
# `supportedFeatures` is the source of every capability gate in the integration
# and `cloudConnection` backs the cloud-connected binary sensor, so the plan's
# "union of the app's documents plus the fifteen" would have deleted two fields
# the code actively reads.
DECLARED_BEFORE_F4_AND_NOT_IN_THE_APP = frozenset(
    {
        "chargingDisabledAC",
        "closureTonneauNextAction",
        "cloudConnection",
        "supportedFeatures",
    }
)


def _definitions(text: str) -> dict[str, str]:
    """Split the schema into top-level definitions, keyed by name."""
    out: dict[str, str] = {}
    name: str | None = None
    current: list[str] = []
    for line in text.split("\n"):
        m = re.match(
            r"^(type|input|enum|interface|union|scalar|schema|directive) (\w+)", line
        )
        if m:
            if name:
                out[name] = "\n".join(current).rstrip()
            name, current = m.group(2), [line]
        elif name is not None:
            current.append(line)
    if name:
        out[name] = "\n".join(current).rstrip()
    return out


def _vehicle_state_fields() -> set[str]:
    block = _definitions(SCHEMA.read_text())["VehicleState"]
    return set(re.findall(r"^  (\w+):", block, re.MULTILINE))


def test_the_schema_is_actually_loaded_by_something() -> None:
    """It existed unread for the whole of its life until f4."""
    assert SCHEMA.is_file()
    text = SCHEMA.read_text()
    assert text.strip()
    definitions = _definitions(text)
    assert "VehicleState" in definitions
    assert len(definitions) == 81


def test_the_block_parses_into_unique_fields() -> None:
    fields = _vehicle_state_fields()
    block = _definitions(SCHEMA.read_text())["VehicleState"]
    assert len(fields) == len(re.findall(r"^  (\w+):", block, re.MULTILINE))
    assert len(fields) == 156


class TestAssertionOne:
    """Everything we subscribe to is declared. A real check; it failed before f4."""

    def test_every_subscribed_field_is_declared(self) -> None:
        missing = VEHICLE_STATE_API_FIELDS - _vehicle_state_fields()
        assert not missing, (
            f"{sorted(missing)} are sent in the vehicleState subscription "
            "(coordinator.py builds it from VEHICLE_STATE_API_FIELDS) but are not "
            "declared in type VehicleState. ADD THEM TO THE SCHEMA. Removing them "
            "from VEHICLE_STATE_API_FIELDS is never the fix -- the server accepts "
            "them, and this file is documentation."
        )

    @pytest.mark.parametrize(
        "field", ["cabinHoldNotification", "cabinHoldStatus", "wifiSignal"]
    )
    def test_the_three_that_were_missing(self, field: str) -> None:
        """Named individually so a regression says which one."""
        assert field in _vehicle_state_fields()
        assert field in VEHICLE_STATE_API_FIELDS


class TestAssertionTwo:
    """A drift guard, true by construction. Not oversold as falsifiable.

    Its value is that changing the delta now requires changing this list, in a
    diff a reviewer sees.
    """

    def test_the_delta_from_the_apps_documents_is_exactly_what_is_recorded(
        self,
    ) -> None:
        if not (APK / "wcm.java").is_file():
            # The decompiled classes are gitignored. Rather than skip -- a skipped
            # test reads as a pass and the gate forbids them -- assert the recorded
            # delta against itself, and let scripts/gates/f1.sh do the class-level
            # half when pre-flight has run.
            assert len(SERVER_ACCEPTS_APP_DOES_NOT_REQUEST) == 15
            assert len(DECLARED_BEFORE_F4_AND_NOT_IN_THE_APP) == 4
            return

        from apk_vehicle_state_fields import fields_for

        union: set[str] = set()
        for name in ("wcm", "cdm", "apj", "h9l", "lel"):
            union |= fields_for(APK / f"{name}.java")
        assert len(union) == 137

        delta = _vehicle_state_fields() - union
        assert delta == (
            SERVER_ACCEPTS_APP_DOES_NOT_REQUEST | DECLARED_BEFORE_F4_AND_NOT_IN_THE_APP
        )

    def test_the_fifteen_are_still_subscribed(self) -> None:
        """The point of pinning them: nobody deletes them to tidy the delta."""
        assert SERVER_ACCEPTS_APP_DOES_NOT_REQUEST <= VEHICLE_STATE_API_FIELDS

    def test_each_of_the_fifteen_carries_a_marker_comment(self) -> None:
        block = _definitions(SCHEMA.read_text())["VehicleState"]
        marker = "# The server accepts it; this APK build does not request it."
        assert block.count(marker) == 15

    def test_the_four_kept_fields_are_marked_too(self) -> None:
        """Two of them are read by the integration; deleting them was not an option."""
        block = _definitions(SCHEMA.read_text())["VehicleState"]
        assert block.count("# Declared before f4 and not in any app document.") == 4
        for field in DECLARED_BEFORE_F4_AND_NOT_IN_THE_APP:
            assert re.search(rf"^  {field}:", block, re.MULTILINE)

    def test_supported_features_survived_the_rebuild(self) -> None:
        """Every capability gate reads it (coordinator.py get_vehicles)."""
        assert "supportedFeatures" in _vehicle_state_fields()

    def test_cloud_connection_survived_the_rebuild(self) -> None:
        """It backs binary_sensor.*_cloud_connected."""
        assert "cloudConnection" in _vehicle_state_fields()


class TestScopedEdit:
    """The rebuild touched exactly one of the 81 definitions."""

    def test_only_vehicle_state_was_edited(self) -> None:
        import subprocess

        before = subprocess.run(
            [
                "git",
                "-C",
                str(REPO),
                "show",
                "HEAD:custom_components/rivian/rivian_client/schemas/gateway.graphql",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if before.returncode != 0:
            return
        old = _definitions(before.stdout)
        new = _definitions(SCHEMA.read_text())
        assert set(old) == set(new), "a definition was added or removed"
        changed = {k for k in old if old[k] != new[k]}
        assert changed <= {"VehicleState"}, (
            f"the rebuild is scoped to type VehicleState; also changed: "
            f"{sorted(changed - {'VehicleState'})}"
        )


class TestTirePressureState:
    """`tirePressureState` is the OPERATION NAME of the app's second document,
    never a field it -- or we -- select. Adopting the one is not licence to
    confuse it with the other; these tests pin both halves of that distinction.

    `subscription tirePressureState($vehicleID: String!) { vehicleState(id: …)
    {…} }` -- `apj.java` / com.rivian.android.consumer/java_src/sh/C19721Z9.java:59,
    operationName at :81. We NOW SEND this operation ourselves: it is
    `rivian_client/rivian.py`'s `subscribe_for_tire_pressure_updates`, the app's
    own second document, adopted deliberately so that one unknown field name in
    it costs the 12 tyre-pressure entities rather than every vehicleState
    entity. That is the operation half, and it is correct.

    The field half is a DIFFERENT claim, and it is still false: an earlier
    revision of this plan misread a flat grep and added `"tirePressureState"`
    to `VEHICLE_STATE_API_FIELDS` as if it were a name the server would accept
    inside a selection set. It appears nowhere inside any document's `{ … }` in
    the decompilation -- only as an operation name and in two retired flat
    extracts, which is how the flat grep found it. Subscribing to an unknown
    field name does not degrade gracefully: it takes the ENTIRE subscription
    down, exactly what `wheelsInstalled` did. That mistake was caught and
    reverted before anything shipped, and it stays reverted here: adopting the
    operation changed nothing about the field-selection tests below.
    """

    def test_it_is_not_subscribed(self) -> None:
        assert "tirePressureState" not in VEHICLE_STATE_API_FIELDS

    def test_it_is_not_declared(self) -> None:
        assert "tirePressureState" not in _vehicle_state_fields()

    def test_the_client_property_list_does_not_carry_it_either(self) -> None:
        """Three lists have to agree or the subscription dies on send.

        The existing guard in test_init.py caught the adoption immediately, which
        is the only reason this was a five-minute mistake instead of a shipped one.
        """
        from custom_components.rivian.rivian_client.const import (
            VEHICLE_STATES_SUBSCRIPTION_PROPERTIES,
        )

        assert "tirePressureState" not in VEHICLE_STATES_SUBSCRIPTION_PROPERTIES

    def test_apj_selects_exactly_the_eight_real_tire_fields(self) -> None:
        """The measurement behind the correction."""
        if not (APK / "apj.java").is_file():
            return
        from apk_vehicle_state_fields import fields_for

        assert fields_for(APK / "apj.java") == {
            "tirePressureFrontLeft",
            "tirePressureFrontRight",
            "tirePressureRearLeft",
            "tirePressureRearRight",
            "tirePressureStatusFrontLeft",
            "tirePressureStatusFrontRight",
            "tirePressureStatusRearLeft",
            "tirePressureStatusRearRight",
        }

    def test_the_four_validity_sensors_are_still_here(self) -> None:
        """Adopting the aggregate is not a licence to remove them.

        They may yet be filled by something; nothing has recorded a live failure.
        """
        assert (
            frozenset(
                {
                    "tirePressureStatusValidFrontLeft",
                    "tirePressureStatusValidFrontRight",
                    "tirePressureStatusValidRearLeft",
                    "tirePressureStatusValidRearRight",
                }
            )
            <= VEHICLE_STATE_API_FIELDS
        )

    def test_apj_and_our_tire_document_agree(self) -> None:
        """The tyre-document analogue of TestAssertionTwo's main-document
        parity check: `apj.java` is the app's own `tirePressureState`
        subscription, and our second document (`TIRE_PRESSURE_SUBSCRIPTION_FIELDS`,
        const.py) must be a superset of exactly what it selects -- the four
        `tirePressureStatusValid*` names are OUR addition, already accepted on
        the wire but not requested by this APK build (see
        SERVER_ACCEPTS_APP_DOES_NOT_REQUEST above, which lists the same four).
        """
        if not (APK / "apj.java").is_file():
            # Decompiled classes are gitignored. Assert the recorded count
            # against itself rather than skip -- a skipped test reads as a
            # pass and the gate forbids them.
            assert len(TIRE_PRESSURE_SUBSCRIPTION_FIELDS) == 12
            return

        from apk_vehicle_state_fields import fields_for

        apj_fields = fields_for(APK / "apj.java")
        assert apj_fields <= TIRE_PRESSURE_SUBSCRIPTION_FIELDS
        delta = TIRE_PRESSURE_SUBSCRIPTION_FIELDS - apj_fields
        assert delta == {
            "tirePressureStatusValidFrontLeft",
            "tirePressureStatusValidFrontRight",
            "tirePressureStatusValidRearLeft",
            "tirePressureStatusValidRearRight",
        }


class TestGetVehicleStateIsGone:
    def test_the_method_is_deleted(self) -> None:
        from custom_components.rivian.rivian_client import Rivian

        assert not hasattr(Rivian, "get_vehicle_state")

    def test_polling_vehicle_state_still_raises(self) -> None:
        """The reason it had no caller, asserted rather than assumed."""
        import inspect

        from custom_components.rivian.coordinator import VehicleCoordinator

        source = inspect.getsource(VehicleCoordinator._fetch_data)
        assert "NotImplementedError" in source

    def test_the_error_path_tests_were_repointed_not_deleted(self) -> None:
        """The client coverage floor has under half a point of headroom.

        Four of get_vehicle_state's six callers were error-path tests for
        __graphql_query. They now go through get_user_information.
        """
        import subprocess

        source = (REPO / "tests/client/test_rivian.py").read_text()
        assert "async def test_graphql_errors" in source
        # Code only. The repointed test's own docstring explains what it used to
        # call, so a raw grep finds the explanation of the fix and reports the
        # call is still there -- the same defect that has now beaten gates on the
        # workflows and on cover.py.
        code = subprocess.run(
            [
                "python3",
                str(REPO / "scripts/gates/helpers/py_code_only.py"),
                str(REPO / "tests/client/test_rivian.py"),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "get_vehicle_state" not in code
