"""Rivian (Unofficial)"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import logging
from typing import Any, Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_UNAVAILABLE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import (
    ATTR_COORDINATOR,
    ATTR_VEHICLE,
    ATTR_WALLBOX,
    DOMAIN,
    INVALID_SENSOR_STATES,
    SENSORS,
    WEEK_DAYS_ORDERED,
)
from .coordinator import DriverKeyCoordinator, VehicleCoordinator, WallboxCoordinator
from .data_classes import (
    RivianSensorEntityDescription,
    RivianWallboxSensorEntityDescription,
)
from .entity import (
    RivianChargingEntity,
    RivianEntity,
    RivianVehicleEntity,
    RivianWallboxEntity,
)
from .helpers import vehicle_supports

_LOGGER = logging.getLogger(__name__)

ALL_WEEK_DAYS: Final[frozenset[str]] = frozenset(WEEK_DAYS_ORDERED)
WEEKDAYS_ONLY: Final[frozenset[str]] = frozenset(WEEK_DAYS_ORDERED[:5])

RIVIAN_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor entities."""
    data: dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    vehicles: dict[str, Any] = data[ATTR_VEHICLE]
    coordinators: dict[str, Any] = data[ATTR_COORDINATOR]

    # Add vehicle entities
    vehicle_coordinators: dict[str, VehicleCoordinator] = coordinators[ATTR_VEHICLE]
    entities = [
        RivianSensorEntity(
            vehicle_coordinators[vehicle_id], entry, description, vehicle
        )
        for vehicle_id, vehicle in vehicles.items()
        for description in SENSORS
        if vehicle_supports(description, vehicle)
    ]

    # Add charging entities
    entities.extend(
        RivianChargingSensorEntity(
            vehicle_coordinators[vehicle_id].charging_coordinator,
            description,
            vehicle["vin"],
        )
        for vehicle_id, vehicle in vehicles.items()
        for description in CHARGING_SENSORS
    )

    # Add drivers and keys entities
    entities.extend(
        RivianDriverSensorEntity(
            vehicle_coordinators[vehicle_id].drivers_coordinator,
            description,
            vehicle["vin"],
        )
        for vehicle_id, vehicle in vehicles.items()
        for description in DRIVER_SENSORS
    )

    # Add wallbox entities
    wallbox_coordinator: WallboxCoordinator = coordinators[ATTR_WALLBOX]
    entities.extend(
        RivianWallboxSensorEntity(wallbox_coordinator, description, wallbox)
        for wallbox in wallbox_coordinator.data
        for description in WALLBOX_SENSORS
    )

    for vehicle_id, vehicle in vehicles.items():
        coord = vehicle_coordinators[vehicle_id]
        entities.append(
            RivianChargingScheduleDaysEntity(
                coord, entry, CHARGING_SCHEDULE_DAYS_SENSOR, vehicle
            )
        )

    async_add_entities(entities)


CHARGING_SCHEDULE_DAYS_SENSOR = RivianSensorEntityDescription(
    key="charging_schedule_days",
    translation_key="charging_schedule_days",
    field="charging_schedule_days",
)


class RivianChargingScheduleDaysEntity(RivianVehicleEntity, SensorEntity):
    """Charging Schedule Days Entity."""

    @property
    def available(self) -> bool:
        """Return availability."""
        return self._available

    @property
    def native_value(self) -> str | None:
        """Return native value."""
        sched = self.coordinator.charging_schedule
        raw_days = sched.get("weekDays", [])
        if not raw_days or not isinstance(raw_days, list):
            return None
        days = frozenset(raw_days)

        if days == ALL_WEEK_DAYS:
            return "daily"
        if days == WEEKDAYS_ONLY:
            return "weekdays"

        ordered = [d for d in WEEK_DAYS_ORDERED if d in days]
        return ", ".join(ordered)


