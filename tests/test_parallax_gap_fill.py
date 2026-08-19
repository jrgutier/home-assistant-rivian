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

from custom_components.rivian.coordinator import VehicleCoordinator


def _coordinator() -> MagicMock:
    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator.data = {}
    coordinator._subscription_keys = set()
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

    @pytest.mark.parametrize("field", NINE)
    def test_each_ships_disabled_by_default(self, field: str) -> None:
        """Fault codes and debug counters, and none has been observed arriving on
        this vehicle. Enabling them by default would add nine entities that might
        sit at unknown indefinitely."""
        from custom_components.rivian.const import SENSORS

        for group in SENSORS.values():
            for description in group:
                if description.field == field:
                    assert description.entity_registry_enabled_default is False

    def test_a_decoded_value_actually_reaches_the_coordinator(self) -> None:
        """End to end for one of them, through the real merge."""
        coordinator = _coordinator()
        result = _parallax(
            coordinator,
            "security.access.immobilizer_state",
            {"secureImmobilizerStatus": "authorized_to_drive"},
        )
        assert result["secureImmobilizerStatus"]["value"] == "authorized_to_drive"
