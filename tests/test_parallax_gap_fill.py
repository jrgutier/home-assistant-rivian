"""The vehicleState subscription wins; Parallax fills only the gaps.

19 of the 28 keys the f5 decoders write are also carried by the subscription --
`gearStatus`, `driveMode`, `alarmSoundStatus`, `trailerStatus` among them, all of
which drive automations. The merge used to be `(self.data) | vehicle_updates`, so
whichever arrived last won.

Two sources for one sensor is a defect with precedent in this very file:
`vehicleMileage` needed a monotonic guard because oscillation between an
integer-km Parallax value and a float-metre subscription value corrupted utility
meters. The f5 decoders are transcribed from the app's protobuf classes and
asserted against CONSTRUCTED payloads -- nothing this vehicle has actually sent --
so they must not be able to overwrite a value that is known to be right.

Provenance is tracked rather than inferred from "is the key present". Once
Parallax writes a key it IS present, so a presence test would let a
Parallax-only field update exactly once and then freeze.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.rivian.const import INVALID_SENSOR_STATES
from custom_components.rivian.coordinator import VehicleCoordinator


def _coordinator() -> MagicMock:
    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator.data = {}
    coordinator._subscription_keys = set()
    coordinator._rvm_arrivals = {}
    coordinator._note_unusable = MagicMock()
    coordinator.charging_coordinator = MagicMock()
    coordinator.vehicle_id = "veh-1"
    coordinator.async_set_updated_data = MagicMock()
    return coordinator


def _parallax(coordinator: MagicMock, rvm: str, decoded: dict) -> dict:
    """Drive the real _process_parallax_data with an already-decoded payload."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            "custom_components.rivian.coordinator.decode_parallax_message",
            lambda **_: decoded,
        )
        VehicleCoordinator._process_parallax_data(
            coordinator,
            {
                "payload": {
                    "data": {
                        "parallaxMessages": {"rvm": rvm, "payload": "", "timestamp": 0}
                    }
                }
            },
        )
    if not coordinator.async_set_updated_data.called:
        return {}
    return coordinator.async_set_updated_data.call_args[0][0]


class TestSubscriptionWins:
    def test_parallax_does_not_overwrite_a_subscribed_field(self) -> None:
        """The whole point. gearStatus drives a Gear Change automation."""
        coordinator = _coordinator()
        coordinator._subscription_keys = {"gearStatus"}
        coordinator.data = {"gearStatus": {"value": "park", "history": {"park"}}}

        result = _parallax(
            coordinator, "dynamics.vehicle.gear", {"gearStatus": "drive"}
        )

        assert result == {} or result["gearStatus"]["value"] == "park"

    def test_a_parallax_only_field_is_written(self) -> None:
        """The subscription never names vasAccessCanFaulted, so Parallax is its
        only source and must not be blocked."""
        coordinator = _coordinator()
        coordinator._subscription_keys = {"gearStatus"}

        result = _parallax(
            coordinator, "security.access.vas_fault", {"vasAccessCanFaulted": "failure"}
        )

        assert result["vasAccessCanFaulted"]["value"] == "failure"

    def test_a_parallax_only_field_keeps_updating(self) -> None:
        """Presence is not provenance.

        A "write only if the key is absent" rule would let this field update once
        and then freeze forever, because Parallax's own first write makes it
        present.
        """
        coordinator = _coordinator()
        first = _parallax(
            coordinator,
            "security.access.vas_fault",
            {"vasAccessCanFaulted": "no_failure"},
        )
        coordinator.data = first
        second = _parallax(
            coordinator, "security.access.vas_fault", {"vasAccessCanFaulted": "failure"}
        )

        assert second["vasAccessCanFaulted"]["value"] == "failure"

    def test_a_mixed_message_writes_only_its_unsubscribed_half(self) -> None:
        """SYNTHETIC keys, deliberately.

        This used to be `security.access.btm`: five of its six fields subscribed,
        `btmOcHardwareFailureStatus` the lone unsubscribed one. The §D shrink
        subscribes it too, so that premise is now false -- all six of that
        topic's real fields are subscribed and there is no genuinely split RVM
        topic left to point this at (PARALLAX_ONLY_FIELDS is down to seven
        fields, none of which shares an RVM topic with a subscribed field).

        The mechanism under test -- a single Parallax message can be half
        accepted and half dropped, per key -- is still real and still needs
        coverage, so this keeps it with a made-up topic and made-up field names
        that cannot be mistaken for real Rivian fields.
        """
        coordinator = _coordinator()
        coordinator._subscription_keys = {
            "syntheticSubscribedFieldA",
            "syntheticSubscribedFieldB",
        }
        coordinator.data = {
            "syntheticSubscribedFieldA": {"value": "unspecified", "history": set()}
        }

        result = _parallax(
            coordinator,
            "synthetic.mixed.message",
            {
                "syntheticSubscribedFieldA": "set",
                "syntheticSubscribedFieldB": "set",
                "syntheticUnsubscribedField": "set",
            },
        )

        assert result["syntheticUnsubscribedField"]["value"] == "set"
        assert result["syntheticSubscribedFieldA"]["value"] == "unspecified"
        assert "syntheticSubscribedFieldB" not in result

    def test_the_subscription_reclaims_a_field_parallax_had_filled(self) -> None:
        """If the subscription starts carrying a field, it takes it over and
        Parallax stops writing it."""
        coordinator = _coordinator()
        coordinator.data = _parallax(
            coordinator, "dynamics.vehicle.gear", {"gearStatus": "drive"}
        )
        assert coordinator.data["gearStatus"]["value"] == "drive"

        # The subscription arrives.
        coordinator._subscription_keys = {"gearStatus"}
        coordinator.data = {"gearStatus": {"value": "park", "history": {"park"}}}

        result = _parallax(
            coordinator, "dynamics.vehicle.gear", {"gearStatus": "drive"}
        )
        assert result == {} or result["gearStatus"]["value"] == "park"


