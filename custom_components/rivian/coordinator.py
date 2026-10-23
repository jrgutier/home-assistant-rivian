from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
import logging
import time
from typing import Any, Final, Generic, TypeVar
import uuid

from aiohttp import ClientError, ClientResponse

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
    EVENT_COMMAND_FAILED,
    EVENT_COMMAND_INITIATED,
    EVENT_COMMAND_SUCCESS,
    RIVIAN_TIMESTAMP_FORMAT,
    VEHICLE_STATE_SUBSCRIPTION_FIELDS,
    is_invalid_state,
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

INITIAL_UPDATE_TIMEOUT = 60
CHARGING_SCHEDULE_COOL_OFF = 10
CHARGING_SCHEDULE_REFRESH_INTERVAL = 900
SLOW_POLL_SECONDS: Final = 15 * 60

COMMAND_STATE_CONTINUE: Final[frozenset[int]] = frozenset({1, 2, 3, 5})
COMMAND_STATE_STRING_TERMINAL: Final[frozenset[str]] = frozenset(
    {"COMPLETED_SUCCESS", "COMPLETED_ERROR", "FAILED"}
)
COMMAND_STATE_WINDOW = 60
COMMAND_STATE_CAPACITY = 32

SEND_COMMAND_ERRORS: Final = (RivianApiException, KeyError, TypeError, ValueError)


def _command_state_is_lifecycle(state: Any) -> bool | None:
    if isinstance(state, int):
        return state in COMMAND_STATE_CONTINUE
    if state in COMMAND_STATE_STRING_TERMINAL:
        return False
    return None


