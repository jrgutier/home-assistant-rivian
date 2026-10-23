from __future__ import annotations

import asyncio
import logging
from typing import Any, Final, Literal, NamedTuple

from aiohttp import ClientError, ClientWebSocketResponse, WSMsgType
from webrtc_models import RTCConfiguration, RTCIceCandidateInit, RTCIceServer

from homeassistant.components.camera import (
    Camera,
    CameraEntityFeature,
    WebRTCAnswer,
    WebRTCCandidate,
    WebRTCClientConfiguration,
    WebRTCError,
    WebRTCSendMessage,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .camera_ws import async_setup_camera_ws
from .connectivity import ConnectivityState
from .const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from .coordinator import COMMAND_STATE_CONTINUE, SEND_COMMAND_ERRORS, VehicleCoordinator
from .data_classes import RivianCameraEntityDescription
from .entity import (
    COMMAND_TIMEOUT_SLEEPING,
    RivianVehicleControlEntity,
    vehicle_control_enabled,
)
from .gear_guard import CAMERAS
from .helpers import vehicle_supports
from .kvs_signaling import (
    client_id_from_endpoint,
    ice_candidate_message,
    ice_servers_from_config,
    ice_usable_seconds,
    new_client_id,
    offer_exceeds_kvs_limit,
    offer_message,
    parse_signaling_event,
    signaling_ws_url,
)
from .rivian_client import VehicleCommand
from .sdp import trim_offer_for_kvs

_LOGGER = logging.getLogger(__name__)

CONFIG_TIMEOUT: Final = 30
STREAMING_UNAVAILABLE: Final = 1101
LIVE_START_ATTEMPTS: Final = 3
LIVE_START_RETRY_DELAY: Final = 0.2
PREPARE_REUSE_SECONDS: Final = 60


@callback
def _noop_message(message: Any) -> None:
    pass


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data: dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    vehicles: dict[str, dict[str, Any]] = data[ATTR_VEHICLE]
    coordinators: dict[str, VehicleCoordinator] = data[ATTR_COORDINATOR][ATTR_VEHICLE]

    entities = [
        RivianLiveCameraEntity(coordinators[vehicle_id], entry, description, vehicle)
        for vehicle_id, vehicle in vehicles.items()
        if vehicle_control_enabled(vehicle)
        for description in CAMERAS
        if vehicle_supports(description, vehicle)
    ]
    async_add_entities(entities)
    async_setup_camera_ws(hass)


async def _unsub_config(unsub: Any) -> None:
    if unsub is None:
        return
    try:
        result = unsub()
        if asyncio.iscoroutine(result):
            await result
    except Exception:
        _LOGGER.debug("Unsubscribe gearGuardLiveConfig failed", exc_info=True)


def _log_session_failure(err: BaseException, what: str) -> None:
    _LOGGER.error(
        "%s (%s status=%s)",
        what,
        type(err).__name__,
        getattr(err, "status", None),
    )


_FetchReason = Literal["ok", "closed", "no_command_id", "no_config", "error"]


class _Prepared(NamedTuple):
    config: dict[str, Any]
    camera: str | None
    at: float


def _live_config_from_frame(msg: dict[str, Any]) -> dict[str, Any] | None:
    data = ((msg.get("payload") or {}).get("data") or {}).get("gearGuardLiveConfig")
    if data is None and isinstance(msg.get("data"), dict):
        data = msg["data"].get("gearGuardLiveConfig")
    if not isinstance(data, dict):
        return None
    if not data.get("endpoint") or not data.get("channelArn"):
        return None
    return data


class RivianLiveCameraEntity(RivianVehicleControlEntity, Camera):
    entity_description: RivianCameraEntityDescription
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self,
        coordinator: VehicleCoordinator,
        config_entry: ConfigEntry,
        description: RivianCameraEntityDescription,
        vehicle: dict[str, Any],
    ) -> None:
        RivianVehicleControlEntity.__init__(
            self, coordinator, config_entry, description, vehicle
        )
        Camera.__init__(self)
        self._sessions: dict[str, _LiveSession] = {}
        self._cached_ice: list[dict[str, Any]] = []
        self._cached_ice_expires = 0.0
        self._session_camera: str | None = None
        self._live_switch_hold = False
        self._prepared: _Prepared | None = None
        self._prepare_lock = asyncio.Lock()

    def set_live_switch_hold(self, hold: bool) -> None:
        self._live_switch_hold = hold

    @property
    def _vas_camera(self) -> str:
        chosen = getattr(self.coordinator, "gear_guard_camera", None)
        if isinstance(chosen, str) and chosen:
            return chosen
        return self.entity_description.camera

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = super().extra_state_attributes or {}
        attrs["camera"] = self._vas_camera
        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._sessions and self._session_camera not in (None, self._vas_camera):
            if self._live_switch_hold:
                super()._handle_coordinator_update()
                return
            self.hass.async_create_task(
                self._async_close_all_sessions(
                    f"Camera changed to {self._vas_camera} - reload to view it"
                )
            )
        super()._handle_coordinator_update()

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        return None

    @callback
    def _async_get_webrtc_client_configuration(self) -> WebRTCClientConfiguration:
        servers = [
            RTCIceServer(
                urls=entry["urls"],
                username=entry.get("username"),
                credential=entry.get("credential"),
            )
            for entry in self._valid_cached_ice()
        ]
        return WebRTCClientConfiguration(
            configuration=RTCConfiguration(ice_servers=servers),
            data_channel="data",
        )

    def _valid_cached_ice(self) -> list[dict[str, Any]]:
        if not self._cached_ice:
            return []
        if self.hass.loop.time() >= self._cached_ice_expires:
            self._cached_ice = []
            self._cached_ice_expires = 0.0
        return self._cached_ice

    def _store_ice(self, config: dict[str, Any]) -> None:
        ice = config.get("iceServers")
        self._cached_ice = ice_servers_from_config(ice)
        self._cached_ice_expires = self.hass.loop.time() + ice_usable_seconds(ice)

    def _store_prepared(self, config: dict[str, Any]) -> None:
        self._store_ice(config)
        self._prepared = _Prepared(
            config=config, camera=self._session_camera, at=self.hass.loop.time()
        )

    def _suits_offer(self, prepared: _Prepared) -> bool:
        return (
            prepared.camera == self._vas_camera
            and self.hass.loop.time() - prepared.at <= PREPARE_REUSE_SECONDS
        )

    def _take_prepared(self) -> dict[str, Any] | None:
        prepared, self._prepared = self._prepared, None
        if prepared is None or not self._suits_offer(prepared):
            return None
        self._session_camera = prepared.camera
        return prepared.config

    async def async_prepare_live(self) -> None:
        async with self._prepare_lock:
            held = self._prepared
            if (
                self._valid_cached_ice()
                and held is not None
                and self._suits_offer(held)
            ):
                return
            live = _LiveSession(session_id="prepare", send_message=_noop_message)
            try:
                config, reason = await self._async_fetch_live_config(live)
            except SEND_COMMAND_ERRORS as err:
                _log_session_failure(err, "Gear Guard live prepare failed")
                config, reason = None, "error"
            finally:
                await live.aclose()
            if config is None:
                _LOGGER.debug(
                    "Gear Guard prepare got no live config (%s responseCode=%s)",
                    reason,
                    live.last_response_code,
                )
                return
            self._store_prepared(config)

    async def async_handle_async_webrtc_offer(
        self, offer_sdp: str, session_id: str, send_message: WebRTCSendMessage
    ) -> None:
        if not self.available:
            send_message(
                WebRTCError("webrtc_offer_failed", "Live view is not available")
            )
            return

        if (trimmed := trim_offer_for_kvs(offer_sdp)) is not offer_sdp:
            _LOGGER.info(
                "Rewrote an oversized offer to fit KVS signaling: %d -> %d "
                "bytes of SDP (kept H264, dropped codecs the vehicle declines)",
                len(offer_sdp),
                len(trimmed),
            )
            offer_sdp = trimmed

        if offer_exceeds_kvs_limit(offer_sdp):
            _LOGGER.warning(
                "Offer is too large for KVS signaling (%d bytes of SDP) even "
                "after trimming; the vehicle would never answer it. A viewer "
                "that offers no H264 at all cannot be reduced -- see sdp.py.",
                len(offer_sdp),
            )
            send_message(
                WebRTCError(
                    "webrtc_offer_failed",
                    "Offer too large for the vehicle's signaling channel",
                )
            )
            return

        live = _LiveSession(session_id=session_id, send_message=send_message)
        self._sessions[session_id] = live
        for existing in list(self._sessions):
            if existing != session_id:
                await self._async_close_session(existing)
        if live.closed:
            return

        try:
            await self._async_run_offer(live, offer_sdp)
        except BaseException as err:
            if isinstance(err, Exception):
                _log_session_failure(err, "Gear Guard live session failed")
                await self._async_close_session(
                    session_id, "Gear Guard live session failed"
                )
                return
            await self._async_close_session(session_id)
            raise

    async def _async_fetch_live_config(
        self, live: _LiveSession
    ) -> tuple[dict[str, Any] | None, _FetchReason]:
        for attempt in range(LIVE_START_ATTEMPTS):
            self._session_camera = self._vas_camera
            command_id = await self.coordinator.send_vehicle_command(
                VehicleCommand.START_GEAR_GUARD_MASTER_SESSION,
                {"camera": self._vas_camera},
            )
            if live.closed:
                return None, "closed"
            if not command_id:
                return None, "no_command_id"
            config = await self._wait_for_live_config(live, command_id)
            if live.closed:
                return None, "closed"
            if config is not None:
                return config, "ok"
            if (
                live.last_response_code != STREAMING_UNAVAILABLE
                or attempt == LIVE_START_ATTEMPTS - 1
            ):
                break
            await asyncio.sleep(LIVE_START_RETRY_DELAY)
        return None, "no_config"

    async def _async_run_offer(self, live: _LiveSession, offer_sdp: str) -> None:
        config = self._take_prepared()
        if config is None:
            config, reason = await self._async_fetch_live_config(live)
            if live.closed:
                return
        if config is None:
            if reason == "no_command_id":
                live.send_message(
                    WebRTCError(
                        "webrtc_offer_failed",
                        "START_GEAR_GUARD_MASTER_SESSION returned no command id",
                    )
                )
            else:
                _LOGGER.warning(
                    "START_GEAR_GUARD_MASTER_SESSION ended without live config "
                    "(responseCode=%s camera=%s)",
                    live.last_response_code,
                    self._session_camera,
                )
                live.send_message(
                    WebRTCError(
                        "webrtc_offer_failed",
                        "gearGuardLiveConfig did not arrive",
                    )
                )
            await self._async_close_session(live.session_id)
            return

        if bound := client_id_from_endpoint(config["endpoint"]):
            live.client_id = bound
        self._store_ice(config)
        self._prepared = None
        url = signaling_ws_url(config["endpoint"], config["channelArn"], live.client_id)
        if live.closed:
            return
        http = async_get_clientsession(self.hass)
        try:
            live.ws = await http.ws_connect(url, heartbeat=30)
        except ClientError as err:
            _log_session_failure(err, "Gear Guard signaling connect failed")
            live.send_message(
                WebRTCError("webrtc_offer_failed", "Gear Guard live session failed")
            )
            await self._async_close_session(live.session_id)
            return
        if live.closed:
            if live.ws is not None and not live.ws.closed:
                await live.ws.close()
                live.ws = None
            return
        live.pump_task = self.hass.async_create_task(
            self._pump_signaling(live), f"rivian_kvs_{live.session_id}"
        )
        await live.send_json(offer_message(offer_sdp, live.client_id))
        await live.flush_pending_ice()
        if live.closed:
            return
        self._attr_is_streaming = True
        self.async_write_ha_state()

    async def _wait_for_live_config(
        self, live: _LiveSession, command_id: str
    ) -> dict[str, Any] | None:
        arrived: asyncio.Event = asyncio.Event()
        holder: dict[str, dict[str, Any]] = {}

        def on_frame(msg: dict[str, Any]) -> None:
            if cfg := _live_config_from_frame(msg):
                holder["cfg"] = cfg
                arrived.set()

        unsub = await self.coordinator.api.subscribe_gear_guard_live_config(
            self.coordinator.vehicle_id, command_id, on_frame
        )
        if live.closed:
            await _unsub_config(unsub)
            return None
        live.unsub_config = unsub
        live.last_response_code = None
        timeout = (
            COMMAND_TIMEOUT_SLEEPING
            if self.coordinator.connectivity_state() is ConnectivityState.SLEEPING
            else CONFIG_TIMEOUT
        )
        arrived_task = asyncio.create_task(arrived.wait())
        closed_task = asyncio.create_task(live.closed_event.wait())
        failed_code: int | None = None
        try:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                _done, _pending = await asyncio.wait(
                    {arrived_task, closed_task},
                    timeout=min(0.5, remaining),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if live.closed or arrived.is_set():
                    break
                rec = self.coordinator.get_command_state(command_id)
                st = rec.get("state") if rec else None
                if isinstance(st, int) and st not in COMMAND_STATE_CONTINUE and st != 0:
                    failed_code = rec.get("responseCode")
                    break
        finally:
            for task in (arrived_task, closed_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(arrived_task, closed_task, return_exceptions=True)
            await _unsub_config(live.unsub_config)
            live.unsub_config = None
        if live.closed:
            return None
        if arrived.is_set():
            return holder.get("cfg")
        if failed_code is not None:
            live.last_response_code = (
                failed_code if isinstance(failed_code, int) else None
            )
            return None
        _LOGGER.warning("gearGuardLiveConfig timed out after %ss", timeout)
        return None

    async def _pump_signaling(self, live: _LiveSession) -> None:
        assert live.ws is not None
        try:
            async for msg in live.ws:
                if msg.type in (
                    WSMsgType.CLOSE,
                    WSMsgType.CLOSING,
                    WSMsgType.CLOSED,
                ):
                    break
                if msg.type != WSMsgType.TEXT:
                    continue
                event = parse_signaling_event(msg.data)
                if event is None:
                    continue
                payload = event["payload"]
                msg_type = event["messageType"]
                _LOGGER.debug(
                    "KVS event %s senderClientId=%r pending_ice=%d",
                    msg_type,
                    event.get("senderClientId"),
                    len(live.pending_ice),
                )
                if msg_type in ("SDP_ANSWER", "ICE_CANDIDATE"):
                    if sender := event.get("senderClientId"):
                        live.recipient_client_id = sender
                    await live.flush_pending_ice()
                if msg_type == "SDP_ANSWER":
                    sdp = payload.get("sdp")
                    if isinstance(sdp, str) and sdp:
                        live.send_message(WebRTCAnswer(sdp))
                elif msg_type == "ICE_CANDIDATE":
                    candidate = payload.get("candidate")
                    if isinstance(candidate, str) and candidate:
                        mid = payload.get("sdpMid")
                        index = payload.get("sdpMLineIndex")
                        live.send_message(
                            WebRTCCandidate(
                                RTCIceCandidateInit(
                                    candidate=candidate,
                                    sdp_mid=mid if isinstance(mid, str) else None,
                                    sdp_m_line_index=(
                                        index if isinstance(index, int) else 0
                                    ),
                                )
                            )
                        )
        except (ClientError, ConnectionError) as err:
            _log_session_failure(err, "KVS signaling closed unexpectedly")
        finally:
            if live.session_id in self._sessions and not live.closed:
                await self._async_close_session(live.session_id)

    async def async_on_webrtc_candidate(
        self, session_id: str, candidate: RTCIceCandidateInit
    ) -> None:
        live = self._sessions.get(session_id)
        if live is None:
            return
        if live.ws is None or live.ws.closed:
            live.pending_ice.append(candidate)
            return
        await live.send_ice(candidate)

    @callback
    def close_webrtc_session(self, session_id: str) -> None:
        self.hass.async_create_task(self._async_close_session(session_id))

    async def _async_close_all_sessions(self, error: str | None = None) -> None:
        for session_id in list(self._sessions):
            await self._async_close_session(session_id, error)

    async def _async_close_session(
        self, session_id: str, error: str | None = None
    ) -> None:
        live = self._sessions.pop(session_id, None)
        if live is None:
            return
        if error is not None and not live.closed:
            live.send_message(WebRTCError("webrtc_offer_failed", error))
        await live.aclose()
        if not self._sessions:
            self._attr_is_streaming = False
            self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        await self._async_close_all_sessions()
        await super().async_will_remove_from_hass()


class _LiveSession:
    def __init__(self, session_id: str, send_message: WebRTCSendMessage) -> None:
        self.session_id = session_id
        self.send_message = send_message
        self.client_id = new_client_id()
        self.recipient_client_id = ""
        self.closed = False
        self.closed_event = asyncio.Event()
        self.ws: ClientWebSocketResponse | None = None
        self.unsub_config: Any = None
        self.pump_task: asyncio.Task | None = None
        self.pending_ice: list[RTCIceCandidateInit] = []
        self.last_response_code: int | None = None

    async def aclose(self) -> None:
        self.closed = True
        self.closed_event.set()
        current = asyncio.current_task()
        if (
            self.pump_task
            and not self.pump_task.done()
            and self.pump_task is not current
        ):
            self.pump_task.cancel()
            try:
                await self.pump_task
            except asyncio.CancelledError:
                pass
        await _unsub_config(self.unsub_config)
        self.unsub_config = None
        if self.ws is not None and not self.ws.closed:
            await self.ws.close()
            self.ws = None

    async def send_json(self, payload: dict[str, str]) -> None:
        if self.ws is None or self.ws.closed:
            return
        await self.ws.send_json(payload)

    async def flush_pending_ice(self) -> None:
        if self.ws is None or self.ws.closed or not self.pending_ice:
            return
        pending = list(self.pending_ice)
        self.pending_ice.clear()
        for candidate in pending:
            await self.send_ice(candidate)

    async def send_ice(self, candidate: RTCIceCandidateInit) -> None:
        if not candidate.candidate:
            return
        if self.ws is None or self.ws.closed:
            self.pending_ice.append(candidate)
            return
        await self.send_json(
            ice_candidate_message(
                candidate.candidate,
                candidate.sdp_mid,
                candidate.sdp_m_line_index,
                self.client_id,
                self.recipient_client_id,
            )
        )
