"""The one server-verified Parallax write, wired to a real entity.

Two defects this closes:

* The switch read `cabinHoldStatus` while writing through a different mechanism
  entirely. Both fields are real, but read and write came from different sources
  -- the same split that produced the two-writer conflict in ChargingCoordinator.
  They now share the Parallax source.

* It wrote via VehicleCommand.CLIMATE_HOLD_ON/OFF. The verified path is the
  Parallax climate_hold_setting write, captured live: 5 minutes encodes as
  08ac02 = 300 seconds, and clearing it writes 0.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_USER, DOMAIN
from custom_components.rivian.coordinator import VehicleCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

PHONE_UUID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def coordinator(hass: HomeAssistant, mock_config_entry: ConfigEntry):
    api = MagicMock()
    api.set_climate_hold = AsyncMock(return_value={"success": True})
    c = VehicleCoordinator(
        hass=hass, config_entry=mock_config_entry, client=api, vehicle_id="01-2769"
    )
    user = MagicMock()
    user.get_enrolled_phone_data = MagicMock(return_value=(PHONE_UUID, {}))
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {ATTR_COORDINATOR: {ATTR_USER: user}}
    }
    return c


class TestTheWrite:
    async def test_setting_a_hold_sends_the_duration(self, coordinator) -> None:
        await coordinator.async_set_climate_hold(5)
        kwargs = coordinator.api.set_climate_hold.await_args.kwargs
        assert kwargs["duration_minutes"] == 5
        assert kwargs["vehicle_id"] == "01-2769"

    async def test_the_phone_id_is_16_raw_bytes(self, coordinator) -> None:
        """Confirmed against the live API: uuid.UUID(vasPhoneId).bytes, not the
        36-character string. Nine docstrings in the client said 32 bytes."""
        await coordinator.async_set_climate_hold(5)
        phone_id = coordinator.api.set_climate_hold.await_args.kwargs["phone_id"]
        assert isinstance(phone_id, bytes)
        assert len(phone_id) == 16
        assert phone_id == uuid.UUID(PHONE_UUID).bytes

    async def test_clearing_writes_zero(self, coordinator) -> None:
        # Verified live: writing 0 returns the RVM to an empty payload.
        await coordinator.async_set_climate_hold(0)
        assert (
            coordinator.api.set_climate_hold.await_args.kwargs["duration_minutes"] == 0
        )

    async def test_a_missing_enrolled_phone_is_reported(
        self, coordinator, hass, mock_config_entry
    ) -> None:
        from homeassistant.exceptions import HomeAssistantError

        user = hass.data[DOMAIN][mock_config_entry.entry_id][ATTR_COORDINATOR][
            ATTR_USER
        ]
        user.get_enrolled_phone_data = MagicMock(return_value=None)
        with pytest.raises(HomeAssistantError):
            await coordinator.async_set_climate_hold(5)


class TestTheSwitchReadsDecodedData:
    def _description(self):
        from custom_components.rivian.switch import SWITCHES

        return next(d for d in SWITCHES if d.key == "cabin_climate_hold")

    def test_it_reads_the_parallax_field_by_choice(self) -> None:
        """Both fields are real: cabinHoldStatus IS requested by the subscription.

        Reading the Parallax one is deliberate, so that the read and the write
        share a single source -- splitting them is what produced the two-writer
        conflict in ChargingCoordinator. This test exists because the first
        version of this change justified itself with the claim that
        cabinHoldStatus was never populated, which was false.
        """
        from custom_components.rivian.const import VEHICLE_STATE_API_FIELDS

        assert "cabinHoldStatus" in VEHICLE_STATE_API_FIELDS

        coordinator = MagicMock()
        coordinator.get = lambda key, default=None: {"climateHoldStatus": "on"}.get(
            key, default
        )
        assert self._description().is_on(coordinator) is True

    def test_it_reports_off_when_the_hold_is_off(self) -> None:
        coordinator = MagicMock()
        coordinator.get = lambda key, default=None: {"climateHoldStatus": "off"}.get(
            key, default
        )
        assert self._description().is_on(coordinator) is False

    def test_it_writes_through_parallax_not_a_vehicle_command(self) -> None:
        d = self._description()
        assert d.command_on is None and d.command_off is None
        assert d.turn_on is not None and d.turn_off is not None


class TestListValuedParallaxFields:
    async def test_a_list_field_does_not_crash_the_router(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """decode_vehicle_wheels returns a LIST. The router wrapped every value as
        {"value": x, "history": {x}}, and a set of a list raises
        `unhashable type: 'list'` -- which would kill the whole Parallax message,
        not just that field."""
        api = MagicMock()
        c = VehicleCoordinator(
            hass=hass, config_entry=mock_config_entry, client=api, vehicle_id="v1"
        )
        c.async_set_updated_data = MagicMock(
            side_effect=lambda d: setattr(c, "data", d)
        )
        c.charging_coordinator.update_from_parallax = MagicMock()
        with patch(
            "custom_components.rivian.coordinator.decode_parallax_message",
            return_value={"wheels": [{"wheelPackage": 1}], "wheelsInstalled": 1},
        ):
            c._process_parallax_data(
                {
                    "payload": {
                        "data": {"parallaxMessages": {"rvm": "r", "payload": "x"}}
                    }
                }
            )
        assert c.get("wheelsInstalled") == 1
        assert c.get("wheels") == [{"wheelPackage": 1}]