class TestProvenanceIsRecorded:
    def test_building_the_subscription_dict_records_its_keys(self) -> None:
        coordinator = _coordinator()
        coordinator.data = None

        VehicleCoordinator._build_vehicle_info_dict(
            coordinator,
            {
                "gearStatus": {"value": "park", "timeStamp": "t0"},
                "driveMode": {"value": "everyday", "timeStamp": "t0"},
            },
        )

        assert {"gearStatus", "driveMode"} <= coordinator._subscription_keys

    def test_falsy_entries_are_not_recorded_as_supplied(self) -> None:
        """`_build_vehicle_info_dict` drops falsy values, so a field the server
        named but did not fill must not count as supplied -- otherwise Parallax
        would be blocked from a field nothing is providing."""
        coordinator = _coordinator()
        coordinator.data = None

        VehicleCoordinator._build_vehicle_info_dict(
            coordinator,
            {"gearStatus": {"value": "park", "timeStamp": "t0"}, "driveMode": None},
        )

        assert "gearStatus" in coordinator._subscription_keys
        assert "driveMode" not in coordinator._subscription_keys

    def test_structured_fields_stay_claimed(self) -> None:
        """gnssLocation and gnssError have no top-level "value" key at all --
        they are nested structures (latitude/longitude, bearing/speed/...) -- so
        the `"value" in v` branch in `_build_vehicle_info_dict` never fires for
        them. They must still enter `_subscription_keys` on the strength of the
        outer dict alone, or `_process_parallax_data`'s unconditional
        `gnssLocation` branch (coordinator.py:1135) starts overwriting real GPS
        with Parallax's."""
        coordinator = _coordinator()
        coordinator.data = None

        VehicleCoordinator._build_vehicle_info_dict(
            coordinator,
            {
                "gnssLocation": {
                    "latitude": 1.0,
                    "longitude": 2.0,
                    "timeStamp": "t0",
                },
                "gnssError": {
                    "bearing": 1.0,
                    "positionHorizontal": 2.0,
                    "positionVertical": 3.0,
                    "speed": 4.0,
                    "timeStamp": "t0",
                },
            },
        )

        assert "gnssLocation" in coordinator._subscription_keys
        assert "gnssError" in coordinator._subscription_keys


