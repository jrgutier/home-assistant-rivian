"""A structured field must not crash the frame merge.

Regression for a defect that shipped in 1.6.0-beta13 and was found only by
running it against a real vehicle:

    File "custom_components/rivian/coordinator.py", in _build_vehicle_info_dict
        new_data[key]["history"] |= prev_items.get(key, {}).get("history", set())
    KeyError: 'history'

`_build_vehicle_info_dict` attaches "history" only when a field carries a
top-level "value". Structured fields do not. `gnssLocation` is filtered out of
the merge loop, so while it was the only structured field on the wire the
missing key was unreachable. s18's field-parity work put `gnssError` on the
wire -- also structured, and NOT filtered -- so every frame carrying it raised.

This is why the test matters beyond the one field: the gateway may add another
structured field at any time, and the fix guards on presence rather than
extending the `gnssLocation` filter.

Note what did NOT catch this: 1845 unit tests, six gates, and a live gateway
probe that accepted the 137-field document. The probe verifies what the wire
accepts, not what the coordinator does with the frame.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.rivian.coordinator import VehicleCoordinator


def _coordinator(previous: dict) -> MagicMock:
    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator.data = previous
    coordinator._subscription_keys = set()
    coordinator._note_unusable = MagicMock()
    coordinator.vehicle_id = "veh-1"
    return coordinator


GNSS_ERROR = {
    "__typename": "GnssError",
    "positionVertical": 1.5,
    "positionHorizontal": 2.5,
    "speed": 0.1,
    "bearing": 3.0,
}


def _frame(**fields: dict) -> dict:
    return dict(fields)


class TestStructuredFieldSurvivesTheMerge:
    """The steady-state merge path, which is where the crash lived."""

    def test_gnss_error_does_not_raise_on_a_steady_state_frame(self) -> None:
        """The exact live failure: a second frame carrying gnssError."""
        previous = {"batteryLevel": {"value": 70, "history": {70}}}
        coordinator = _coordinator(previous)

        merged = VehicleCoordinator._build_vehicle_info_dict(
            coordinator,
            _frame(batteryLevel={"value": 71}, gnssError=GNSS_ERROR),
        )

        assert merged["gnssError"] == GNSS_ERROR
        assert "history" not in merged["gnssError"]

    def test_a_valued_field_still_accumulates_history(self) -> None:
        """The guard must not cost valued fields their history merge."""
        previous = {"batteryLevel": {"value": 70, "history": {70}}}
        coordinator = _coordinator(previous)

        merged = VehicleCoordinator._build_vehicle_info_dict(
            coordinator,
            _frame(batteryLevel={"value": 71}, gnssError=GNSS_ERROR),
        )

        assert merged["batteryLevel"]["history"] == {70, 71}

    def test_an_unknown_structured_field_also_survives(self) -> None:
        """Guarding on presence, not on a name, is the point of the fix."""
        previous = {"batteryLevel": {"value": 70, "history": {70}}}
        coordinator = _coordinator(previous)

        merged = VehicleCoordinator._build_vehicle_info_dict(
            coordinator,
            _frame(
                batteryLevel={"value": 71},
                someFutureStructuredField={"__typename": "X", "a": 1},
            ),
        )

        assert merged["someFutureStructuredField"] == {"__typename": "X", "a": 1}
