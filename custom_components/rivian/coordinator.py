"""Data update coordinator for the Rivian integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections.abc import Coroutine
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Generic, TypeVar

from rivian import Rivian, VehicleCommand
from rivian.exceptions import (
    RivianApiException,
    RivianApiRateLimitError,
    RivianExpiredTokenError,
    RivianUnauthenticated,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ATTR_COORDINATOR,
    ATTR_USER,
    ATTR_VEHICLE,
    DOMAIN,
    INVALID_SENSOR_STATES,
    VEHICLE_STATE_API_FIELDS,
)
from .helpers import redact

_LOGGER = logging.getLogger(__name__)
T = TypeVar("T", bound=dict[str, Any] | list[dict[str, Any]])


class RivianDataUpdateCoordinator(DataUpdateCoordinator[T], Generic[T], ABC):
    """Data update coordinator for the Rivian integration."""

    key: str
    _update_interval_seconds = 30
    _error_count = 0

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, client: Rivian
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=(
                timedelta(seconds=self._update_interval_seconds)
                if self._update_interval_seconds
                else None
            ),
            always_update=False,
        )
        self.api = client

    def _set_update_interval(self, seconds: float | None = None) -> None:
        """Set the update interval or calculate new one based on errors."""
        if not seconds:
            seconds = min(self._update_interval_seconds * 2**self._error_count, 900)
        if self._update_interval_seconds != seconds:
            refresh = self.update_interval and self._update_interval_seconds > seconds
            self.update_interval = timedelta(seconds=seconds)
            if refresh and self.data:
                task = self.async_request_refresh()
                self.config_entry.async_create_task(self.hass, task)
            else:
                self._schedule_refresh()
            _LOGGER.info("Polling set to %s seconds", seconds)

    async def _async_update_data(self) -> T:
        """Get the latest data from Rivian."""
        try:
            data = await self._fetch_data()
            _LOGGER.debug(
                "[%s] %s",
                self.__class__.__name__.replace("Coordinator", ""),
                redact(data),
            )
            if self._error_count:
                self._error_count = 0
                self._set_update_interval()
            return data

        except RivianExpiredTokenError:
            _LOGGER.info("Rivian token expired, refreshing")
            await self.api.create_csrf_token()
            return await self._async_update_data()
        except RivianApiRateLimitError as err:
            _LOGGER.error("Rate limit being enforced: %s", err, exc_info=1)
            self._set_update_interval()
        except RivianUnauthenticated as err:
            await self.api.close()
            raise ConfigEntryAuthFailed from err
        except RivianApiException as ex:
            _LOGGER.error("Rivian api exception: %s", ex, exc_info=1)
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.error(
                "Unknown Exception while updating Rivian data: %s", ex, exc_info=1
            )

        self._error_count += 1
        if self.data:
            return self.data
        raise UpdateFailed("Error communicating with API")

    @abstractmethod
    async def _fetch_data(self) -> T:
        """Fetch the data."""
        raise NotImplementedError


class ChargingCoordinator(RivianDataUpdateCoordinator[dict[str, Any]]):
    """Charging data update coordinator for Rivian."""

    key = "getLiveSessionData"
    _unplugged_interval = 15 * 60  # 15 minutes
    _plugged_interval = 30  # 30 seconds
    _update_interval_seconds = _unplugged_interval  # 15 minutes

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: Rivian,
        vehicle_id: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(hass=hass, config_entry=config_entry, client=client)
        self.vehicle_id = vehicle_id
        self._initial = asyncio.Event()
        self._unsub_handler: Coroutine[None, None, None] | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Get the latest data from Rivian."""
        if not self.data or not self.last_update_success:
            await self._unsubscribe()
            self._unsub_handler = await self.api.subscribe_for_charging_session(
                vehicle_id=self.vehicle_id,
                callback=self._process_new_data,
            )

            try:
                await asyncio.wait_for(self._initial.wait(), 5)
            except asyncio.TimeoutError:
                # Subscription established but no initial data received
                # This is normal when vehicle is not charging
                _LOGGER.debug("No initial charging data received (likely not charging)")
                self._initial.set()
                if not self.data:
                    self.data = {}

        return self.data

    async def _fetch_data(self) -> dict[str, Any]:
        """Fetch the data."""
        raise NotImplementedError("Polling charging data no longer allowed")

    async def async_shutdown(self) -> None:
        """Shutdown coordinator."""
        await self._unsubscribe()
        return await super().async_shutdown()

    @callback
    def _process_new_data(self, data: dict[str, Any]) -> None:
        """Process new charging data from subscription."""
        if not (payload := data.get("payload")) or not (pdata := payload.get("data")):
            _LOGGER.error("Received unknown charging subscription update: %s", data)
            self._error_count += 1
            if not self._initial.is_set() or self._error_count > 5:
                task = self._unsubscribe()
                self.config_entry.async_create_task(self.hass, task, eager_start=True)
            return

        charging_data = pdata.get("chargingSession", {})

        # Handle case where chargingSession is a list (e.g., empty list when not charging)
        if isinstance(charging_data, list):
            if not charging_data:
                # Empty list means no active charging session
                _LOGGER.debug("No active charging session")
                self.async_set_updated_data({})
                self._error_count = 0
                self._initial.set()
                return
            # If it's a non-empty list, take the first item
            charging_data = charging_data[0]

        # Merge chartData and liveData into flat structure matching current API
        processed_data = self._process_charging_data(charging_data)
        self.async_set_updated_data(processed_data)
        self._error_count = 0
        self._initial.set()

    def _process_charging_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Process charging session data into expected format.

        Subscription returns nested chartData/liveData, but sensors expect flat structure.
        """
        live_data = data.get("liveData", {})
        chart_data = data.get("chartData", {})

        # Handle case where liveData or chartData might be lists
        if isinstance(live_data, list):
            live_data = live_data[0] if live_data else {}
        if isinstance(chart_data, list):
            chart_data = chart_data[0] if chart_data else {}

        # Merge both structures, preferring liveData
        return {
            **chart_data,
            **live_data,
        }

    async def _unsubscribe(self, close_monitor: bool = False):
        """Unsubscribe from charging session updates."""
        if unsub := self._unsub_handler:
            await unsub()
            self._unsub_handler = None
            self._initial.clear()

    # def adjust_update_interval(self, is_plugged_in: bool) -> None:
    #     """Adjust update interval based on plugged in status."""
    #     self._set_update_interval(
    #         self._plugged_interval if is_plugged_in else self._unplugged_interval
    #     )


class DriverKeyCoordinator(RivianDataUpdateCoordinator[dict[str, Any]]):
    """Drivers/keys data update coordinator for Rivian."""

    key = "getVehicle"
    _update_interval_seconds = 15 * 60  # 15 minutes

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: Rivian,
        vehicle_id: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(hass=hass, config_entry=config_entry, client=client)
        self.vehicle_id = vehicle_id

    async def _fetch_data(self) -> dict[str, Any]:
        """Fetch the data."""
        return await self.api.get_drivers_and_keys(vehicle_id=self.vehicle_id)

    def get_device_details(self, identity_id: str) -> dict[str, Any] | None:
        """Get the details of a device."""
        if not self.data:
            return None
        return next(
            (
                device
                for user in self.data.get("invitedUsers")
                if user["__typename"] == "ProvisionedUser"
                for device in user["devices"]
                if device["mappedIdentityId"] == identity_id
            ),
            None,
        )


class UserCoordinator(RivianDataUpdateCoordinator[dict[str, Any]]):
    """User data update coordinator for Rivian."""

    key = "currentUser"

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: Rivian,
        include_phones: bool = False,
    ) -> None:
        super().__init__(hass=hass, config_entry=config_entry, client=client)
        self.include_phones = include_phones

    async def _fetch_data(self) -> dict[str, Any]:
        """Fetch the data."""
        return await self.api.get_user_information(self.include_phones)

    def get_enrolled_phone_data(
        self, public_key: str
    ) -> tuple[str, dict[str, str]] | None:
        """Get enrolled phone data."""
        phones = self.data.get("enrolledPhones", [])
        if phone := next(
            (phone for phone in phones if phone["vas"]["publicKey"] == public_key), None
        ):
            phone_id = phone["vas"]["vasPhoneId"]
            vehicle_entry = {
                entry["vehicleId"]: entry["identityId"] for entry in phone["enrolled"]
            }
            return (phone_id, vehicle_entry)
        return None

    def get_vehicles(self) -> dict[str, dict[str, Any]]:
        """Get the user's vehicles."""
        return {
            vehicle["id"]: vehicle["vehicle"]
            | {
                "name": vehicle["name"],
                "supported_features": [
                    supported_feature.get("name")
                    for supported_feature in vehicle.get("vehicle", {})
                    .get("vehicleState", {})
                    .get("supportedFeatures", [])
                    if supported_feature.get("status") == "AVAILABLE"
                ],
                "vas_id": (vas := vehicle.get("vas", {})).get("vasVehicleId"),
                "public_key": vas.get("vehiclePublicKey"),
            }
            for vehicle in self.data["vehicles"]
        }