class TestSubscribingDoesNotBlockParallax:
    """The direct proof for the §D shrink: subscribing to a field does not, by
    itself, claim it for the subscription -- only a DELIVERED, truthy frame
    value does. `_subscription_keys` is fed at `_build_vehicle_info_dict`
    (coordinator.py:1292) from frames the gateway actually sends, never from the
    requested property set, so `batteryCellType`, `coldRangeNotification` and
    `btmOcHardwareFailureStatus` moving out of PARALLAX_ONLY_FIELDS does not by
    itself take Parallax's write path away from them.

    Three cases per field, and the middle one is the one that matters: a frame
    can name a key AND still not supply a usable value for it
    (`{"timeStamp": ..., "value": None}` -- the server selected the field and
    got nothing back). `_build_vehicle_info_dict` filters on the OUTER dict's
    truthiness only (`if v` at coordinator.py:1289) -- a non-empty dict is
    truthy regardless of what its "value" key holds -- so today that case is
    wrongly claimed and Parallax is wrongly blocked. That is the second case
    below, and it is written to demonstrate the bug, not to pass: it is expected
    RED until the value-based provenance fix lands (coordinator.py:1292, wave 3).
    """

    NEWLY_SUBSCRIBABLE = (
        "batteryCellType",
        "coldRangeNotification",
        "btmOcHardwareFailureStatus",
    )

    @pytest.mark.parametrize("field", NEWLY_SUBSCRIBABLE)
    def test_a_null_top_level_frame_does_not_claim_the_key(self, field: str) -> None:
        """The gateway named the field and returned nothing for it at all --
        the ordinary "not delivered this frame" case. Parallax must remain
        free to supply it."""
        coordinator = _coordinator()
        coordinator.data = None
        VehicleCoordinator._build_vehicle_info_dict(coordinator, {field: None})
        assert field not in coordinator._subscription_keys

        result = _parallax(coordinator, "synthetic.newly.subscribable", {field: "px"})
        assert result[field]["value"] == "px"

    @pytest.mark.parametrize("field", NEWLY_SUBSCRIBABLE)
    def test_a_wrapped_null_value_does_not_claim_the_key(self, field: str) -> None:
        """EXPECTED RED until the value-based provenance fix lands.

        The gateway named the field and wrapped it -- {"timeStamp": ...,
        "value": None} -- but supplied no usable value. This must behave
        identically to the top-level-None case above: the key stays free for
        Parallax. It does not, because `if v` at coordinator.py:1289 only
        checks the OUTER dict's truthiness, and a non-empty dict with
        "value": None is still truthy -- so the key gets claimed anyway and
        Parallax's write is wrongly blocked.
        """
        coordinator = _coordinator()
        coordinator.data = None
        VehicleCoordinator._build_vehicle_info_dict(
            coordinator, {field: {"timeStamp": "t0", "value": None}}
        )
        assert field not in coordinator._subscription_keys

        result = _parallax(coordinator, "synthetic.newly.subscribable", {field: "px"})
        assert result[field]["value"] == "px"

    @pytest.mark.parametrize("field", NEWLY_SUBSCRIBABLE)
    def test_a_real_value_claims_the_key_and_blocks_parallax(self, field: str) -> None:
        """The ordinary case once these three are genuinely subscribed and
        delivering: the subscription value wins and Parallax is skipped."""
        coordinator = _coordinator()
        coordinator.data = None
        VehicleCoordinator._build_vehicle_info_dict(
            coordinator, {field: {"timeStamp": "t0", "value": "gateway"}}
        )
        assert field in coordinator._subscription_keys
        coordinator.data = {field: {"value": "gateway", "history": {"gateway"}}}

        result = _parallax(coordinator, "synthetic.newly.subscribable", {field: "px"})
        assert result == {} or result[field]["value"] == "gateway"


