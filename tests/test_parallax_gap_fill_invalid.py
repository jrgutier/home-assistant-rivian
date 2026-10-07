"""An unusable subscription value must not block a usable Parallax one.

The gap-fill rule is "the subscription wins; Parallax fills gaps". Until s51 a
key counted as the subscription's as soon as it delivered ANY non-null value,
and `signal_not_available` is non-null. So the gateway saying "I have nothing"
beat Parallax saying `closed`.

Seen on the live host on 2026-10-06, after a restart: the subscription's first
frame carried `signal_not_available` for closureSideBinLeftClosed,
closureSideBinRightClosed and closureTailgateClosed. `body.closures.states`
then arrived six times with all three `closed`, was discarded six times, and the
three binary sensors read unknown for 28 minutes -- until the subscription
happened to send a real value.

The existing provenance tests are in tests/test_parallax_gap_fill.py and are
unchanged; this file is the invalid-value case they did not cover.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.rivian.const import INVALID_SENSOR_STATES
from custom_components.rivian.coordinator import VehicleCoordinator

STUCK_ON_THE_HOST = (
    "closureSideBinLeftClosed",
    "closureSideBinRightClosed",
    "closureTailgateClosed",
)


def _coordinator() -> MagicMock:
    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator.data = None
    coordinator._subscription_keys = set()
    coordinator._rvm_arrivals = {}
    coordinator._note_unusable = MagicMock()
    coordinator.charging_coordinator = MagicMock()
    coordinator.vehicle_id = "veh-1"
    coordinator.async_set_updated_data = MagicMock()
    return coordinator


def _subscription(coordinator: MagicMock, frame: dict) -> None:
    """Apply a vehicleState frame the way the real stream does."""
    coordinator.data = VehicleCoordinator._build_vehicle_info_dict(coordinator, frame)


def _parallax(coordinator: MagicMock, decoded: dict) -> None:
    """Drive the real _process_parallax_data with an already-decoded payload."""
    coordinator.async_set_updated_data.reset_mock()
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
                        "parallaxMessages": {
                            "rvm": "body.closures.states",
                            "payload": "",
                            "timestamp": 0,
                        }
                    }
                }
            },
        )
    if coordinator.async_set_updated_data.called:
        coordinator.data = coordinator.async_set_updated_data.call_args[0][0]


def _wrapped(value: object) -> dict:
    return {"timeStamp": "t0", "value": value}


class TestTheIncident:
    """The exact sequence from the host, one field at a time."""

    @pytest.mark.parametrize("field", STUCK_ON_THE_HOST)
    def test_parallax_fills_a_key_the_subscription_only_called_unavailable(
        self, field: str
    ) -> None:
        coordinator = _coordinator()
        _subscription(coordinator, {field: _wrapped("signal_not_available")})
        assert field not in coordinator._subscription_keys

        _parallax(coordinator, {field: "closed"})
        assert coordinator.data[field]["value"] == "closed"

    @pytest.mark.parametrize("field", STUCK_ON_THE_HOST)
    def test_the_sibling_with_a_real_value_is_still_the_subscriptions(
        self, field: str
    ) -> None:
        """The frunk and doors on the same frame: valid, claimed, untouched."""
        coordinator = _coordinator()
        _subscription(
            coordinator,
            {
                field: _wrapped("signal_not_available"),
                "closureFrunkClosed": _wrapped("closed"),
            },
        )
        assert "closureFrunkClosed" in coordinator._subscription_keys

        _parallax(coordinator, {field: "closed", "closureFrunkClosed": "open"})
        assert coordinator.data["closureFrunkClosed"]["value"] == "closed"
        assert coordinator.data[field]["value"] == "closed"


class TestEveryInvalidState:
    @pytest.mark.parametrize("invalid", sorted(INVALID_SENSOR_STATES))
    def test_does_not_claim(self, invalid: str) -> None:
        coordinator = _coordinator()
        _subscription(coordinator, {"closureTailgateClosed": _wrapped(invalid)})
        assert "closureTailgateClosed" not in coordinator._subscription_keys

    @pytest.mark.parametrize("invalid", ["SNA", "Signal_Not_Available", "UNDEFINED"])
    def test_whatever_its_casing(self, invalid: str) -> None:
        """The entities compare case-insensitively; provenance must agree."""
        coordinator = _coordinator()
        _subscription(coordinator, {"closureTailgateClosed": _wrapped(invalid)})
        assert "closureTailgateClosed" not in coordinator._subscription_keys


class TestTheSubscriptionStillWins:
    def test_a_usable_value_claims_and_blocks_parallax(self) -> None:
        coordinator = _coordinator()
        _subscription(coordinator, {"closureTailgateClosed": _wrapped("open")})
        assert "closureTailgateClosed" in coordinator._subscription_keys

        _parallax(coordinator, {"closureTailgateClosed": "closed"})
        assert coordinator.data["closureTailgateClosed"]["value"] == "open"

    def test_a_usable_value_takes_the_key_back_from_parallax(self) -> None:
        """Invalid, Parallax fills, then the gateway finds its voice."""
        coordinator = _coordinator()
        _subscription(
            coordinator, {"closureTailgateClosed": _wrapped("signal_not_available")}
        )
        _parallax(coordinator, {"closureTailgateClosed": "closed"})
        assert coordinator.data["closureTailgateClosed"]["value"] == "closed"

        _subscription(coordinator, {"closureTailgateClosed": _wrapped("open")})
        assert "closureTailgateClosed" in coordinator._subscription_keys
        assert coordinator.data["closureTailgateClosed"]["value"] == "open"

        _parallax(coordinator, {"closureTailgateClosed": "closed"})
        assert coordinator.data["closureTailgateClosed"]["value"] == "open"


class TestAKeyThatGoesInvalidIsReleased:
    def test_parallax_can_refresh_a_value_the_subscription_stopped_supplying(
        self,
    ) -> None:
        """Valid, then invalid. The merge keeps the last good value on screen;
        without a release nothing could ever update it again."""
        coordinator = _coordinator()
        _subscription(coordinator, {"closureTailgateClosed": _wrapped("closed")})
        _subscription(
            coordinator, {"closureTailgateClosed": _wrapped("signal_not_available")}
        )
        assert coordinator.data["closureTailgateClosed"]["value"] == "closed"
        assert "closureTailgateClosed" not in coordinator._subscription_keys

        _parallax(coordinator, {"closureTailgateClosed": "open"})
        assert coordinator.data["closureTailgateClosed"]["value"] == "open"

    def test_an_invalid_value_never_replaces_what_parallax_supplied(self) -> None:
        coordinator = _coordinator()
        _subscription(
            coordinator, {"closureTailgateClosed": _wrapped("signal_not_available")}
        )
        _parallax(coordinator, {"closureTailgateClosed": "closed"})
        _subscription(
            coordinator, {"closureTailgateClosed": _wrapped("signal_not_available")}
        )
        assert coordinator.data["closureTailgateClosed"]["value"] == "closed"


class TestWhatDidNotChange:
    def test_a_null_value_neither_claims_nor_releases(self) -> None:
        coordinator = _coordinator()
        _subscription(coordinator, {"gearStatus": _wrapped("park")})
        _subscription(coordinator, {"gearStatus": _wrapped(None)})
        assert "gearStatus" in coordinator._subscription_keys

        fresh = _coordinator()
        _subscription(fresh, {"gearStatus": _wrapped(None)})
        assert "gearStatus" not in fresh._subscription_keys

    def test_structured_fields_still_claim_without_a_value_key(self) -> None:
        """gnssLocation must stay claimed, or Parallax overwrites real GPS."""
        coordinator = _coordinator()
        _subscription(
            coordinator,
            {
                "gnssLocation": {"latitude": 1.0, "longitude": 2.0, "timeStamp": "t0"},
                "gnssError": {"positionHorizontal": 1.5, "timeStamp": "t0"},
            },
        )
        assert {"gnssLocation", "gnssError"} <= coordinator._subscription_keys

    def test_an_unrelated_frame_releases_nothing(self) -> None:
        coordinator = _coordinator()
        _subscription(coordinator, {"gearStatus": _wrapped("park")})
        _subscription(coordinator, {"driveMode": _wrapped("signal_not_available")})
        assert "gearStatus" in coordinator._subscription_keys
        assert "driveMode" not in coordinator._subscription_keys