class RivianSensorEntity(RivianVehicleEntity, SensorEntity):
    """Representation of a Rivian sensor entity."""

    entity_description: RivianSensorEntityDescription

    @property
    def native_value(self) -> str | None:
        """Return the value reported by the sensor."""
        if _fn := self.entity_description.value_fn:
            return _fn(self.coordinator)

        if (val := self._get_value(self.entity_description.field)) is None:
            return STATE_UNAVAILABLE if not self.native_unit_of_measurement else None

        # A value the vehicle flags as unusable is not a state -- report unknown.
        #
        # Tested on the RAW value, BEFORE value_lambda runs, exactly as
        # binary_sensor.py's is_on does. It used to test the lambda's OUTPUT, and
        # that let three of the four spellings through: most lambdas run
        # _to_title_case, which turns underscores into spaces, so
        # "signal_not_available" arrived here as "signal not available" and
        # matched nothing in the set. 27 of the 31 ENUM sensors leaked that way.
        #
        # All four spellings are the app's own -- p069Ci/EnumC0996d.java declares
        # FAULT, SIGNAL_NOT_AVAILABLE, SNA and UNDEFINED as distinct constants --
        # so INVALID_SENSOR_STATES is already right. Only the comparison point
        # was wrong.
        #
        # This is the right layer for it. Suppressing it in the coordinator was
        # tried twice and is wrong: the raw value has to keep flowing, because
        # RivianVehicleEntity.available is driven by the field being present, and
        # dropping it makes the matching CONTROL unavailable too. On a real R1T the
        # rear seat heaters report SNA whenever the vehicle is parked, so dropping
        # it meant you could not preheat them remotely -- the one time you would
        # want to.
        #
        # Without this, the branch below appends "SNA" to the entity's own options
        # list, so the vehicle's error code silently becomes a valid state for the
        # life of the process, and the select beside it shows "unknown".
        if str(val).lower() in INVALID_SENSOR_STATES:
            return None

        rval = _fn(val) if (_fn := self.entity_description.value_lambda) else val
        # NOT redundant with the raw check above, and not dead. A lambda can
        # manufacture an invalid spelling out of a value that was perfectly fine
        # on the wire. The live case is cabin_preconditioning_status, whose
        # lambda is `_to_title_case(v) if v else "Undefined"`: an EMPTY value
        # passes the raw test ("" is not one of the four spellings), then the
        # lambda turns it into "Undefined", which is. Without this second test
        # that entity renders a literal "Undefined" instead of unknown.
        #
        # An earlier revision of this comment claimed a probe "found ZERO cases".
        # That probe simply never fed a lambda the empty string.
        if str(rval).lower() in INVALID_SENSOR_STATES:
            return None

        if self.device_class == SensorDeviceClass.ENUM and rval not in self.options:
            _LOGGER.error(
                "Sensor %s provides state value '%s', which is not in the list of known options. Please consider opening an issue at https://github.com/bretterer/home-assistant-rivian/issues with the following info: 'field: \"%s\" / value: \"%s\"'",
                self.entity_id or self.unique_id,
                rval,
                self.entity_description.field,
                val,
            )
            self.options.append(rval)
        return rval

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the state attributes of the device."""
        # A description that derives its own attributes owns them outright.
        # Only the parked-energy windows do today: their value is a nested
        # dict, and the branches below would read "timeStamp"/"history" off a
        # Parallax-fed field that has neither. See data_classes.py's
        # `attributes_lambda`.
        if _fn := self.entity_description.attributes_lambda:
            value = self._get_value(self.entity_description.field)
            return _fn(value) if value is not None else None

        try:
            # `field` may be dotted (e.g. "gnssError.positionVertical") for a
            # sensor reading one leaf of a structured field. coordinator.data
            # is keyed by the ENVELOPE name, not the leaf, so look up the base
            # key -- and that is the correct lookup, not a workaround: the
            # attributes below (last_update, history) describe when/how the
            # whole envelope last changed, which every leaf sensor shares.
            base_field = self.entity_description.field.partition(".")[0]
            entity = self.coordinator.data[base_field]
            if entity is None:
                return None
            if self.entity_description.value_lambda is None:
                return {
                    "last_update": entity["timeStamp"],
                }
            return {
                "native_value": entity["value"],
                "last_update": entity["timeStamp"],
                "history": str(entity["history"]),
            }
        except KeyError:
            return None


class RivianChargingSensorEntity(RivianChargingEntity, SensorEntity):
    """Representation of a Rivian charging sensor entity."""

    entity_description: RivianSensorEntityDescription

    @property
    def native_value(self) -> str | float | None:
        """Return the value reported by the sensor."""
        val = self.coordinator.data.get(self.entity_description.field)
        if isinstance(val, dict):
            val = val["value"]
        if value_fn := self.entity_description.value_lambda:
            return value_fn(val)
        return val

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement of the sensor, if any."""
        if self.entity_description.field == "price":
            return self.coordinator.data.get("currency", self.hass.config.currency)
        return super().native_unit_of_measurement