# The names PARALLAX_ONLY_FIELDS carries. ONE hardcoded copy: both the pinning
# test below and TestTheParallaxOnlyKeysHaveEntities parametrize off this same
# tuple, rather than each keeping its own hand-typed list that could drift from
# the other -- team-lead's correction to an earlier draft of this file, which
# had exactly that duplication.
#
# RENAMED from PARALLAX_ONLY_SEVEN. A count in the name is a promise the code
# keeps breaking: this repo has recorded five wrong counts, the symbol was
# already "SEVEN" for a set that had been nine, and s40 makes it 18. The name no
# longer carries a number; `len()` does.
#
# The original seven split 4/3 for two DIFFERENT reasons, checked directly
# against rivian_client/schemas/gateway.graphql:
#   - not declared in the schema at all -- subscribing to one of these is fatal,
#     the wheelsInstalled failure, killing the WHOLE document:
#     wheelsInstalled, consecutiveAlarmDisabledNotification, knownLocation,
#     secureImmobilizerStatus
#   - declared, but requested by no app document -- subscribing would not be
#     fatal, it merely has no live precedent for actually arriving:
#     passiveEntryUnlockFailReason, vasAccessCanFaulted, vasSecureElementFaulted
# `vasAccessCanFaulted` arriving populated via
# TestTheParallaxOnlyKeysHaveEntities.ENABLED is the only witness that
# `security.access.vas_fault` lands at all -- the second group's reasoning has
# that live evidence behind it and the first group's does not.
#
# The eleven s40 added are a THIRD group, and the strongest of the three: names
# that appear in no GraphQL schema because they are not GraphQL at all -- they
# are protobuf field names invented by this repo's own decoders for the four s34
# RVMs, every one of which has a frame captured off the live truck and committed
# under tests/client/fixtures/parallax/ (see tests/test_parallax_s34_decoders.py).
PARALLAX_ONLY_KEYS = (
    "cabinVentilationDurationMinutes",
    "cabinVentilationEnabled",
    "cabinVentilationMode",
    "cabinVentilationSunroofOpenPercent",
    "cabinVentilationWindowsOpenPercent",
    "consecutiveAlarmDisabledNotification",
    "gearGuardStreamingConsent",
    "gearGuardStreamingDailyLimit",
    "gearGuardStreamingLimitResetTime",
    "knownLocation",
    "parkedEnergyLast24Hours",
    "parkedEnergyLast8Hours",
    "parkedEnergyLastParkSession",
    "passiveEntryUnlockFailReason",
    "secureImmobilizerStatus",
    "vasAccessCanFaulted",
    "vasSecureElementFaulted",
    "wheelsInstalled",
)


def test_the_parallax_only_keys_are_what_we_think_they_are() -> None:
    """Pinned, so the set changes only in a diff someone reads.

    Was nine, then seven, now 18. The 2026-09-02 shrink moved batteryCellType,
    coldRangeNotification and btmOcHardwareFailureStatus out (all three are in
    the app's document and now subscribed); s40 added the eleven keys behind the
    four s34 decoders' entities. See PARALLAX_ONLY_KEYS's comment for why the
    original seven split 4/3 and why the eleven are a third group.

    This does NOT say "if a future story subscribes to one of these, Parallax
    stops writing it automatically" -- that was never true and the shrink is the
    proof: `_subscription_keys` (coordinator.py:1292) is populated only from
    frames the gateway actually DELIVERS with a truthy value, never from the
    requested property set, so being named in the subscription document is not
    what claims a key. TestSubscribingDoesNotBlockParallax above is the direct
    demonstration. What this test actually pins is narrower and still real: none
    of these should be REQUESTED in the subscription document, because a name
    the server does not know takes the WHOLE document down (the wheelsInstalled
    failure) and, for the names the schema does declare, a genuinely delivered
    value WOULD claim the key and freeze Parallax as their only source.
    """
    from custom_components.rivian.const import (
        PARALLAX_ONLY_FIELDS,
        VEHICLE_STATE_API_FIELDS,
    )

    assert set(PARALLAX_ONLY_KEYS) == PARALLAX_ONLY_FIELDS
    assert not (set(PARALLAX_ONLY_KEYS) & VEHICLE_STATE_API_FIELDS)