def _online_label(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return "online" if value else "offline"


def _payload_data(data: dict[str, Any]) -> dict[str, Any] | None:
    if not (payload := data.get("payload")) or not (pdata := payload.get("data")):
        return None
    return pdata


def _supported_features(vehicle: dict[str, Any]) -> list[dict[str, Any]]:
    return (
        vehicle.get("vehicle", {}).get("vehicleState", {}).get("supportedFeatures", [])
    )


class RivianDataUpdateCoordinator(DataUpdateCoordinator[T], ABC, Generic[T]):
    key: str
    _update_interval_seconds = 30
    _error_count = 0

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, client: Rivian
    ) -> None:
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
        self._watchdog_task: asyncio.Task | None = None
        self._last_update_time: datetime | None = None
        self._subscription_start_time: datetime | None = None
        self._subscription_count = 0
        self._watchdog_restarts = 0
        self._last_restart_reason: str | None = None

    def _set_update_interval(self, seconds: float | None = None) -> None:
        if not seconds:
            seconds = min(
                self._update_interval_seconds * 2**self._error_count, SLOW_POLL_SECONDS
            )
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
                    raise UpdateFailed(
                        f"{self.key} missing from the response payload"
                    ) from err
            resp.raise_for_status()

        except UpdateFailed:
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
        except ClientError as ex:
            _LOGGER.error("Rivian request failed: %s", redact_text(str(ex)))
        except (AttributeError, KeyError, TypeError, ValueError) as ex:
            _LOGGER.error("Rivian returned malformed data: %s", redact_text(str(ex)))
        except Exception as ex:
            self._error_count += 1
            raise UpdateFailed(
                f"Unknown exception while updating Rivian data: {redact_text(str(ex))}"
            ) from ex

        self._error_count += 1
        if self.data:
            return self.data
        raise UpdateFailed("Error communicating with API")

    _watchdog_timeout = 5 * 60
    _watchdog_interval = 60

    def _watchdog_skip_reason(self) -> str | None:
        return None

    async def _watchdog_tick(self) -> bool:
        if not self._last_update_time:
            return False

        if reason := self._watchdog_skip_reason():
            _LOGGER.debug(
                "Watchdog skipping check for vehicle %s: %s", self.vehicle_id, reason
            )
            return False

        idle = (datetime.now(UTC) - self._last_update_time).total_seconds()
        if idle <= self._watchdog_timeout:
            return False

        age = self._subscription_age_minutes()
        _LOGGER.warning(
            "%s subscription for vehicle %s stale, no updates for %.1f minutes. "
            "Subscription #%d age: %.1f min, WebSocket state: %s. Restarting...",
            type(self).__name__,
            self.vehicle_id,
            idle / 60,
            self._subscription_count,
            age,
            self._ws_state,
        )
        self._watchdog_restarts += 1
        self._last_restart_reason = f"stale for {idle / 60:.1f} min"
        await self._unsubscribe()
        task = self.async_request_refresh()
        self.config_entry.async_create_task(self.hass, task, eager_start=True)
        return True

    async def _watchdog_ticks(self) -> None:
        await self._watchdog_tick()

    def _start_watchdog(self) -> None:
        if self._watchdog_task and not self._watchdog_task.done():
            return

        async def _watchdog_loop() -> None:
            while True:
                await asyncio.sleep(self._watchdog_interval)
                await self._watchdog_ticks()

        # A BACKGROUND task, deliberately. config_entry.async_create_task registers
        # work Home Assistant waits for while finishing startup, and _watchdog_loop
        # is `while True` -- so it never completes and bootstrap blocks on it until
        self._watchdog_task = self.config_entry.async_create_background_task(
            self.hass,
            _watchdog_loop(),
            name=f"rivian {type(self).__name__} watchdog {self.vehicle_id}",
        )
        _LOGGER.debug(
            "Started %s watchdog for vehicle %s", type(self).__name__, self.vehicle_id
        )

    def _stop_watchdog(self) -> None:
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
        self._watchdog_task = None

    @property
    def _ws_state(self) -> str:
        monitor = self.api._ws_monitor
        return "active" if monitor and monitor.connected else "inactive/closed"

    def _subscription_age_minutes(self, now: datetime | None = None) -> float:
        if not self._subscription_start_time:
            return 0
        return (
            (now or datetime.now(UTC)) - self._subscription_start_time
        ).total_seconds() / 60

    def _log_resubscribe(self) -> None:
        if not self._subscription_start_time:
            return
        reasons = []
        if not self.data:
            reasons.append("no data")
        if not self.last_update_success:
            reasons.append("last update failed")
        if not self._unsub_handler:
            reasons.append("no active subscription")
        _LOGGER.debug(
            self._log_subscription_ended,
            self.vehicle_id,
            self._subscription_age_minutes(),
            ", ".join(reasons),
        )

    _initial: asyncio.Event
    _log_backend_error: str
    _log_unknown_frame: str
    _log_too_many_errors: str
    _log_subscription_ended: str

    def _frame_data(self, data: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        if data.get("type") == "error":
            error_payload = data.get("payload", [])
            if isinstance(error_payload, list) and error_payload:
                error_info = error_payload[0]
                error_message = error_info.get("message", "Unknown error")
                extensions = error_info.get("extensions", {})
                rest_info = extensions.get("rest", {})
                status_code = rest_info.get("status")

                _LOGGER.warning(
                    self._log_backend_error,
                    self.vehicle_id,
                    error_message,
                    status_code or "unknown",
                    self._subscription_count,
                    self._subscription_age_minutes(now),
                    self._ws_state,
                )

                if status_code in (502, 504):
                    task = self._unsubscribe()
                    self.config_entry.async_create_task(
                        self.hass, task, eager_start=True
                    )
                    refresh_task = self.async_request_refresh()
                    self.config_entry.async_create_task(
                        self.hass, refresh_task, eager_start=True
                    )
                return None

        if not (pdata := _payload_data(data)):
            _LOGGER.error(
                self._log_unknown_frame,
                data,
                self._ws_state,
                self._subscription_age_minutes(now),
            )
            self._error_count += 1
            if not self._initial.is_set() or self._error_count > 5:
                _LOGGER.warning(
                    self._log_too_many_errors,
                    self._error_count,
                    self.vehicle_id,
                )
                task = self._unsubscribe()
                self.config_entry.async_create_task(self.hass, task, eager_start=True)
            return None

        return pdata

    def get(self, key: str, default: Any | None = None) -> Any | None:
        if not self.data:
            return default

        value: Any = self.data
        for part in key.split("."):
            if not isinstance(value, dict):
                return default
            value = value.get(part)
            if value is None:
                return default

        if isinstance(value, dict) and "value" in value:
            value = value["value"]

        return value if value is not None else default

    @abstractmethod
    async def _fetch_data(self) -> ClientResponse:
        raise NotImplementedError


SUBSCRIBED_RVMS: Final[list[str]] = sorted(
    {*PARALLAX_RVMS, *CHARGING_RVMS} & set(RVM_DECODERS)
)


class ChargingCoordinator(RivianDataUpdateCoordinator[dict[str, Any]]):
    key = "getLiveSessionData"
    _update_interval_seconds = 0
    _watchdog_timeout = 5 * 60
    _log_backend_error = (
        "Charging subscription for vehicle %s received backend error: %s (HTTP %s). "
        "Subscription #%d age: %.1f min, WebSocket state: %s. Restarting subscription..."
    )
    _log_unknown_frame = (
        "Received unknown charging subscription update: %s. "
        "WebSocket state: %s, subscription age: %.1f min"
    )
    _log_too_many_errors = (
        "Too many errors (%d) on charging subscription for vehicle %s, unsubscribing"
    )
    _log_subscription_ended = (
        "Charging subscription for vehicle %s ended after %.1f minutes. Reasons: %s"
    )

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: Rivian,
        vehicle_id: str,
    ) -> None:
        super().__init__(hass=hass, config_entry=config_entry, client=client)
        self.vehicle_id = vehicle_id
        self._initial = asyncio.Event()
        self._unsub_handler: Callable[[], Awaitable[None]] | None = None
        self._subscription_enabled = True
        self._synthetic_start_time = False
        self._source_data: dict[str, dict[str, Any]] = {
            "subscription": {},
            "parallax": {},
        }

    async def _async_update_data(self) -> dict[str, Any]:
        if not self._subscription_enabled:
            _LOGGER.debug(
                "Charging subscription disabled for vehicle %s (not charging)",
                self.vehicle_id,
            )
            return self.data or {}

        if not self.data or not self.last_update_success or not self._unsub_handler:
            self._log_resubscribe()

            await self._unsubscribe()
            self._subscription_count += 1
            self._subscription_start_time = datetime.now(UTC)

            _LOGGER.debug(
                "Creating charging subscription #%d for vehicle %s. WebSocket monitor state: %s",
                self._subscription_count,
                self.vehicle_id,
                self._ws_state,
            )

            self._unsub_handler = await self.api.subscribe_for_charging_session(
                vehicle_id=self.vehicle_id,
                callback=self._process_new_data,
            )
            self._last_update_time = datetime.now(UTC)

            _LOGGER.debug(
                "Charging subscription #%d created for vehicle %s",
                self._subscription_count,
                self.vehicle_id,
            )

            try:
                await asyncio.wait_for(self._initial.wait(), 5)
            except TimeoutError:
                _LOGGER.debug("No initial charging data received (likely not charging)")
                self._initial.set()
                if not self.data:
                    self.data = {}

        return self.data

    async def _fetch_data(self) -> dict[str, Any]:
        raise NotImplementedError("Polling charging data no longer allowed")

    def _publish_resolved(self) -> None:
        subscription = self._source_data["subscription"]
        parallax = self._source_data["parallax"]
        resolved = {**subscription, **parallax}
        if self._synthetic_start_time and subscription.get("startTime"):
            resolved["startTime"] = subscription["startTime"]
        self.async_set_updated_data(resolved)

    @callback
    def update_from_parallax(self, decoded: dict[str, Any]) -> None:
        clean = {k: v for k, v in decoded.items() if not k.startswith("_")}
        if not clean:
            return

        now = datetime.now(UTC)
        new_data = self._source_data["parallax"]

        if "startTime" in clean:
            old_start = new_data.get("startTime")
            if (
                old_start
                and old_start != clean["startTime"]
                and not self._synthetic_start_time
            ):
                new_data.clear()
            new_data["startTime"] = clean["startTime"]
            self._synthetic_start_time = False
        elif not new_data.get("startTime") and clean.get("power", 0) > 0:
            new_data["startTime"] = now.strftime(RIVIAN_TIMESTAMP_FORMAT)
            self._synthetic_start_time = True

        new_data.update(clean)

        self._publish_resolved()
        _LOGGER.debug("Charging data updated from Parallax: %s", clean)

    def adjust_update_interval(self, is_plugged_in: bool) -> None:
        pass

    async def async_shutdown(self) -> None:
        self._stop_watchdog()
        await self._unsubscribe()
        return await super().async_shutdown()

    @callback
    def _process_new_data(self, data: dict[str, Any]) -> None:
        now = datetime.now(UTC)
        if self._last_update_time:
            time_since_last = (now - self._last_update_time).total_seconds()
            if time_since_last > 60:
                _LOGGER.debug(
                    "Charging data update gap for vehicle %s: %.1f minutes",
                    self.vehicle_id,
                    time_since_last / 60,
                )

        if (pdata := self._frame_data(data, now)) is None:
            return

        charging_data = pdata.get("chargingSession", {})

        if isinstance(charging_data, list):
            if not charging_data:
                _LOGGER.debug("No active charging session")
                self._source_data["subscription"] = {}
                self._synthetic_start_time = False
                self._publish_resolved()
                self._error_count = 0
                self._initial.set()
                self._last_update_time = datetime.now(UTC)
                return
            charging_data = charging_data[0]

        processed_data = self._process_charging_data(charging_data)
        self._source_data["subscription"] = processed_data
        self._publish_resolved()
        self._error_count = 0
        self._initial.set()

        self._last_update_time = datetime.now(UTC)

    def _process_charging_data(self, data: dict[str, Any]) -> dict[str, Any]:
        live_data = data.get("liveData", {})
        chart_data = data.get("chartData", {})

        if isinstance(live_data, list):
            live_data = live_data[0] if live_data else {}
        if isinstance(chart_data, list):
            chart_data = chart_data[0] if chart_data else {}

        return {
            **chart_data,
            **live_data,
        }

    async def _unsubscribe(self, close_monitor: bool = False):
        if unsub := self._unsub_handler:
            _LOGGER.debug(
                "Unsubscribing from charging subscription #%d for vehicle %s (active for %.1f min)",
                self._subscription_count,
                self.vehicle_id,
                self._subscription_age_minutes(),
            )
            await unsub()
            self._unsub_handler = None
            self._initial.clear()

    def toggle_watchdog(self, enabled: bool) -> None:
        if enabled:
            self._start_watchdog()
        else:
            self._stop_watchdog()

    async def toggle_subscription(self, enabled: bool) -> None:
        if enabled and not self._subscription_enabled:
            _LOGGER.info(
                "Enabling charging subscription for vehicle %s (charger connected)",
                self.vehicle_id,
            )
            self._subscription_enabled = True
            await self.async_request_refresh()
        elif not enabled and self._subscription_enabled:
            _LOGGER.info(
                "Disabling charging subscription for vehicle %s (charger disconnected)",
                self.vehicle_id,
            )
            self._subscription_enabled = False
            if self._unsub_handler:
                await self._unsubscribe()


