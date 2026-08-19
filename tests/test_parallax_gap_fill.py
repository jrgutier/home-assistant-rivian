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
    coordinator._awake = MagicMock()
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
        """security.access.btm carries six fields; five are subscribed and
        btmOcHardwareFailureStatus is not."""
        coordinator = _coordinator()
        coordinator._subscription_keys = {
            "btmFfHardwareFailureStatus",
            "btmIcHardwareFailureStatus",
        }
        coordinator.data = {
            "btmFfHardwareFailureStatus": {"value": "unspecified", "history": set()}
        }

        result = _parallax(
            coordinator,
            "security.access.btm",
            {
                "btmFfHardwareFailureStatus": "set",
                "btmIcHardwareFailureStatus": "set",
                "btmOcHardwareFailureStatus": "set",
            },
        )

        assert result["btmOcHardwareFailureStatus"]["value"] == "set"
        assert result["btmFfHardwareFailureStatus"]["value"] == "unspecified"
        assert "btmIcHardwareFailureStatus" not in result

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


def test_the_nine_parallax_only_keys_are_what_we_think_they_are() -> None:
    """Pinned, so the split changes only in a diff someone reads.

    If a future story subscribes to one of these, Parallax stops writing it
    automatically and this test goes red to say so.
    """
    from custom_components.rivian.const import VEHICLE_STATE_API_FIELDS

    parallax_only = {
        "batteryCellType",
        "btmOcHardwareFailureStatus",
        "coldRangeNotification",
        "consecutiveAlarmDisabledNotification",
        "knownLocation",
        "passiveEntryUnlockFailReason",
        "secureImmobilizerStatus",
        "vasAccessCanFaulted",
        "vasSecureElementFaulted",
    }
    assert not (parallax_only & VEHICLE_STATE_API_FIELDS)


class TestTheNineHaveEntities:
    """Decoding a field and exposing it are different things.

    When the gap-fill rule landed, the fourteen f5 decoders surfaced NOTHING: the
    19 overlapping keys were blocked by the subscription, and the nine
    Parallax-only keys had no sensor description, so they were decoded into the
    coordinator and read by nobody. These tests are the guard against that state
    returning.
    """

    NINE = (
        "batteryCellType",
        "btmOcHardwareFailureStatus",
        "coldRangeNotification",
        "consecutiveAlarmDisabledNotification",
        "knownLocation",
        "passiveEntryUnlockFailReason",
        "secureImmobilizerStatus",
        "vasAccessCanFaulted",
        "vasSecureElementFaulted",
    )

    @pytest.mark.parametrize("field", NINE)
    def test_each_backs_a_sensor(self, field: str) -> None:
        from custom_components.rivian.const import SENSORS

        fields = {d.field for group in SENSORS.values() for d in group}
        assert field in fields, f"{field} is decoded but exposed by nothing"

    @pytest.mark.parametrize("field", NINE)
    def test_none_of_them_reaches_the_subscription(self, field: str) -> None:
        """VEHICLE_STATE_API_FIELDS is DERIVED from the sensor descriptions, so
        adding a sensor puts its field in the subscription automatically.

        For these nine that is doubly wrong. A name the server does not know takes
        down the WHOLE subscription -- the wheelsInstalled failure -- and a
        subscribed field is recorded in _subscription_keys, which makes the
        gap-fill rule skip it and pins the sensor at unknown forever.

        PARALLAX_ONLY_FIELDS is what keeps them out.
        """
        from custom_components.rivian.const import (
            PARALLAX_ONLY_FIELDS,
            VEHICLE_STATE_API_FIELDS,
        )

        assert field in PARALLAX_ONLY_FIELDS
        assert field not in VEHICLE_STATE_API_FIELDS

    # Which of the nine ship enabled, and WHY. The reason rides along as the
    # parametrize id, so a failure names the ground the entity was standing on.
    #
    # The line is whether the message is PROVEN TO ARRIVE -- not whether a field
    # held a value in one snapshot. A snapshot criterion flips with the weather:
    # knownLocation reads `home` because the truck is parked at home.
    ENABLED = [
        ("vasAccessCanFaulted", "witness: arrived populated, proving its RVM lands"),
        ("vasSecureElementFaulted", "same message, and armed before the fault"),
        ("batteryCellType", "static hardware fact"),
        ("coldRangeNotification", "user-facing, no entity_category"),
        ("knownLocation", "user-facing, no entity_category"),
    ]
    STILL_DISABLED = [
        ("btmOcHardwareFailureStatus", "vocabulary clash with its five siblings"),
        ("passiveEntryUnlockFailReason", "arrival unwitnessed"),
        ("secureImmobilizerStatus", "arrival unwitnessed"),
        ("consecutiveAlarmDisabledNotification", "arrival unwitnessed"),
    ]

    @staticmethod
    def _enabled_default(field: str) -> bool:
        from custom_components.rivian.const import SENSORS

        for group in SENSORS.values():
            for description in group:
                if description.field == field:
                    return description.entity_registry_enabled_default
        raise AssertionError(f"{field} backs no sensor")

    @pytest.mark.parametrize(
        "field", [f for f, _ in ENABLED], ids=[r for _, r in ENABLED]
    )
    def test_the_five_proven_ones_ship_enabled(self, field: str) -> None:
        assert self._enabled_default(field) is not False

    @pytest.mark.parametrize(
        "field", [f for f, _ in STILL_DISABLED], ids=[r for _, r in STILL_DISABLED]
    )
    def test_the_four_unproven_ones_stay_disabled(self, field: str) -> None:
        """Not "it would read unknown" -- that argument would condemn the five
        enabled ones too. Three of these have no unsubscribed sibling, so absence
        cannot be told apart from the decoder never firing; btm_oc additionally
        speaks a different enum vocabulary than its five enabled siblings."""
        assert self._enabled_default(field) is False

    def test_the_split_covers_all_nine_exactly_once(self) -> None:
        assert len(self.ENABLED) + len(self.STILL_DISABLED) == len(self.NINE)
        assert {f for f, _ in self.ENABLED} | {
            f for f, _ in self.STILL_DISABLED
        } == set(self.NINE)

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
    ambiguity is the stated reason three of the nine sensors ship disabled, so the
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
        arrivals = VehicleCoordinator.rvm_arrivals.fget(coordinator)
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