class TestTheParallaxOnlyKeysHaveEntities:
    """Decoding a field and exposing it are different things.

    When the gap-fill rule landed, the fourteen f5 decoders surfaced NOTHING: the
    19 overlapping keys were blocked by the subscription, and the
    Parallax-only keys had no sensor description, so they were decoded into the
    coordinator and read by nobody. s34 repeated it in miniature -- four
    decoders, verified against captured frames, read by nothing until s40. These
    tests are the guard against that state returning.

    `wheelsInstalled` is one of these, but it is NOT one of the original
    "nine" this class used to enumerate -- it is the f4 flagship case: a name
    the gateway does not know at all, which took the ENTIRE subscription down
    the one time it was requested. It backs a real sensor (`wheels_installed`)
    same as the others, so it belongs in this class's checks; its inclusion
    is not lost history, just recorded here so the next count change does not
    have to rediscover why it is different.
    """

    KEYS = PARALLAX_ONLY_KEYS

    @pytest.mark.parametrize("field", KEYS)
    def test_each_backs_an_entity(self, field: str) -> None:
        """SENSORS *or* BINARY_SENSORS.

        Was SENSORS only, which was accurate while every Parallax-only key held
        a string. `cabinVentilationEnabled` is a real `bool` off the wire
        (decode_cabin_ventilation_setting), and a bool belongs in a
        binary_sensor -- as a sensor its state renders "True"/"False", which is
        neither translatable nor a vocabulary. Widening the lookup is the honest
        fix; narrowing the entity to fit the test would not be.
        """
        from custom_components.rivian.const import BINARY_SENSORS, SENSORS

        fields = {d.field for d in SENSORS}
        fields |= {d.field for d in BINARY_SENSORS if isinstance(d.field, str)}
        assert field in fields, f"{field} is decoded but exposed by nothing"

    @pytest.mark.parametrize("field", KEYS)
    def test_none_of_them_reaches_the_subscription(self, field: str) -> None:
        """A name the server does not know takes down the WHOLE subscription --
        the wheelsInstalled failure -- and a subscribed field is recorded in
        _subscription_keys, which makes the gap-fill rule skip it and pins the
        sensor at unknown forever.

        PARALLAX_ONLY_FIELDS is what keeps them out. (The wire lists are literal
        now rather than derived from the descriptions, so adding a sensor no
        longer auto-adds its field to the subscription -- but membership here is
        still what the two collision guards in test_init.py check against.)
        """
        from custom_components.rivian.const import (
            PARALLAX_ONLY_FIELDS,
            VEHICLE_STATE_API_FIELDS,
        )

        assert field in PARALLAX_ONLY_FIELDS
        assert field not in VEHICLE_STATE_API_FIELDS

    # Which of them ship enabled, and WHY. The reason rides along as the
    # parametrize id, so a failure names the ground the entity was standing on.
    #
    # The line is whether the MESSAGE is PROVEN TO ARRIVE -- not whether a field
    # held a value in one snapshot. A snapshot criterion flips with the weather:
    # knownLocation reads `home` because the truck is parked at home.
    _S34_FIXTURE = "s34 decoder, frame captured off the live truck and committed"
    ENABLED = [
        ("vasAccessCanFaulted", "witness: arrived populated, proving its RVM lands"),
        ("vasSecureElementFaulted", "same message, and armed before the fault"),
        ("knownLocation", "user-facing, no entity_category"),
        (
            "wheelsInstalled",
            (
                "its own defect story (wheelsInstalled on the wire, f4) is "
                "direct proof decode_vehicle_wheels fires"
            ),
        ),
        # The eleven s40 keys. Every one of the four RVMs behind them has a
        # committed fixture, which is arrival proof of the same kind the four
        # above rest on -- and stronger, since it is the frame itself rather
        # than an inference from a sibling field.
        ("cabinVentilationEnabled", f"{_S34_FIXTURE}; the one field it carried"),
        ("cabinVentilationMode", f"{_S34_FIXTURE}; optional field, absent so far"),
        (
            "cabinVentilationWindowsOpenPercent",
            f"{_S34_FIXTURE}; optional field, absent so far",
        ),
        (
            "cabinVentilationSunroofOpenPercent",
            f"{_S34_FIXTURE}; optional field, absent so far",
        ),
        (
            "cabinVentilationDurationMinutes",
            f"{_S34_FIXTURE}; optional field, absent so far",
        ),
        ("gearGuardStreamingConsent", f"{_S34_FIXTURE}; decoded not_consented"),
        ("gearGuardStreamingDailyLimit", f"{_S34_FIXTURE}; decoded not_hit"),
        ("gearGuardStreamingLimitResetTime", f"{_S34_FIXTURE}; decoded verbatim"),
        ("parkedEnergyLast24Hours", f"{_S34_FIXTURE}; all ten measurements decoded"),
        ("parkedEnergyLast8Hours", f"{_S34_FIXTURE}; all ten measurements decoded"),
        (
            "parkedEnergyLastParkSession",
            f"{_S34_FIXTURE}; nine measurements, outletsKwh not sent",
        ),
    ]
    STILL_DISABLED = [
        ("passiveEntryUnlockFailReason", "arrival unwitnessed"),
        ("secureImmobilizerStatus", "arrival unwitnessed"),
        ("consecutiveAlarmDisabledNotification", "arrival unwitnessed"),
    ]

    @staticmethod
    def _enabled_default(field: str) -> bool:
        from custom_components.rivian.const import BINARY_SENSORS, SENSORS

        for description in (*SENSORS, *BINARY_SENSORS):
            if description.field == field:
                return description.entity_registry_enabled_default
        raise AssertionError(f"{field} backs no entity")

    @pytest.mark.parametrize(
        "field", [f for f, _ in ENABLED], ids=[r for _, r in ENABLED]
    )
    def test_the_proven_ones_ship_enabled(self, field: str) -> None:
        assert self._enabled_default(field) is not False

    @pytest.mark.parametrize(
        "field", [f for f, _ in STILL_DISABLED], ids=[r for _, r in STILL_DISABLED]
    )
    def test_the_three_unproven_ones_stay_disabled(self, field: str) -> None:
        """Not "it would read unknown" -- that argument would condemn the
        enabled ones too. All three have no unsubscribed sibling, so absence
        cannot be told apart from the decoder never firing."""
        assert self._enabled_default(field) is False

    def test_the_split_covers_every_key_exactly_once(self) -> None:
        assert len(self.ENABLED) + len(self.STILL_DISABLED) == len(self.KEYS)
        assert {f for f, _ in self.ENABLED} | {
            f for f, _ in self.STILL_DISABLED
        } == set(self.KEYS)

    def test_absence_is_not_read_as_health(self) -> None:
        """The correction that produced this split.

        Proto3 omits zero values, but that means "healthy" only where healthy IS
        zero. For the vas pair it is not: both maps start at 1 = no_failure with no
        0 entry, and vasAccessCanFaulted arrived AS no_failure -- an explicit
        non-zero value. So vasSecureElementFaulted being absent means UNSPECIFIED,
        not healthy. It is enabled on the arming argument, not on a health claim.
        """
        from custom_components.rivian.rivian_client.parallax import (
            _ACCESS_CAN_FAULTED_MAP,
            _HARDWARE_FAILURE_MAP,
            _SECURE_ELEMENT_FAULTED_MAP,
        )

        assert 0 not in _SECURE_ELEMENT_FAULTED_MAP
        assert 0 not in _ACCESS_CAN_FAULTED_MAP
        assert _SECURE_ELEMENT_FAULTED_MAP[1] == "no_failure"
        # The one map where zero-means-healthy does hold.
        assert _HARDWARE_FAILURE_MAP[0] == "unspecified"

    def test_a_decoded_value_actually_reaches_the_coordinator(self) -> None:
        """End to end for one of them, through the real merge."""
        coordinator = _coordinator()
        result = _parallax(
            coordinator,
            "security.access.immobilizer_state",
            {"secureImmobilizerStatus": "authorized_to_drive"},
        )
        assert result["secureImmobilizerStatus"]["value"] == "authorized_to_drive"