class DriverKeyCoordinator(RivianDataUpdateCoordinator[dict[str, Any]]):
    key = "getVehicle"
    _update_interval_seconds = SLOW_POLL_SECONDS

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: Rivian,
        vehicle_id: str,
    ) -> None:
        super().__init__(hass=hass, config_entry=config_entry, client=client)
        self.vehicle_id = vehicle_id

    async def _fetch_data(self) -> ClientResponse:
        return await self.api.get_drivers_and_keys(vehicle_id=self.vehicle_id)

    def get_device_details(self, identity_id: str) -> dict[str, Any] | None:
        if not self.data:
            return None
        return next(
            (
                device
                for user in self.data.get("invitedUsers", [])
                if "devices" in user
                for device in user.get("devices", [])
                if device.get("mappedIdentityId") == identity_id
            ),
            None,
        )


def _extract_option_codes(vehicle: dict[str, Any]) -> list[str] | None:
    mobile_configuration = vehicle.get("mobileConfiguration")
    if mobile_configuration is None:
        return None
    return [
        option["optionId"]
        for key in ("tonneauOption", "wheelOption")
        if (option := mobile_configuration.get(key)) and option.get("optionId")
    ]


class UserCoordinator(RivianDataUpdateCoordinator[dict[str, Any]]):
    key = "currentUser"

    _update_interval_seconds = SLOW_POLL_SECONDS

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
        return await self.api.get_user_information(self.include_phones)

    def get_enrolled_phone_data(
        self, public_key: str
    ) -> tuple[str, dict[str, str]] | None:
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
        return {
            vehicle["id"]: vehicle["vehicle"]
            | {
                "name": vehicle["name"],
                "supported_features": [
                    supported_feature.get("name")
                    for supported_feature in _supported_features(vehicle)
                    if supported_feature.get("status") == "AVAILABLE"
                ],
                "vas_id": (vas := vehicle.get("vas", {})).get("vasVehicleId"),
                "public_key": vas.get("vehiclePublicKey"),
                "option_codes": _extract_option_codes(vehicle.get("vehicle", {})),
            }
            for vehicle in self.data["vehicles"]
        }


