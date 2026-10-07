"""The climate-hold duration finally shows up somewhere.

`switch.cabin_climate_hold` writes `comfort.cabin.climate_hold_setting`, which
sets how long a hold lasts. It does not turn a hold on: the hold status stays
`off`, so the switch never moves, and until s52 no entity read the duration
back. A hardware check on 2026-10-06 waited five minutes for the switch to
change while the vehicle had echoed 7200 seconds within one second.

These tests run a real frame through the real decoder and the real coordinator
path, because the point is the whole chain: frame -> decoder key -> gap-fill ->
the field a description reads.
"""

from __future__ import annotations

import base64
from unittest.mock import MagicMock

import pytest

from custom_components.rivian.const import (
    PARALLAX_ONLY_FIELDS,
    SENSORS,
    VEHICLE_STATE_API_FIELDS,
)
from custom_components.rivian.coordinator import SUBSCRIBED_RVMS, VehicleCoordinator
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfTime

TOPIC = "comfort.cabin.climate_hold_setting"
FIELD = "climateHoldDurationSeconds"


def _description():
    (found,) = [d for d in SENSORS if d.field == FIELD]
    return found


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


def _deliver(coordinator: MagicMock, raw: bytes) -> dict:
    """Push one frame through the real decoder and the real gap-fill path."""
    VehicleCoordinator._process_parallax_data(
        coordinator,
        {
            "payload": {
                "data": {
                    "parallaxMessages": {
                        "rvm": TOPIC,
                        "payload": base64.b64encode(raw).decode(),
                        "timestamp": 0,
                    }
                }
            }
        },
    )
    assert coordinator.async_set_updated_data.called, "the frame produced no update"
    return coordinator.async_set_updated_data.call_args[0][0]


class TestTheDescription:
    def test_exactly_one_sensor_reads_the_field(self) -> None:
        assert _description().key == "climate_hold_duration"

    def test_it_is_a_duration_in_seconds_shown_as_minutes(self) -> None:
        description = _description()
        assert description.device_class is SensorDeviceClass.DURATION
        assert description.native_unit_of_measurement == UnitOfTime.SECONDS
        assert description.suggested_unit_of_measurement == UnitOfTime.MINUTES

    def test_it_ships_enabled_and_ungated(self) -> None:
        """The switch that writes it is ungated; its only feedback must be too."""
        description = _description()
        assert description.entity_registry_enabled_default is True
        assert getattr(description, "feature", None) is None

    def test_the_field_is_parallax_only(self) -> None:
        """Requesting a name the gateway does not know takes the whole
        subscription document down."""
        assert FIELD in PARALLAX_ONLY_FIELDS
        assert FIELD not in VEHICLE_STATE_API_FIELDS

    def test_no_new_subscription_was_needed(self) -> None:
        assert TOPIC in SUBSCRIBED_RVMS


class TestTheValue:
    @pytest.mark.parametrize(
        ("frame", "seconds"),
        [
            pytest.param("08a038", 7200, id="what the switch writes: 120 minutes"),
            pytest.param("08ac02", 300, id="five minutes"),
            pytest.param("", 0, id="no hold set: the vehicle sends nothing"),
        ],
    )
    def test_a_frame_becomes_the_number_of_seconds(
        self, frame: str, seconds: int
    ) -> None:
        data = _deliver(_coordinator(), bytes.fromhex(frame))
        assert data[FIELD]["value"] == seconds
        assert type(data[FIELD]["value"]) is int

    def test_no_hold_reads_zero_not_unknown(self) -> None:
        """An empty payload is the vehicle saying "none", which is an answer."""
        data = _deliver(_coordinator(), b"")
        assert FIELD in data
        assert data[FIELD]["value"] == 0

    def test_clearing_a_hold_replaces_the_old_duration(self) -> None:
        coordinator = _coordinator()
        coordinator.data = _deliver(coordinator, bytes.fromhex("08a038"))
        assert _deliver(coordinator, b"")[FIELD]["value"] == 0
