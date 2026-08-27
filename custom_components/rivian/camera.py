"""Rivian Gear Guard live camera — APK KVS WebRTC path.

View start: VAS START_GEAR_GUARD_MASTER_SESSION with params.camera (default
left), subscribe gearGuardLiveConfig, then relay HA native WebRTC through
the KVS signaling websocket. Tear-down is local; there is no stop VASCommand.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Final

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
from .coordinator import COMMAND_STATE_CONTINUE, VehicleCoordinator
from .data_classes import RivianCameraEntityDescription
from .entity import COMMAND_TIMEOUT_SLEEPING, RivianVehicleControlEntity
from .helpers import vehicle_supports
from .kvs_signaling import (
    client_id_from_endpoint,
    ice_candidate_message,
    ice_servers_from_config,
    new_client_id,
    offer_message,
    parse_signaling_event,
    signaling_ws_url,
)
from .rivian_client import VehicleCommand

_LOGGER = logging.getLogger(__name__)

CONFIG_TIMEOUT: Final = 30
# w37.REMOTE_COMMAND_STREAMING_UNAVAILABLE. ji8.java:51-57 retries
# while h <= 2 after a 200 ms pause.
STREAMING_UNAVAILABLE: Final = 1101
LIVE_START_ATTEMPTS: Final = 3
LIVE_START_RETRY_DELAY: Final = 0.2

# RivianMotionCamera camName values. Default is LEFT / DEFAULT_MOTION_CAMERA.
DEFAULT_MOTION_CAMERA: Final = "left"
EXTERIOR_CAMERAS: Final = ("left", "right", "front", "rear")
BED_CAMERA: Final = "bed"
INTERIOR_CAMERA: Final = "interior"

CAMERAS: Final[tuple[RivianCameraEntityDescription, ...]] = (
    RivianCameraEntityDescription(
        key="gear_guard_live",
        translation_key="gear_guard_live",
        icon="mdi:cctv",
        feature=("LIVE_CAM", "MOTION_CAM"),
        camera=DEFAULT_MOTION_CAMERA,
    ),
)


def gear_guard_camera_options(vehicle: dict[str, Any]) -> tuple[str, ...]:
    """Cameras the live-view picker lists, matching the app's enum."""
    options = list(EXTERIOR_CAMERAS)
    model = str(vehicle.get("model") or "").upper()
    if "R1T" in model:
        options.append(BED_CAMERA)
    features = vehicle.get("supported_features") or []
    if "INTERIOR_CAMERA" in features:
        options.append(INTERIOR_CAMERA)
    return tuple(options)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Gear Guard live camera entities."""
    data: dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    vehicles: dict[str, dict[str, Any]] = data[ATTR_VEHICLE]
    coordinators: dict[str, VehicleCoordinator] = data[ATTR_COORDINATOR][ATTR_VEHICLE]

    entities = [
        RivianLiveCameraEntity(coordinators[vehicle_id], entry, description, vehicle)
        for vehicle_id, vehicle in vehicles.items()
        if vehicle.get("phone_identity_id")
        for description in CAMERAS
        if vehicle_supports(description, vehicle)
    ]
    async_add_entities(entities)
    async_setup_camera_ws(hass)


async def _unsub_config(unsub: Any) -> None:
    """Drop a gearGuardLiveConfig subscription."""
    if unsub is None:
        return
    try:
        result = unsub()
        if asyncio.iscoroutine(result):
            await result
    except Exception:  # noqa: BLE001 -- teardown
        _LOGGER.debug("Unsubscribe gearGuardLiveConfig failed")


def _log_session_failure(err: BaseException, what: str) -> None:
    """Log a session failure without aiohttp's signed URL in the traceback."""
    _LOGGER.error(
        "%s (%s status=%s)",
        what,
        type(err).__name__,
        getattr(err, "status", None),
    )