class SupportedFeaturesCoordinator(RivianDataUpdateCoordinator[dict[str, Any]]):
    key = "currentUser"
    _update_interval_seconds = SLOW_POLL_SECONDS

    async def _fetch_data(self) -> ClientResponse:
        return await self.api.get_supported_features()

    def available_features(self) -> dict[str, frozenset[str]]:
        if not self.data:
            return {}
        return {
            vehicle["id"]: frozenset(
                feature["name"]
                for feature in _supported_features(vehicle)
                if feature.get("status") == "AVAILABLE"
            )
            for vehicle in self.data.get("vehicles", [])
        }

    def features_by_status(self) -> dict[str, dict[str, str]]:
        if not self.data:
            return {}
        return {
            vehicle["id"]: {
                feature["name"]: feature["status"]
                for feature in _supported_features(vehicle)
                if feature.get("name") and feature.get("status")
            }
            for vehicle in self.data.get("vehicles", [])
        }


class VehicleCoordinator(RivianDataUpdateCoordinator[dict[str, Any]]):
    key = "vehicleState"
    _update_interval_seconds = SLOW_POLL_SECONDS
    _watchdog_timeout = 5 * 60
    _log_backend_error = (
        "Vehicle %s subscription received backend error: %s (HTTP %s). "
        "Subscription #%d age: %.1f min, WebSocket state: %s. Restarting subscription..."
    )
    _log_unknown_frame = (
        "Received an unknown subscription update: %s. "
        "WebSocket state: %s, subscription age: %.1f min"
    )
    _log_too_many_errors = (
        "Too many errors (%d) on vehicle %s subscription, unsubscribing"
    )
    _log_subscription_ended = (
        "Vehicle %s subscription ended after %.1f minutes. Reasons: %s"
    )
    _tpms_watchdog_timeout = 5 * 60

    def _watchdog_skip_reason(self) -> str | None:
        if self.get("powerState") == "sleep":
            return "vehicle is sleeping"
        return None

    async def _tpms_watchdog_tick(self) -> bool:
        if not self._tpms_last_update_time:
            return False
        idle = (datetime.now(UTC) - self._tpms_last_update_time).total_seconds()
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
        if unsub := self._unsub_tire_pressure:
            await unsub()
            self._unsub_tire_pressure = None
        await self._subscribe_tpms(
            "Tire pressure re-subscription failed for vehicle %s"
        )

    async def _subscribe_tpms(self, failure_log: str) -> None:
        try:
            self._unsub_tire_pressure = (
                await self.api.subscribe_for_tire_pressure_updates(
                    vehicle_id=self.vehicle_id,
                    callback=self._process_tire_pressure_data,
                )
            )
            self._tpms_last_update_time = datetime.now(UTC)
        except RivianApiException:
            _LOGGER.exception(failure_log, self.vehicle_id)
            self._unsub_tire_pressure = None

    async def _watchdog_ticks(self) -> None:
        await self._watchdog_tick()
        await self._tpms_watchdog_tick()

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: Rivian,
        vehicle_id: str,
    ) -> None:
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
        self._last_document_error: str | None = None
        self._tpms_last_update_time: datetime | None = None
        self._tpms_frames_seen = 0
        self._is_online: bool | None = None
        self._last_sync: str | None = None
        self._command_state_subscriptions: dict[str, Callable[[], Awaitable[None]]] = {}
        self._command_states: dict[str, dict[str, Any]] = {}
        self._command_tracking_started: dict[str, float] = {}
        self._prev_charger_state: str | None = None
        self._subscription_keys: set[str] = set()
        self._parallax_filled_keys: set[str] = set()
        self._rvm_arrivals: dict[str, int] = {}
        self._dropped_reported: set[str] = set()
        self._charging_schedule: dict[str, Any] | None = None
        self._last_schedule_fetch: float = 0.0
        self.gear_guard_camera: str = "left"

    @property
    def charging_schedule(self) -> dict[str, Any]:
        return self._charging_schedule or {}

    async def get_charging_schedule_data(
        self, force_refresh: bool = False
    ) -> dict[str, Any]:
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
            except (RivianApiException, AttributeError, TypeError) as err:
                _LOGGER.error("Error fetching charging schedule: %s", err)

            if self._charging_schedule is None:
                self._charging_schedule = dict(DEFAULT_CHARGING_SCHEDULE)
        return self._charging_schedule

    async def update_charging_schedule_data(self, schedule: dict[str, Any]) -> None:
        current = dict(await self.get_charging_schedule_data(force_refresh=True))
        current.update(schedule)
        try:
            await self.api.set_charging_schedules(self.vehicle_id, [current])
        except RivianApiException as err:
            _LOGGER.error("Error setting charging schedule: %s", err)
        self._charging_schedule = current
        self.async_update_listeners()

    async def get_ota_release_notes_url(self) -> str | None:
        response = await self.api.get_vehicle_ota_update_details(self.vehicle_id)
        data = (await response.json())["data"]["getVehicle"]
        if details := data["availableOTAUpdateDetails"]:
            return details["url"]
        return data["currentOTAUpdateDetails"]["url"]

    async def _async_update_data(self) -> dict[str, Any]:
        await self.get_charging_schedule_data()
        if not self.data or not self.last_update_success or not self._unsub_handler:
            self._log_resubscribe()
            await self._unsubscribe()
            self._subscription_count += 1
            self._subscription_start_time = datetime.now(UTC)

            _LOGGER.debug(
                "Creating vehicle subscription #%d for vehicle %s. WebSocket monitor state: %s",
                self._subscription_count,
                self.vehicle_id,
                self._ws_state,
            )

            try:
                self._unsub_handler = await self.api.subscribe_for_vehicle_updates(
                    vehicle_id=self.vehicle_id,
                    properties=VEHICLE_STATE_SUBSCRIPTION_FIELDS,
                    callback=self._process_new_data,
                )
                self._last_document_error = None
            except RivianApiException as ex:
                self._last_document_error = str(ex)
                raise

            await self._subscribe_tpms(
                "Tire pressure subscription failed for vehicle %s; the 12 "
                "tyre-pressure entities will be unavailable until it is "
                "re-established"
            )

            try:
                self._unsub_parallax = await self.api.subscribe_for_parallax_messages(
                    vehicle_id=self.vehicle_id,
                    callback=self._process_parallax_data,
                    rvms=SUBSCRIBED_RVMS,
                )
            except RivianApiException:
                _LOGGER.exception(
                    "Parallax subscription failed for vehicle %s; live telemetry "
                    "will be unavailable until it is re-established",
                    self.vehicle_id,
                )
                self._unsub_parallax = None

            self._connection_unsub_handler = (
                await self.api.subscribe_for_cloud_connection(
                    vehicle_id=self.vehicle_id,
                    callback=self._process_cloud_connection_data,
                )
            )

            self._last_update_time = datetime.now(UTC)

            _LOGGER.debug(
                "Vehicle subscription #%d created for vehicle %s",
                self._subscription_count,
                self.vehicle_id,
            )

            try:
                await asyncio.wait_for(self._initial.wait(), INITIAL_UPDATE_TIMEOUT)
            except TimeoutError as err:
                raise UpdateFailed(
                    "Timed out waiting for initial vehicle data after "
                    f"{INITIAL_UPDATE_TIMEOUT}s"
                ) from err

            self._start_watchdog()

        return self.data

    async def _fetch_data(self) -> dict[str, Any]:
        raise NotImplementedError("Polling VehicleState no longer allowed")

    async def async_shutdown(self) -> None:
        self._stop_watchdog()

        for command_id in list(self._command_state_subscriptions.keys()):
            await self._unsubscribe_command_state(command_id)

        await self._unsubscribe(True)
        return await super().async_shutdown()

    @property
    def rvm_arrivals(self) -> dict[str, int]:
        return dict(sorted(self._rvm_arrivals.items()))

    @callback
    def _process_parallax_data(self, data: dict[str, Any]) -> None:
        if not (pdata := _payload_data(data)):
            return
        px = pdata.get("parallaxMessages")
        if not px:
            return
        if rvm := px.get("rvm"):
            self._rvm_arrivals[rvm] = self._rvm_arrivals.get(rvm, 0) + 1

        decoded = decode_parallax_message(**px)
        if not decoded:
            return

        clean = {k: v for k, v in decoded.items() if not k.startswith("_")}
        if not clean:
            return

        if charging_keys := clean.keys() & CHARGING_STATE_KEYS:
            self.charging_coordinator.update_from_parallax(clean)

        vehicle_keys = (clean.keys() - charging_keys) | (
            clean.keys() & {"timeToEndOfCharge"}
        )
        if vehicle_keys:
            vehicle_updates: dict[str, Any] = {}
            for k in vehicle_keys:
                if k in self._subscription_keys:
                    continue
                if k == "gnssLocation":
                    vehicle_updates[k] = clean[k]
                elif k == "vehicleMileage":
                    prev_val = (
                        (self.data or {}).get("vehicleMileage", {}).get("value", 0)
                    )
                    new_val = clean[k]
                    if isinstance(new_val, (int, float)) and new_val >= prev_val:
                        vehicle_updates[k] = {"value": new_val, "history": {new_val}}
                else:
                    value = clean[k]
                    if is_invalid_state(value):
                        if k in (self.data or {}):
                            vehicle_updates[k] = self.data[k]
                            continue
                        self._note_unusable(k, value)
                    try:
                        history = {value}
                    except TypeError:
                        history = set()
                    vehicle_updates[k] = {"value": value, "history": history}
            self._parallax_filled_keys = (
                self._parallax_filled_keys | vehicle_updates.keys()
            )
            new_data = (self.data or {}) | vehicle_updates
            self.async_set_updated_data(new_data)
            _LOGGER.debug(
                "Vehicle state updated from Parallax (%s): %s", px.get("rvm"), clean
            )

    @callback
    def _process_new_data(self, data: dict[str, Any]) -> None:
        now = datetime.now(UTC)
        if self._last_update_time:
            time_since_last = (now - self._last_update_time).total_seconds()
            if time_since_last > 60:
                _LOGGER.debug(
                    "Vehicle %s data update gap: %.1f minutes (powerState: %s)",
                    self.vehicle_id,
                    time_since_last / 60,
                    self.get("powerState") or "unknown",
                )

        if (pdata := self._frame_data(data, now)) is None:
            return
        self._apply_vehicle_frame(pdata.get(self.key, {}))
        self._error_count = 0
        self._initial.set()

        self._last_update_time = datetime.now(UTC)

    def _apply_vehicle_frame(self, vijson: dict[str, Any]) -> dict[str, Any]:
        vehicle_info = self._build_vehicle_info_dict(vijson)
        self.async_set_updated_data(vehicle_info)
        return vehicle_info

    @callback
    def _process_tire_pressure_data(self, data: dict[str, Any]) -> None:
        if not (pdata := _payload_data(data)):
            _LOGGER.error(
                "Received an unknown tire pressure subscription update: %s. "
                "WebSocket state: %s",
                data,
                self._ws_state,
            )
            return
        self._apply_vehicle_frame(pdata.get(self.key, {}))
        self._tpms_last_update_time = datetime.now(UTC)
        self._tpms_frames_seen += 1

    def _note_unusable(self, key: str, value: Any) -> None:
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
        items = {
            k: v | ({"history": {v["value"]}} if "value" in v else {})
            for k, v in vijson.items()
            if v
        }
        usable: set[str] = set()
        unusable: set[str] = set()
        for k, v in items.items():
            if "value" not in v:
                usable.add(k)
            elif v["value"] is None:
                continue
            elif is_invalid_state(v["value"]):
                unusable.add(k)
            else:
                usable.add(k)
        self._subscription_keys = (self._subscription_keys - unusable) | usable

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
                items["timeToEndOfCharge"] = {"value": 0, "history": {0}}

        if charger_state_data := items.get("chargerState"):
            charger_state = charger_state_data.get("value")
            if charger_state != self._prev_charger_state:
                self._prev_charger_state = charger_state
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
                self.charging_coordinator.toggle_watchdog(is_connected)
                task = self.charging_coordinator.toggle_subscription(is_connected)
                self.config_entry.async_create_task(self.hass, task, eager_start=True)

        if not (prev_items := (self.data or {})):
            for key, item in items.items():
                if key != "gnssLocation" and is_invalid_state(item.get("value")):
                    self._note_unusable(key, item.get("value"))
            return items
        if not items or prev_items == items:
            return prev_items

        new_data = prev_items | items
        for key in filter(lambda i: i != "gnssLocation", items):
            value = items[key].get("value")
            if is_invalid_state(value):
                if key in prev_items:
                    new_data[key] = prev_items[key]
                else:
                    self._note_unusable(key, value)
            if "history" in new_data[key]:
                new_data[key]["history"] |= prev_items.get(key, {}).get(
                    "history", set()
                )

        return new_data

    @callback
    def _process_cloud_connection_data(self, data: dict[str, Any]) -> None:
        if not (pdata := _payload_data(data)):
            _LOGGER.error("Received unknown cloud connection update: %s", data)
            return

        connection_data = pdata.get("vehicleCloudConnection", {})
        prev_online = self._is_online
        self._is_online = connection_data.get("isOnline")
        self._last_sync = connection_data.get("lastSync")

        if prev_online != self._is_online:
            _LOGGER.info(
                "Vehicle %s cloud connection state changed: %s -> %s (lastSync=%s, subscription #%d age: %.1f min)",
                self.vehicle_id,
                _online_label(prev_online),
                _online_label(self._is_online),
                self._last_sync,
                self._subscription_count,
                self._subscription_age_minutes(),
            )
            self.async_update_listeners()
        else:
            _LOGGER.debug(
                "Vehicle %s cloud connection: online=%s, lastSync=%s",
                self.vehicle_id,
                self._is_online,
                self._last_sync,
            )

    def is_online(self) -> bool | None:
        return self._is_online

    def connectivity_state(self) -> ConnectivityState:
        return derive_connectivity_state(self._is_online, self.get("powerState"))

    def last_sync(self) -> str | None:
        return self._last_sync

    async def _unsubscribe(self, close_monitor: bool = False):
        if unsub := self._unsub_parallax:
            await unsub()
            self._unsub_parallax = None

        if unsub := self._unsub_tire_pressure:
            await unsub()
            self._unsub_tire_pressure = None

        if unsub := self._unsub_handler:
            _LOGGER.debug(
                "Unsubscribing from vehicle subscription #%d for vehicle %s (active for %.1f min)",
                self._subscription_count,
                self.vehicle_id,
                self._subscription_age_minutes(),
            )
            await unsub()
            self._unsub_handler = None
            self._initial.clear()

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
        if not (pdata := _payload_data(data)):
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

        event_data = {
            "vehicle_id": self.vehicle_id,
            "command_id": command_id,
            "command": cmd_state.get("command"),
            "state": state,
            "response_code": cmd_state.get("responseCode"),
            "status_code": cmd_state.get("statusCode"),
        }

        if state in COMMAND_STATE_STRING_TERMINAL:
            self.hass.bus.fire(
                EVENT_COMMAND_SUCCESS
                if state == "COMPLETED_SUCCESS"
                else EVENT_COMMAND_FAILED,
                event_data,
            )
            asyncio.create_task(self._unsubscribe_command_state(command_id))

    async def _subscribe_to_command_state(self, command_id: str) -> None:
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

            async def _auto_unsubscribe():
                await asyncio.sleep(60)
                await self._unsubscribe_command_state(command_id)

            asyncio.create_task(_auto_unsubscribe())
        except RivianApiException as ex:
            _LOGGER.error("Failed to subscribe to command %s state: %s", command_id, ex)

    async def _unsubscribe_command_state(self, command_id: str) -> None:
        if unsub := self._command_state_subscriptions.pop(command_id, None):
            try:
                await unsub()
                _LOGGER.debug("Unsubscribed from command %s state updates", command_id)
            except Exception:
                _LOGGER.exception("Error unsubscribing from command %s", command_id)
        self._command_tracking_started.pop(command_id, None)
        self.async_update_listeners()

    def get_command_state(self, command_id: str) -> dict[str, Any] | None:
        return self._command_states.get(command_id)

    async def send_vehicle_command(
        self, command: VehicleCommand, params: dict[str, Any] | None = None
    ) -> str | None:
        _LOGGER.debug("Sending command %s with params: %s", command, params)

        if (
            self.connectivity_state() is ConnectivityState.SLEEPING
            and command != VehicleCommand.WAKE_VEHICLE
        ):
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

            self.hass.bus.fire(
                EVENT_COMMAND_INITIATED,
                {
                    "vehicle_id": self.vehicle_id,
                    "command": command.value,
                    "command_id": command_id,
                },
            )

            await self._subscribe_to_command_state(command_id)

        return command_id

    async def async_set_climate_hold(self, duration_minutes: int) -> dict[str, Any]:
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
        _LOGGER.debug(
            "Sending Parallax command %s with kwargs: %s", method_name, kwargs
        )

        method = getattr(self.api, method_name)

        return await method(vehicle_id=self.vehicle_id, **kwargs)


class VehicleImageCoordinator(RivianDataUpdateCoordinator[list[dict[str, Any]]]):
    key = "getVehicleMobileImages"
    _update_interval_seconds = 0
    _last_updated: datetime | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: Rivian,
        version: str,
    ) -> None:
        super().__init__(hass=hass, config_entry=config_entry, client=client)
        self.version = version

    async def _fetch_data(self) -> ClientResponse:
        response = await self.api.get_vehicle_images(
            resolution="@3x", vehicle_version=self.version
        )
        self._last_updated = datetime.now(UTC)
        return response

    @property
    def last_updated(self) -> datetime | None:
        return self._last_updated


class WallboxCoordinator(RivianDataUpdateCoordinator[list[dict[str, Any]]]):
    key = "getRegisteredWallboxes"

    _update_interval_seconds = SLOW_POLL_SECONDS

    async def _fetch_data(self) -> ClientResponse:
        return await self.api.get_registered_wallboxes()
