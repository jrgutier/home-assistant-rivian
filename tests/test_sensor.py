"""Tests for Rivian sensor platform."""

from unittest.mock import MagicMock

import pytest

from custom_components.rivian.const import (
    ATTR_COORDINATOR,
    ATTR_VEHICLE,
    ATTR_WALLBOX,
    DOMAIN,
)
from custom_components.rivian.coordinator import (
    ChargingCoordinator,
    DriverKeyCoordinator,
    VehicleCoordinator,
    WallboxCoordinator,
)
from custom_components.rivian.data_classes import RivianSensorEntityDescription
from custom_components.rivian.sensor import (
    RivianChargingSensorEntity,
    RivianDriverSensorEntity,
    RivianSensorEntity,
    RivianWallboxSensorEntity,
    async_setup_entry,
)
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, UnitOfElectricCurrent, UnitOfPower
from homeassistant.core import HomeAssistant


class TestRivianSensorEntity:
    """Test RivianSensorEntity class."""

    async def test_native_value_with_value_fn(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test native_value when value_fn is defined."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {"batteryLevel": {"value": 80.5}}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianSensorEntityDescription(
            key="test_sensor",
            translation_key="test_sensor",
            field="batteryLevel",
            value_fn=lambda coord: "custom_value",
        )

        entity = RivianSensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.native_value == "custom_value"

    async def test_native_value_with_field(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test native_value retrieves from field."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {"batteryLevel": {"value": 80.5}}
        coordinator.get = MagicMock(return_value=80.5)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianSensorEntityDescription(
            key="battery_level",
            translation_key="battery_level",
            field="batteryLevel",
        )

        entity = RivianSensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.native_value == 80.5

    async def test_native_value_with_value_lambda(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test native_value applies value_lambda transformation."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value=80.6)

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianSensorEntityDescription(
            key="battery_level",
            translation_key="battery_level",
            field="batteryLevel",
            value_lambda=lambda val: int(round(val, 0)),
        )

        entity = RivianSensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.native_value == 81

    async def test_native_value_unavailable_with_unit(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test native_value returns None when field is None with unit."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value=None)
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianSensorEntityDescription(
            key="battery_level",
            translation_key="battery_level",
            field="batteryLevel",
            native_unit_of_measurement="%",
        )

        entity = RivianSensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # When field returns None with a unit, it returns None (not STATE_UNAVAILABLE)
        assert entity.native_value is None

    async def test_native_value_none_without_unit(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test native_value returns STATE_UNAVAILABLE when field is None without unit."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.get = MagicMock(return_value=None)
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianSensorEntityDescription(
            key="power_state",
            translation_key="power_state",
            field="powerState",
        )

        entity = RivianSensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # When field returns None without a unit, it returns STATE_UNAVAILABLE
        assert entity.native_value == STATE_UNAVAILABLE

    async def test_extra_state_attributes_with_value_lambda(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test extra_state_attributes includes native_value and timestamp."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {
            "batteryLevel": {
                "value": 80.5,
                "timeStamp": "2024-01-01T00:00:00Z",
                "history": ["80.5", "79.8"],
            }
        }

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianSensorEntityDescription(
            key="battery_level",
            translation_key="battery_level",
            field="batteryLevel",
            value_lambda=lambda val: round(val, 0),
        )

        entity = RivianSensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        attrs = entity.extra_state_attributes
        assert attrs["native_value"] == 80.5
        assert attrs["last_update"] == "2024-01-01T00:00:00Z"
        assert "history" in attrs

    async def test_extra_state_attributes_without_value_lambda(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test extra_state_attributes only includes timestamp when no value_lambda."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {
            "powerState": {
                "value": "go",
                "timeStamp": "2024-01-01T00:00:00Z",
            }
        }

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianSensorEntityDescription(
            key="power_state",
            translation_key="power_state",
            field="powerState",
        )

        entity = RivianSensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        attrs = entity.extra_state_attributes
        assert attrs["last_update"] == "2024-01-01T00:00:00Z"
        assert "native_value" not in attrs

    async def test_extra_state_attributes_with_dotted_field(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """A dotted field (e.g. one leaf of gnssError) must look up the
        envelope's `last_update`, not KeyError against a literal dotted key
        that never exists in coordinator.data.
        """
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {
            "gnssError": {
                "timeStamp": "2024-01-01T00:00:00Z",
                "positionVertical": 1.5,
                "positionHorizontal": 2.5,
                "speed": 0.1,
                "bearing": 3.0,
            }
        }

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianSensorEntityDescription(
            key="gnss_error_position_vertical",
            translation_key="gnss_error_position_vertical",
            field="gnssError.positionVertical",
        )

        entity = RivianSensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        attrs = entity.extra_state_attributes
        assert attrs["last_update"] == "2024-01-01T00:00:00Z"

    async def test_extra_state_attributes_none_when_field_missing(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test extra_state_attributes returns None when field is missing."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.data = {}

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        description = RivianSensorEntityDescription(
            key="battery_level",
            translation_key="battery_level",
            field="batteryLevel",
        )

        entity = RivianSensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        assert entity.extra_state_attributes is None


class TestRivianChargingSensorEntity:
    """Test RivianChargingSensorEntity class."""

    async def test_native_value_simple(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test native_value with simple field value."""
        coordinator = MagicMock(spec=ChargingCoordinator)
        coordinator.data = {"powerKW": 11.0}

        description = RivianSensorEntityDescription(
            key="charging_speed",
            translation_key="charging_speed",
            field="powerKW",
        )

        entity = RivianChargingSensorEntity(
            coordinator=coordinator,
            description=description,
            vin="TEST123456789",
        )

        assert entity.native_value == 11.0

    async def test_native_value_dict_value(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test native_value extracts from dict value."""
        coordinator = MagicMock(spec=ChargingCoordinator)
        coordinator.data = {"powerKW": {"value": 11.0}}

        description = RivianSensorEntityDescription(
            key="charging_speed",
            translation_key="charging_speed",
            field="powerKW",
        )

        entity = RivianChargingSensorEntity(
            coordinator=coordinator,
            description=description,
            vin="TEST123456789",
        )

        assert entity.native_value == 11.0

    async def test_native_value_with_value_lambda(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test native_value applies value_lambda transformation."""
        coordinator = MagicMock(spec=ChargingCoordinator)
        coordinator.data = {"isFreeSession": True}

        description = RivianSensorEntityDescription(
            key="charging_is_free",
            translation_key="charging_is_free",
            field="isFreeSession",
            value_lambda=lambda val: str(val).lower() if val is not None else None,
        )

        entity = RivianChargingSensorEntity(
            coordinator=coordinator,
            description=description,
            vin="TEST123456789",
        )

        assert entity.native_value == "true"

    async def test_native_unit_of_measurement_price(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test native_unit_of_measurement returns currency for price field."""
        coordinator = MagicMock(spec=ChargingCoordinator)
        coordinator.data = {"price": 5.50, "currency": "USD"}

        description = RivianSensorEntityDescription(
            key="charging_cost",
            translation_key="charging_cost",
            field="price",
            device_class=SensorDeviceClass.MONETARY,
        )

        entity = RivianChargingSensorEntity(
            coordinator=coordinator,
            description=description,
            vin="TEST123456789",
        )
        entity.hass = hass

        assert entity.native_unit_of_measurement == "USD"

    async def test_native_unit_of_measurement_default(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test native_unit_of_measurement returns default for non-price fields."""
        coordinator = MagicMock(spec=ChargingCoordinator)
        coordinator.data = {"powerKW": 11.0}

        description = RivianSensorEntityDescription(
            key="charging_speed",
            translation_key="charging_speed",
            field="powerKW",
            native_unit_of_measurement=UnitOfPower.KILO_WATT,
        )

        entity = RivianChargingSensorEntity(
            coordinator=coordinator,
            description=description,
            vin="TEST123456789",
        )

        assert entity.native_unit_of_measurement == UnitOfPower.KILO_WATT


class TestRivianWallboxSensorEntity:
    """Test RivianWallboxSensorEntity class."""

    async def test_native_value_enum(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test native_value converts enum to lowercase."""
        from custom_components.rivian.data_classes import (
            RivianWallboxSensorEntityDescription,
        )

        coordinator = MagicMock(spec=WallboxCoordinator)

        wallbox_data = {
            "wallboxId": "wallbox_123",
            "serialNumber": "WB123456",
            "name": "Home Charger",
            "model": "Rivian Wall Charger",
            "softwareVersion": "1.2.3",
            "chargingStatus": "AVAILABLE",
        }

        description = RivianWallboxSensorEntityDescription(
            key="charging_status",
            translation_key="charging_status",
            field="chargingStatus",
            device_class=SensorDeviceClass.ENUM,
        )

        entity = RivianWallboxSensorEntity(
            coordinator=coordinator,
            description=description,
            wallbox=wallbox_data,
        )

        assert entity.native_value == "available"

    async def test_native_value_non_enum(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test native_value returns raw value for non-enum."""
        from custom_components.rivian.data_classes import (
            RivianWallboxSensorEntityDescription,
        )

        coordinator = MagicMock(spec=WallboxCoordinator)

        wallbox_data = {
            "wallboxId": "wallbox_123",
            "serialNumber": "WB123456",
            "name": "Home Charger",
            "model": "Rivian Wall Charger",
            "softwareVersion": "1.2.3",
            "currentAmps": 48,
        }

        description = RivianWallboxSensorEntityDescription(
            key="amperage",
            translation_key="amperage",
            field="currentAmps",
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        )

        entity = RivianWallboxSensorEntity(
            coordinator=coordinator,
            description=description,
            wallbox=wallbox_data,
        )

        assert entity.native_value == 48


class TestRivianDriverSensorEntity:
    """Test RivianDriverSensorEntity class."""

    async def test_native_value_drivers_count(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test native_value counts drivers."""
        coordinator = MagicMock(spec=DriverKeyCoordinator)
        coordinator.data = {
            "invitedUsers": [
                {"name": "Driver 1", "devices": ["phone1"]},
                {"name": "Driver 2", "devices": ["phone2"]},
                {"name": "Pending", "status": "pending"},  # No devices
            ]
        }

        description = RivianSensorEntityDescription(
            key="drivers",
            translation_key="drivers",
            field="invitedUsers",
            value_lambda=lambda data: len(
                [user for user in (data or []) if "devices" in user]
            ),
        )

        entity = RivianDriverSensorEntity(
            coordinator,
            description,
            "TEST123456789",
        )

        assert entity.native_value == 2

    async def test_native_value_keys_count(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test native_value counts keys."""
        coordinator = MagicMock(spec=DriverKeyCoordinator)
        coordinator.data = {
            "invitedUsers": [
                {"name": "Driver 1", "devices": ["phone1", "phone2"]},
                {"name": "Driver 2", "devices": ["phone3"]},
            ]
        }

        description = RivianSensorEntityDescription(
            key="keys",
            translation_key="keys",
            field="invitedUsers",
            value_lambda=lambda data: len(
                [
                    keys
                    for user in (data or [])
                    if "devices" in user
                    for keys in user.get("devices", [])
                ]
            ),
        )

        entity = RivianDriverSensorEntity(
            coordinator,
            description,
            "TEST123456789",
        )

        assert entity.native_value == 3

    async def test_native_value_empty_data(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test native_value returns 0 when coordinator data is empty."""
        coordinator = MagicMock(spec=DriverKeyCoordinator)
        coordinator.data = None

        description = RivianSensorEntityDescription(
            key="drivers",
            translation_key="drivers",
            field="invitedUsers",
            value_lambda=lambda data: len(
                [user for user in (data or []) if "devices" in user]
            ),
        )

        entity = RivianDriverSensorEntity(
            coordinator,
            description,
            "TEST123456789",
        )

        assert entity.native_value == 0

    async def test_extra_state_attributes_keys(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test extra_state_attributes for keys sensor."""
        coordinator = MagicMock(spec=DriverKeyCoordinator)
        coordinator.data = {
            "invitedUsers": [
                {
                    "name": "Driver 1",
                    "devices": [
                        {"isPaired": True, "isEnabled": True},
                        {"isPaired": True, "isEnabled": False},
                    ],
                },
                {
                    "name": "Driver 2",
                    "devices": [
                        {"isPaired": False, "isEnabled": True},
                    ],
                },
            ]
        }

        description = RivianSensorEntityDescription(
            key="keys",
            translation_key="keys",
            field="invitedUsers",
            value_lambda=lambda data: len(
                [
                    keys
                    for user in (data or [])
                    if "devices" in user
                    for keys in user.get("devices", [])
                ]
            ),
        )

        entity = RivianDriverSensorEntity(
            coordinator,
            description,
            "TEST123456789",
        )

        attrs = entity.extra_state_attributes
        assert attrs["paired"] == 2
        assert attrs["enabled"] == 2


@pytest.mark.asyncio
async def test_async_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
) -> None:
    """Test sensor platform setup."""
    vehicle_coordinator = MagicMock(spec=VehicleCoordinator)
    vehicle_coordinator.data = {}

    charging_coordinator = MagicMock(spec=ChargingCoordinator)
    charging_coordinator.data = {}

    drivers_coordinator = MagicMock(spec=DriverKeyCoordinator)
    drivers_coordinator.data = {}

    vehicle_coordinator.charging_coordinator = charging_coordinator
    vehicle_coordinator.drivers_coordinator = drivers_coordinator

    wallbox_coordinator = MagicMock(spec=WallboxCoordinator)
    wallbox_coordinator.data = []

    vehicle_data = {
        "test_vehicle_123": {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }
    }

    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            ATTR_VEHICLE: vehicle_data,
            ATTR_COORDINATOR: {
                ATTR_VEHICLE: {"test_vehicle_123": vehicle_coordinator},
                ATTR_WALLBOX: wallbox_coordinator,
            },
        }
    }

    entities_added = []

    def mock_add_entities(entities):
        entities_added.extend(entities)

    await async_setup_entry(hass, mock_config_entry, mock_add_entities)

    # Should have created multiple sensor entities
    assert len(entities_added) > 0

    # Verify we have vehicle sensors, charging sensors, and driver sensors
    vehicle_sensors = [e for e in entities_added if isinstance(e, RivianSensorEntity)]
    charging_sensors = [
        e for e in entities_added if isinstance(e, RivianChargingSensorEntity)
    ]
    driver_sensors = [
        e for e in entities_added if isinstance(e, RivianDriverSensorEntity)
    ]

    assert len(vehicle_sensors) > 0
    assert len(charging_sensors) > 0
    assert len(driver_sensors) > 0


class TestRivianSensorEntityEdgeCases:
    """Test RivianSensorEntity edge cases."""

    async def test_native_value_enum_not_in_options(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test native_value with enum value not in options."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.data = {
            "test_field": {
                "value": "unknown_value",
                "timeStamp": "2024-01-01T00:00:00Z",
            }
        }
        coordinator.get = MagicMock(return_value="unknown_value")

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        from custom_components.rivian.data_classes import RivianSensorEntityDescription
        from homeassistant.components.sensor import SensorDeviceClass

        description = RivianSensorEntityDescription(
            key="test_enum",
            translation_key="test_enum",
            field="test_field",
            device_class=SensorDeviceClass.ENUM,
            options=["option1", "option2"],  # unknown_value not in options
        )

        entity = RivianSensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )
        entity.hass = hass
        entity.entity_id = "sensor.test_enum"

        # Should log error and append unknown value to options (lines 119-126)
        result = entity.native_value
        assert result == "unknown_value"
        assert "unknown_value" in entity.options

    async def test_extra_state_attributes_entity_none(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test extra_state_attributes returns None when entity is None."""
        coordinator = MagicMock(spec=VehicleCoordinator)
        coordinator.hass = hass
        coordinator.data = {
            "test_field": None,  # Entity is None
        }

        vehicle_data = {
            "id": "test_vehicle_123",
            "vin": "TEST123456789",
            "name": "Test R1T",
            "model": "R1T",
        }

        from custom_components.rivian.data_classes import RivianSensorEntityDescription

        description = RivianSensorEntityDescription(
            key="test_sensor",
            translation_key="test_sensor",
            field="test_field",
        )

        entity = RivianSensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=vehicle_data,
        )

        # Should return None when entity is None (line 135)
        result = entity.extra_state_attributes
        assert result is None


class TestRivianDriverSensorEntityEdgeCases:
    """Test RivianDriverSensorEntity edge cases."""

    async def test_extra_state_attributes_calls_super(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ) -> None:
        """Test extra_state_attributes calls super for non-key-count sensors."""
        coordinator = MagicMock(spec=DriverKeyCoordinator)
        coordinator.hass = hass
        coordinator.data = {}

        from custom_components.rivian.data_classes import RivianSensorEntityDescription

        # Description without key="keys"
        description = RivianSensorEntityDescription(
            key="other_sensor",
            translation_key="other_sensor",
            field="some_field",
        )

        entity = RivianDriverSensorEntity(
            coordinator=coordinator,
            entity_description=description,
            vin="TEST123456789",
        )

        # Should call super().extra_state_attributes (line 411)
        result = entity.extra_state_attributes
        # Result could be None or dict depending on super implementation
        assert result is None or isinstance(result, dict)


class TestUnusableValuesDoNotBecomeStates:
    """The vehicle's own "no signal" code must not become a sensor state.

    Without this the ENUM branch appends the bad value to the entity's options, so
    'SNA' silently becomes valid for the life of the process, HA logs an error at
    every startup, and the select beside it shows 'unknown'.

    Handled here rather than in the coordinator, which was tried twice and is
    wrong: the raw value must keep flowing, because entity availability is driven
    by the field being present. Dropping it made the matching CONTROL unavailable
    too -- and on a real R1T the rear seat heaters report SNA whenever the vehicle
    is parked, so you could not preheat them remotely, which is exactly when you
    would want to.
    """

    def _sensor(self, value, options):
        from custom_components.rivian.data_classes import RivianSensorEntityDescription
        from custom_components.rivian.sensor import RivianSensorEntity

        entity = RivianSensorEntity.__new__(RivianSensorEntity)
        entity.entity_description = RivianSensorEntityDescription(
            key="k",
            field="f",
            device_class=SensorDeviceClass.ENUM,
            options=list(options),
        )
        entity._get_value = lambda field: value
        entity.entity_id = "sensor.test"
        return entity

    @pytest.mark.parametrize(
        "bad", ["SNA", "sna", "signal_not_available", "Fault", "undefined"]
    )
    def test_an_unusable_value_reads_as_unknown(self, bad: str) -> None:
        entity = self._sensor(bad, ["Off", "Level 1"])
        assert RivianSensorEntity.native_value.fget(entity) is None

    def test_the_options_list_is_not_polluted(self) -> None:
        """The specific harm: 'SNA' becoming a permanent valid option."""
        entity = self._sensor("SNA", ["Off", "Level 1"])
        RivianSensorEntity.native_value.fget(entity)
        assert "SNA" not in entity.entity_description.options

    def test_a_real_value_still_passes_through(self) -> None:
        entity = self._sensor("Off", ["Off", "Level 1"])
        assert RivianSensorEntity.native_value.fget(entity) == "Off"

    def test_a_genuinely_unknown_option_still_reports_itself(self) -> None:
        """Only the vehicle's no-signal codes are suppressed. A real value missing
        from `options` is a gap in our table and must stay loud."""
        entity = self._sensor("Level 4", ["Off", "Level 1"])
        assert RivianSensorEntity.native_value.fget(entity) == "Level 4"
