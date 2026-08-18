"""Data update coordinator for the Rivian integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Any, Generic, TypeVar

from rivian import Rivian, VehicleCommand
from rivian.exceptions import (
    RivianApiException,
    RivianApiRateLimitError,
    RivianExpiredTokenError,
    RivianUnauthenticated,
)
from rivian.parallax import CHARGING_RVMS, PARALLAX_RVMS, decode_parallax_message

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ATTR_COORDINATOR,
    ATTR_USER,
    ATTR_VEHICLE,
    CHARGING_STATE_KEYS,
    DEFAULT_CHARGING_SCHEDULE,
    DOMAIN,
    INVALID_SENSOR_STATES,
    VEHICLE_STATE_API_FIELDS,
)
from .helpers import redact

_LOGGER = logging.getLogger(__name__)
T = TypeVar("T", bound=dict[str, Any] | list[dict[str, Any]])

# Maximum time to wait for the first vehicle state to arrive after subscribing.
# The first `_process_new_data` callback has been observed ~27s after the
# subscription is established, so this needs meaningful headroom.
INITIAL_UPDATE_TIMEOUT = 60
CHARGING_SCHEDULE_COOL_OFF = 10
CHARGING_SCHEDULE_REFRESH_INTERVAL = 900


class RivianDataUpdateCoordinator(DataUpdateCoordinator[T], ABC, Generic[T]):
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

    def get(self, key: str, default: Any | None = None) -> Any | None:
        """Get a data value by key, supporting dot notation for nested keys.

        The ONE accessor for every coordinator. There used to be three with
        incompatible signatures -- the base took (key, default), VehicleCoordinator
        took (key) only, and ParallaxCoordinator read a separate store -- so
        `vehicle_coordinator.get("x", False)` raised TypeError depending purely on
        which coordinator the caller happened to hold.

        VehicleCoordinator wraps each field as {"value": ..., "history": {...}}
        while ChargingCoordinator stores flat values, so a wrapped field is
        unwrapped here rather than at every call site.
        """
        if not self.data:
            return default

        value: Any = self.data
        for part in key.split("."):
            if not isinstance(value, dict):
                return default
            value = value.get(part)
            if value is None:
                return default

        # Unwrap the {"value": ..., "history": ...} envelope.
        if isinstance(value, dict) and "value" in value:
            value = value["value"]

        return value if value is not None else default

    @abstractmethod
    async def _fetch_data(self) -> T:
        """Fetch the data."""
        raise NotImplementedError


class ChargingCoordinator(RivianDataUpdateCoordinator[dict[str, Any]]):
    """Charging data update coordinator for Rivian.

    This coordinator receives live charging data from Parallax protobuf
    messages decoded by the VehicleCoordinator. It no longer polls the
    deprecated getLiveSessionData REST endpoint.
    """

    key = "getLiveSessionData"
    _unplugged_interval = 15 * 60  # 15 minutes
    _plugged_interval = 30  # 30 seconds
    _update_interval_seconds = 0  # disabled - data is pushed via Parallax
    _watchdog_timeout = 5 * 60  # 5 minutes

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
        self._unsub_handler: Callable[[], Awaitable[None]] | None = None
        self._last_update_time: datetime | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._subscription_start_time: datetime | None = None
        self._subscription_count = 0  # Track number of resubscriptions
        self._subscription_enabled = True  # Track if subscription should be active
        self._is_charging: bool = False
        self._session_start_time: datetime | None = None
        # True when the Parallax namespace's startTime was SYNTHESISED rather than
        # reported by the vehicle. Without this, the real startTime arriving later
        # differs from the invented one, looks like a brand-new session, and
        # clears everything the session has accumulated.
        self._synthetic_start_time = False
        # Two sources write this coordinator and they are not interchangeable:
        # four sensors (price, powerKW, timeRemaining, isFreeSession) exist only
        # in the subscription snapshot, and five (displayStatus, evseType,
        # plugConnectionStatus, currentPrice, currentCurrency) only in Parallax.
        # Each owns a namespace and the view entities read is resolved from both,
        # so neither can clobber the other AND a field the subscription stops
        # sending still disappears -- a plain in-place merge could not express the
        # second without breaking the first.
        self._source_data: dict[str, dict[str, Any]] = {
            "subscription": {},
            "parallax": {},
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Get the latest data from Rivian."""
        # Don't create subscription if it's intentionally disabled (not charging)
        if not self._subscription_enabled:
            _LOGGER.debug(
                "Charging subscription disabled for vehicle %s (not charging)",
                self.vehicle_id,
            )
            return self.data or {}

        if not self.data or not self.last_update_success or not self._unsub_handler:
            # Debug: Log why we're (re)subscribing
            reasons = []
            if not self.data:
                reasons.append("no data")
            if not self.last_update_success:
                reasons.append("last update failed")
            if not self._unsub_handler:
                reasons.append("no active subscription")

            # Track subscription lifecycle
            if self._subscription_start_time:
                duration = (
                    datetime.now(timezone.utc) - self._subscription_start_time
                ).total_seconds()
                _LOGGER.debug(
                    "Charging subscription for vehicle %s ended after %.1f minutes. Reasons: %s",
                    self.vehicle_id,
                    duration / 60,
                    ", ".join(reasons),
                )

            await self._unsubscribe()
            self._subscription_count += 1
            self._subscription_start_time = datetime.now(timezone.utc)

            _LOGGER.debug(
                "Creating charging subscription #%d for vehicle %s. WebSocket monitor state: %s",
                self._subscription_count,
                self.vehicle_id,
                "active"
                if self.api._ws_monitor and self.api._ws_monitor.connected
                else "inactive/closed",
            )

            self._unsub_handler = await self.api.subscribe_for_charging_session(
                vehicle_id=self.vehicle_id,
                callback=self._process_new_data,
            )
            # Reset watchdog timer on resubscription
            self._last_update_time = datetime.now(timezone.utc)

            _LOGGER.debug(
                "Charging subscription #%d created for vehicle %s",
                self._subscription_count,
                self.vehicle_id,
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

    def _publish_resolved(self) -> None:
        """Resolve the per-source namespaces into the view entities read.

        Precedence is Parallax over the subscription snapshot, because Parallax
        pushes throughout a session while the snapshot lags. The one exception is
        startTime: a synthesised value must never displace one the vehicle
        actually reported.
        """
        subscription = self._source_data["subscription"]
        parallax = self._source_data["parallax"]
        resolved = {**subscription, **parallax}
        if self._synthetic_start_time and subscription.get("startTime"):
            resolved["startTime"] = subscription["startTime"]
        self.async_set_updated_data(resolved)

    @callback
    def update_from_parallax(self, decoded: dict[str, Any]) -> None:
        """Update charging data from decoded Parallax protobuf fields.

        Merges new fields into existing data and notifies listeners.
        Internal/private fields (prefixed with '_') are excluded.
        """
        # Filter out internal decoder fields
        clean = {k: v for k, v in decoded.items() if not k.startswith("_")}
        if not clean:
            return

        now = datetime.now(timezone.utc)
        new_data = self._source_data["parallax"]

        # If a verified startTime arrives from graph data that differs from existing,
        # it indicates a brand new charging session.
        if "startTime" in clean:
            old_start = new_data.get("startTime")
            if (
                old_start
                and old_start != clean["startTime"]
                and not self._synthetic_start_time
            ):
                # New session started - clear old session metrics
                new_data.clear()
            new_data["startTime"] = clean["startTime"]
            self._synthetic_start_time = False
        elif not new_data.get("startTime") and clean.get("power", 0) > 0:
            new_data["startTime"] = now.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
            self._synthetic_start_time = True

        new_data.update(clean)

        self._publish_resolved()
        _LOGGER.debug("Charging data updated from Parallax: %s", clean)

    def adjust_update_interval(self, is_plugged_in: bool) -> None:
        """Adjust update interval based on plugged in status.

        With Parallax push, polling is disabled. This method is kept for
        backward compatibility with VehicleCoordinator's chargerStatus handler.
        """

    async def async_shutdown(self) -> None:
        """Shutdown coordinator."""
        self._stop_watchdog()
        await self._unsubscribe()
        return await super().async_shutdown()

    @callback
    def _process_new_data(self, data: dict[str, Any]) -> None:
        """Process new charging data from subscription."""
        # Debug: Track time between updates
        now = datetime.now(timezone.utc)
        time_since_last = None
        if self._last_update_time:
            time_since_last = (now - self._last_update_time).total_seconds()
            if time_since_last > 60:  # Log if gap > 1 minute
                _LOGGER.debug(
                    "Charging data update gap for vehicle %s: %.1f minutes",
                    self.vehicle_id,
                    time_since_last / 60,
                )

        # Check for GraphQL error messages from Rivian backend
        if data.get("type") == "error":
            error_payload = data.get("payload", [])
            if isinstance(error_payload, list) and error_payload:
                error_info = error_payload[0]
                error_message = error_info.get("message", "Unknown error")
                extensions = error_info.get("extensions", {})
                rest_info = extensions.get("rest", {})
                status_code = rest_info.get("status")

                _LOGGER.warning(
                    "Charging subscription for vehicle %s received backend error: %s (HTTP %s). "
                    "Subscription #%d age: %.1f min, WebSocket state: %s. Restarting subscription...",
                    self.vehicle_id,
                    error_message,
                    status_code or "unknown",
                    self._subscription_count,
                    (now - self._subscription_start_time).total_seconds() / 60
                    if self._subscription_start_time
                    else 0,
                    "active"
                    if self.api._ws_monitor and self.api._ws_monitor.connected
                    else "inactive/closed",
                )

                # Immediately restart subscription on backend errors (504, 502, etc.)
                if status_code in (502, 504):
                    task = self._unsubscribe()
                    self.config_entry.async_create_task(
                        self.hass, task, eager_start=True
                    )
                    # Request refresh to resubscribe
                    refresh_task = self.async_request_refresh()
                    self.config_entry.async_create_task(
                        self.hass, refresh_task, eager_start=True
                    )
                return

        if not (payload := data.get("payload")) or not (pdata := payload.get("data")):
            _LOGGER.error(
                "Received unknown charging subscription update: %s. WebSocket state: %s, subscription age: %.1f min",
                data,
                "active"
                if self.api._ws_monitor and self.api._ws_monitor.connected
                else "inactive/closed",
                (now - self._subscription_start_time).total_seconds() / 60
                if self._subscription_start_time
                else 0,
            )
            self._error_count += 1
            if not self._initial.is_set() or self._error_count > 5:
                _LOGGER.warning(
                    "Too many errors (%d) on charging subscription for vehicle %s, unsubscribing",
                    self._error_count,
                    self.vehicle_id,
                )
                task = self._unsubscribe()
                self.config_entry.async_create_task(self.hass, task, eager_start=True)
            return

        charging_data = pdata.get("chargingSession", {})

        # Handle case where chargingSession is a list (e.g., empty list when not charging)
        if isinstance(charging_data, list):
            if not charging_data:
                # Empty list means no active charging session
                _LOGGER.debug("No active charging session")
                # Clear only the subscription's namespace. Parallax state such as
                # plugConnectionStatus is not session-scoped -- the car can still
                # be plugged in after a session ends.
                self._source_data["subscription"] = {}
                self._synthetic_start_time = False
                self._publish_resolved()
                self._error_count = 0
                self._initial.set()
                # Update watchdog timestamp even for empty session
                self._last_update_time = datetime.now(timezone.utc)
                return
            # If it's a non-empty list, take the first item
            charging_data = charging_data[0]

        # Merge chartData and liveData into flat structure matching current API
        processed_data = self._process_charging_data(charging_data)
        # A snapshot: it REPLACES the subscription's namespace, so a field it
        # stops sending disappears, while Parallax's namespace is untouched.
        self._source_data["subscription"] = processed_data
        self._publish_resolved()
        self._error_count = 0
        self._initial.set()

        # Update watchdog timestamp
        self._last_update_time = datetime.now(timezone.utc)

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
            _LOGGER.debug(
                "Unsubscribing from charging subscription #%d for vehicle %s (active for %.1f min)",
                self._subscription_count,
                self.vehicle_id,
                (
                    datetime.now(timezone.utc) - self._subscription_start_time
                ).total_seconds()
                / 60
                if self._subscription_start_time
                else 0,
            )
            await unsub()
            self._unsub_handler = None
            self._initial.clear()

    def _start_watchdog(self) -> None:
        """Start the subscription watchdog."""
        if self._watchdog_task and not self._watchdog_task.done():
            return  # Watchdog already running

        async def _watchdog_loop():
            """Monitor subscription health and restart if stale."""
            while True:
                await asyncio.sleep(60)  # Check every minute

                if not self._last_update_time:
                    continue

                time_since_update = (
                    datetime.now(timezone.utc) - self._last_update_time
                ).total_seconds()

                # Restart subscription if stale
                if time_since_update > self._watchdog_timeout:
                    subscription_age = (
                        (
                            datetime.now(timezone.utc) - self._subscription_start_time
                        ).total_seconds()
                        / 60
                        if self._subscription_start_time
                        else 0
                    )
                    _LOGGER.warning(
                        "Charging subscription for vehicle %s stale, no updates for %.1f minutes. "
                        "Subscription #%d age: %.1f min, WebSocket state: %s. Restarting...",
                        self.vehicle_id,
                        time_since_update / 60,
                        self._subscription_count,
                        subscription_age,
                        "active"
                        if self.api._ws_monitor and self.api._ws_monitor.connected
                        else "inactive/closed",
                    )
                    await self._unsubscribe()
                    task = self.async_request_refresh()
                    self.config_entry.async_create_task(
                        self.hass, task, eager_start=True
                    )

        self._watchdog_task = self.config_entry.async_create_task(
            self.hass, _watchdog_loop(), eager_start=True
        )
        _LOGGER.debug("Started charging watchdog for vehicle %s", self.vehicle_id)

    def _stop_watchdog(self) -> None:
        """Stop the subscription watchdog."""
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            self._watchdog_task = None
            _LOGGER.debug("Stopped charging watchdog for vehicle %s", self.vehicle_id)

    def toggle_watchdog(self, enabled: bool) -> None:
        """Enable or disable the watchdog based on charging state."""
        if enabled:
            self._start_watchdog()
        else:
            self._stop_watchdog()

    async def toggle_subscription(self, enabled: bool) -> None:
        """Enable or disable the charging subscription based on charging state.

        This manages the subscription lifecycle to reduce bandwidth when not charging.
        """
        if enabled and not self._subscription_enabled:
            # Start subscription when charging begins
            _LOGGER.info(
                "Enabling charging subscription for vehicle %s (charger connected)",
                self.vehicle_id,
            )
            self._subscription_enabled = True
            # Trigger a refresh which will create the subscription
            await self.async_request_refresh()
        elif not enabled and self._subscription_enabled:
            # Stop subscription when charging ends
            _LOGGER.info(
                "Disabling charging subscription for vehicle %s (charger disconnected)",
                self.vehicle_id,
            )
            self._subscription_enabled = False
            if self._unsub_handler:
                await self._unsubscribe()

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
                for user in self.data.get("invitedUsers", [])
                if "devices" in user  # Only provisioned users have devices
                for device in user.get("devices", [])
                if device.get("mappedIdentityId") == identity_id
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
    _watchdog_timeout = 5 * 60  # 5 minutes

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
        self._unsub_handler: Callable[[], Awaitable[None]] | None = None
        self._unsub_parallax: Callable[[], Awaitable[None]] | None = None
        self._connection_unsub_handler: Callable[[], Awaitable[None]] | None = None
        self._is_online: bool = False
        self._last_sync: str | None = None
        self._awake = asyncio.Event()
        self._command_state_subscriptions: dict[str, Callable[[], Awaitable[None]]] = {}
        self._command_states: dict[str, dict[str, Any]] = {}
        self._last_update_time: datetime | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._prev_charger_state: str | None = None
        self._subscription_start_time: datetime | None = None
        self._subscription_count = 0  # Track number of resubscriptions
        self._charging_schedule: dict[str, Any] | None = None
        self._last_schedule_fetch: float = 0.0

    @property
    def charging_schedule(self) -> dict[str, Any]:
        """Return the charging schedule or empty dict."""
        return self._charging_schedule or {}

    async def get_charging_schedule_data(
        self, force_refresh: bool = False
    ) -> dict[str, Any]:
        """Fetch charging schedule via Rivian API."""
        now = time.time()
        cooldown = (
            CHARGING_SCHEDULE_COOL_OFF
            if force_refresh
            else CHARGING_SCHEDULE_REFRESH_INTERVAL
        )
        if self._charging_schedule is None or (
            now - self._last_schedule_fetch > cooldown
        ):
            self._last_schedule_fetch = now
            try:
                response = await self.api.get_charging_schedules(self.vehicle_id)
                res_json = await response.json()
                if (
                    res_json
                    and "data" in res_json
                    and res_json["data"].get("getVehicle")
                ):
                    schedules = res_json["data"]["getVehicle"].get(
                        "chargingSchedules", []
                    )
                    if schedules:
                        old_schedule = self._charging_schedule
                        self._charging_schedule = schedules[0]
                        if old_schedule != self._charging_schedule:
                            self.async_update_listeners()
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("Error fetching charging schedule: %s", err)

            if self._charging_schedule is None:
                self._charging_schedule = dict(DEFAULT_CHARGING_SCHEDULE)
        return self._charging_schedule

    async def update_charging_schedule_data(self, schedule: dict[str, Any]) -> None:
        """Update charging schedule via Rivian API mutation."""
        current = dict(await self.get_charging_schedule_data(force_refresh=True))
        current.update(schedule)
        try:
            await self.api.set_charging_schedules(self.vehicle_id, [current])
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error setting charging schedule: %s", err)
        self._charging_schedule = current
        self.async_update_listeners()

    async def _async_update_data(self) -> dict[str, Any]:
        """Get the latest data from Rivian."""
        await self.get_charging_schedule_data()
        if not self.data or not self.last_update_success or not self._unsub_handler:
            # Debug: Log why we're (re)subscribing
            reasons = []
            if not self.data:
                reasons.append("no data")
            if not self.last_update_success:
                reasons.append("last update failed")
            if not self._unsub_handler:
                reasons.append("no active subscription")

            # Track subscription lifecycle
            if self._subscription_start_time:
                duration = (
                    datetime.now(timezone.utc) - self._subscription_start_time
                ).total_seconds()
                _LOGGER.debug(
                    "Vehicle %s subscription ended after %.1f minutes. Reasons: %s",
                    self.vehicle_id,
                    duration / 60,
                    ", ".join(reasons),
                )
            await self._unsubscribe()
            self._subscription_count += 1
            self._subscription_start_time = datetime.now(timezone.utc)

            _LOGGER.debug(
                "Creating vehicle subscription #%d for vehicle %s. WebSocket monitor state: %s",
                self._subscription_count,
                self.vehicle_id,
                "active"
                if self.api._ws_monitor and self.api._ws_monitor.connected
                else "inactive/closed",
            )

            self._unsub_handler = await self.api.subscribe_for_vehicle_updates(
                vehicle_id=self.vehicle_id,
                properties=VEHICLE_STATE_API_FIELDS,
                callback=self._process_new_data,
            )

            # Parallax. The RVM list is explicit and DEDUPED rather than rvms=None:
            # PARALLAX_RVMS and CHARGING_RVMS overlap by five topics, so naive
            # concatenation would ask for 25 subscriptions covering 20 topics and
            # every duplicated message would be delivered and decoded twice.
            self._unsub_parallax = await self.api.subscribe_for_parallax_messages(
                vehicle_id=self.vehicle_id,
                callback=self._process_parallax_data,
                rvms=sorted({*PARALLAX_RVMS, *CHARGING_RVMS}),
            )

            # Also subscribe to cloud connection for online/offline status
            self._connection_unsub_handler = (
                await self.api.subscribe_for_cloud_connection(
                    vehicle_id=self.vehicle_id,
                    callback=self._process_cloud_connection_data,
                )
            )

            # Reset watchdog timer on resubscription
            self._last_update_time = datetime.now(timezone.utc)

            _LOGGER.debug(
                "Vehicle subscription #%d created for vehicle %s",
                self._subscription_count,
                self.vehicle_id,
            )

            try:
                await asyncio.wait_for(self._initial.wait(), INITIAL_UPDATE_TIMEOUT)
            except asyncio.TimeoutError as err:
                raise UpdateFailed(
                    "Timed out waiting for initial vehicle data after "
                    f"{INITIAL_UPDATE_TIMEOUT}s"
                ) from err

            # Start watchdog after successful subscription
            self._start_watchdog()

        return self.data

    async def _fetch_data(self) -> dict[str, Any]:
        """Fetch the data."""
        raise NotImplementedError("Polling VehicleState no longer allowed")

    def _start_watchdog(self) -> None:
        """Start the subscription watchdog."""
        if self._watchdog_task and not self._watchdog_task.done():
            return  # Watchdog already running

        async def _watchdog_loop():
            """Monitor subscription health and restart if stale."""
            while True:
                await asyncio.sleep(60)  # Check every minute

                if not self._last_update_time:
                    continue

                time_since_update = (
                    datetime.now(timezone.utc) - self._last_update_time
                ).total_seconds()

                # Skip if vehicle is sleeping (no updates expected)
                power_state = self.get("powerState")
                if power_state == "sleep":
                    _LOGGER.debug(
                        "Vehicle %s is sleeping, skipping watchdog check",
                        self.vehicle_id,
                    )
                    continue

                # Restart subscription if stale
                if time_since_update > self._watchdog_timeout:
                    subscription_age = (
                        (
                            datetime.now(timezone.utc) - self._subscription_start_time
                        ).total_seconds()
                        / 60
                        if self._subscription_start_time
                        else 0
                    )
                    _LOGGER.warning(
                        "Vehicle %s subscription stale, no updates for %.1f minutes (powerState: %s). "
                        "Subscription #%d age: %.1f min, WebSocket state: %s, online: %s. Restarting...",
                        self.vehicle_id,
                        time_since_update / 60,
                        power_state,
                        self._subscription_count,
                        subscription_age,
                        "active"
                        if self.api._ws_monitor and self.api._ws_monitor.connected
                        else "inactive/closed",
                        self._is_online,
                    )
                    await self._unsubscribe()
                    task = self.async_request_refresh()
                    self.config_entry.async_create_task(
                        self.hass, task, eager_start=True
                    )

        self._watchdog_task = self.config_entry.async_create_task(
            self.hass, _watchdog_loop(), eager_start=True
        )
        _LOGGER.debug("Started watchdog for vehicle %s", self.vehicle_id)

    def _stop_watchdog(self) -> None:
        """Stop the subscription watchdog."""
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            self._watchdog_task = None
            _LOGGER.debug("Stopped watchdog for vehicle %s", self.vehicle_id)

    async def async_shutdown(self) -> None:
        # Stop watchdog
        self._stop_watchdog()

        # Unsubscribe from all active command state subscriptions
        for command_id in list(self._command_state_subscriptions.keys()):
            await self._unsubscribe_command_state(command_id)

        await self._unsubscribe(True)
        return await super().async_shutdown()

    @callback
    def _process_parallax_data(self, data: dict[str, Any]) -> None:
        """Process incoming Parallax subscription messages."""
        if not (payload := data.get("payload")) or not (pdata := payload.get("data")):
            return
        px = pdata.get("parallaxMessages")
        if not px:
            return
        decoded = decode_parallax_message(**px)
        if not decoded:
            return

        clean = {k: v for k, v in decoded.items() if not k.startswith("_")}
        if not clean:
            return

        # Route charging fields to ChargingCoordinator
        if charging_keys := clean.keys() & CHARGING_STATE_KEYS:
            self.charging_coordinator.update_from_parallax(clean)

        # Route vehicle state fields to VehicleCoordinator
        # Note: timeToEndOfCharge is defined in VEHICLE_SENSORS, so it updates VehicleCoordinator too
        vehicle_keys = (clean.keys() - charging_keys) | (
            clean.keys() & {"timeToEndOfCharge"}
        )
        if vehicle_keys:
            vehicle_updates: dict[str, Any] = {}
            for k in vehicle_keys:
                if k == "gnssLocation":
                    vehicle_updates[k] = clean[k]
                elif k == "vehicleMileage":
                    # Parallax encodes odometer as integer km; GraphQL provides float meters.
                    # Both sources active causes oscillation that corrupts utility meters.
                    # Only accept Parallax value if >= stored (monotonic increase).
                    prev_val = (
                        (self.data or {}).get("vehicleMileage", {}).get("value", 0)
                    )
                    new_val = clean[k]
                    if isinstance(new_val, (int, float)) and new_val >= prev_val:
                        vehicle_updates[k] = {"value": new_val, "history": {new_val}}
                else:
                    vehicle_updates[k] = {"value": clean[k], "history": {clean[k]}}
            new_data = (self.data or {}) | vehicle_updates
            self.async_set_updated_data(new_data)
            _LOGGER.debug(
                "Vehicle state updated from Parallax (%s): %s", px.get("rvm"), clean
            )

    @callback
    def _process_new_data(self, data: dict[str, Any]) -> None:
        """Process new data."""
        # Debug: Track time between updates
        now = datetime.now(timezone.utc)
        time_since_last = None
        if self._last_update_time:
            time_since_last = (now - self._last_update_time).total_seconds()
            if time_since_last > 60:  # Log if gap > 1 minute
                _LOGGER.debug(
                    "Vehicle %s data update gap: %.1f minutes (powerState: %s)",
                    self.vehicle_id,
                    time_since_last / 60,
                    self.get("powerState") or "unknown",
                )

        # Check for GraphQL error messages from Rivian backend
        if data.get("type") == "error":
            error_payload = data.get("payload", [])
            if isinstance(error_payload, list) and error_payload:
                error_info = error_payload[0]
                error_message = error_info.get("message", "Unknown error")
                extensions = error_info.get("extensions", {})
                rest_info = extensions.get("rest", {})
                status_code = rest_info.get("status")

                _LOGGER.warning(
                    "Vehicle %s subscription received backend error: %s (HTTP %s). "
                    "Subscription #%d age: %.1f min, WebSocket state: %s. Restarting subscription...",
                    self.vehicle_id,
                    error_message,
                    status_code or "unknown",
                    self._subscription_count,
                    (now - self._subscription_start_time).total_seconds() / 60
                    if self._subscription_start_time
                    else 0,
                    "active"
                    if self.api._ws_monitor and self.api._ws_monitor.connected
                    else "inactive/closed",
                )

                # Immediately restart subscription on backend errors (504, 502, etc.)
                # These indicate Rivian's backend is having issues and the subscription
                # won't recover on its own
                if status_code in (502, 504):
                    task = self._unsubscribe()
                    self.config_entry.async_create_task(
                        self.hass, task, eager_start=True
                    )
                    # Request refresh to resubscribe
                    refresh_task = self.async_request_refresh()
                    self.config_entry.async_create_task(
                        self.hass, refresh_task, eager_start=True
                    )
                return

        if not (payload := data.get("payload")) or not (pdata := payload.get("data")):
            _LOGGER.error(
                "Received an unknown subscription update: %s. WebSocket state: %s, subscription age: %.1f min",
                data,
                "active"
                if self.api._ws_monitor and self.api._ws_monitor.connected
                else "inactive/closed",
                (now - self._subscription_start_time).total_seconds() / 60
                if self._subscription_start_time
                else 0,
            )
            self._error_count += 1
            if not self._initial.is_set() or self._error_count > 5:
                _LOGGER.warning(
                    "Too many errors (%d) on vehicle %s subscription, unsubscribing",
                    self._error_count,
                    self.vehicle_id,
                )
                task = self._unsubscribe()
                self.config_entry.async_create_task(self.hass, task, eager_start=True)
            return
        vehicle_info = self._build_vehicle_info_dict(pdata.get(self.key, {}))
        self.async_set_updated_data(vehicle_info)
        self._error_count = 0
        self._initial.set()

        # Update watchdog timestamp
        self._last_update_time = datetime.now(timezone.utc)

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
        if charger_status := items.get("chargerStatus"):
            raw_status = str(charger_status.get("value", "")).lower()
            is_charging = (
                "charging" in raw_status
                and "not" not in raw_status
                and "disconnected" not in raw_status
            )
            self.charging_coordinator.adjust_update_interval(
                is_plugged_in=raw_status != "chrgr_sts_not_connected"
            )
            if not is_charging:
                # Reset instantaneous charging metrics when not actively charging
                items["timeToEndOfCharge"] = {"value": 0, "history": {0}}

        # Monitor chargerState changes to enable/disable charging watchdog
        if charger_state_data := items.get("chargerState"):
            charger_state = charger_state_data.get("value")
            if charger_state != self._prev_charger_state:
                self._prev_charger_state = charger_state
                # Enable watchdog when charger is connected (any charging state)
                # Disable when not connected (None, "chg_station_disconnected", etc.)
                is_connected = charger_state in (
                    "charging_active",
                    "charging_connecting",
                    "chg_station_connected",
                    "chg_complete",
                )
                _LOGGER.debug(
                    "Vehicle %s chargerState changed to %s, charging subscription: %s",
                    self.vehicle_id,
                    charger_state,
                    "enabled" if is_connected else "disabled",
                )
                # Toggle both watchdog and subscription based on charging state
                self.charging_coordinator.toggle_watchdog(is_connected)
                # Schedule subscription toggle as a task (it's async)
                task = self.charging_coordinator.toggle_subscription(is_connected)
                self.config_entry.async_create_task(self.hass, task, eager_start=True)

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
        prev_online = self._is_online
        self._is_online = connection_data.get("isOnline", False)
        self._last_sync = connection_data.get("lastSync")

        # Debug: Log state changes (online/offline transitions)
        if prev_online != self._is_online:
            _LOGGER.info(
                "Vehicle %s cloud connection state changed: %s -> %s (lastSync=%s, subscription #%d age: %.1f min)",
                self.vehicle_id,
                "online" if prev_online else "offline",
                "online" if self._is_online else "offline",
                self._last_sync,
                self._subscription_count,
                (
                    datetime.now(timezone.utc) - self._subscription_start_time
                ).total_seconds()
                / 60
                if self._subscription_start_time
                else 0,
            )
        else:
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
        if unsub := self._unsub_parallax:
            await unsub()
            self._unsub_parallax = None

        # Unsubscribe from vehicle state
        if unsub := self._unsub_handler:
            _LOGGER.debug(
                "Unsubscribing from vehicle subscription #%d for vehicle %s (active for %.1f min)",
                self._subscription_count,
                self.vehicle_id,
                (
                    datetime.now(timezone.utc) - self._subscription_start_time
                ).total_seconds()
                / 60
                if self._subscription_start_time
                else 0,
            )
            await unsub()
            self._unsub_handler = None
            self._initial.clear()

        # Unsubscribe from cloud connection
        if connection_unsub := self._connection_unsub_handler:
            _LOGGER.debug(
                "Unsubscribing from cloud connection subscription for vehicle %s",
                self.vehicle_id,
            )
            await connection_unsub()
            self._connection_unsub_handler = None

        if close_monitor and (monitor := self.api._ws_monitor):
            _LOGGER.info(
                "Closing WebSocket monitor for vehicle %s (close_monitor=%s)",
                self.vehicle_id,
                close_monitor,
            )
            await monitor.close()

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
        except Exception as ex:  # noqa: BLE001 -- a failed command-state subscription must not abort the command itself
            _LOGGER.error("Failed to subscribe to command %s state: %s", command_id, ex)

    async def _unsubscribe_command_state(self, command_id: str) -> None:
        """Unsubscribe from command state updates."""
        if unsub := self._command_state_subscriptions.pop(command_id, None):
            try:
                await unsub()
                _LOGGER.debug("Unsubscribed from command %s state updates", command_id)
            except Exception as ex:  # noqa: BLE001 -- teardown: an unsubscribe failure must not mask the caller's outcome
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

    async def send_parallax_command(
        self, method_name: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Send a Parallax command to the vehicle.

        Parallax commands use the cloud-based protocol and don't require HMAC signing,
        but do require phone pairing for authorization.

        Args:
            method_name: The API method name (e.g., "set_halloween_settings")
            **kwargs: Parameters to pass to the API method

        Returns:
            dict with success status and response payload
        """
        _LOGGER.debug(
            "Sending Parallax command %s with kwargs: %s", method_name, kwargs
        )

        # Get the API method by name
        method = getattr(self.api, method_name)

        # Call the method with vehicle_id and any additional kwargs
        return await method(vehicle_id=self.vehicle_id, **kwargs)


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