CHARGING_SENSORS: Final[tuple[RivianSensorEntityDescription, ...]] = (
    RivianSensorEntityDescription(
        key="charging_cost",
        translation_key="charging_cost",
        field="price",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
    ),
    RivianSensorEntityDescription(
        key="charging_energy_delivered",
        translation_key="charging_energy_delivered",
        field="totalChargedEnergy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=1,
    ),
    RivianSensorEntityDescription(
        key="charging_range_added",
        translation_key="charging_range_added",
        field="rangeAddedThisSession",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_unit_of_measurement=UnitOfLength.MILES,
    ),
    RivianSensorEntityDescription(
        key="charging_rate",
        translation_key="charging_rate",
        field="kilometersChargedPerHour",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
    ),
    RivianSensorEntityDescription(
        key="charging_speed",
        translation_key="charging_speed",
        field="powerKW",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    RivianSensorEntityDescription(
        key="charging_start_time",
        translation_key="charging_start_time",
        field="startTime",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_lambda=lambda val: (
            (
                datetime.fromtimestamp(val / 1000, tz=timezone.utc)
                if isinstance(val, int)
                # RIVIAN_TIMESTAMP_FORMAT ends in %z, so this IS tz-aware; ruff
                # cannot see through the module-level constant.
                else datetime.strptime(val, RIVIAN_TIMESTAMP_FORMAT)  # noqa: DTZ007
            )
            if val
            else val
        ),
    ),
    RivianSensorEntityDescription(
        key="charging_time_elapsed",
        translation_key="charging_time_elapsed",
        field="timeElapsed",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    RivianSensorEntityDescription(
        key="charging_time_remaining",
        translation_key="charging_time_remaining",
        field="timeRemaining",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-sand",
    ),
    RivianSensorEntityDescription(
        key="charging_is_free",
        translation_key="charging_is_free",
        field="isFreeSession",
        icon="mdi:cash-off",
        device_class=SensorDeviceClass.ENUM,
        options=["true", "false"],
        value_lambda=lambda val: str(val).lower() if val is not None else None,
    ),
)


class RivianWallboxSensorEntity(RivianWallboxEntity, SensorEntity):
    """Representation of a Rivian wallbox sensor entity."""

    entity_description: RivianWallboxSensorEntityDescription

    @property
    def native_value(self) -> StateType:
        """Return the value reported by the sensor."""
        value = self.wallbox[self.entity_description.field]
        if self.device_class == SensorDeviceClass.ENUM:
            return value.lower()
        return value


WALLBOX_SENSORS = (
    RivianWallboxSensorEntityDescription(
        key="charging_status",
        translation_key="charging_status",
        field="chargingStatus",
        icon="mdi:ev-plug-type1",
        device_class=SensorDeviceClass.ENUM,
        options=["unavailable", "available", "disconnected", "plugged_in", "charging"],
    ),
    RivianWallboxSensorEntityDescription(
        key="amperage",
        translation_key="amperage",
        field="currentAmps",
        device_class=SensorDeviceClass.CURRENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    RivianWallboxSensorEntityDescription(
        key="amperage_maximum",
        translation_key="amperage_maximum",
        field="maxAmps",
        device_class=SensorDeviceClass.CURRENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    RivianWallboxSensorEntityDescription(
        key="power",
        translation_key="power",
        field="power",
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
    ),
    RivianWallboxSensorEntityDescription(
        key="power_maximum",
        translation_key="power_maximum",
        field="maxPower",
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
    ),
    RivianWallboxSensorEntityDescription(
        key="voltage",
        translation_key="voltage",
        field="currentVoltage",
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    RivianWallboxSensorEntityDescription(
        key="voltage_maximum",
        translation_key="voltage_maximum",
        field="maxVoltage",
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)

DRIVER_SENSORS: Final[tuple[RivianSensorEntityDescription, ...]] = (
    RivianSensorEntityDescription(
        key="drivers",
        translation_key="drivers",
        icon="mdi:account-multiple",
        field="invitedUsers",
        value_lambda=lambda data: len(
            [user for user in (data or []) if "devices" in user]
        ),
    ),
    RivianSensorEntityDescription(
        key="keys",
        translation_key="keys",
        icon="mdi:car-key",
        field="invitedUsers",
        value_lambda=lambda data: len(
            [
                keys
                for user in (data or [])
                if "devices" in user
                for keys in user.get("devices", [])
            ]
        ),
    ),
)


class RivianDriverSensorEntity(RivianEntity[DriverKeyCoordinator], SensorEntity):
    """Representation of a Rivian driver sensor entity."""

    entity_description: RivianSensorEntityDescription
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: DriverKeyCoordinator,
        entity_description: RivianSensorEntityDescription,
        vin: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, vin)})
        self._attr_unique_id = f"{vin}-{entity_description.key}"

    @property
    def native_value(self) -> int:
        """Return the value reported by the sensor."""
        if self.coordinator.data:
            data = self.coordinator.data.get(self.entity_description.field)
            return self.entity_description.value_lambda(data)
        return 0

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return entity specific state attributes."""
        if self.entity_description.key == "keys":

            def get_count(key: str) -> int:
                field = self.entity_description.field
                return len(
                    [
                        keys
                        for user in (self.coordinator.data.get(field) or [])
                        if "devices" in user
                        for keys in user.get("devices", [])
                        if keys.get(key)
                    ]
                )

            return {"paired": get_count("isPaired"), "enabled": get_count("isEnabled")}
        return super().extra_state_attributes
