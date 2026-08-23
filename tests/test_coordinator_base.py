"""Tests for base coordinator functionality."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.coordinator import UserCoordinator, WallboxCoordinator
from custom_components.rivian.rivian_client.exceptions import (
    RivianApiException,
    RivianApiRateLimitError,
    RivianUnauthenticated,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed


def _response(payload: dict, status: int = 200) -> MagicMock:
    """The client's real contract: an object with .status and awaitable .json()."""
    response = MagicMock()
    response.status = status
    response.json = AsyncMock(return_value=payload)
    response.raise_for_status = MagicMock()
    return response


class TestRivianDataUpdateCoordinatorBase:
    """Test base coordinator error handling and interval management."""

    async def test_set_update_interval_doubles_on_error(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that update interval doubles on error."""
        mock_client = MagicMock()
        mock_client.get_user_information = AsyncMock(return_value={})

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )

        # Set initial data without refresh
        coordinator.data = {}
        coordinator.update_interval = timedelta(seconds=300)

        # Initial interval
        initial_interval = coordinator._update_interval_seconds
        assert initial_interval == 300  # 5 minutes

        # Simulate error
        coordinator._error_count = 1
        coordinator._set_update_interval()

        # Should double
        assert coordinator.update_interval.total_seconds() == initial_interval * 2
        await coordinator.async_shutdown()

    async def test_set_update_interval_caps_at_900_seconds(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that update interval caps at 15 minutes."""
        mock_client = MagicMock()

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )

        # Simulate many errors
        coordinator._error_count = 10
        coordinator._set_update_interval()

        # Should cap at 900 seconds (15 minutes)
        assert coordinator.update_interval.total_seconds() == 900

        # Setting an interval schedules a refresh timer. HA 2026.8's verify_cleanup
        # fails the test if it is still pending at teardown; older HA did not check,
        # so these three leaked one on every run.
        await coordinator.async_shutdown()

    async def test_set_update_interval_with_explicit_seconds(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test setting explicit update interval."""
        mock_client = MagicMock()

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )

        coordinator._set_update_interval(seconds=600)

        assert coordinator.update_interval.total_seconds() == 600
        await coordinator.async_shutdown()

    # test_async_update_data_handles_expired_token was deleted in w10 with the
    # handler it covered. It hand-raised RivianExpiredTokenError from a mocked
    # client; nothing in the real client raises it -- ERROR_CODE_CLASS_MAP has no
    # entry producing it -- so it asserted that unreachable code worked, and was the
    # only thing keeping that code alive. The handler also recursed into
    # _async_update_data with no depth guard.

    async def test_async_update_data_handles_rate_limit(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that rate limit increases interval."""
        mock_client = MagicMock()
        mock_client.get_user_information = AsyncMock(
            side_effect=RivianApiRateLimitError("Rate limited")
        )

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator.data = {"userId": "test_user"}  # Existing data

        result = await coordinator._async_update_data()

        # Should return existing data
        assert result == {"userId": "test_user"}
        assert coordinator._error_count == 1

    async def test_async_update_data_handles_unauthenticated(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that unauthenticated raises ConfigEntryAuthFailed."""
        mock_client = MagicMock()
        mock_client.close = AsyncMock()
        mock_client.get_user_information = AsyncMock(
            side_effect=RivianUnauthenticated("Not authenticated")
        )

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )

        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()

        mock_client.close.assert_called_once()

    async def test_async_update_data_handles_api_exception(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that API exception returns existing data."""
        mock_client = MagicMock()
        mock_client.get_user_information = AsyncMock(
            side_effect=RivianApiException("API error")
        )

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator.data = {"userId": "test_user"}

        result = await coordinator._async_update_data()

        assert result == {"userId": "test_user"}
        assert coordinator._error_count == 1

    async def test_async_update_data_handles_unknown_exception(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that unknown exception returns existing data."""
        mock_client = MagicMock()
        mock_client.get_user_information = AsyncMock(side_effect=ValueError("Unknown"))

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator.data = {"userId": "test_user"}

        result = await coordinator._async_update_data()

        assert result == {"userId": "test_user"}
        assert coordinator._error_count == 1

    async def test_async_update_data_raises_on_error_with_no_data(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that error with no existing data raises UpdateFailed."""
        mock_client = MagicMock()
        mock_client.get_user_information = AsyncMock(
            side_effect=RivianApiException("API error")
        )

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    async def test_async_update_data_resets_error_count_on_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that error count resets on successful fetch."""
        mock_client = MagicMock()
        # Mocked at the client's real contract -- a response with .status and an
        # awaitable .json() -- not as an already-unwrapped dict. Mocking the latter
        # is what hid the missing unwrap in _async_update_data until a live boot.
        response = _response({"data": {"currentUser": {"id": "u1"}}})
        mock_client.get_user_information = AsyncMock(return_value=response)

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator._error_count = 5

        await coordinator._async_update_data()

        assert coordinator._error_count == 0


class TestUserCoordinator:
    """Test UserCoordinator functionality."""

    async def test_fetch_data(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test fetching user data."""
        mock_client = MagicMock()
        mock_client.get_user_information = AsyncMock(
            return_value={"userId": "test_user", "email": "test@example.com"}
        )

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )

        data = await coordinator._fetch_data()

        assert data["userId"] == "test_user"
        assert data["email"] == "test@example.com"
        mock_client.get_user_information.assert_called_once()


class TestWallboxCoordinator:
    """Test WallboxCoordinator functionality."""

    async def test_fetch_data_with_wallbox(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test fetching wallbox data."""
        mock_client = MagicMock()
        mock_client.get_registered_wallboxes = AsyncMock(
            return_value=[
                {
                    "wallboxId": "wallbox_123",
                    "power": 11.5,
                    "name": "Home Charger",
                }
            ]
        )

        coordinator = WallboxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )

        data = await coordinator._fetch_data()

        assert len(data) == 1
        assert data[0]["wallboxId"] == "wallbox_123"
        mock_client.get_registered_wallboxes.assert_called_once()

    async def test_fetch_data_no_wallbox(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test fetching wallbox data with no wallboxes."""
        mock_client = MagicMock()
        mock_client.get_registered_wallboxes = AsyncMock(return_value=[])

        coordinator = WallboxCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )

        data = await coordinator._fetch_data()

        assert data == []


class TestCoordinatorGetMethod:
    """Test coordinator get() method."""

    async def test_get_method_returns_value(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get() method returns value from data."""
        mock_client = MagicMock()

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator.data = {"batteryLevel": {"value": 80}}

        # Should return nested value
        result = coordinator.get("batteryLevel.value")
        assert result == 80

    async def test_get_method_returns_none_for_missing(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get() method returns None for missing key."""
        mock_client = MagicMock()

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator.data = {}

        # Should return None for missing key
        result = coordinator.get("nonexistent")
        assert result is None

    async def test_get_method_with_default(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get() method returns default for missing key."""
        mock_client = MagicMock()

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator.data = {}

        # Should return default for missing key
        result = coordinator.get("nonexistent", "default_value")
        assert result == "default_value"


class TestUserCoordinatorMethods:
    """Test UserCoordinator specific methods."""

    async def test_get_vehicles(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get_vehicles method."""
        mock_client = MagicMock()

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator.data = {
            "vehicles": [
                {
                    "id": "v1",
                    "name": "Vehicle 1",
                    "vehicle": {"vin": "VIN1"},
                    "vas": {
                        "vasVehicleId": "vas_v1",
                        "vehiclePublicKey": "key1",
                    },
                },
                {
                    "id": "v2",
                    "name": "Vehicle 2",
                    "vehicle": {"vin": "VIN2"},
                    "vas": {
                        "vasVehicleId": "vas_v2",
                        "vehiclePublicKey": "key2",
                    },
                },
            ]
        }

        vehicles = coordinator.get_vehicles()

        assert len(vehicles) == 2
        assert "v1" in vehicles
        assert vehicles["v1"]["name"] == "Vehicle 1"
        assert vehicles["v1"]["vin"] == "VIN1"
        # S19: no "mobileConfiguration" key at all -- the fragment was rejected
        # and rivian.py's get_user_information() retried without it. None, not
        # [], is what distinguishes that from "asked and got none".
        assert vehicles["v1"]["option_codes"] is None

    async def test_get_vehicles_option_codes_populated(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """S19: the fragment was accepted and the vehicle has a powered
        tonneau -- option_codes is the flat list get_vehicles() builds for the
        containment check ("TON-P01" in option_codes), never equality."""
        mock_client = MagicMock()
        coordinator = UserCoordinator(
            hass=hass, config_entry=mock_config_entry, client=mock_client
        )
        coordinator.data = {
            "vehicles": [
                {
                    "id": "v1",
                    "name": "Vehicle 1",
                    "vehicle": {
                        "vin": "VIN1",
                        "mobileConfiguration": {
                            "tonneauOption": {
                                "optionId": "TON-P01",
                                "optionName": "Power Tonneau Cover",
                            },
                            "wheelOption": {
                                "optionId": "WHL-A01",
                                "optionName": "20in All-Terrain",
                            },
                        },
                    },
                    "vas": {"vasVehicleId": "vas_v1", "vehiclePublicKey": "key1"},
                }
            ]
        }

        option_codes = coordinator.get_vehicles()["v1"]["option_codes"]

        assert option_codes == ["TON-P01", "WHL-A01"]
        assert "TON-P01" in option_codes

    async def test_get_vehicles_option_codes_accepted_but_empty(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """S19: the fragment was accepted but this vehicle has neither option
        -- [] means "asked and got none", distinguishable from None ("never
        asked", tested above)."""
        mock_client = MagicMock()
        coordinator = UserCoordinator(
            hass=hass, config_entry=mock_config_entry, client=mock_client
        )
        coordinator.data = {
            "vehicles": [
                {
                    "id": "v1",
                    "name": "Vehicle 1",
                    "vehicle": {
                        "vin": "VIN1",
                        "mobileConfiguration": {
                            "tonneauOption": None,
                            "wheelOption": None,
                        },
                    },
                    "vas": {"vasVehicleId": "vas_v1", "vehiclePublicKey": "key1"},
                }
            ]
        }

        option_codes = coordinator.get_vehicles()["v1"]["option_codes"]

        assert option_codes == []
        assert option_codes is not None

    async def test_get_enrolled_phone_data_no_phones(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test get_enrolled_phone_data with no enrolled phones."""
        mock_client = MagicMock()

        coordinator = UserCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=mock_client,
        )
        coordinator.data = {}

        result = coordinator.get_enrolled_phone_data("test_key")

        assert result is None


class TestTheResponseIsUnwrapped:
    """The client returns aiohttp ClientResponse objects, not dicts.

    Every coordinator that relies on the base _async_update_data must therefore
    check the status, await .json(), and pull data["data"][key] out. Upstream does
    exactly that; the s05 merge dropped it, and nothing failed, because the tests
    mock self.api.get_*() as already-returning the unwrapped dict -- the wrong
    boundary. The integration then died on the first real boot with
    'HassClientResponse' object has no attribute 'get' at __init__.py:81.

    These tests mock at the client's real contract: an object with .status and an
    awaitable .json(). That is the only shape that can distinguish a coordinator
    which unwraps from one which does not.
    """

    async def test_user_coordinator_returns_the_inner_object(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        client = MagicMock()
        client.get_user_information = AsyncMock(
            return_value=_response(
                {"data": {"currentUser": {"id": "u1", "vehicles": []}}}
            )
        )
        coordinator = UserCoordinator(
            hass=hass, config_entry=mock_config_entry, client=client
        )
        data = await coordinator._async_update_data()

        # The equality is what kills a revert; `hasattr(data, "get")` looked like a
        # check for the production failure (.get on a ClientResponse) but MagicMock
        # synthesises .get, so it held either way. Removed rather than kept as
        # decoration.
        assert data == {"id": "u1", "vehicles": []}

    async def test_a_non_200_does_not_silently_become_data(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """Returning the response object on an error status is how a 500 turns into
        entities holding a ClientResponse instead of an error."""
        response = _response({"errors": [{"message": "boom"}]}, status=500)
        response.raise_for_status = MagicMock(side_effect=RuntimeError("500"))
        client = MagicMock()
        client.get_user_information = AsyncMock(return_value=response)

        coordinator = UserCoordinator(
            hass=hass, config_entry=mock_config_entry, client=client
        )
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

        # The status must be acted on. Returning the response object instead is how
        # a 500 ends up in entity state as a ClientResponse.
        response.raise_for_status.assert_called_once()

    async def test_wallbox_coordinator_returns_the_inner_list(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        client = MagicMock()
        client.get_registered_wallboxes = AsyncMock(
            return_value=_response(
                {"data": {"getRegisteredWallboxes": [{"serialNumber": "W1"}]}}
            )
        )
        coordinator = WallboxCoordinator(
            hass=hass, config_entry=mock_config_entry, client=client
        )
        assert await coordinator._async_update_data() == [{"serialNumber": "W1"}]

    async def test_driver_key_coordinator_returns_the_inner_object(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        from custom_components.rivian.coordinator import DriverKeyCoordinator

        client = MagicMock()
        client.get_drivers_and_keys = AsyncMock(
            return_value=_response({"data": {"getVehicle": {"invitedUsers": []}}})
        )
        coordinator = DriverKeyCoordinator(
            hass=hass, config_entry=mock_config_entry, client=client, vehicle_id="v1"
        )
        assert await coordinator._async_update_data() == {"invitedUsers": []}

    async def test_vehicle_image_coordinator_returns_the_inner_list(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        from custom_components.rivian.coordinator import VehicleImageCoordinator

        client = MagicMock()
        client.get_vehicle_images = AsyncMock(
            return_value=_response(
                {"data": {"getVehicleMobileImages": [{"url": "https://x/y.png"}]}}
            )
        )
        coordinator = VehicleImageCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=client,
            version="1",
        )
        assert await coordinator._async_update_data() == [{"url": "https://x/y.png"}]


class TestInvalidStatesArePublishedNotSuppressed:
    """A value the vehicle flags unusable is still published when there is nothing
    better, and never overwrites a good previous value.

    Suppressing it was tried and reverted. It sounds more honest -- an entity that
    says "unavailable" beats one showing a stale reading -- but on a real R1T the
    vehicle reports SNA at startup for the climate hold switch, both front seat
    climate selects, the alarm, charging enabled, steering wheel heating and the
    charge limit. Fifteen-plus entities went unavailable and stayed that way until
    a good value happened to arrive, which for a parked vehicle can be hours.

    So: publish it, and keep the substitution that matters -- once a good value
    exists, a later SNA must not clobber it.
    """

    @staticmethod
    def _coordinator(hass: HomeAssistant, entry: ConfigEntry):
        from custom_components.rivian.coordinator import VehicleCoordinator

        return VehicleCoordinator(
            hass=hass, config_entry=entry, client=MagicMock(), vehicle_id="v1"
        )

    def test_an_invalid_first_value_is_still_published(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        coordinator = self._coordinator(hass, mock_config_entry)
        coordinator.data = None
        result = coordinator._build_vehicle_info_dict(
            {"seatRearLeftHeat": {"value": "SNA"}}
        )
        assert "seatRearLeftHeat" in result

    def test_a_new_key_arriving_invalid_is_still_published(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """self.data being non-empty does not mean THIS key has a previous value:
        Parallax populates other keys first. Such a key must not vanish."""
        coordinator = self._coordinator(hass, mock_config_entry)
        coordinator.data = {"powerState": {"value": "ready", "history": {"ready"}}}
        result = coordinator._build_vehicle_info_dict(
            {"seatRearLeftHeat": {"value": "SNA"}}
        )
        assert "seatRearLeftHeat" in result
        assert result["powerState"]["value"] == "ready"

    def test_a_good_previous_value_survives_a_later_invalid_one(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """The guard that earns its keep: SNA must not clobber a real reading."""
        coordinator = self._coordinator(hass, mock_config_entry)
        coordinator.data = {
            "seatRearLeftHeat": {"value": "Level 2", "history": {"Level 2"}}
        }
        result = coordinator._build_vehicle_info_dict(
            {"seatRearLeftHeat": {"value": "SNA"}}
        )
        assert result["seatRearLeftHeat"]["value"] == "Level 2"

    def test_sna_counts_as_invalid(self) -> None:
        """The vehicle's abbreviation, not just the long form."""
        from custom_components.rivian.const import INVALID_SENSOR_STATES

        assert "sna" in INVALID_SENSOR_STATES

    def test_a_valid_first_value_is_kept(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        coordinator = self._coordinator(hass, mock_config_entry)
        coordinator.data = None
        result = coordinator._build_vehicle_info_dict(
            {"seatRearLeftHeat": {"value": "Level 1"}}
        )
        assert result["seatRearLeftHeat"]["value"] == "Level 1"


class TestAMissingKeyFailsLoudly:
    """A renamed or withdrawn top-level field must not present stale data as fresh.

    The miss used to land in the broad `except Exception`, which returns self.data,
    so entities kept their last good values with last_update_success still True --
    visible only as one ERROR line per poll.
    """

    async def test_a_missing_key_raises_update_failed(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        response = _response({"data": {"somethingElse": {}}})
        client = MagicMock()
        client.get_user_information = AsyncMock(return_value=response)

        coordinator = UserCoordinator(
            hass=hass, config_entry=mock_config_entry, client=client
        )
        coordinator.data = {"id": "stale"}
        with pytest.raises(UpdateFailed, match="currentUser"):
            await coordinator._async_update_data()

    async def test_a_null_data_block_raises_update_failed(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """GraphQL may answer 200 with data: null alongside errors."""
        response = _response({"data": None, "errors": [{"message": "nope"}]})
        client = MagicMock()
        client.get_user_information = AsyncMock(return_value=response)

        coordinator = UserCoordinator(
            hass=hass, config_entry=mock_config_entry, client=client
        )
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


class TestOtaReleaseNotesUrl:
    """The OTA release-notes URL is unwrapped by the coordinator, not the entity.

    The update entity used to await .json() on the client's response and index
    ["data"]["getVehicle"] itself. Moving that here is only safe if the branch
    preference it encodes -- pending update wins, current update is the fallback
    -- stays pinned somewhere, and the entity tests can no longer pin it because
    they mock this method.
    """

    def _coordinator(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry, payload
    ):
        from custom_components.rivian.coordinator import VehicleCoordinator

        client = MagicMock()
        client.get_vehicle_ota_update_details = AsyncMock(
            return_value=_response(payload)
        )
        return VehicleCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            client=client,
            vehicle_id="v1",
        )

    async def test_pending_update_url_wins(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        coordinator = self._coordinator(
            hass,
            mock_config_entry,
            {
                "data": {
                    "getVehicle": {
                        "availableOTAUpdateDetails": {
                            "url": "https://rivian.software/2024-04-0/"
                        },
                        "currentOTAUpdateDetails": {
                            "url": "https://rivian.software/2024-03-0/"
                        },
                    }
                }
            },
        )

        assert (
            await coordinator.get_ota_release_notes_url()
            == "https://rivian.software/2024-04-0/"
        )
        coordinator.api.get_vehicle_ota_update_details.assert_awaited_once_with("v1")

    async def test_falls_back_to_the_current_update(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """No pending update: the API sends availableOTAUpdateDetails as null."""
        coordinator = self._coordinator(
            hass,
            mock_config_entry,
            {
                "data": {
                    "getVehicle": {
                        "availableOTAUpdateDetails": None,
                        "currentOTAUpdateDetails": {
                            "url": "https://rivian.software/2024-03-0/"
                        },
                    }
                }
            },
        )

        assert (
            await coordinator.get_ota_release_notes_url()
            == "https://rivian.software/2024-03-0/"
        )

    async def test_a_missing_envelope_raises_for_the_entity_to_catch(
        self, hass: HomeAssistant, mock_config_entry: ConfigEntry
    ) -> None:
        """The entity's fallback to the generated URL depends on this raising."""
        coordinator = self._coordinator(hass, mock_config_entry, {"data": {}})

        with pytest.raises(KeyError):
            await coordinator.get_ota_release_notes_url()
