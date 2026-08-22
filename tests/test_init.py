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
    ATTR_SUPPORTED_FEATURES,
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


@pytest.fixture
def mock_features_coordinator():
    """Return a mocked SupportedFeaturesCoordinator."""
    coordinator = MagicMock()
    coordinator.async_refresh = AsyncMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.data = {"vehicles": []}
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
        mock_features_coordinator,
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
            patch(
                "custom_components.rivian.SupportedFeaturesCoordinator",
                return_value=mock_features_coordinator,
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

            # SupportedFeaturesCoordinator uses async_refresh(), never
            # async_config_entry_first_refresh() -- a capability feed
            # failure must never raise ConfigEntryNotReady and block setup.
            mock_features_coordinator.async_refresh.assert_called_once()
            mock_features_coordinator.async_config_entry_first_refresh.assert_not_called()

            # Verify platforms were forwarded
            mock_forward.assert_called_once()

            # Verify data structure
            entry_data = hass.data[DOMAIN][mock_config_entry.entry_id]
            assert ATTR_API in entry_data
            assert ATTR_VEHICLE in entry_data
            assert ATTR_COORDINATOR in entry_data
            assert (
                entry_data[ATTR_COORDINATOR][ATTR_SUPPORTED_FEATURES]
                is mock_features_coordinator
            )

    async def test_setup_succeeds_when_the_features_feed_genuinely_fails(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_rivian_api,
        mock_user_coordinator,
        mock_vehicle_coordinator,
        mock_wallbox_coordinator,
    ) -> None:
        """End-to-end, with a REAL SupportedFeaturesCoordinator (not a mock
        of its methods) whose client call raises -- so this exercises
        DataUpdateCoordinator.async_refresh()'s real error-swallowing
        behaviour, not just that __init__.py calls the right method name.
        """
        mock_rivian_api.get_supported_features = AsyncMock(
            side_effect=Exception("gateway 500")
        )

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
            patch.object(hass.config_entries, "async_forward_entry_setups"),
        ):
            result = await async_setup_entry(hass, mock_config_entry)

        assert result is True

        entry_data = hass.data[DOMAIN][mock_config_entry.entry_id]
        features_coordinator = entry_data[ATTR_COORDINATOR][ATTR_SUPPORTED_FEATURES]
        assert features_coordinator.last_update_success is False
        assert features_coordinator.data is None
        mock_rivian_api.get_supported_features.assert_called_once()

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

    def test_every_subscribed_field_is_one_the_gateway_knows(self) -> None:
        """The real invariant, checked against the client's own property list.

        The first version of this test asserted only that PARALLAX_ONLY_FIELDS was
        excluded from VEHICLE_STATE_API_FIELDS -- a restatement of the fix, not a
        check of anything. Add another Parallax-fed sensor tomorrow and it passes
        while the subscription dies again, which is precisely the bug it was
        written for.

        This is the check that would have caught wheelsInstalled: the field is
        computed by a Parallax decoder and appears in no gateway property list.
        """
        from custom_components.rivian.const import VEHICLE_STATE_API_FIELDS
        from custom_components.rivian.rivian_client.const import (
            VEHICLE_STATES_SUBSCRIPTION_PROPERTIES,
        )

        unknown = set(VEHICLE_STATE_API_FIELDS) - VEHICLE_STATES_SUBSCRIPTION_PROPERTIES
        assert not unknown, (
            f"{sorted(unknown)} would be sent in the vehicleState subscription but "
            "are not fields the gateway advertises. Rivian rejects the WHOLE "
            "subscription on the first unknown field, so this delivers no vehicle "
            "state at all. If the field is Parallax-derived, add it to "
            "PARALLAX_ONLY_FIELDS; if the gateway really does accept it, add it to "
            "the client's VEHICLE_STATE_PROPERTIES with evidence."
        )

    def test_parallax_only_fields_are_actually_excluded(self) -> None:
        """Kept as a narrow check on the mechanism itself, no longer as the guard."""
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

    def test_app_and_extra_documents_are_disjoint(self) -> None:
        """APP_VEHICLE_STATE_FIELDS is transcribed from the app's own subscription;
        EXTRA_VEHICLE_STATE_FIELDS is what this integration reads beyond it. If a
        name ever appeared in both, the union arithmetic below would silently
        undercount -- (APP | EXTRA) hides duplicates that a naive len(APP) +
        len(EXTRA) would not.
        """
        from custom_components.rivian.const import (
            APP_VEHICLE_STATE_FIELDS,
            EXTRA_VEHICLE_STATE_FIELDS,
        )

        overlap = APP_VEHICLE_STATE_FIELDS & EXTRA_VEHICLE_STATE_FIELDS
        assert not overlap, f"{sorted(overlap)} are in both documents"

    def test_api_fields_is_the_union_of_both_wire_documents(self) -> None:
        """VEHICLE_STATE_API_FIELDS is never sent as a document -- it is kept only
        because eight test modules and several scripts import it under that name.
        What actually reaches the gateway is the two WIRE symbols, and this pins
        the relationship between the historical name and the two that replaced it.
        """
        from custom_components.rivian.const import (
            TIRE_PRESSURE_SUBSCRIPTION_FIELDS,
            VEHICLE_STATE_API_FIELDS,
            VEHICLE_STATE_SUBSCRIPTION_FIELDS,
        )

        assert (
            VEHICLE_STATE_API_FIELDS
            == VEHICLE_STATE_SUBSCRIPTION_FIELDS | TIRE_PRESSURE_SUBSCRIPTION_FIELDS
        )

    def test_the_wire_documents_exclude_parallax_only_fields(self) -> None:
        """N3: the `- PARALLAX_ONLY_FIELDS` guard was once applied to
        VEHICLE_STATE_API_FIELDS, a symbol this module itself documents as never
        sent as a document -- so the guard protected nothing and the collision
        assert was a tautology. It belongs on the two symbols that are actually
        sent, and each assertion below names the wire symbol it guards so a
        failure points at the cause instead of at the harmless union.
        """
        from custom_components.rivian.const import (
            PARALLAX_ONLY_FIELDS,
            TIRE_PRESSURE_SUBSCRIPTION_FIELDS,
            VEHICLE_STATE_SUBSCRIPTION_FIELDS,
        )

        collision = VEHICLE_STATE_SUBSCRIPTION_FIELDS & PARALLAX_ONLY_FIELDS
        assert not collision, (
            f"{sorted(collision)} are in VEHICLE_STATE_SUBSCRIPTION_FIELDS (the "
            "main vehicleState wire document) AND in PARALLAX_ONLY_FIELDS"
        )
        collision = TIRE_PRESSURE_SUBSCRIPTION_FIELDS & PARALLAX_ONLY_FIELDS
        assert not collision, (
            f"{sorted(collision)} are in TIRE_PRESSURE_SUBSCRIPTION_FIELDS (the "
            "TPMS wire document) AND in PARALLAX_ONLY_FIELDS"
        )

    def test_core_fields_are_a_subset_of_the_subscription_wire(self) -> None:
        """CORE_VEHICLE_STATE_FIELDS (rivian_client/const.py) is the reduced
        document retried when the full subscription is rejected. Every name in it
        must actually be part of the main wire document, or the retry would ask
        for a field the primary attempt never requested either.
        """
        from custom_components.rivian.const import VEHICLE_STATE_SUBSCRIPTION_FIELDS
        from custom_components.rivian.rivian_client.const import (
            CORE_VEHICLE_STATE_FIELDS,
        )

        assert CORE_VEHICLE_STATE_FIELDS < VEHICLE_STATE_SUBSCRIPTION_FIELDS

    def test_the_wire_field_lists_are_literal_not_derived(self) -> None:
        """Belt and braces: read the expression, not only its value.

        Reconstructing a set in a test cannot catch a change to how const.py
        builds it, because the test would rebuild it correctly either way. This
        parses the SOURCE (via `ast`, so it survives reformatting) and confirms
        each of the three literal lists is built from a `frozenset({...})` of
        string constants -- not a comprehension over SENSORS/BINARY_SENSORS,
        which is the exact mechanism that put wheelsInstalled on the wire and
        killed the whole subscription.
        """
        import ast
        import inspect

        from custom_components.rivian import const

        module = ast.parse(inspect.getsource(const))
        assignments = {
            node.target.id: node.value
            for node in ast.walk(module)
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        for name in (
            "APP_VEHICLE_STATE_FIELDS",
            "EXTRA_VEHICLE_STATE_FIELDS",
            "TIRE_PRESSURE_SUBSCRIPTION_FIELDS",
        ):
            value = assignments[name]
            # TIRE_PRESSURE_SUBSCRIPTION_FIELDS is `frozenset({...}) - PARALLAX_ONLY_FIELDS`;
            # unwrap the subtraction to reach the frozenset() call underneath.
            if isinstance(value, ast.BinOp):
                value = value.left
            assert isinstance(value, ast.Call), (
                f"{name} is not a frozenset() call: {ast.dump(value)}"
            )
            assert isinstance(value.func, ast.Name) and value.func.id == "frozenset", (
                name
            )
            (arg,) = value.args
            assert isinstance(arg, ast.Set), (
                f"{name}'s frozenset() argument is not a literal set"
            )
            for element in arg.elts:
                assert isinstance(element, ast.Constant) and isinstance(
                    element.value, str
                ), f"{name} contains a non-literal element: {ast.dump(element)}"

    @staticmethod
    def _description_base_fields() -> set[str]:
        """Every field a SENSOR/BINARY_SENSOR description reads, reduced to its
        base wire name.

        A structured field with no top-level `value` -- `gnssError` is
        `{timeStamp, positionVertical, positionHorizontal, speed, bearing}`, no
        `value` key at all -- is split into one sensor per member, on a dotted
        `field="gnssError.bearing"` that `coordinator.get()` walks with
        `str.split(".")`. What is actually READ off the wire is the base name
        before the first dot; the dotted suffix is a path into it, not a second
        field. `gnssLocation` is the same shape and the next candidate for this,
        per worker-5.
        """
        from custom_components.rivian.const import BINARY_SENSORS, SENSORS

        raw: set[str] = {
            description.field for sensors in SENSORS.values() for description in sensors
        }
        for sensors in BINARY_SENSORS.values():
            for description in sensors:
                field = description.field
                raw.update([field] if isinstance(field, str) else field)
        return {f.partition(".")[0] for f in raw}

    def test_every_description_field_is_requested_or_parallax_only(self) -> None:
        """The invariant DERIVATION gave for free, now that the wire lists are
        literal. Add a sensor fed by the vehicleState subscription and forget to
        add its field to APP_VEHICLE_STATE_FIELDS or EXTRA_VEHICLE_STATE_FIELDS,
        and this is what would have caught it.

        Normalises dotted description fields to their base wire name first (see
        `_description_base_fields`) -- a literal string diff has no dotted-name
        precedent to normalise against and flagged `gnssError.bearing` and its
        three siblings as unrequested, when the base field `gnssError` they all
        read is requested. `test_the_normalization_does_not_swallow_a_genuine_
        omission` below is the check that this normalisation still catches a
        field that is actually missing, not just a false alarm on dotted names.
        """
        from custom_components.rivian.const import (
            PARALLAX_ONLY_FIELDS,
            VEHICLE_STATE_API_FIELDS,
        )

        unaccounted = (
            self._description_base_fields()
            - VEHICLE_STATE_API_FIELDS
            - PARALLAX_ONLY_FIELDS
        )
        assert not unaccounted, (
            f"{sorted(unaccounted)} are read by a sensor description but are "
            "neither requested nor marked PARALLAX_ONLY_FIELDS"
        )

    def test_the_normalization_does_not_swallow_a_genuine_omission(self) -> None:
        """Belt and braces for the fix above. `partition(".")[0]` must still
        catch a field that is truly missing, not merely stop flagging legitimate
        dotted children -- the two are easy to conflate, since both make the
        assertion pass. A synthetic pair proves the mechanism keeps both
        behaviours without editing SENSORS/BINARY_SENSORS, which is worker-5's
        file: one dotted name that is a real base field's child (must NOT be
        flagged) and one that names no document at all (must be flagged).
        """
        from custom_components.rivian.const import (
            PARALLAX_ONLY_FIELDS,
            VEHICLE_STATE_API_FIELDS,
        )

        synthetic_raw_fields = {
            "gnssError.bearing",
            "definitelyNotARequestedField.child",
        }
        base_fields = {f.partition(".")[0] for f in synthetic_raw_fields}
        unaccounted = base_fields - VEHICLE_STATE_API_FIELDS - PARALLAX_ONLY_FIELDS
        assert unaccounted == {"definitelyNotARequestedField"}

    def test_every_requested_field_is_read_or_is_part_of_the_apps_document(
        self,
    ) -> None:
        """The reverse of the invariant above: every requested field is read by
        a description (base key, same normalisation as above) or is otherwise
        justified.

        Before worker-5's 25 sensors this was a loose guarantee -- ~23 app
        fields (cellular*, wifi*, charging trip target*, ...) were requested to
        match the app's topology (field-parity decision) but read by nothing
        yet, tolerated by `unread <= APP_VEHICLE_STATE_FIELDS`. Those 25 sensors
        closed nearly all of that gap, so this pins the exact set now rather
        than a loose subset check -- a much tighter guarantee, and one that
        fails the moment a second field goes unread for an unexamined reason.

        Exactly one name is requested and read by no description at all:
        `gnssLocation`, consumed directly by `device_tracker.py` rather than by
        any SENSOR/BINARY_SENSOR table. `gnssError` looks like a second case at
        first -- no description reads the literal name `"gnssError"` either --
        but it is not one: `gnssError.bearing` and its three siblings all read
        it, and the SAME base-key normalisation that fixed the forward test
        above resolves those dotted children back to it. Applying that
        normalisation only on one side of this pair of tests would just move the
        dotted-field bug from one test to the other, so it is applied to both.
        """
        from custom_components.rivian.const import VEHICLE_STATE_API_FIELDS

        unread = VEHICLE_STATE_API_FIELDS - self._description_base_fields()
        assert unread == {"gnssLocation"}, (
            f"the requested-but-unread set is {sorted(unread)}, not the expected "
            "{'gnssLocation'} -- update this pin deliberately, and confirm each "
            "name in it either has a non-table consumer (like device_tracker.py) "
            "or is explained some other way, not just added to a looser check"
        )


class TestVocabularyMatchesTheVehicle:
    """Both of these were found by booting against the real vehicle; every unit
    test passed, because the values only appear in live data."""

    # Every ENUM sensor fed by a Parallax decoder, with the decoder's full output
    # vocabulary. Testing only cabinPreconditioningStatus was too narrow: an
    # independent review mutated away the "Off" in defrost_defog_status's options
    # and NOTHING failed, even though decode_defrost emits exactly Defrost | Off.
    # Same exposure, no guard.
    PARALLAX_ENUM_VOCABULARIES = (
        ("cabinPreconditioningStatus", ("active", "initiate", "off")),
        ("defrostDefogStatus", ("defrost", "off")),
    )

    @pytest.mark.parametrize(
        ("field", "emitted"), PARALLAX_ENUM_VOCABULARIES, ids=lambda v: str(v)[:30]
    )
    def test_enum_options_cover_every_decoder_output(
        self, field: str, emitted: tuple[str, ...]
    ) -> None:
        """A value the decoder can emit but the sensor does not list makes HA log an
        error and append it to the options at runtime, so the vocabulary silently
        becomes whatever the vehicle happened to send."""
        from custom_components.rivian.const import SENSORS, _to_title_case

        description = next(
            d for sensors in SENSORS.values() for d in sensors if d.field == field
        )
        missing = [
            _to_title_case(v)
            for v in emitted
            if _to_title_case(v) not in description.options
        ]
        assert not missing, f"{field} cannot represent {missing}"

    def test_sna_is_treated_as_an_invalid_state(self) -> None:
        """The vehicle abbreviates signal-not-available to SNA. The set is compared
        with .lower(), so the lowercase form is the one that matters."""
        from custom_components.rivian.const import INVALID_SENSOR_STATES

        assert "SNA".lower() in INVALID_SENSOR_STATES
        assert all(entry == entry.lower() for entry in INVALID_SENSOR_STATES)
