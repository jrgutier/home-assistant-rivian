"""Tests for Rivian integration initialization."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.rivian import (
    async_remove_config_entry_device,
    async_remove_entry,
    async_setup_entry,
    async_unload_entry,
    update_listener,
)
from custom_components.rivian.const import (
    ATTR_API,
    ATTR_COORDINATOR,
    ATTR_USER,
    ATTR_VEHICLE,
    ATTR_WALLBOX,
    DOMAIN,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceEntry


@pytest.fixture
def mock_rivian_api():
    """Return a mocked Rivian API client."""
    api = MagicMock()
    api.create_csrf_token = AsyncMock()
    api.close = AsyncMock()
    api.disenroll_phone = AsyncMock()
    return api


@pytest.fixture
def mock_user_coordinator():
    """Return a mocked UserCoordinator."""
    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.data = {
        "registrationChannels": ["SMS"],
        "enrolledPhones": [],
    }
    coordinator.get_vehicles = MagicMock(
        return_value={
            "test_vehicle_123": {
                "id": "test_vehicle_123",
                "vin": "TEST123456789",
                "name": "Test R1T",
                "vas_id": "test_vas_id",
                "public_key": "test_vehicle_public_key",
            }
        }
    )
    coordinator.get_enrolled_phone_data = MagicMock(return_value=None)
    return coordinator


@pytest.fixture
def mock_vehicle_coordinator():
    """Return a mocked VehicleCoordinator."""
    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.data = {"powerState": {"value": "go"}}
    coordinator.charging_coordinator = MagicMock()
    coordinator.charging_coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.drivers_coordinator = MagicMock()
    coordinator.drivers_coordinator.async_config_entry_first_refresh = AsyncMock()
    # Added in f3e62e3 alongside ParallaxCoordinator; the fixture was never updated,
    # so __init__.py:110 awaited a plain MagicMock.
    coordinator.parallax_coordinator = MagicMock()
    coordinator.parallax_coordinator.async_config_entry_first_refresh = AsyncMock()
    return coordinator


@pytest.fixture
def mock_wallbox_coordinator():
    """Return a mocked WallboxCoordinator."""
    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.data = []
    return coordinator


class TestAsyncSetupEntry:
    """Test async_setup_entry function."""

    async def test_setup_entry_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_rivian_api,
        mock_user_coordinator,
        mock_vehicle_coordinator,
        mock_wallbox_coordinator,
    ) -> None:
        """Test successful setup of config entry."""
        with (
            patch(
                "custom_components.rivian.get_rivian_api_from_entry",
                return_value=mock_rivian_api,
            ),
            patch(
                "custom_components.rivian.UserCoordinator",
                return_value=mock_user_coordinator,
            ),
            patch(
                "custom_components.rivian.VehicleCoordinator",
                return_value=mock_vehicle_coordinator,
            ),
            patch(
                "custom_components.rivian.WallboxCoordinator",
                return_value=mock_wallbox_coordinator,
            ),
            patch.object(
                hass.config_entries, "async_forward_entry_setups"
            ) as mock_forward,
        ):
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True
            assert DOMAIN in hass.data
            assert mock_config_entry.entry_id in hass.data[DOMAIN]

            # Verify API client was initialized
            mock_rivian_api.create_csrf_token.assert_called_once()

            # Verify coordinators were refreshed
            mock_user_coordinator.async_config_entry_first_refresh.assert_called_once()
            mock_vehicle_coordinator.async_config_entry_first_refresh.assert_called_once()
            mock_vehicle_coordinator.charging_coordinator.async_config_entry_first_refresh.assert_called_once()
            mock_vehicle_coordinator.drivers_coordinator.async_config_entry_first_refresh.assert_called_once()
            mock_wallbox_coordinator.async_config_entry_first_refresh.assert_called_once()

            # Verify platforms were forwarded
            mock_forward.assert_called_once()

            # Verify data structure
            entry_data = hass.data[DOMAIN][mock_config_entry.entry_id]
            assert ATTR_API in entry_data
            assert ATTR_VEHICLE in entry_data
            assert ATTR_COORDINATOR in entry_data

    async def test_setup_entry_api_error(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test setup fails when API client raises error."""
        mock_api = MagicMock()
        mock_api.create_csrf_token = AsyncMock(side_effect=Exception("API Error"))
        mock_api.close = AsyncMock()

        with (
            patch(
                "custom_components.rivian.get_rivian_api_from_entry",
                return_value=mock_api,
            ),
            pytest.raises(ConfigEntryNotReady),
        ):
            await async_setup_entry(hass, mock_config_entry)

        # Verify API was closed on error
        mock_api.close.assert_called_once()

    async def test_setup_entry_no_vehicle_data(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_rivian_api,
        mock_user_coordinator,
        mock_wallbox_coordinator,
    ) -> None:
        """Test setup fails when vehicle coordinator has no data."""
        # Create vehicle coordinator with no data
        mock_vehicle_coord = MagicMock()
        mock_vehicle_coord.async_config_entry_first_refresh = AsyncMock()
        mock_vehicle_coord.data = None  # No data

        with (
            patch(
                "custom_components.rivian.get_rivian_api_from_entry",
                return_value=mock_rivian_api,
            ),
            patch(
                "custom_components.rivian.UserCoordinator",
                return_value=mock_user_coordinator,
            ),
            patch(
                "custom_components.rivian.VehicleCoordinator",
                return_value=mock_vehicle_coord,
            ),
            patch(
                "custom_components.rivian.WallboxCoordinator",
                return_value=mock_wallbox_coordinator,
            ),
            pytest.raises(ConfigEntryNotReady),
        ):
            await async_setup_entry(hass, mock_config_entry)

    async def test_setup_entry_creates_2fa_issue_when_missing(
        self,
        hass: HomeAssistant,
        mock_rivian_api,
        mock_user_coordinator,
        mock_vehicle_coordinator,
        mock_wallbox_coordinator,
    ) -> None:
        """Test setup creates issue when vehicle control enabled but 2FA missing."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.rivian.const import DOMAIN

        # Create config entry with vehicle control option
        mock_config_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Rivian",
            data={
                "username": "test@example.com",
                "password": "test_password",
            },
            options={"vehicle_control": ["test_vehicle_123"]},
            entry_id="test_entry_id",
        )
        mock_config_entry.add_to_hass(hass)

        # Set coordinator data without registrationChannels (no 2FA)
        mock_user_coordinator.data = {}

        with (
            patch(
                "custom_components.rivian.get_rivian_api_from_entry",
                return_value=mock_rivian_api,
            ),
            patch(
                "custom_components.rivian.UserCoordinator",
                return_value=mock_user_coordinator,
            ),
            patch(
                "custom_components.rivian.VehicleCoordinator",
                return_value=mock_vehicle_coordinator,
            ),
            patch(
                "custom_components.rivian.WallboxCoordinator",
                return_value=mock_wallbox_coordinator,
            ),
            patch("custom_components.rivian.async_create_issue") as mock_create_issue,
            patch.object(hass.config_entries, "async_forward_entry_setups"),
        ):
            result = await async_setup_entry(hass, mock_config_entry)

            assert result is True
            # Verify issue was created
            mock_create_issue.assert_called_once()


class TestAsyncUnloadEntry:
    """Test async_unload_entry function."""

    async def test_unload_entry_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test successful unload of config entry."""
        # Setup entry data
        mock_api = MagicMock()
        mock_api.close = AsyncMock()

        hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {
                ATTR_API: mock_api,
                ATTR_VEHICLE: {},
                ATTR_COORDINATOR: {
                    ATTR_USER: MagicMock(),
                    ATTR_VEHICLE: {},
                    ATTR_WALLBOX: MagicMock(),
                },
            }
        }

        with patch.object(
            hass.config_entries, "async_unload_platforms", return_value=True
        ):
            result = await async_unload_entry(hass, mock_config_entry)

            assert result is True
            # Verify API was closed
            mock_api.close.assert_called_once()
            # Verify entry data was removed
            assert mock_config_entry.entry_id not in hass.data[DOMAIN]

    async def test_unload_entry_platforms_fail(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test unload when platforms fail to unload."""
        # Setup entry data
        mock_api = MagicMock()
        mock_api.close = AsyncMock()

        hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {
                ATTR_API: mock_api,
                ATTR_VEHICLE: {},
                ATTR_COORDINATOR: {},
            }
        }

        with patch.object(
            hass.config_entries, "async_unload_platforms", return_value=False
        ):
            result = await async_unload_entry(hass, mock_config_entry)

            assert result is False
            # API still closed
            mock_api.close.assert_called_once()
            # Entry data NOT removed
            assert mock_config_entry.entry_id in hass.data[DOMAIN]


class TestAsyncRemoveEntry:
    """Test async_remove_entry function."""

    async def test_remove_entry_with_enrolled_phone(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test removal of entry with enrolled phone."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.rivian.const import DOMAIN

        # Create config entry with public key option
        mock_config_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Rivian",
            data={
                "username": "test@example.com",
                "password": "test_password",
            },
            options={"public_key": "test_public_key"},
            entry_id="test_entry_id",
        )
        mock_config_entry.add_to_hass(hass)

        # Mock API and coordinator
        mock_api = MagicMock()
        mock_api.disenroll_phone = AsyncMock()
        mock_api.close = AsyncMock()

        mock_coordinator = MagicMock()
        mock_coordinator.async_config_entry_first_refresh = AsyncMock()
        mock_coordinator.get_enrolled_phone_data = MagicMock(
            return_value=(
                "test_phone_id",
                {"vehicle_123": "identity_123", "vehicle_456": "identity_456"},
            )
        )

        with (
            patch(
                "custom_components.rivian.get_rivian_api_from_entry",
                return_value=mock_api,
            ),
            patch(
                "custom_components.rivian.UserCoordinator",
                return_value=mock_coordinator,
            ),
        ):
            await async_remove_entry(hass, mock_config_entry)

            # Verify phones were disenrolled
            assert mock_api.disenroll_phone.call_count == 2
            mock_api.close.assert_called_once()

    async def test_remove_entry_without_public_key(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test removal of entry without public key."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.rivian.const import DOMAIN

        # Create config entry without public key
        mock_config_entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Rivian",
            data={
                "username": "test@example.com",
                "password": "test_password",
            },
            options={},
            entry_id="test_entry_id",
        )
        mock_config_entry.add_to_hass(hass)

        # Function should complete without errors
        await async_remove_entry(hass, mock_config_entry)


class TestUpdateListener:
    """Test update_listener function."""

    async def test_update_listener_reloads_entry(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that update listener reloads config entry."""
        with patch.object(hass.config_entries, "async_reload") as mock_reload:
            await update_listener(hass, mock_config_entry)

            mock_reload.assert_called_once_with(mock_config_entry.entry_id)


class TestAsyncRemoveConfigEntryDevice:
    """Test async_remove_config_entry_device function."""

    async def test_cannot_remove_vehicle_device(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that vehicle devices cannot be removed."""
        # Setup mock coordinators
        mock_user_coordinator = MagicMock()
        mock_user_coordinator.get_vehicles = MagicMock(return_value={"vehicle_123": {}})

        mock_wallbox_coordinator = MagicMock()
        mock_wallbox_coordinator.data = []

        hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {
                ATTR_COORDINATOR: {
                    ATTR_USER: mock_user_coordinator,
                    ATTR_WALLBOX: mock_wallbox_coordinator,
                }
            }
        }

        # Create device entry for vehicle
        device_entry = MagicMock(spec=DeviceEntry)
        device_entry.identifiers = {(DOMAIN, "vehicle_123")}

        result = await async_remove_config_entry_device(
            hass, mock_config_entry, device_entry
        )

        # Should NOT be able to remove
        assert result is False

    async def test_can_remove_non_vehicle_device(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test that non-vehicle devices can be removed."""
        # Setup mock coordinators
        mock_user_coordinator = MagicMock()
        mock_user_coordinator.get_vehicles = MagicMock(return_value={"vehicle_123": {}})

        mock_wallbox_coordinator = MagicMock()
        mock_wallbox_coordinator.data = []

        hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {
                ATTR_COORDINATOR: {
                    ATTR_USER: mock_user_coordinator,
                    ATTR_WALLBOX: mock_wallbox_coordinator,
                }
            }
        }

        # Create device entry for non-existent device
        device_entry = MagicMock(spec=DeviceEntry)
        device_entry.identifiers = {(DOMAIN, "unknown_device_999")}

        result = await async_remove_config_entry_device(
            hass, mock_config_entry, device_entry
        )

        # Should be able to remove
        assert result is True


class TestTheReportedVersion:
    """const.VERSION is logged at startup with "Please report issues at ...", so a
    stale value puts a version that never existed into every bug report.

    It had drifted: const.py said 1.4.2-beta16 while manifest.json -- the version
    HACS and Home Assistant actually display -- said 1.5.4-beta1. Both release
    workflows rewrite the two together, so they only diverge in the working tree,
    which is exactly where nobody looks.
    """

    def test_const_version_matches_the_manifest(self) -> None:
        import json
        from pathlib import Path

        from custom_components.rivian.const import VERSION

        manifest = json.loads(
            (
                Path(__file__).resolve().parent.parent
                / "custom_components"
                / "rivian"
                / "manifest.json"
            ).read_text()
        )
        assert VERSION == manifest["version"]

    def test_the_version_still_satisfies_the_pre_release_regex(self) -> None:
        """pre-release.yaml parses the manifest version with ^X.Y.Z-betaN$ or
        ^X.Y.Z$ and exits 1 otherwise. Upstream's "0.0.0" matches the second form,
        so a bad merge does not fail the workflow -- it silently publishes
        0.0.0-beta1, sorting below every existing release.
        """
        import json
        from pathlib import Path
        import re

        version = json.loads(
            (
                Path(__file__).resolve().parent.parent
                / "custom_components"
                / "rivian"
                / "manifest.json"
            ).read_text()
        )["version"]
        assert re.fullmatch(r"\d+\.\d+\.\d+(-beta\d+)?", version)
        assert version != "0.0.0", "upstream's placeholder would publish 0.0.0-beta1"


class TestTheSubscriptionFieldList:
    """VEHICLE_STATE_API_FIELDS is derived from every sensor's `field`, so a sensor
    fed by Parallax silently adds its field to the GraphQL subscription query.

    Rivian's gateway rejects the entire subscription on the first unknown field:

        {"type":"error","payload":[{"message":
          "Cannot query field \"wheelsInstalled\" on type \"VehicleState\"."}]}

    and then delivers nothing -- no battery level, no odometer, no tire pressures.
    Observed on a live boot; every unit test passed, because none of them talks to
    the real gateway.
    """

    def test_parallax_only_fields_stay_out_of_the_subscription(self) -> None:
        from custom_components.rivian.const import (
            PARALLAX_ONLY_FIELDS,
            VEHICLE_STATE_API_FIELDS,
        )

        assert PARALLAX_ONLY_FIELDS
        assert not (PARALLAX_ONLY_FIELDS & VEHICLE_STATE_API_FIELDS)

    def test_the_sensor_still_exists_and_still_reads_the_field(self) -> None:
        """Excluding the field from the subscription must not remove the sensor --
        Parallax populates it, so it works; that is why exclusion is the right fix
        rather than deleting the entity."""
        from custom_components.rivian.const import SENSORS

        fields = {
            description.field for sensors in SENSORS.values() for description in sensors
        }
        assert "wheelsInstalled" in fields

    def test_the_sans_tpms_variant_is_still_a_strict_subset(self) -> None:
        """VEHICLE_STATE_SANS_TPMS_API_FIELDS is built with ^, which ADDS any name
        that is not already present. It is only a subtraction while every tyre field
        really is in the base set -- so this asserts the base set, not the operator.
        """
        from custom_components.rivian.const import (
            VEHICLE_STATE_API_FIELDS,
            VEHICLE_STATE_SANS_TPMS_API_FIELDS,
        )

        assert VEHICLE_STATE_SANS_TPMS_API_FIELDS < VEHICLE_STATE_API_FIELDS
        for tyre in (
            "tirePressureFrontLeft",
            "tirePressureFrontRight",
            "tirePressureRearLeft",
            "tirePressureRearRight",
        ):
            assert tyre in VEHICLE_STATE_API_FIELDS
            assert tyre not in VEHICLE_STATE_SANS_TPMS_API_FIELDS


class TestVocabularyMatchesTheVehicle:
    """Both of these were found by booting against the real vehicle; every unit
    test passed, because the values only appear in live data."""

    def test_preconditioning_options_cover_every_decoder_output(self) -> None:
        """decode_preconditioning emits "active" | "initiate" | "off"; the sensor's
        options were written for the GraphQL vocabulary and omitted "Off"."""
        from custom_components.rivian.const import SENSORS, _to_title_case

        description = next(
            d
            for sensors in SENSORS.values()
            for d in sensors
            if d.field == "cabinPreconditioningStatus"
        )
        for emitted in ("active", "initiate", "off"):
            assert _to_title_case(emitted) in description.options

    def test_sna_is_treated_as_an_invalid_state(self) -> None:
        """The vehicle abbreviates signal-not-available to SNA. The set is compared
        with .lower(), so the lowercase form is the one that matters."""
        from custom_components.rivian.const import INVALID_SENSOR_STATES

        assert "SNA".lower() in INVALID_SENSOR_STATES
        assert all(entry == entry.lower() for entry in INVALID_SENSOR_STATES)