class TestRvmArrivalCounters:
    """Counting arrival is what makes "absent" interpretable.

    Without it, a missing field is ambiguous between "the message arrived and the
    field was zero, which proto3 omits" and "the message never arrived". That
    ambiguity is the stated reason three of the seven sensors ship disabled, so the
    counter is load-bearing rather than instrumentation for its own sake.
    """

    def test_arrival_is_counted_even_when_every_key_is_discarded(self) -> None:
        """The case a naive placement gets wrong.

        Every field of security.access.btm is subscribed, so the merge loop drops
        all of them. Count after that loop and this topic -- one of the exact ones
        the counter exists to witness -- registers as never having arrived.
        """
        coordinator = _coordinator()
        coordinator._subscription_keys = {
            "btmFfHardwareFailureStatus",
            "btmIcHardwareFailureStatus",
        }
        result = _parallax(
            coordinator,
            "security.access.btm",
            {
                "btmFfHardwareFailureStatus": "set",
                "btmIcHardwareFailureStatus": "set",
            },
        )

        assert result == {}, "every key should have been discarded"
        assert coordinator._rvm_arrivals["security.access.btm"] == 1

    def test_repeated_arrivals_accumulate(self) -> None:
        coordinator = _coordinator()
        for _ in range(3):
            _parallax(coordinator, "dynamics.vehicle.gear", {"gearStatus": "park"})
        assert coordinator._rvm_arrivals["dynamics.vehicle.gear"] == 3

    def test_a_topic_that_never_arrives_is_simply_absent(self) -> None:
        """Absent from the map, not zero -- so "never delivered" is readable."""
        coordinator = _coordinator()
        _parallax(coordinator, "dynamics.vehicle.gear", {"gearStatus": "park"})
        assert "security.access.immobilizer_state" not in coordinator._rvm_arrivals

    def test_an_undecodable_payload_still_counts_as_arrival(self) -> None:
        """Arrival and decodability are different questions, and conflating them
        would hide a topic that lands but decodes to nothing."""
        coordinator = _coordinator()
        _parallax(coordinator, "security.alarm.state", {})
        assert coordinator._rvm_arrivals["security.alarm.state"] == 1

    def test_diagnostics_surfaces_the_counters(self) -> None:
        """coordinator.data would have been the wrong home: that namespace is read
        by coordinator.get() for entity fields, and a counter there would collide.
        """
        import inspect

        from custom_components.rivian import diagnostics

        source = inspect.getsource(diagnostics)
        assert "parallax_rvm_arrivals" in source
        # Through the public accessor, not the private attribute -- diagnostics
        # reads coordinator.data and the sibling coordinators the same way.
        assert "coordinator.rvm_arrivals" in source
        # The private ACCESS, not the substring: "parallax_rvm_arrivals" is the
        # payload key and contains "_rvm_arrivals", so a bare substring check
        # fails against correct code. Fourth time that shape has bitten here.
        assert "coordinator._rvm_arrivals" not in source

    def test_the_accessor_reports_never_delivered_as_absent(self) -> None:
        coordinator = _coordinator()
        _parallax(coordinator, "dynamics.vehicle.gear", {"gearStatus": "park"})
        # coordinator is MagicMock(spec=VehicleCoordinator), so plain attribute
        # access would return a Mock rather than run the real property -- reach
        # for the descriptor's getter directly. `property.fget` is typed
        # Optional in general (a property need not have a getter); this one
        # always does, so narrow it rather than silence the warning.
        getter = VehicleCoordinator.rvm_arrivals.fget
        assert getter is not None
        arrivals = getter(coordinator)
        assert arrivals == {"dynamics.vehicle.gear": 1}
        assert "security.access.btm" not in arrivals