class VehicleCoordinator(RivianDataUpdateCoordinator[dict[str, Any]]):
    """Vehicle data update coordinator for Rivian."""

    key = "vehicleState"
    _update_interval_seconds = 15 * 60  # 15 minutes

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: Rivian,
        vehicle_id: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(hass=hass, config_entry=config_entry, client=client)
        self.vehicle_id = vehicle_id
        self.charging_coordinator = ChargingCoordinator(
            hass=hass, config_entry=config_entry, client=client, vehicle_id=vehicle_id
        )
        self.drivers_coordinator = DriverKeyCoordinator(
            hass=hass, config_entry=config_entry, client=client, vehicle_id=vehicle_id
        )
        self._initial = asyncio.Event()
        self._unsub_handler: Coroutine[None, None, None] | None = None
        self._connection_unsub_handler: Coroutine[None, None, None] | None = None
        self._is_online: bool = False
        self._last_sync: str | None = None
        self._awake = asyncio.Event()
        self._command_state_subscriptions: dict[str, Coroutine[None, None, None]] = {}
        self._command_states: dict[str, dict[str, Any]] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Get the latest data from Rivian."""
        if not self.data or not self.last_update_success:
            await self._unsubscribe()
            self._unsub_handler = await self.api.subscribe_for_vehicle_updates(
                vehicle_id=self.vehicle_id,
                properties=VEHICLE_STATE_API_FIELDS,
                callback=self._process_new_data,
            )

            # Also subscribe to cloud connection for online/offline status
            self._connection_unsub_handler = (
                await self.api.subscribe_for_cloud_connection(
                    vehicle_id=self.vehicle_id,
                    callback=self._process_cloud_connection_data,
                )
            )

            try:
                await asyncio.wait_for(self._initial.wait(), 1)
            except asyncio.TimeoutError as err:
                raise UpdateFailed from err

        return self.data

    async def _fetch_data(self) -> dict[str, Any]:
        """Fetch the data."""
        raise NotImplementedError("Polling VehicleState no longer allowed")

    async def async_shutdown(self) -> None:
        # Unsubscribe from all active command state subscriptions
        for command_id in list(self._command_state_subscriptions.keys()):
            await self._unsubscribe_command_state(command_id)

        await self._unsubscribe(True)
        return await super().async_shutdown()

    @callback
    def _process_new_data(self, data: dict[str, Any]) -> None:
        """Process new data."""
        if not (payload := data.get("payload")) or not (pdata := payload.get("data")):
            _LOGGER.error("Received an unknown subscription update: %s", data)
            self._error_count += 1
            if not self._initial.is_set() or self._error_count > 5:
                task = self._unsubscribe()
                self.config_entry.async_create_task(self.hass, task, eager_start=True)
            return
        vehicle_info = self._build_vehicle_info_dict(pdata.get(self.key, {}))
        self.async_set_updated_data(vehicle_info)
        self._error_count = 0
        self._initial.set()

    def _build_vehicle_info_dict(self, vijson: dict[str, Any]) -> dict[str, Any]:
        """Take the json output of vehicle_info and build a dictionary."""
        items = {
            k: v | ({"history": {v["value"]}} if "value" in v else {})
            for k, v in vijson.items()
            if v
        }

        if items:
            _LOGGER.debug("Vehicle %s updated: %s", self.vehicle_id, redact(items))

        if power_state := items.get("powerState"):
            if power_state.get("value") == "sleep":
                self._awake.clear()
            else:
                self._awake.set()

        if not (prev_items := (self.data or {})):
            return items
        if not items or prev_items == items:
            return prev_items

        new_data = prev_items | items
        for key in filter(lambda i: i != "gnssLocation", items):
            value = items[key].get("value")
            if str(value).lower() in INVALID_SENSOR_STATES and key in prev_items:
                new_data[key] = prev_items[key]
            new_data[key]["history"] |= prev_items.get(key, {}).get("history", set())

        return new_data

    @callback
    def _process_cloud_connection_data(self, data: dict[str, Any]) -> None:
        """Process cloud connection updates."""
        if not (payload := data.get("payload")) or not (pdata := payload.get("data")):
            _LOGGER.error("Received unknown cloud connection update: %s", data)
            return

        connection_data = pdata.get("vehicleCloudConnection", {})
        self._is_online = connection_data.get("isOnline", False)
        self._last_sync = connection_data.get("lastSync")

        _LOGGER.debug(
            "Vehicle %s cloud connection: online=%s, lastSync=%s",
            self.vehicle_id,
            self._is_online,
            self._last_sync,
        )

    def is_online(self) -> bool:
        """Return whether vehicle is online."""
        return self._is_online

    def last_sync(self) -> str | None:
        """Return last sync timestamp."""
        return self._last_sync

    async def _unsubscribe(self, close_monitor: bool = False):
        """Unsubscribe."""
        # Unsubscribe from vehicle state
        if unsub := self._unsub_handler:
            await unsub()
            self._unsub_handler = None
            self._initial.clear()

        # Unsubscribe from cloud connection
        if connection_unsub := self._connection_unsub_handler:
            await connection_unsub()
            self._connection_unsub_handler = None

        if close_monitor and (monitor := self.api._ws_monitor):
            await monitor.close()

    def get(self, key: str) -> Any | None:
        """Get a data value by key."""
        if entity := self.data.get(key, {}):
            return entity.get("value")
        return None

    @callback
    def _process_command_state(self, command_id: str, data: dict[str, Any]) -> None:
        """Process command state updates."""
        if not (payload := data.get("payload")) or not (pdata := payload.get("data")):
            _LOGGER.error("Received unknown command state update: %s", data)
            return

        cmd_state = pdata.get("vehicleCommandState", {})
        state = cmd_state.get("state")

        if state is None:
            _LOGGER.warning(
                "Received command state update for %s with missing or null state: %s",
                command_id,
                cmd_state,
            )
            # Unsubscribe from this malformed subscription
            asyncio.create_task(self._unsubscribe_command_state(command_id))
            return

        _LOGGER.debug(
            "Command %s state update: %s",
            command_id,
            cmd_state,
        )

        # Store command state
        self._command_states[command_id] = {
            "command": cmd_state.get("command"),
            "state": state,
            "responseCode": cmd_state.get("responseCode"),
            "statusCode": cmd_state.get("statusCode"),
            "createdAt": cmd_state.get("createdAt"),
        }

        # Keep only last 10 command states
        if len(self._command_states) > 10:
            oldest_key = next(iter(self._command_states))
            self._command_states.pop(oldest_key)

        # Fire events based on state
        event_data = {
            "vehicle_id": self.vehicle_id,
            "command_id": command_id,
            "command": cmd_state.get("command"),
            "state": state,
            "response_code": cmd_state.get("responseCode"),
            "status_code": cmd_state.get("statusCode"),
        }

        if state == "COMPLETED_SUCCESS":
            from .const import EVENT_COMMAND_SUCCESS

            self.hass.bus.fire(EVENT_COMMAND_SUCCESS, event_data)
            # Unsubscribe from this command
            asyncio.create_task(self._unsubscribe_command_state(command_id))
        elif state in ["COMPLETED_ERROR", "FAILED"]:
            from .const import EVENT_COMMAND_FAILED

            self.hass.bus.fire(EVENT_COMMAND_FAILED, event_data)
            # Unsubscribe from this command
            asyncio.create_task(self._unsubscribe_command_state(command_id))

    async def _subscribe_to_command_state(self, command_id: str) -> None:
        """Subscribe to command state updates."""
        if command_id in self._command_state_subscriptions:
            _LOGGER.debug("Already subscribed to command %s", command_id)
            return

        try:
            unsubscribe = await self.api.subscribe_for_command_state(
                command_id=command_id,
                callback=lambda data: self._process_command_state(command_id, data),
            )
            if unsubscribe:
                self._command_state_subscriptions[command_id] = unsubscribe
                _LOGGER.debug("Subscribed to command %s state updates", command_id)

                # Auto-unsubscribe after 60 seconds to prevent memory leaks
                async def _auto_unsubscribe():
                    await asyncio.sleep(60)
                    await self._unsubscribe_command_state(command_id)

                asyncio.create_task(_auto_unsubscribe())
        except Exception as ex:
            _LOGGER.error("Failed to subscribe to command %s state: %s", command_id, ex)

    async def _unsubscribe_command_state(self, command_id: str) -> None:
        """Unsubscribe from command state updates."""
        if unsub := self._command_state_subscriptions.pop(command_id, None):
            try:
                await unsub()
                _LOGGER.debug("Unsubscribed from command %s state updates", command_id)
            except Exception as ex:
                _LOGGER.error("Error unsubscribing from command %s: %s", command_id, ex)

    def get_command_state(self, command_id: str) -> dict[str, Any] | None:
        """Get the state of a specific command."""
        return self._command_states.get(command_id)

    async def send_vehicle_command(
        self, command: VehicleCommand, params: dict[str, Any] | None = None
    ) -> str | None:
        """Send a command to the vehicle.

        Returns:
            Command ID if successful, None otherwise
        """
        _LOGGER.debug("Sending command %s with params: %s", command, params)

        if self.get("powerState") == "sleep" and command != VehicleCommand.WAKE_VEHICLE:
            await self.send_vehicle_command(VehicleCommand.WAKE_VEHICLE)
            try:
                await asyncio.wait_for(self._awake.wait(), 30)
            except asyncio.TimeoutError:
                pass  # didn't wake-up in time, but we'll try command anyway

        entry_data = self.hass.data[DOMAIN][self.config_entry.entry_id]
        vehicle = entry_data[ATTR_VEHICLE][self.vehicle_id]
        user: UserCoordinator = entry_data[ATTR_COORDINATOR][ATTR_USER]
        phone_info = user.get_enrolled_phone_data(
            self.config_entry.options.get("public_key")
        )

        command_id = await self.api.send_vehicle_command(
            command=command,
            vehicle_id=self.vehicle_id,
            phone_id=phone_info[0],
            identity_id=vehicle["phone_identity_id"],
            vehicle_key=vehicle["public_key"],
            private_key=self.config_entry.options.get("private_key"),
            params=params,
        )

        if command_id:
            _LOGGER.debug("%s command sent with ID: %s", command, command_id)

            # Fire initiated event
            from .const import EVENT_COMMAND_INITIATED

            self.hass.bus.fire(
                EVENT_COMMAND_INITIATED,
                {
                    "vehicle_id": self.vehicle_id,
                    "command": command.value,
                    "command_id": command_id,
                },
            )

            # Subscribe to command state updates
            await self._subscribe_to_command_state(command_id)

        return command_id


class VehicleImageCoordinator(RivianDataUpdateCoordinator[list[dict[str, Any]]]):
    """Vehicle image data update coordinator for Rivian."""

    key = "getVehicleMobileImages"
    _update_interval_seconds = 0  # disabled
    _last_updated: datetime | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: Rivian,
        version: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(hass=hass, config_entry=config_entry, client=client)
        self.version = version

    async def _fetch_data(self) -> list[dict[str, Any]]:
        """Fetch the data."""
        data = await self.api.get_vehicle_images(
            resolution="@3x", vehicle_version=self.version
        )
        self._last_updated = datetime.now(timezone.utc)
        # Extract just the vehicle images list
        return data.get(self.key, [])


class WallboxCoordinator(RivianDataUpdateCoordinator[list[dict[str, Any]]]):
    """Wallbox data update coordinator for Rivian."""

    key = "getRegisteredWallboxes"

    async def _fetch_data(self) -> list[dict[str, Any]]:
        """Fetch the data."""
        return await self.api.get_registered_wallboxes()
