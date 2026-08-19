"""A binary sensor must not report a vehicle error code as a confident state.

`sensor.py` already refuses to publish `fault` / `sna` / `signal_not_available` /
`undefined` as a sensor state. Binary sensors did not, and their failure is worse
than a sensor's: a sensor showing `SNA` at least looks wrong, whereas
`doorFrontLeftLocked = "signal_not_available"` simply is not equal to `"locked"`,
so the entity reports a confident **Unlocked** for a door whose lock state the
vehicle has just said it does not know.

The distinction this file holds onto is `unknown` vs `unavailable`. Returning
`None` from `is_on` yields `unknown`; it does **not** change availability, which
`RivianVehicleEntity.available` derives purely from the field being present
(`entity.py:64-68`). That is deliberate. Making the entity unavailable instead
would take the matching *control* down with it -- the mistake that was made, and
reverted, in the coordinator twice.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.rivian.binary_sensor import (
    RivianBinarySensorEntity,
    async_setup_entry,
)
from custom_components.rivian.const import (
    ATTR_COORDINATOR,
    ATTR_VEHICLE,
    BINARY_SENSORS,
    DOMAIN,
    INVALID_SENSOR_STATES,
)
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.data_classes import RivianBinarySensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

VEHICLE = {
    "id": "veh-1",
    "vin": "TESTVIN0000000001",
    "name": "Test R1T",
    "model": "R1T",
}


def _entity(
    config_entry: ConfigEntry,
    value: object,
    *,
    on_value: object = "locked",
    negate: bool = False,
) -> RivianBinarySensorEntity:
    """Build one binary sensor over a single field holding `value`."""
    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator.get = MagicMock(return_value=value)
    coordinator.data = {}
    description = RivianBinarySensorEntityDescription(
        key="door_front_left_lock",
        translation_key="door_front_left_lock",
        field="doorFrontLeftLocked",
        on_value=on_value,
        negate=negate,
    )
    return RivianBinarySensorEntity(
        coordinator=coordinator,
        config_entry=config_entry,
        description=description,
        vehicle=VEHICLE,
    )


@pytest.mark.parametrize("invalid", sorted(INVALID_SENSOR_STATES))
async def test_invalid_value_reports_unknown_not_a_confident_state(
    hass: HomeAssistant, mock_config_entry: ConfigEntry, invalid: str
) -> None:
    """Every value in INVALID_SENSOR_STATES makes is_on None, never False.

    `False` is the dangerous answer: for a lock it renders as Unlocked.
    """
    entity = _entity(mock_config_entry, invalid)
    assert entity.is_on is None, (
        f"{invalid!r} produced {entity.is_on!r}; a value the vehicle flags as "
        "unusable must not become a confident binary state"
    )


@pytest.mark.parametrize("invalid", sorted(INVALID_SENSOR_STATES))
async def test_invalid_value_is_matched_case_insensitively(
    hass: HomeAssistant, mock_config_entry: ConfigEntry, invalid: str
) -> None:
    """The vehicle reports these upper-cased on the wire -- a literal 'SNA'."""
    entity = _entity(mock_config_entry, invalid.upper())
    assert entity.is_on is None


async def test_negate_does_not_resurrect_an_invalid_value(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """`negate` must not turn an unusable value into a confident True.

    Filtering after the negation would do exactly that: `not False` is `True`.
    """
    entity = _entity(mock_config_entry, "signal_not_available", negate=True)
    assert entity.is_on is None


async def test_the_entity_stays_available_it_only_goes_unknown(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """unknown, NOT unavailable.

    This is the whole point of filtering here rather than in the coordinator.
    Availability is driven by the field being *present*; the value keeps flowing
    so the matching control stays operable.
    """
    entity = _entity(mock_config_entry, "sna")
    assert entity.is_on is None
    assert entity.available is True


@pytest.mark.parametrize(
    ("value", "on_value", "negate", "expected"),
    [
        ("locked", "locked", False, True),
        ("unlocked", "locked", False, False),
        ("locked", "locked", True, False),
        ("unlocked", "locked", True, True),
        ("open", ["open", "ajar"], False, True),
        ("closed", ["open", "ajar"], False, False),
    ],
)
async def test_usable_values_are_untouched(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
    value: str,
    on_value: object,
    negate: bool,
    expected: bool,
) -> None:
    """Regression guard: the filter must not change any ordinary resolution."""
    entity = _entity(mock_config_entry, value, on_value=on_value, negate=negate)
    assert entity.is_on is expected


class TestAggregateUnchanged:
    """Aggregate binary sensors must behave EXACTLY as before.

    `binary_sensor.py:79-82` already ignores unusable values structurally -- an
    aggregate asks whether `on_value` appears among its members, and `"sna"` is
    simply not `"open"`. Adding a filter to that branch would change `available`,
    because the aggregate's availability is `any(member values)`.
    """

    @staticmethod
    def _aggregate(
        config_entry: ConfigEntry, values: dict[str, object]
    ) -> RivianBinarySensorEntity:
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(side_effect=values.get)
        coordinator.data = {}
        description = RivianBinarySensorEntityDescription(
            key="closures",
            translation_key="closures",
            field=set(values),
            on_value="open",
        )
        return RivianBinarySensorEntity(
            coordinator=coordinator,
            config_entry=config_entry,
            description=description,
            vehicle=VEHICLE,
        )

    async def test_one_member_open_among_unusable_ones_is_still_on(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        entity = self._aggregate(
            mock_config_entry,
            {"a": "open", "b": "sna", "c": "closed"},
        )
        assert entity.is_on is True
        assert entity.available is True

    async def test_all_members_unusable_is_off_and_still_available(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Unchanged behaviour, asserted so a later refactor cannot drift it.

        `"sna"` is a truthy value, so `any()` holds and the aggregate stays
        available while reporting off. That is the pre-existing contract.
        """
        entity = self._aggregate(mock_config_entry, {"a": "sna", "b": "fault"})
        assert entity.is_on is False
        assert entity.available is True

    async def test_no_member_reports_at_all_is_unavailable(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        entity = self._aggregate(mock_config_entry, {"a": None, "b": None})
        assert entity.available is False


async def test_filter_is_reachable_on_a_first_update_with_no_history(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The filter must be exercised by the path that actually publishes SNA.

    `VehicleCoordinator._build_vehicle_info_dict` carries a previous good value
    forward whenever a field reports an unusable one (`coordinator.py:1224-1242`),
    so a field that has *ever* reported well never reaches the binary sensor with
    a bad value. Only the first update -- empty history, no previous data -- passes
    one through. A test built on a hand-made coordinator dict would pass without
    proving the filter is reachable at all; this one drives the real merge.
    """
    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator.data = None
    coordinator._note_unusable = MagicMock()
    # Assigned in __init__, so a spec'd mock raises AttributeError for it.
    coordinator._subscription_keys = set()
    coordinator.charging_coordinator = MagicMock()
    coordinator.vehicle_id = "veh-1"
    coordinator._awake = MagicMock()

    merged = VehicleCoordinator._build_vehicle_info_dict(
        coordinator, {"doorFrontLeftLocked": {"value": "SNA", "timeStamp": "t0"}}
    )

    # The coordinator deliberately publishes it: dropping it here makes the
    # matching control unavailable, which was tried and reverted.
    assert merged["doorFrontLeftLocked"]["value"] == "SNA"
    coordinator._note_unusable.assert_called_once()

    # And the binary sensor is what refuses to call that a state.
    real = MagicMock(spec=VehicleCoordinator)
    real.get = MagicMock(return_value=merged["doorFrontLeftLocked"]["value"])
    real.data = merged
    entity = RivianBinarySensorEntity(
        coordinator=real,
        config_entry=mock_config_entry,
        description=RivianBinarySensorEntityDescription(
            key="door_front_left_lock",
            translation_key="door_front_left_lock",
            field="doorFrontLeftLocked",
            on_value="locked",
        ),
        vehicle=VEHICLE,
    )
    assert entity.is_on is None
    assert entity.available is True


async def test_the_entity_set_is_exactly_what_binary_sensors_declares(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """This story changes a value, never a set.

    A snapshot taken *within* one commit cannot compare against a past tree, so
    the honest invariant is that the platform still creates exactly the entities
    `BINARY_SENSORS` declares for this model, plus the one cloud-connection
    sensor. That breaks if this story ever starts dropping entities instead of
    values -- which is the failure it is guarding against.

    The committed cross-model fixture belongs to f3a, not here: f3b-a adds the
    tonneau cover before f3a runs, so a committed snapshot taken now would go red
    at the very next story with no legal move under the stop rule.
    """
    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator.get = MagicMock(return_value="closed")
    coordinator.data = {}
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            ATTR_VEHICLE: {"veh-1": VEHICLE},
            ATTR_COORDINATOR: {ATTR_VEHICLE: {"veh-1": coordinator}},
        }
    }

    added: list = []
    await async_setup_entry(hass, mock_config_entry, lambda e: added.extend(e))

    expected = 1 + sum(
        len(descriptions)
        for model, descriptions in BINARY_SENSORS.items()
        if model in VEHICLE["model"]
    )
    assert len(added) == expected
    assert sum(1 for e in added if e.unique_id.endswith("-cloud_connected")) == 1