# climateHoldStatus is Parallax-only (absent from VEHICLE_STATE_API_FIELDS), so
# the gap-fill guard never skips it. It is also the field whose decoder emits
# "fault" (_CLIMATE_HOLD_STATUS[4]), which is why this filter exists.
_PARALLAX_ONLY_KEY = "climateHoldStatus"
_PARALLAX_ONLY_RVM = "comfort.cabin.climate_hold_status"


class TestParallaxInvalidStateFilter:
    """Parallax must apply the same INVALID_SENSOR_STATES policy as GraphQL.

    Decision 4 / known_gaps[0]. Dropping an invalid value with no previous was
    tried twice and reverted: it makes the entity unavailable and takes the
    matching control down with it. Parametrised over the real constant rather
    than a hardcoded "fault" so a value added later cannot silently stop being
    covered.
    """

    @pytest.mark.parametrize("invalid", sorted(INVALID_SENSOR_STATES))
    def test_invalid_with_previous_keeps_the_previous(self, invalid: str) -> None:
        coordinator = _coordinator()
        coordinator.data = {
            _PARALLAX_ONLY_KEY: {"value": "on", "history": {"on"}},
        }

        result = _parallax(
            coordinator, _PARALLAX_ONLY_RVM, {_PARALLAX_ONLY_KEY: invalid}
        )

        assert result[_PARALLAX_ONLY_KEY]["value"] == "on"
        coordinator._note_unusable.assert_not_called()

    @pytest.mark.parametrize("invalid", sorted(INVALID_SENSOR_STATES))
    def test_invalid_with_no_previous_is_passed_through(self, invalid: str) -> None:
        coordinator = _coordinator()

        result = _parallax(
            coordinator, _PARALLAX_ONLY_RVM, {_PARALLAX_ONLY_KEY: invalid}
        )

        assert result[_PARALLAX_ONLY_KEY]["value"] == invalid
        coordinator._note_unusable.assert_called_once_with(_PARALLAX_ONLY_KEY, invalid)

    @pytest.mark.parametrize("invalid", sorted(INVALID_SENSOR_STATES))
    def test_gnss_location_invalid_value_is_exempt(self, invalid: str) -> None:
        coordinator = _coordinator()

        result = _parallax(coordinator, "gnss.location", {"gnssLocation": invalid})

        assert result["gnssLocation"] == invalid
        coordinator._note_unusable.assert_not_called()

    def test_gnss_location_is_passed_through_unwrapped(self) -> None:
        """The gnssLocation branch assigns clean[k] raw, without the wrapper."""
        coordinator = _coordinator()
        gnss = {"latitude": 1.0, "longitude": 2.0}

        result = _parallax(coordinator, "gnss.location", {"gnssLocation": gnss})

        assert result["gnssLocation"] == gnss
        coordinator._note_unusable.assert_not_called()

    def test_vehicle_mileage_increase_is_still_accepted(self) -> None:
        coordinator = _coordinator()
        coordinator.data = {"vehicleMileage": {"value": 1000, "history": {1000}}}

        result = _parallax(
            coordinator, "dynamics.vehicle.odometer", {"vehicleMileage": 1200}
        )

        assert result["vehicleMileage"]["value"] == 1200

    def test_vehicle_mileage_decrease_is_still_rejected(self) -> None:
        """The filter must not short-circuit the oscillation guard."""
        coordinator = _coordinator()
        coordinator.data = {"vehicleMileage": {"value": 1000, "history": {1000}}}

        result = _parallax(
            coordinator, "dynamics.vehicle.odometer", {"vehicleMileage": 900}
        )

        assert result["vehicleMileage"]["value"] == 1000

    @pytest.mark.parametrize("invalid", sorted(INVALID_SENSOR_STATES))
    def test_a_subscribed_invalid_value_is_still_skipped(self, invalid: str) -> None:
        """The gap-fill rule outranks the filter: the subscription owns the key."""
        coordinator = _coordinator()
        coordinator._subscription_keys = {"gearStatus"}
        coordinator.data = {"gearStatus": {"value": "park", "history": {"park"}}}

        result = _parallax(
            coordinator, "dynamics.vehicle.gear", {"gearStatus": invalid}
        )

        assert result == {} or result["gearStatus"]["value"] == "park"
        coordinator._note_unusable.assert_not_called()