def _live_config_from_frame(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Pull gearGuardLiveConfig out of an Apollo next frame."""
    data = ((msg.get("payload") or {}).get("data") or {}).get("gearGuardLiveConfig")
    if data is None and isinstance(msg.get("data"), dict):
        data = msg["data"].get("gearGuardLiveConfig")
    if not isinstance(data, dict):
        return None
    if not data.get("endpoint") or not data.get("channelArn"):
        return None
    return data


class RivianLiveCameraEntity(RivianVehicleControlEntity, Camera):
    """Gear Guard live view as a native WebRTC camera."""

    entity_description: RivianCameraEntityDescription
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self,
        coordinator: VehicleCoordinator,
        config_entry: ConfigEntry,
        description: RivianCameraEntityDescription,
        vehicle: dict[str, Any],
    ) -> None:
        """Construct the live camera."""
        RivianVehicleControlEntity.__init__(
            self, coordinator, config_entry, description, vehicle
        )
        Camera.__init__(self)
        self._sessions: dict[str, _LiveSession] = {}
        self._cached_ice: list[dict[str, Any]] = []
        self._session_camera: str | None = None
        self._live_switch_hold = False

    def set_live_switch_hold(self, hold: bool) -> None:
        """Custom card owns in-session SWITCH_CAMERA; skip VAS teardown."""
        self._live_switch_hold = hold

    @property
    def _vas_camera(self) -> str:
        """VAS params.camera — selector value, else the APK default."""
        chosen = getattr(self.coordinator, "gear_guard_camera", None)
        if isinstance(chosen, str) and chosen:
            return chosen
        return self.entity_description.camera

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the selected camera next to command status."""
        attrs = super().extra_state_attributes or {}
        attrs["camera"] = self._vas_camera
        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        """Drop an in-flight live session when the camera selector changes."""
        if self._sessions and self._session_camera not in (None, self._vas_camera):
            if self._live_switch_hold:
                super()._handle_coordinator_update()
                return
            # The frontend cannot renegotiate on its own once the session ends,
            # so tearing down silently leaves the card idle and blank. Say why.
            self.hass.async_create_task(
                self._async_close_all_sessions(
                    f"Camera changed to {self._vas_camera} - reload to view it"
                )
            )
        super()._handle_coordinator_update()

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Live view has no still JPEG path."""
        return None

    @callback
    def _async_get_webrtc_client_configuration(self) -> WebRTCClientConfiguration:
        """Return cached KVS ICE servers from the last live config, if any."""
        servers = [
            RTCIceServer(
                urls=entry["urls"],
                username=entry.get("username"),
                credential=entry.get("credential"),
            )
            for entry in self._cached_ice
        ]
        return WebRTCClientConfiguration(
            configuration=RTCConfiguration(ice_servers=servers),
            data_channel="data",
        )

    async def async_handle_async_webrtc_offer(
        self, offer_sdp: str, session_id: str, send_message: WebRTCSendMessage
    ) -> None:
        """Start the APK live session and relay the frontend offer to KVS."""
        if not self.available:
            send_message(
                WebRTCError("webrtc_offer_failed", "Live view is not available")
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
        except asyncio.CancelledError:
            await self._async_close_session(session_id)
            raise
        except Exception as err:  # noqa: BLE001 -- offer boundary: never leak URLs
            _log_session_failure(err, "Gear Guard live session failed")
            send_message(
                WebRTCError("webrtc_offer_failed", "Gear Guard live session failed")
            )
            await self._async_close_session(session_id)

    async def _async_run_offer(self, live: _LiveSession, offer_sdp: str) -> None:
        """Send VAS, wait for live config, connect KVS, send SDP_OFFER."""
        config: dict[str, Any] | None = None
        for attempt in range(LIVE_START_ATTEMPTS):
            self._session_camera = self._vas_camera
            command_id = await self.coordinator.send_vehicle_command(
                VehicleCommand.START_GEAR_GUARD_MASTER_SESSION,
                {"camera": self._vas_camera},
            )
            if live.closed:
                return
            if not command_id:
                live.send_message(
                    WebRTCError(
                        "webrtc_offer_failed",
                        "START_GEAR_GUARD_MASTER_SESSION returned no command id",
                    )
                )
                await self._async_close_session(live.session_id)
                return
            config = await self._wait_for_live_config(live, command_id)
            if live.closed:
                return
            if config is not None:
                break
            if (
                live.last_response_code != STREAMING_UNAVAILABLE
                or attempt == LIVE_START_ATTEMPTS - 1
            ):
                break
            await asyncio.sleep(LIVE_START_RETRY_DELAY)
        if config is None:
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
        self._cached_ice = ice_servers_from_config(config.get("iceServers"))
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
        """Subscribe gearGuardLiveConfig until endpoint+channelArn arrive."""
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
        """Read KVS events and push SDP_ANSWER / ICE to the HA frontend."""
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
                    # Master senderClientId is often "". Flush anyway; waiting
                    # for it stranded viewer ICE and blocked TURN.
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
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 -- pump must not crash the entity
            _log_session_failure(err, "KVS signaling closed unexpectedly")
        finally:
            if live.session_id in self._sessions and not live.closed:
                await self._async_close_session(live.session_id)

    async def async_on_webrtc_candidate(
        self, session_id: str, candidate: RTCIceCandidateInit
    ) -> None:
        """Relay a frontend ICE candidate onto the KVS websocket."""
        live = self._sessions.get(session_id)
        if live is None:
            return
        if live.ws is None or live.ws.closed:
            live.pending_ice.append(candidate)
            return
        await live.send_ice(candidate)

    @callback
    def close_webrtc_session(self, session_id: str) -> None:
        """Local tear-down only — the app has no stop VASCommand."""
        self.hass.async_create_task(self._async_close_session(session_id))

    async def _async_close_all_sessions(self, error: str | None = None) -> None:
        """Close every live session (camera selector changed)."""
        for session_id in list(self._sessions):
            await self._async_close_session(session_id, error)

    async def _async_close_session(
        self, session_id: str, error: str | None = None
    ) -> None:
        """Close one live session's websocket and GraphQL subscription.

        `error` is for tear-downs the viewer did not ask for; a normal
        close_webrtc_session leaves it None and stays silent.
        """
        live = self._sessions.pop(session_id, None)
        if live is None:
            return
        if error is not None and not live.closed:
            live.send_message(WebRTCError("webrtc_offer_failed", error))
        live.closed = True
        live.closed_event.set()
        current = asyncio.current_task()
        if (
            live.pump_task
            and not live.pump_task.done()
            and live.pump_task is not current
        ):
            live.pump_task.cancel()
            try:
                await live.pump_task
            except asyncio.CancelledError:
                pass
        await _unsub_config(live.unsub_config)
        live.unsub_config = None
        if live.ws is not None and not live.ws.closed:
            await live.ws.close()
            live.ws = None
        if not self._sessions:
            self._cached_ice = []
            self._attr_is_streaming = False
            self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Drop any open live session on unload."""
        for session_id in list(self._sessions):
            await self._async_close_session(session_id)
        await super().async_will_remove_from_hass()


class _LiveSession:
    """One HA WebRTC session ↔ one KVS signaling websocket."""

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

    async def send_json(self, payload: dict[str, str]) -> None:
        """Send one KVS signaling JSON object."""
        if self.ws is None or self.ws.closed:
            return
        await self.ws.send_json(payload)

    async def flush_pending_ice(self) -> None:
        """Drain candidates queued while the signaling socket was still opening."""
        if self.ws is None or self.ws.closed or not self.pending_ice:
            return
        pending = list(self.pending_ice)
        self.pending_ice.clear()
        for candidate in pending:
            await self.send_ice(candidate)

    async def send_ice(self, candidate: RTCIceCandidateInit) -> None:
        """Send one frontend ICE candidate. Empty recipientClientId is valid."""
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
