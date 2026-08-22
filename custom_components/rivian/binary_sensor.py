"""Rivian (Unofficial)"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_COORDINATOR,
    ATTR_VEHICLE,
    BINARY_SENSORS,
    DOMAIN,
    INVALID_SENSOR_STATES,
)
from .coordinator import VehicleCoordinator
from .data_classes import RivianBinarySensorEntityDescription
from .entity import RivianVehicleEntity
from .helpers import groups_for_model


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the binary sensor entities."""
    data: dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    vehicles: dict[str, Any] = data[ATTR_VEHICLE]
    coordinators: dict[str, VehicleCoordinator] = data[ATTR_COORDINATOR][ATTR_VEHICLE]

    entities = [
        RivianBinarySensorEntity(coordinators[vehicle_id], entry, description, vehicle)
        for vehicle_id, vehicle in vehicles.items()
        for model, descriptions in BINARY_SENSORS.items()
        if model in groups_for_model(vehicle.get("model"))
        for description in descriptions
    ]

    # Add cloud connection binary sensor for each vehicle
    entities.extend(
        [
            RivianCloudConnectionBinarySensor(coordinators[vehicle_id], entry, vehicle)
            for vehicle_id, vehicle in vehicles.items()
        ]
    )

    async_add_entities(entities)


class RivianBinarySensorEntity(RivianVehicleEntity, BinarySensorEntity):
    """Rivian Binary Sensor Entity."""

    entity_description: RivianBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: VehicleCoordinator,
        config_entry: ConfigEntry,
        description: RivianBinarySensorEntityDescription,
        vehicle: dict[str, Any],
    ) -> None:
        """Create a Rivian binary sensor."""
        super().__init__(coordinator, config_entry, description, vehicle)
        self._aggregate = isinstance(self.entity_description.field, set)

    @property
    def available(self) -> bool:
        """Return the availability of the entity."""
        if self._aggregate:
            return self._available and any(
                self._get_value(entity_key)
                for entity_key in self.entity_description.field
            )
        return super().available

    @property
    def is_on(self) -> bool | None:
        """Return true if sensor is on."""
        fields = self.entity_description.field
        if self._aggregate:
            # `on_values`, not `on_value`. The old form asked
            # `on_value in (values...)`, which reads naturally only while
            # on_value is a bare string: widen one of these descriptions to
            # ["open", "opened"] and the test becomes
            # `["open", "opened"] in ("closed", "open", ...)`, which is False for
            # every possible frame. `door_state` and `closure_state` would not
            # error -- they would report Closed forever.
            values = self.entity_description.on_values
            return any(self._get_value(entity_key) in values for entity_key in fields)
        if (val := self._get_value(fields)) is not None:
            # A value the vehicle flags as unusable is not a state -- report
            # unknown, mirroring sensor.py:184.
            #
            # This matters more here than it does for a sensor. A sensor showing
            # "SNA" at least looks wrong; a binary sensor silently resolves it,
            # because "signal_not_available" is not equal to "locked", so a door
            # whose lock state the vehicle has just said it does not know renders
            # as a confident Unlocked.
            #
            # BEFORE the negate, not after: `not False` is True, so filtering
            # afterwards would turn an unusable value into a confident True on
            # every negated description.
            #
            # Returning None yields `unknown`, NOT `unavailable` --
            # RivianVehicleEntity.available (entity.py:77) keys on the field
            # being present, and the raw value still flows. That is deliberate:
            # suppressing the value in the coordinator instead was tried twice and
            # reverted, because it takes the matching CONTROL down with it.
            if str(val).lower() in INVALID_SENSOR_STATES:
                return None
            result = val in self.entity_description.on_values
            return result if not self.entity_description.negate else not result
        return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the state attributes of the device."""
        if self._aggregate:
            return None
        try:
            entity = self.coordinator.data[self.entity_description.field]
            if entity is None:
                return None
            return {
                "value": entity["value"],
                "last_update": entity["timeStamp"],
                "history": str(entity["history"]),
            }
        except KeyError:
            return None


class RivianCloudConnectionBinarySensor(RivianVehicleEntity, BinarySensorEntity):
    """Binary sensor for vehicle cloud connection status."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        coordinator: VehicleCoordinator,
        config_entry: ConfigEntry,
        vehicle: dict[str, Any],
    ) -> None:
        """Create a Rivian cloud connection binary sensor."""
        from homeassistant.helpers.entity import EntityDescription

        description = EntityDescription(
            key="cloud_connected",
            name="Cloud Connected",
        )
        super().__init__(coordinator, config_entry, description, vehicle)

    @property
    def is_on(self) -> bool:
        """Return true if vehicle is connected to cloud."""
        # bool(), because _is_online is tri-state upstream (None = no cloud frame yet,
        # or a frame whose isOnline was null). HA renders a None from is_on as
        # `unknown`, not `off`, and `unknown` does not fire a `to: "off"` state trigger
        # -- so an automation on this sensor would silently stop firing at every
        # restart. This is the MINIMAL change, not a no-op: the common path (startup ->
        # off) is preserved exactly, and one path never seen in the field record (an
        # explicit `isOnline: null` frame, which already renders `unknown` today)
        # collapses to `off`. Giving the sensor honest tri-state semantics is a
        # separate story -- in HA the right shape for "we have heard nothing" is
        # available = False, not is_on = None.
        return bool(self.coordinator.is_online())

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the state attributes."""
        return {
            "last_sync": self.coordinator.last_sync(),
        }