def test_some_decoders_emit_invalid_sensor_states() -> None:
    """prd.json claimed no decoder can emit INVALID_SENSOR_STATES. False.

    Walks every module-level dict in parallax.py whose values are strings,
    intersects with INVALID_SENSOR_STATES, and asserts the intersection is
    non-empty so that claim cannot be re-derived by hand.

    Limit: this sees dict-valued vocabularies and not ternary-emitted strings.
    decode_locks (parallax.py:489) and decode_closures (:395) emit from a
    conditional expression and are invisible to it.
    """
    from custom_components.rivian.rivian_client import parallax
    from custom_components.rivian.rivian_client.parallax import (
        _ALARM_SOUND_MAP,
        _CLIMATE_HOLD_STATUS,
        _DRIVE_MODE_MAP,
    )

    emitted: set[str] = set()
    for obj in vars(parallax).values():
        if not isinstance(obj, dict):
            continue
        for value in obj.values():
            if isinstance(value, str):
                emitted.add(value.lower())

    intersection = emitted & INVALID_SENSOR_STATES
    assert intersection, (
        "a decoder emits a value in INVALID_SENSOR_STATES; that is why the "
        "Parallax coordinator filter exists"
    )
    assert _CLIMATE_HOLD_STATUS[4] == "fault"
    assert _ALARM_SOUND_MAP[3] == "signal_not_available"
    assert _DRIVE_MODE_MAP[7] == "fault"
    assert "fault" in intersection
    assert "signal_not_available" in intersection
