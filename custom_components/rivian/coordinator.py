"""Data update coordinator for the Rivian integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Any, Final, Generic, TypeVar
import uuid

from aiohttp import ClientResponse

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .connectivity import ConnectivityState, derive_connectivity_state
from .const import (
    ATTR_COORDINATOR,
    ATTR_USER,
    ATTR_VEHICLE,
    CHARGING_STATE_KEYS,
    DEFAULT_CHARGING_SCHEDULE,
    DOMAIN,
    INVALID_SENSOR_STATES,
    VEHICLE_STATE_SUBSCRIPTION_FIELDS,
)
from .helpers import redact, redact_text
from .rivian_client import Rivian, VehicleCommand
from .rivian_client.exceptions import (
    RivianApiException,
    RivianApiRateLimitError,
    RivianUnauthenticated,
)
from .rivian_client.parallax import (
    CHARGING_RVMS,
    PARALLAX_RVMS,
    RVM_DECODERS,
    decode_parallax_message,
)

_LOGGER = logging.getLogger(__name__)
T = TypeVar("T", bound=dict[str, Any] | list[dict[str, Any]])

# Maximum time to wait for the first vehicle state to arrive after subscribing.
# The first `_process_new_data` callback has been observed ~27s after the
# subscription is established, so this needs meaningful headroom.
INITIAL_UPDATE_TIMEOUT = 60
CHARGING_SCHEDULE_COOL_OFF = 10
CHARGING_SCHEDULE_REFRESH_INTERVAL = 900

# Continue-set of vehicleCommandState integers, transcribed from the app's
# switch (C4171i / C2225j). Must stay equal to
# tests.apk.transcription.COMMAND_STATE_CONTINUE. This module cannot import
# that package: tests/ is not in the HACS zip, and an import would unload the
# integration on every production install.
COMMAND_STATE_CONTINUE: Final[frozenset[int]] = frozenset({1, 2, 3, 5})
COMMAND_STATE_STRING_TERMINAL: Final[frozenset[str]] = frozenset(
    {"COMPLETED_SUCCESS", "COMPLETED_ERROR", "FAILED"}
)
# Age invariant for _command_states. 32 is a floor, not a cap: in-window
# entries are never evicted, even if that takes the map above 32.
COMMAND_STATE_WINDOW = 60
COMMAND_STATE_CAPACITY = 32


def _command_state_is_lifecycle(state: Any) -> bool | None:
    """Return whether a command-state frame is still in-flight.

    True: int in COMMAND_STATE_CONTINUE ({1,2,3,5}).
    False: any other int (the app's switch default is terminal too), or one of
    the three known string enum members.
    None: any other string or type -- unknown to us, not a guess.
    """
    if isinstance(state, int):
        return state in COMMAND_STATE_CONTINUE
    if state in COMMAND_STATE_STRING_TERMINAL:
        return False
    return None


def _online_label(value: bool | None) -> str:
    """Render the tri-state cloud flag for the transition log.

    Three labels, not two: the log line is the only record a transition leaves, and
    rendering None as "offline" would make an investigation of a post-restart or a
    null-payload transition read as a genuine disconnection.
    """
    if value is None:
        return "unknown"
    return "online" if value else "offline"


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
        # Watchdog state, shared by every coordinator that runs one.
        self._watchdog_task: asyncio.Task | None = None
        self._last_update_time: datetime | None = None
        self._subscription_start_time: datetime | None = None
        self._subscription_count = 0
        # For diagnostics (§G): how many times _watchdog_tick has restarted this
        # coordinator's subscription, and why the most recent one fired.
        self._watchdog_restarts = 0
        self._last_restart_reason: str | None = None

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
        """Get the latest data from Rivian.

        _fetch_data returns an aiohttp ClientResponse -- that is the client's
        contract for every method reaching this base class -- so the envelope has
        to come off here: check the status, await .json(), and take
        data["data"][key].

        This unwrapping was dropped during the upstream merge and nothing failed,
        because the tests mock self.api.get_*() as already returning the inner
        dict. The integration died on its first real boot with
        "'HassClientResponse' object has no attribute 'get'". self.key existed on
        every subclass the whole time with nothing reading it, which is the tell.
        """
        try:
            resp = await self._fetch_data()
            if resp.status == 200:
                payload = await resp.json()
                _LOGGER.debug(
                    "[%s] %s",
                    self.__class__.__name__.replace("Coordinator", ""),
                    redact(payload),
                )
                if self._error_count:
                    self._error_count = 0
                    self._set_update_interval()
                try:
                    return payload["data"][self.key]
                except (KeyError, TypeError) as err:
                    # Without this the miss lands in the broad `except Exception`
                    # below, which returns self.data -- so a renamed or withdrawn
                    # field leaves entities showing plausible but frozen values
                    # indefinitely, with last_update_success still True. One ERROR
                    # line per poll and nothing visible in the UI. Fail loudly:
                    # UpdateFailed marks the coordinator unsuccessful and the
                    # entities unavailable.
                    raise UpdateFailed(
                        f"{self.key} missing from the response payload"
                    ) from err
            resp.raise_for_status()

        except UpdateFailed:
            # Raised deliberately just above for a missing key. Without this it
            # falls into the broad handler below, which returns self.data -- the
            # exact stale-data-presented-as-fresh behaviour the raise exists to
            # stop -- and the specific message is lost.
            raise
        except RivianApiRateLimitError as err:
            _LOGGER.error(
                "Rate limit being enforced: %s", redact_text(str(err)), exc_info=1
            )
            self._set_update_interval()
        except RivianUnauthenticated as err:
            await self.api.close()
            raise ConfigEntryAuthFailed from err
        except RivianApiException as ex:
            _LOGGER.error("Rivian api exception: %s", redact_text(str(ex)), exc_info=1)
        # Anything reaching here was built outside RivianApiException's redacting
        # constructor, so its traceback would render verbatim. exc_info is dropped
        # on purpose; BLE001 exists to catch a traceback discarded by accident.
        except Exception as ex:  # noqa: BLE001
            _LOGGER.error(
                "Unknown Exception while updating Rivian data: %s", redact_text(str(ex))
            )

        self._error_count += 1
        if self.data:
            return self.data
        raise UpdateFailed("Error communicating with API")

    # --- subscription watchdog -------------------------------------------
    #
    # Lifted here from ChargingCoordinator and VehicleCoordinator, which carried
    # near-identical ~50-line copies differing only in log wording and one skip
    # rule. A tick is its own method so the logic can be driven directly in tests:
    # the previous per-coordinator tests re-derived the trigger conditions in the
    # test body and could not fail when the logic changed.

    _watchdog_timeout = 5 * 60  # seconds without data before we resubscribe
    _watchdog_interval = 60  # seconds between checks

    def _watchdog_skip_reason(self) -> str | None:
        """Return why this tick should be skipped, or None to proceed."""
        return None

    async def _watchdog_tick(self) -> bool:
        """Run one health check. Returns True if the subscription was restarted."""
        if not self._last_update_time:
            # Nothing has arrived yet, so there is nothing to be stale relative
            # to; restarting here would fight the initial subscription.
            return False

        if reason := self._watchdog_skip_reason():
            _LOGGER.debug(
                "Watchdog skipping check for vehicle %s: %s", self.vehicle_id, reason
            )
            return False

        idle = (datetime.now(timezone.utc) - self._last_update_time).total_seconds()
        if idle <= self._watchdog_timeout:
            return False

        age = (
            (datetime.now(timezone.utc) - self._subscription_start_time).total_seconds()
            / 60
            if self._subscription_start_time
            else 0
        )
        _LOGGER.warning(
            "%s subscription for vehicle %s stale, no updates for %.1f minutes. "
            "Subscription #%d age: %.1f min, WebSocket state: %s. Restarting...",
            type(self).__name__,
            self.vehicle_id,
            idle / 60,
            self._subscription_count,
            age,
            "active"
            if self.api._ws_monitor and self.api._ws_monitor.connected
            else "inactive/closed",
        )
        self._watchdog_restarts += 1
        self._last_restart_reason = f"stale for {idle / 60:.1f} min"
        await self._unsubscribe()
        task = self.async_request_refresh()
        self.config_entry.async_create_task(self.hass, task, eager_start=True)
        return True

    def _start_watchdog(self) -> None:
        """Start the subscription watchdog, if it is not already running."""
        if self._watchdog_task and not self._watchdog_task.done():
            return

        async def _watchdog_loop() -> None:
            while True:
                await asyncio.sleep(self._watchdog_interval)
                await self._watchdog_tick()

        # A BACKGROUND task, deliberately. config_entry.async_create_task registers
        # work Home Assistant waits for while finishing startup, and _watchdog_loop
        # is `while True` -- so it never completes and bootstrap blocks on it until
        # it times out. Measured on a real instance: "Home Assistant initialized in
        # 327.59s", every restart, with the bootstrap warning naming this coroutine.
        self._watchdog_task = self.config_entry.async_create_background_task(
            self.hass,
            _watchdog_loop(),
            name=f"rivian {type(self).__name__} watchdog {self.vehicle_id}",
        )
        _LOGGER.debug(
            "Started %s watchdog for vehicle %s", type(self).__name__, self.vehicle_id
        )

    def _stop_watchdog(self) -> None:
        """Stop the subscription watchdog."""
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
        self._watchdog_task = None

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

    # Returns the raw response, NOT T. _async_update_data above unwraps it to T.
    @abstractmethod
    async def _fetch_data(self) -> ClientResponse:
        """Fetch the data."""
        raise NotImplementedError


# The topics we subscribe to: everything in upstream's two lists that we can
# actually decode.
#
# CHARGING_RVMS names three -- charging.session.notification, .remote_command and
# .soc_slider -- that RVM_DECODERS does not cover. The vehicle pushes them, the
# payload is discarded, and the client logs "Unknown Parallax RVM topic" for each,
# roughly every three minutes on a live instance. Subscribing bought nothing.
#
# Filtered here rather than by narrowing CHARGING_RVMS, which is upstream's and
# vendored: editing it would diverge a file we merge. The intersection is also
# self-maintaining -- add a decoder and its topic is subscribed automatically.
SUBSCRIBED_RVMS: Final[list[str]] = sorted(
    {*PARALLAX_RVMS, *CHARGING_RVMS} & set(RVM_DECODERS)
)


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

    async def _fetch_data(self) -> ClientResponse:
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


def _extract_option_codes(vehicle: dict[str, Any]) -> list[str] | None:
    """Flatten `mobileConfiguration`'s option ids for containment checks.

    The app gates the powered tonneau with Kotlin `contains`, not `==`
    (java_src/.../UserVehicle.java:616-618:
    `tonneauOptionId.contains(TONNEAU_POWER_OPTION_ID)`), so the eventual gate
    here is `"TON-P01" in option_codes`, never equality -- a flat list is the
    natural shape for that.

    None means the fragment was rejected and rivian.py's
    get_user_information() retried without mobileConfiguration -- the key is
    then absent from `vehicle` entirely. That is deliberately distinguishable
    from an empty list, which means the fragment was accepted and the vehicle
    simply has no matching options.
    """
    mobile_configuration = vehicle.get("mobileConfiguration")
    if mobile_configuration is None:
        return None
    return [
        option["optionId"]
        for key in ("tonneauOption", "wheelOption")
        if (option := mobile_configuration.get(key)) and option.get("optionId")
    ]


class UserCoordinator(RivianDataUpdateCoordinator[dict[str, Any]]):
    """User data update coordinator for Rivian."""

    key = "currentUser"

    # 900 s, not the base's 30. `currentUser` carries the account, its enrolled
    # phones and the vehicle capability list -- a heavyweight query whose payload
    # changes on the order of months, re-fetched twice a minute.
    #
    # 900 exactly, because _set_update_interval computes
    # min(base * 2**error_count, 900) and never reassigns the base. Any value
    # ABOVE 900 is used verbatim at construction and then collapses to 900 on the
    # first error, never climbing back -- a back-off that only ever ratchets
    # downward. Sitting at the cap makes that unreachable.
    #
    # The cost, stated rather than hidden: at the cap the back-off is a no-op, so
    # an erroring coordinator keeps retrying every 15 minutes instead of
    # stretching further. 900 s is the ceiling the old 30 s base reached anyway
    # after five consecutive failures, and the point of the back-off was to stop a
    # failing API being polled every 30 seconds. Starting at the ceiling does that
    # outright.
    _update_interval_seconds = 15 * 60  # 15 minutes

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: Rivian,
        include_phones: bool = False,
    ) -> None:
        super().__init__(hass=hass, config_entry=config_entry, client=client)
        self.include_phones = include_phones

    async def _fetch_data(self) -> ClientResponse:
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
                "option_codes": _extract_option_codes(vehicle.get("vehicle", {})),
            }
            for vehicle in self.data["vehicles"]
        }


class SupportedFeaturesCoordinator(RivianDataUpdateCoordinator[dict[str, Any]]):
    """SupportedFeatures feed coordinator for Rivian.

    A standalone query the app fetches separately from getUserInfo (see
    Rivian.get_supported_features), rather than the supportedFeatures
    fragment UserCoordinator.get_vehicles() already reads out of
    getUserInfo's embedded vehicleState. `key = "currentUser"` because that
    is this query's root too; the 15-minute interval matches UserCoordinator
    for the same reason given on its `_update_interval_seconds` -- a
    heavyweight, slow-changing query with no business being polled fast.

    ADDITIVE SIGNAL, NOT A FILTER. Feature absence here is not evidence of
    absent capability: TONNEAU_CMD appears in no vehicle's supportedFeatures
    and in none of the app's decompiled files, yet both tonneau commands
    physically move the cover (docs/development/MODEL_SPECIFIC_ENTITIES.md,
    around lines 9-15). Nothing gates on this coordinator's output; it exists
    to make the feed observable (diagnostics) alongside the embedded
    fallback in UserCoordinator.get_vehicles(), which stays in place and is
    used by __init__.py when this feed is unavailable.
    """

    key = "currentUser"
    _update_interval_seconds = 15 * 60  # 15 minutes, see UserCoordinator above

    async def _fetch_data(self) -> ClientResponse:
        """Fetch the data."""
        return await self.api.get_supported_features()

    def available_features(self) -> dict[str, frozenset[str]]:
        """Return AVAILABLE feature names per vehicle id."""
        if not self.data:
            return {}
        return {
            vehicle["id"]: frozenset(
                feature["name"]
                for feature in vehicle.get("vehicle", {})
                .get("vehicleState", {})
                .get("supportedFeatures", [])
                if feature.get("status") == "AVAILABLE"
            )
            for vehicle in self.data.get("vehicles", [])
        }

    def features_by_status(self) -> dict[str, dict[str, str]]:
        """Return {feature_name: status} per vehicle id, every status included.

        AVAILABLE and UPDATE_FIRMWARE both survive here -- unlike
        available_features() above, which is AVAILABLE-only -- so
        diagnostics can surface UPDATE_FIRMWARE instead of silently
        dropping it.
        """
        if not self.data:
            return {}
        return {
            vehicle["id"]: {
                feature["name"]: feature["status"]
                for feature in vehicle.get("vehicle", {})
                .get("vehicleState", {})
                .get("supportedFeatures", [])
                if feature.get("name") and feature.get("status")
            }
            for vehicle in self.data.get("vehicles", [])
        }


class VehicleCoordinator(RivianDataUpdateCoordinator[dict[str, Any]]):
    """Vehicle data update coordinator for Rivian."""

    key = "vehicleState"
    _update_interval_seconds = 15 * 60  # 15 minutes
    _watchdog_timeout = 5 * 60  # 5 minutes
    # S4: its own timeout, not shared with _watchdog_timeout -- the two streams
    # are independent and a shared constant would be a coincidence, not a fact.
    _tpms_watchdog_timeout = 5 * 60

    def _watchdog_skip_reason(self) -> str | None:
        """A sleeping vehicle sends nothing, so silence is expected, not stale.

        ChargingCoordinator deliberately has NO such rule: a charging session
        continues while the vehicle sleeps, and skipping there would stop
        watching an active charge.
        """
        if self.get("powerState") == "sleep":
            return "vehicle is sleeping"
        return None

    async def _tpms_watchdog_tick(self) -> bool:
        """VehicleCoordinator-local liveness check for the TPMS stream (S4).

        Deliberately its own method, not folded into _watchdog_tick:
        _watchdog_tick's only restart action is _unsubscribe(), which tears
        down Parallax, the main vehicleState stream AND the cloud-connection
        subscription -- for a TPMS-only outage that kills two healthy
        subscriptions to fix one dead one. _watchdog_tick also returns early
        whenever _last_update_time is unset, so a check folded into it would
        never run while the main stream itself is silent -- exactly when a
        TPMS problem is worth knowing about independently. Returns True if the
        TPMS subscription was restarted.
        """
        if not self._tpms_last_update_time:
            return False
        idle = (
            datetime.now(timezone.utc) - self._tpms_last_update_time
        ).total_seconds()
        if idle <= self._tpms_watchdog_timeout:
            return False
        _LOGGER.warning(
            "Tire pressure subscription for vehicle %s stale, no updates for "
            "%.1f minutes. Restarting...",
            self.vehicle_id,
            idle / 60,
        )
        await self._resubscribe_tpms()
        return True

    async def _resubscribe_tpms(self) -> None:
        """Restart ONLY the tire-pressure subscription (S4).

        Touches _unsub_tire_pressure exclusively -- unlike _unsubscribe(),
        which also tears down Parallax, the main vehicleState stream and the
        cloud-connection subscription. A dead TPMS stream must cost the 12
        tyre-pressure entities, not a reset of everything else that was fine.
        """
        if unsub := self._unsub_tire_pressure:
            await unsub()
            self._unsub_tire_pressure = None
        try:
            self._unsub_tire_pressure = (
                await self.api.subscribe_for_tire_pressure_updates(
                    vehicle_id=self.vehicle_id,
                    callback=self._process_tire_pressure_data,
                )
            )
            self._tpms_last_update_time = datetime.now(timezone.utc)
        except RivianApiException:
            _LOGGER.exception(
                "Tire pressure re-subscription failed for vehicle %s",
                self.vehicle_id,
            )
            self._unsub_tire_pressure = None

    def _start_watchdog(self) -> None:
        """Start the subscription watchdog(s).

        The base loop already drives _watchdog_tick every _watchdog_interval;
        this adds a call to _tpms_watchdog_tick to the SAME loop rather than a
        second background task, so _start_watchdog still creates exactly one
        background task per vehicle (see
        tests/test_coordinator_watchdog.py::TestTheWatchdogDoesNotBlockStartup,
        which pins that count). The TPMS check itself stays its own method,
        never merged into _watchdog_tick -- see _tpms_watchdog_tick's
        docstring for why.
        """
        if self._watchdog_task and not self._watchdog_task.done():
            return

        async def _watchdog_loop() -> None:
            while True:
                await asyncio.sleep(self._watchdog_interval)
                await self._watchdog_tick()
                await self._tpms_watchdog_tick()

        self._watchdog_task = self.config_entry.async_create_background_task(
            self.hass,
            _watchdog_loop(),
            name=f"rivian {type(self).__name__} watchdog {self.vehicle_id}",
        )
        _LOGGER.debug(
            "Started %s watchdog for vehicle %s", type(self).__name__, self.vehicle_id
        )

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
        self._unsub_tire_pressure: Callable[[], Awaitable[None]] | None = None
        self._connection_unsub_handler: Callable[[], Awaitable[None]] | None = None
        # S1: which vehicleState document (main) was last rejected, if any --
        # diagnostics-only, mirrors what api.subscription_document() reports live.
        self._last_document_error: str | None = None
        # S4: the TPMS stream's OWN liveness clock. Deliberately separate from
        # _last_update_time -- see _process_tire_pressure_data.
        self._tpms_last_update_time: datetime | None = None
        self._tpms_frames_seen = 0
        self._is_online: bool | None = None
        self._last_sync: str | None = None
        self._command_state_subscriptions: dict[str, Callable[[], Awaitable[None]]] = {}
        self._command_states: dict[str, dict[str, Any]] = {}
        self._command_tracking_started: dict[str, float] = {}
        self._last_update_time: datetime | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._prev_charger_state: str | None = None
        # Field names the vehicleState SUBSCRIPTION has supplied at least once.
        #
        # Parallax and the subscription both carry many of the same fields -- 19 of
        # the 28 the decoders write -- and the merge below used to let Parallax
        # overwrite whichever arrived first. Two sources for one sensor is a defect
        # with precedent here: vehicleMileage needed a monotonic guard because the
        # oscillation between an integer-km Parallax value and a float-metre
        # subscription value corrupted utility meters.
        #
        # So the subscription wins where both supply a field, and Parallax fills
        # only the gaps. Provenance has to be tracked rather than inferred from
        # "is the key present", because once Parallax writes a key it IS present,
        # and a Parallax-only field must keep updating.
        self._subscription_keys: set[str] = set()
        # Keys Parallax has actually written at least once, for diagnostics'
        # provenance block (§G) -- the direct complement to _subscription_keys.
        self._parallax_filled_keys: set[str] = set()
        # How many Parallax messages have arrived, per RVM topic.
        #
        # Without this, "the field is absent" is ambiguous between "the message
        # arrived and the field was zero, which proto3 omits" and "the message
        # never arrived at all". That ambiguity is why four of the nine
        # Parallax-only sensors ship disabled: their topics have no unsubscribed
        # sibling, so nothing witnesses arrival. A count settles it.
        self._rvm_arrivals: dict[str, int] = {}
        # Fields already reported as unusable, so the warning fires once each.
        self._dropped_reported: set[str] = set()
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

            try:
                self._unsub_handler = await self.api.subscribe_for_vehicle_updates(
                    vehicle_id=self.vehicle_id,
                    properties=VEHICLE_STATE_SUBSCRIPTION_FIELDS,
                    callback=self._process_new_data,
                )
                self._last_document_error = None
            except RivianApiException as ex:
                # S1: this still raises -- the client already tried the core
                # fallback and failed too -- but the error is recorded first so
                # diagnostics.subscription.last_document_error survives it.
                self._last_document_error = str(ex)
                raise

            # Tire pressure. A sibling of the main subscription (§C, S4): its
            # own document, so an unknown field there costs only the 12
            # tyre-pressure entities, not the whole vehicleState. Same
            # degrade-not-abort policy as Parallax below.
            try:
                self._unsub_tire_pressure = (
                    await self.api.subscribe_for_tire_pressure_updates(
                        vehicle_id=self.vehicle_id,
                        callback=self._process_tire_pressure_data,
                    )
                )
                self._tpms_last_update_time = datetime.now(timezone.utc)
            except RivianApiException:
                _LOGGER.exception(
                    "Tire pressure subscription failed for vehicle %s; the 12 "
                    "tyre-pressure entities will be unavailable until it is "
                    "re-established",
                    self.vehicle_id,
                )
                self._unsub_tire_pressure = None

            # Parallax. The RVM list is explicit, DEDUPED and decodable rather than
            # rvms=None: PARALLAX_RVMS and CHARGING_RVMS overlap by five topics, so
            # naive concatenation would ask for 25 subscriptions covering 20 topics
            # and deliver every duplicate twice.
            try:
                self._unsub_parallax = await self.api.subscribe_for_parallax_messages(
                    vehicle_id=self.vehicle_id,
                    callback=self._process_parallax_data,
                    rvms=SUBSCRIBED_RVMS,
                )
            except RivianApiException:
                # Deliberate policy, not a swallow: vehicle state still works
                # without Parallax, so setup degrades rather than aborting. It is
                # logged at error AND surfaces in diagnostics as
                # parallax.<vehicle>.subscribed = false, which is what was missing
                # when a dead subscription looked identical to a healthy one.
                _LOGGER.exception(
                    "Parallax subscription failed for vehicle %s; live telemetry "
                    "will be unavailable until it is re-established",
                    self.vehicle_id,
                )
                self._unsub_parallax = None

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

    async def async_shutdown(self) -> None:
        # Stop watchdog
        self._stop_watchdog()

        # Unsubscribe from all active command state subscriptions
        for command_id in list(self._command_state_subscriptions.keys()):
            await self._unsubscribe_command_state(command_id)

        await self._unsubscribe(True)
        return await super().async_shutdown()

    @property
    def rvm_arrivals(self) -> dict[str, int]:
        """Parallax messages received per RVM topic, for diagnostics.

        A topic absent from this mapping has never delivered. That is the
        distinction the counter exists to make: a field missing from the decoded
        payload is otherwise ambiguous between "the message arrived and the field
        was zero, which proto3 omits" and "the message never arrived at all".
        """
        return dict(sorted(self._rvm_arrivals.items()))

    @callback
    def _process_parallax_data(self, data: dict[str, Any]) -> None:
        """Process incoming Parallax subscription messages."""
        if not (payload := data.get("payload")) or not (pdata := payload.get("data")):
            return
        px = pdata.get("parallaxMessages")
        if not px:
            return
        # Count arrival FIRST -- before the decode can bail, and well before the
        # per-key merge below drops anything the subscription also supplies. Count
        # after that merge and this is blind to exactly the topics it exists to
        # witness: every field of security.access.btm and security.alarm.state is
        # subscribed, so all of them are discarded there.
        if rvm := px.get("rvm"):
            self._rvm_arrivals[rvm] = self._rvm_arrivals.get(rvm, 0) + 1

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
                # The subscription wins. Parallax fills gaps only.
                #
                # 19 of the 28 keys the decoders write are also carried by the
                # subscription, including gearStatus, driveMode, alarmSoundStatus
                # and trailerStatus -- fields that drive automations. The decoders
                # are transcribed from the app's protobuf classes and asserted
                # against constructed payloads, not against anything this vehicle
                # has actually sent, so they must not be able to overwrite a value
                # that is known to be right.
                #
                # Keys nothing else supplies -- vasAccessCanFaulted,
                # passiveEntryUnlockFailReason, batteryCellType and six more -- are
                # unaffected: the subscription never names them, so they are never
                # in _subscription_keys and Parallax remains their only source.
                if k in self._subscription_keys:
                    continue
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
                    value = clean[k]
                    # Same INVALID_SENSOR_STATES policy as the GraphQL path
                    # (_build_vehicle_info_dict). gnssLocation is already exempt
                    # via the branch above; vehicleMileage has its own guard.
                    if str(value).lower() in INVALID_SENSOR_STATES:
                        if k in (self.data or {}):
                            vehicle_updates[k] = self.data[k]
                            continue
                        # No previous value to fall back to. Pass it through
                        # anyway.
                        #
                        # Dropping it here instead was tried and reverted: it
                        # made entities unavailable rather than show a
                        # stale-but-plausible state, which takes the matching
                        # control down with the sensor (sensor.py:172-179,
                        # binary_sensor.py:110).
                        self._note_unusable(k, value)
                    # `history` is a set, so an unhashable value (decode_vehicle_wheels
                    # returns a LIST) raised `unhashable type: 'list'` and killed the
                    # WHOLE message, not just that field.
                    try:
                        history = {value}
                    except TypeError:
                        history = set()
                    vehicle_updates[k] = {"value": value, "history": history}
            # getattr(..., set()) rather than |=: the coordinator fixtures in
            # tests/test_parallax_gap_fill.py are MagicMock(spec=VehicleCoordinator)
            # instances that never run __init__, so this attribute may not exist
            # yet on first call there. Real instances always have it from __init__.
            self._parallax_filled_keys = (
                getattr(self, "_parallax_filled_keys", set()) | vehicle_updates.keys()
            )
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
        self._apply_vehicle_frame(pdata.get(self.key, {}))
        self._error_count = 0
        self._initial.set()

        # Update watchdog timestamp
        self._last_update_time = datetime.now(timezone.utc)

    def _apply_vehicle_frame(self, vijson: dict[str, Any]) -> dict[str, Any]:
        """Build and publish the merged vehicle_info dict from a raw
        vehicleState frame.

        The frame-applying tail shared by the main vehicleState stream
        (_process_new_data) and the TPMS stream (_process_tire_pressure_data)
        below -- both select the same vehicleState(id:) root, so both kinds of
        frame merge through _build_vehicle_info_dict into one vehicle_info
        dict. Callers own their own liveness/initial-frame bookkeeping
        (_last_update_time, _initial, _error_count): deliberately NOT done
        here, so a TPMS frame cannot make a dead main stream look alive (S4).
        """
        vehicle_info = self._build_vehicle_info_dict(vijson)
        self.async_set_updated_data(vehicle_info)
        return vehicle_info

    @callback
    def _process_tire_pressure_data(self, data: dict[str, Any]) -> None:
        """Process incoming tirePressureState frames (§C, S4).

        A sibling of _process_new_data on its own subscription (see
        subscribe_for_tire_pressure_updates()'s docstring): merges through the
        same _apply_vehicle_frame/_build_vehicle_info_dict path so the 12
        tyre-pressure names land in _subscription_keys (coordinator.py:1581,
        provenance -- not liveness), which is what keeps Parallax from
        overwriting gateway-delivered tyre pressures (:1358).

        Deliberately does NOT touch _last_update_time, _initial or
        _error_count -- those belong to the main vehicleState stream. Letting
        a TPMS frame advance _last_update_time would let tyre-pressure updates
        alone make a dead main subscription look healthy to _watchdog_tick
        for as long as they kept arriving.
        """
        if not (payload := data.get("payload")) or not (pdata := payload.get("data")):
            _LOGGER.error(
                "Received an unknown tire pressure subscription update: %s. "
                "WebSocket state: %s",
                data,
                "active"
                if self.api._ws_monitor and self.api._ws_monitor.connected
                else "inactive/closed",
            )
            return
        self._apply_vehicle_frame(pdata.get(self.key, {}))
        self._tpms_last_update_time = datetime.now(timezone.utc)
        self._tpms_frames_seen += 1

    def _note_unusable(self, key: str, value: Any) -> None:
        """Record once, per field, that the vehicle reported it as unusable.

        Purely diagnostic: the value is still published, because suppressing it
        makes the entity unavailable and that proved far more disruptive than a
        stale reading. Debug rather than warning, and once per key per coordinator
        -- these arrive on every update and are normal for hardware a given trim
        does not have (an R1T has no liftgate, so closureLiftgateClosed is
        permanently signal_not_available).
        """
        if key in self._dropped_reported:
            return
        self._dropped_reported.add(key)
        _LOGGER.debug(
            "Vehicle %s reports %s as %r, which is not a usable value",
            self.vehicle_id,
            key,
            value,
        )

    def _build_vehicle_info_dict(self, vijson: dict[str, Any]) -> dict[str, Any]:
        """Take the json output of vehicle_info and build a dictionary."""
        items = {
            k: v | ({"history": {v["value"]}} if "value" in v else {})
            for k, v in vijson.items()
            if v
        }
        # Provenance, for the Parallax gap-fill rule in _process_parallax_data.
        #
        # Value-based, not "is v truthy" (was `set(items)`, i.e. every key of
        # the dict just built above): a {"timeStamp": ..., "value": None} frame
        # is a non-empty dict -- itself truthy -- but supplies nothing usable.
        # That used to still claim the key here, permanently blocking Parallax
        # from a field the gateway was never actually delivering. Structured
        # fields (gnssLocation, gnssError) have no top-level "value" key at all
        # and keep claiming on the strength of the outer dict alone --
        # gnssLocation MUST stay claimed or _process_parallax_data's
        # unconditional branch (coordinator.py:1360) starts overwriting real
        # GPS with Parallax's.
        self._subscription_keys |= {
            k for k, v in items.items() if "value" not in v or v["value"] is not None
        }

        if items:
            _LOGGER.debug("Vehicle %s updated: %s", self.vehicle_id, redact(items))

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
            # First update: the loop below cannot suppress an invalid value because
            # there is no previous one to fall back to, so it would be published
            # as-is. An ENUM sensor then logs an error and appends the bad value to
            # its own options list, where it stays for the life of the process.
            # Observed live as a literal 'SNA' on both rear seat heating sensors at
            # every fresh start. gnssLocation is exempt here for the same reason it
            # is exempt below.
            for key, item in items.items():
                if key != "gnssLocation" and (
                    str(item.get("value")).lower() in INVALID_SENSOR_STATES
                ):
                    self._note_unusable(key, item.get("value"))
            return items
        if not items or prev_items == items:
            return prev_items

        new_data = prev_items | items
        for key in filter(lambda i: i != "gnssLocation", items):
            value = items[key].get("value")
            if str(value).lower() in INVALID_SENSOR_STATES:
                if key in prev_items:
                    new_data[key] = prev_items[key]
                else:
                    # No previous value to fall back to. Pass it through anyway.
                    #
                    # Dropping it here instead was tried and reverted: it made
                    # entities unavailable rather than show a stale-but-plausible
                    # state, which sounds more honest and is much worse in practice.
                    # On a real R1T the vehicle reports SNA at startup for the
                    # climate hold switch, both front seat climate selects, the
                    # alarm, charging enabled, steering wheel heating and the charge
                    # limit -- fifteen-plus entities went unavailable and stayed that
                    # way until a good value happened to arrive. The cost of passing
                    # it through is one log line per ENUM sensor at startup.
                    self._note_unusable(key, value)
            # Structured fields (gnssError, and anything else the gateway sends
            # without a top-level `value`) never got a "history" key above -- it is
            # attached only when `"value" in v`. gnssLocation is filtered out of
            # this loop, so before s18 it was the only such field and this line was
            # safe. s18's field-parity work added gnssError to the subscription,
            # which is NOT filtered here, and every frame carrying it raised
            # KeyError: 'history' -- observed live on beta13. Guard on presence
            # rather than extending the gnssLocation filter, so the next structured
            # field the gateway adds does not reintroduce this.
            if "history" in new_data[key]:
                new_data[key]["history"] |= prev_items.get(key, {}).get(
                    "history", set()
                )

        return new_data

    @callback
    def _process_cloud_connection_data(self, data: dict[str, Any]) -> None:
        """Process cloud connection updates."""
        if not (payload := data.get("payload")) or not (pdata := payload.get("data")):
            _LOGGER.error("Received unknown cloud connection update: %s", data)
            return

        connection_data = pdata.get("vehicleCloudConnection", {})
        prev_online = self._is_online
        self._is_online = connection_data.get("isOnline")
        self._last_sync = connection_data.get("lastSync")

        # Debug: Log state changes (online/offline transitions)
        if prev_online != self._is_online:
            _LOGGER.info(
                "Vehicle %s cloud connection state changed: %s -> %s (lastSync=%s, subscription #%d age: %.1f min)",
                self.vehicle_id,
                _online_label(prev_online),
                _online_label(self._is_online),
                self._last_sync,
                self._subscription_count,
                (
                    datetime.now(timezone.utc) - self._subscription_start_time
                ).total_seconds()
                / 60
                if self._subscription_start_time
                else 0,
            )
            # Push the transition to the entities. This callback writes
            # `_is_online`, which is half of connectivity_state() -- and
            # connectivity_state() is now gate 1 of every control's availability
            # AND the cloud_connected sensor's state. Nothing else refreshes it:
            # `_async_update_data` returns `self.data` unchanged and the
            # coordinator is constructed with `always_update=False`, so the
            # scheduled refresh notifies nobody, and the only other notifier is a
            # vehicleState/Parallax frame -- which a vehicle that just went
            # offline has stopped sending. Without this, a vehicle going OFFLINE
            # leaves every control showing as available and cloud_connected
            # showing `on` until the vehicle comes back and speaks again.
            self.async_update_listeners()
        else:
            _LOGGER.debug(
                "Vehicle %s cloud connection: online=%s, lastSync=%s",
                self.vehicle_id,
                self._is_online,
                self._last_sync,
            )

    def is_online(self) -> bool | None:
        """Return the raw cloud-connection flag, or None when it is unknown.

        The runtime domain has always included None -- an explicit GraphQL
        `isOnline: null` survives `dict.get`, whose default fires only on a missing
        key -- so the old `-> bool` annotation was already inaccurate. None now also
        covers "no cloud connection frame has arrived yet", which is the state after
        every restart. Callers that need a decision, not a flag, want
        connectivity_state(); the one caller that wants the flag is the
        cloud_connected binary sensor, which coerces it.
        """
        return self._is_online

    def connectivity_state(self) -> ConnectivityState:
        """Return the three-state connectivity, per C1611c.java:141-158."""
        return derive_connectivity_state(self._is_online, self.get("powerState"))

    def last_sync(self) -> str | None:
        """Return last sync timestamp."""
        return self._last_sync

    async def _unsubscribe(self, close_monitor: bool = False):
        """Unsubscribe.

        Tears down Parallax, the main vehicleState stream, TPMS and the
        cloud-connection subscription -- all four. Used at shutdown and on a
        full main-stream restart, both of which need every subscription
        re-established from scratch; the S4 TPMS-only restart path
        (_resubscribe_tpms) deliberately does NOT go through this method, or
        it would tear down two subscriptions that were never unhealthy.
        """
        if unsub := self._unsub_parallax:
            await unsub()
            self._unsub_parallax = None

        if unsub := self._unsub_tire_pressure:
            await unsub()
            self._unsub_tire_pressure = None

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

    def _prune_command_states(self) -> None:
        """Evict expired command-state records only.

        An entry still inside its 60 s window is never evicted, for any reason.
        COMMAND_STATE_CAPACITY is a floor: eviction removes only expired
        entries, oldest-first, and only while the map exceeds 32. If more than
        32 are simultaneously in-window, the map is allowed to grow.
        """
        if len(self._command_states) <= COMMAND_STATE_CAPACITY:
            return
        now = time.monotonic()
        expired = [
            cid
            for cid, rec in self._command_states.items()
            if cid not in self._command_state_subscriptions
            and (now - rec.get("first_frame_at", now)) >= COMMAND_STATE_WINDOW
        ]
        expired.sort(key=lambda cid: self._command_states[cid].get("first_frame_at", 0))
        overflow = len(self._command_states) - COMMAND_STATE_CAPACITY
        for cid in expired[:overflow]:
            self._command_states.pop(cid, None)
        if len(self._command_states) > COMMAND_STATE_CAPACITY:
            _LOGGER.warning(
                "Command state map has %s in-window entries (floor is %s); none evicted",
                len(self._command_states),
                COMMAND_STATE_CAPACITY,
            )

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

        now = time.monotonic()
        prior = self._command_states.get(command_id) or {}
        frames_seen = prior.get("frames_seen", 0) + 1
        is_lifecycle = _command_state_is_lifecycle(state)
        if is_lifecycle is None:
            _LOGGER.warning(
                "Unrecognised command state %r for %s; terminality unknown",
                state,
                command_id,
            )
        terminal_reached = bool(prior.get("terminal_reached")) or (
            is_lifecycle is False
        )
        first_frame_at = prior.get("first_frame_at", now)
        started = prior.get("tracking_started_at")
        if started is None:
            started = self._command_tracking_started.get(command_id)
        time_to_first_frame = prior.get("time_to_first_frame")
        if time_to_first_frame is None and started is not None:
            time_to_first_frame = now - started
        terminal_at = prior.get("terminal_at")
        time_to_terminal = prior.get("time_to_terminal")
        if terminal_reached and terminal_at is None:
            terminal_at = now
            if started is not None:
                time_to_terminal = now - started

        self._command_states[command_id] = {
            "command": cmd_state.get("command"),
            "state": state,
            "first_state": prior.get("first_state", state),
            "responseCode": cmd_state.get("responseCode"),
            "statusCode": cmd_state.get("statusCode"),
            "createdAt": cmd_state.get("createdAt"),
            "frames_seen": frames_seen,
            "is_lifecycle": is_lifecycle,
            "terminal_reached": terminal_reached,
            "first_frame_at": first_frame_at,
            "terminal_at": terminal_at,
            "tracking_started_at": started,
            "time_to_first_frame": time_to_first_frame,
            "time_to_terminal": time_to_terminal,
        }

        self._prune_command_states()
        self.async_update_listeners()

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
            self._command_state_subscriptions[command_id] = unsubscribe
            self._command_tracking_started[command_id] = time.monotonic()
            _LOGGER.debug("Subscribed to command %s state updates", command_id)

            # The poll is gone. The app never had one: vehicleCommandState
            # appears in 18 APK files, getVehicleCommand in 0. Owner rulings
            # 15 and 22. Accepted risk: a silent subscription now has no
            # fallback -- TIMEOUT with zero well-formed frames is the
            # signature, and the two malformed-payload log lines in
            # _process_command_state distinguish that from a bad frame.
            # scripts/probe_vehicle_command.py still polls out of band.

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
        self._command_tracking_started.pop(command_id, None)
        self.async_update_listeners()

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

        if (
            self.connectivity_state() is ConnectivityState.SLEEPING
            and command != VehicleCommand.WAKE_VEHICLE
        ):
            # Dispatched, not waited out -- C2150e.java:212-215 builds the command
            # flow, fires WakeVehicle, and collects without an await between them.
            # The accommodation for a sleeping vehicle is the longer command
            # timeout in entity.py, not a blocking wait here. The await below covers
            # the wake's own HTTP dispatch (sub-second), not the vehicle waking up,
            # and it sits in front of _execute_command's timing window, which does not
            # start until the send returns. A hung wake is therefore bounded only by
            # the client's HTTP layer, not by the command ceiling.
            await self.send_vehicle_command(VehicleCommand.WAKE_VEHICLE)

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

    async def async_set_climate_hold(self, duration_minutes: int) -> dict[str, Any]:
        """Set or clear the cabin climate hold via Parallax.

        The ONE Parallax write the server accepts, verified live: 5 minutes
        encodes as 08ac02 = 300 seconds, and writing 0 returns the RVM to an empty
        payload. Unlike send_vehicle_command this needs no HMAC signing, but it
        does need the enrolled phone's id as 16 RAW BYTES -- uuid.UUID(...).bytes,
        not the 36-character string.
        """
        entry_data = self.hass.data[DOMAIN][self.config_entry.entry_id]
        user: UserCoordinator = entry_data[ATTR_COORDINATOR][ATTR_USER]
        phone_info = user.get_enrolled_phone_data(
            self.config_entry.options.get("public_key")
        )
        if not phone_info:
            raise HomeAssistantError(
                "No enrolled phone found for this vehicle; climate hold requires "
                "the pairing step to have completed"
            )
        return await self.api.set_climate_hold(
            vehicle_id=self.vehicle_id,
            phone_id=uuid.UUID(phone_info[0]).bytes,
            duration_minutes=duration_minutes,
        )

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

    async def _fetch_data(self) -> ClientResponse:
        """Fetch the data."""
        response = await self.api.get_vehicle_images(
            resolution="@3x", vehicle_version=self.version
        )
        self._last_updated = datetime.now(timezone.utc)
        # The key extraction that used to live here is the base class's job now,
        # and calling .get on the response was the same bug in miniature.
        return response


class WallboxCoordinator(RivianDataUpdateCoordinator[list[dict[str, Any]]]):
    """Wallbox data update coordinator for Rivian."""

    key = "getRegisteredWallboxes"

    # Same reasoning as UserCoordinator above: the home charger registration is a
    # heavyweight query that changes when you buy a charger, and it was polled
    # twice a minute. 900 s, at the cap, for the same back-off reason.
    _update_interval_seconds = 15 * 60  # 15 minutes

    async def _fetch_data(self) -> ClientResponse:
        """Fetch the data."""
        return await self.api.get_registered_wallboxes()
