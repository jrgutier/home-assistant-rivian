"""Gear Guard live camera: creation gates and APK-shaped send params."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import ClientConnectionError, WSMsgType
from webrtc_models import RTCIceCandidateInit

from custom_components.rivian.camera import (
    CAMERAS,
    PREPARE_REUSE_SECONDS,
    RivianLiveCameraEntity,
    _live_config_from_frame,
    _LiveSession,
    _unsub_config,
    async_setup_entry,
)
from custom_components.rivian.connectivity import ConnectivityState
from custom_components.rivian.const import ATTR_COORDINATOR, ATTR_VEHICLE, DOMAIN
from custom_components.rivian.coordinator import VehicleCoordinator
from custom_components.rivian.gear_guard import gear_guard_camera_options
from custom_components.rivian.kvs_signaling import (
    KVS_MAX_MESSAGE_PAYLOAD,
    encode_payload,
)
from custom_components.rivian.rivian_client import VehicleCommand
from custom_components.rivian.select import (
    RivianGearGuardCameraSelect,
    async_setup_entry as select_setup,
)
from homeassistant.components.camera import CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.webrtc import chrome_offer, sdp_of_length


def _vehicle(**overrides) -> dict:
    data = {
        "id": "test_vehicle_123",
        "vin": "TEST123456789",
        "name": "Test R1T",
        "model": "R1T",
        "phone_identity_id": "test_phone_id",
        "supported_features": ["LIVE_CAM", "MOTION_CAM"],
    }
    data.update(overrides)
    return data


def _hass_entry(
    hass: HomeAssistant, entry: ConfigEntry, vehicle: dict
) -> VehicleCoordinator:
    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator.data = {}
    coordinator.vehicle_id = vehicle["id"]
    coordinator.api = MagicMock()
    coordinator.connectivity_state = MagicMock(return_value=ConnectivityState.ONLINE)
    coordinator.get = MagicMock(
        side_effect=lambda key, *a, **kw: "park" if key == "gearStatus" else None
    )
    hass.data[DOMAIN] = {
        entry.entry_id: {
            ATTR_VEHICLE: {vehicle["id"]: vehicle},
            ATTR_COORDINATOR: {ATTR_VEHICLE: {vehicle["id"]: coordinator}},
        }
    }
    return coordinator


async def _setup(hass, entry, vehicle) -> list:
    _hass_entry(hass, entry, vehicle)
    added: list = []
    await async_setup_entry(hass, entry, added.extend)
    return added


async def test_created_when_paired_and_live_cam(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """LIVE_CAM + pairing is how this R1T gets a live view."""
    entities = await _setup(hass, mock_config_entry, _vehicle())
    assert len(entities) == 1
    assert isinstance(entities[0], RivianLiveCameraEntity)
    assert entities[0].entity_description.key == "gear_guard_live"
    assert entities[0].entity_description.camera == "left"
    assert CameraEntityFeature.STREAM in entities[0].supported_features


async def test_created_when_only_motion_cam(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """MOTION_CAM alone also grants the entity (union, not both flags)."""
    entities = await _setup(
        hass, mock_config_entry, _vehicle(supported_features=["MOTION_CAM"])
    )
    assert len(entities) == 1


async def test_not_created_when_unpaired(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """VAS requires pairing; no phone_identity_id means no camera."""
    vehicle = _vehicle()
    del vehicle["phone_identity_id"]
    entities = await _setup(hass, mock_config_entry, vehicle)
    assert entities == []


async def test_not_created_without_camera_flags(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Interior-only or no camera flags: do not invent a live entity."""
    entities = await _setup(
        hass, mock_config_entry, _vehicle(supported_features=["INTERIOR_CAMERA"])
    )
    assert entities == []
    entities = await _setup(
        hass, mock_config_entry, _vehicle(supported_features=["TAILGATE_CMD"])
    )
    assert entities == []


async def test_no_interior_entity_even_with_interior_flag(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """This story ships one left-camera entity. Interior is a later flag."""
    entities = await _setup(
        hass,
        mock_config_entry,
        _vehicle(supported_features=["LIVE_CAM", "INTERIOR_CAMERA"]),
    )
    assert [e.entity_description.key for e in entities] == ["gear_guard_live"]
    assert all(e.entity_description.camera != "interior" for e in entities)


def _live_entity(hass, entry, coordinator, vehicle) -> RivianLiveCameraEntity:
    entity = RivianLiveCameraEntity(coordinator, entry, CAMERAS[0], vehicle)
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()
    return entity


def test_r1t_selector_lists_bed_not_interior() -> None:
    """This truck has LIVE_CAM/MOTION_CAM, not INTERIOR_CAMERA; bed is R1T."""
    assert gear_guard_camera_options(_vehicle()) == (
        "left",
        "right",
        "front",
        "rear",
        "bed",
    )


def test_interior_option_only_with_flag() -> None:
    """APK shows INTERIOR when the vehicle has INTERIOR_CAMERA."""
    opts = gear_guard_camera_options(
        _vehicle(supported_features=["LIVE_CAM", "INTERIOR_CAMERA"])
    )
    assert "interior" in opts


async def test_select_entity_created_with_camera(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The dashboard picker is a select, not a second camera entity."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    coordinator.gear_guard_camera = "left"
    added: list = []
    await select_setup(hass, mock_config_entry, added.extend)
    cameras = [e for e in added if isinstance(e, RivianGearGuardCameraSelect)]
    assert len(cameras) == 1
    assert cameras[0].options == ["left", "right", "front", "rear", "bed"]
    assert cameras[0].current_option == "left"


async def test_offer_sends_selected_camera(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Changing the picker must change VAS params.camera."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    coordinator.gear_guard_camera = "front"
    coordinator.send_vehicle_command = AsyncMock(return_value=None)
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    messages: list = []
    await entity.async_handle_async_webrtc_offer("v=0", "sess-1", messages.append)
    coordinator.send_vehicle_command.assert_awaited_once_with(
        VehicleCommand.START_GEAR_GUARD_MASTER_SESSION,
        {"camera": "front"},
    )


async def test_offer_sends_master_session_with_camera_left(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The APK default is left; a missing camera param is 1031."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    coordinator.send_vehicle_command = AsyncMock(return_value=None)
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    messages: list = []
    await entity.async_handle_async_webrtc_offer("v=0", "sess-1", messages.append)
    coordinator.send_vehicle_command.assert_awaited_once_with(
        VehicleCommand.START_GEAR_GUARD_MASTER_SESSION,
        {"camera": "left"},
    )
    assert any(getattr(m, "code", None) == "webrtc_offer_failed" for m in messages)


async def test_failed_vas_does_not_wait_full_config_timeout(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """1101 is STREAMING_UNAVAILABLE; fail-fast, then ji8 retries."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    coordinator.send_vehicle_command = AsyncMock(
        side_effect=["cmd-1", "cmd-2", "cmd-3"]
    )
    coordinator.get_command_state = MagicMock(
        return_value={"state": 4, "responseCode": 1101}
    )
    coordinator.api.subscribe_gear_guard_live_config = _subscribe_returning()
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    messages: list = []
    started = time.monotonic()
    with patch("custom_components.rivian.camera.asyncio.sleep", new_callable=AsyncMock):
        await entity.async_handle_async_webrtc_offer("v=0", "sess-1", messages.append)
    assert time.monotonic() - started < 5
    assert coordinator.send_vehicle_command.await_count == 3
    assert any(getattr(m, "code", None) == "webrtc_offer_failed" for m in messages)


async def test_non_1101_failure_does_not_retry(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """1031 is missing camera; retrying would not change the params."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    coordinator.send_vehicle_command = AsyncMock(return_value="cmd-1")
    coordinator.get_command_state = MagicMock(
        return_value={"state": 4, "responseCode": 1031}
    )
    coordinator.api.subscribe_gear_guard_live_config = _subscribe_returning()
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    messages: list = []
    await entity.async_handle_async_webrtc_offer("v=0", "sess-1", messages.append)
    coordinator.send_vehicle_command.assert_awaited_once()
    assert [m.message for m in messages] == ["gearGuardLiveConfig did not arrive"]


async def test_1101_retry_uses_next_command_id(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """A later 490 on the same identity must start a new command id."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    coordinator.send_vehicle_command = AsyncMock(side_effect=["cmd-1", "cmd-2"])
    coordinator.get_command_state = MagicMock(
        side_effect=lambda cid: (
            {"state": 4, "responseCode": 1101}
            if cid == "cmd-1"
            else {"state": 0, "responseCode": 490}
        )
    )
    coordinator.api.subscribe_gear_guard_live_config = _subscribe_returning(
        {**_LIVE_CONFIG, "iceServers": []}, only_for_cid="cmd-2"
    )
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    messages: list = []

    http = await _run_offer(entity, messages)

    assert coordinator.send_vehicle_command.await_count == 2
    http.ws_connect.assert_awaited()
    assert not any(getattr(m, "code", None) == "webrtc_offer_failed" for m in messages)


_LIVE_CONFIG = {
    "endpoint": (
        "https://v-test.kinesisvideo.us-east-1.amazonaws.com/?X-Amz-Signature=x"
    ),
    "channelArn": "arn:aws:kinesisvideo:us-east-1:1:channel/x",
    "role": "viewer",
    "iceServers": [
        {"url": "turn:example", "username": "u", "credential": "c", "ttl": 300}
    ],
}
_SHAPED_ICE = [{"urls": "turn:example", "username": "u", "credential": "c"}]


def _subscribe_returning(
    config: dict | None = None, only_for_cid: str | None = None
) -> AsyncMock:
    """Stub subscribe_gear_guard_live_config, optionally answering with a config.

    Every caller needs the same throwaway unsub, so the shape of
    `subscribe_gear_guard_live_config(vehicle_id, command_id, callback)` is
    asserted here once rather than in each test that stubs it.
    """

    async def subscribe(_vid, cid, callback):
        if config is not None and only_for_cid in (None, cid):
            callback({"payload": {"data": {"gearGuardLiveConfig": config}}})

        async def unsub() -> None:
            return None

        return unsub

    return AsyncMock(side_effect=subscribe)


def _config_coordinator(hass, entry, vehicle) -> VehicleCoordinator:
    """A coordinator whose VAS answers with one usable live config."""
    coordinator = _hass_entry(hass, entry, vehicle)
    coordinator.send_vehicle_command = AsyncMock(side_effect=["cmd-1", "cmd-2"])
    coordinator.get_command_state = MagicMock(
        return_value={"state": 0, "responseCode": 490}
    )
    coordinator.api.subscribe_gear_guard_live_config = _subscribe_returning(
        _LIVE_CONFIG
    )
    return coordinator


async def _run_offer(entity, messages: list) -> MagicMock:
    """Drive one offer to the point of the KVS socket, without pumping it."""
    ws = AsyncMock()
    ws.closed = False
    http = MagicMock()
    http.ws_connect = AsyncMock(return_value=ws)
    with (
        patch(
            "custom_components.rivian.camera.async_get_clientsession",
            return_value=http,
        ),
        patch.object(entity, "_pump_signaling", new_callable=AsyncMock),
        patch("custom_components.rivian.camera.asyncio.sleep", new_callable=AsyncMock),
    ):
        await entity.async_handle_async_webrtc_offer("v=0", "sess-1", messages.append)
    return http


async def test_prepare_hands_over_the_relay_before_any_offer(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """HA asks for the client config before it forwards the offer, so a cold
    entity reports no relay and the viewer gathers only host candidates the
    vehicle cannot reach — signaling completes and no media ever flows."""
    coordinator = _config_coordinator(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    cold = entity._async_get_webrtc_client_configuration()
    assert cold.configuration.ice_servers == []

    await entity.async_prepare_live()

    warm = entity._async_get_webrtc_client_configuration()
    assert warm.configuration.ice_servers[0].urls == "turn:example"
    assert warm.configuration.ice_servers[0].credential == "c"
    # The config-only session it ran on must not be left behind as a viewer.
    assert entity._sessions == {}


async def test_prepare_answers_through_has_own_client_config(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """async_get_webrtc_client_configuration is @final and appends whatever
    ICE servers the user registered with HA. Prepare has to answer through it
    or a user with their own TURN server silently loses it on this path."""
    # camera declares web_rtc as a dependency, so a real HA has always run it;
    # the @final wrapper reads the registry it sets up.
    assert await async_setup_component(hass, "web_rtc", {})
    coordinator = _config_coordinator(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    await entity.async_prepare_live()

    payload = entity.async_get_webrtc_client_configuration().to_frontend_dict()

    urls = [s["urls"] for s in payload["configuration"]["iceServers"]]
    assert "turn:example" in urls
    # HA's own default STUN rides along; the raw KVS list would not have it.
    assert len(urls) > 1


async def test_offer_after_prepare_does_not_start_a_second_session(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Two START_GEAR_GUARD_MASTER_SESSIONs give the vehicle two channels to
    answer on, and the viewer is only listening to one of them."""
    coordinator = _config_coordinator(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    await entity.async_prepare_live()
    assert coordinator.send_vehicle_command.await_count == 1

    messages: list = []
    http = await _run_offer(entity, messages)

    assert coordinator.send_vehicle_command.await_count == 1
    http.ws_connect.assert_awaited()
    assert not any(getattr(m, "code", None) == "webrtc_offer_failed" for m in messages)


async def test_repeated_prepare_reuses_the_live_config(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The card may prepare on every play; only the first should reach the car."""
    coordinator = _config_coordinator(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    await entity.async_prepare_live()
    await entity.async_prepare_live()
    assert coordinator.send_vehicle_command.await_count == 1
    assert entity._valid_cached_ice() == _SHAPED_ICE


async def test_stale_prepare_is_refetched_by_the_offer(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The KVS endpoint is a signed URL. Claiming an old one hands the viewer a
    socket that will not open, so a prepare the viewer never used must expire."""
    coordinator = _config_coordinator(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    await entity.async_prepare_live()
    entity._prepared = entity._prepared._replace(
        at=entity._prepared.at - PREPARE_REUSE_SECONDS - 1
    )

    messages: list = []
    await _run_offer(entity, messages)

    assert coordinator.send_vehicle_command.await_count == 2
    assert not any(getattr(m, "code", None) == "webrtc_offer_failed" for m in messages)


async def test_prepare_for_another_camera_is_not_claimed(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Picking a different camera between prepare and play must not silently
    stream the one that was prepared."""
    coordinator = _config_coordinator(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    await entity.async_prepare_live()
    coordinator.gear_guard_camera = "front"

    messages: list = []
    await _run_offer(entity, messages)

    assert coordinator.send_vehicle_command.await_count == 2
    assert coordinator.send_vehicle_command.await_args.args[1] == {"camera": "front"}


async def test_prepare_that_gets_no_config_reports_no_servers(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Prepare runs on a websocket command, not the offer; a sleeping vehicle
    must leave the card able to fall back, not raise at the viewer."""
    coordinator = _config_coordinator(hass, mock_config_entry, _vehicle())
    coordinator.send_vehicle_command = AsyncMock(return_value=None)
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    await entity.async_prepare_live()
    assert entity._valid_cached_ice() == []
    assert entity._prepared is None
    assert entity._sessions == {}


async def test_cached_ice_outlives_the_session_that_fetched_it(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The next viewer's get_client_config also runs before its offer, so
    clearing on teardown puts every subsequent view back to no relay."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    entity._cached_ice = list(_SHAPED_ICE)
    entity._cached_ice_expires = hass.loop.time() + 60
    entity._sessions["sess-1"] = _LiveSession("sess-1", lambda _m: None)

    await entity._async_close_session("sess-1")

    assert entity._cached_ice == _SHAPED_ICE
    assert entity._attr_is_streaming is False


async def test_an_offer_ha_built_is_trimmed_instead_of_refused(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """HA's built-in player builds its own offer and cannot be told to prefer a
    codec, so on Chrome it lands over the KVS limit through no fault of the
    user. Trim it to what the vehicle would have picked and let the view work,
    rather than refusing a session nobody can make smaller."""
    fat = chrome_offer()
    coordinator = _config_coordinator(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    messages: list = []
    ws = AsyncMock()
    ws.closed = False
    http = MagicMock()
    http.ws_connect = AsyncMock(return_value=ws)

    with (
        patch(
            "custom_components.rivian.camera.async_get_clientsession",
            return_value=http,
        ),
        patch.object(entity, "_pump_signaling", new_callable=AsyncMock),
    ):
        await entity.async_handle_async_webrtc_offer(fat, "sess-1", messages.append)

    assert not any(getattr(m, "code", None) == "webrtc_offer_failed" for m in messages)
    coordinator.send_vehicle_command.assert_awaited_once()
    sent = ws.send_json.await_args_list[0].args[0]
    assert sent["action"] == "SDP_OFFER"
    assert len(sent["messagePayload"]) <= KVS_MAX_MESSAGE_PAYLOAD


async def test_oversized_offer_is_refused_without_opening_a_session(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """An offer over the KVS frame limit can never be answered, so the viewer
    would sit on a session that looks healthy forever. Refuse it loudly and
    leave nothing behind to tear down.

    This does NOT mean the vehicle was spared: on the card path
    `rivian/gear_guard_prepare` has already started a master session before
    the offer arrives. The cold sequence here is HA's built-in player.
    """
    coordinator = _config_coordinator(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    fat = sdp_of_length(12000)
    messages: list = []

    await entity.async_handle_async_webrtc_offer("v=0" + fat, "sess-1", messages.append)

    coordinator.send_vehicle_command.assert_not_called()
    assert entity._sessions == {}
    assert [getattr(m, "message", None) for m in messages] == [
        "Offer too large for the vehicle's signaling channel"
    ]


async def test_missing_command_id_says_so_instead_of_blaming_the_vehicle(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """No command id means the VAS never left HA -- usually a pairing problem
    the user can fix. A missing config means the vehicle did not answer. One
    message for both sends people to the wrong half of the system."""
    coordinator = _config_coordinator(hass, mock_config_entry, _vehicle())
    coordinator.send_vehicle_command = AsyncMock(return_value=None)
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    messages: list = []

    await entity.async_handle_async_webrtc_offer("v=0", "sess-1", messages.append)

    assert [m.message for m in messages] == [
        "START_GEAR_GUARD_MASTER_SESSION returned no command id"
    ]


async def test_the_offer_leaves_no_prepared_config_behind(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The config an offer used is bound to the KVS endpoint it just opened.
    Left claimable, the next viewer takes the same endpoint and the two
    sessions answer over each other -- while the ICE cache, which that next
    viewer legitimately needs before its own offer, must survive."""
    coordinator = _config_coordinator(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    other = {**_LIVE_CONFIG, "endpoint": "https://other.example/?X-Amz-Signature=y"}

    def _prepare_lands_mid_fetch(*_args, **_kwargs):
        # _prepare_lock does not cover the offer, so a second viewer's prepare
        # can store its own config while this offer waits on the vehicle.
        entity._store_prepared(other)
        return "cmd-1"

    coordinator.send_vehicle_command = AsyncMock(side_effect=_prepare_lands_mid_fetch)
    messages: list = []

    await _run_offer(entity, messages)

    assert entity._prepared is None, "a hold from a racing prepare outlived the offer"
    assert entity._take_prepared() is None
    assert entity._valid_cached_ice() == _SHAPED_ICE


async def test_a_ttl_inside_the_margin_caches_nothing(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """ice_usable_seconds floors at zero and _valid_cached_ice drops on >=, so
    a credential that dies inside the margin is never handed out at all. Those
    two halves live in different modules now; this is the seam that says they
    still agree."""
    coordinator = _config_coordinator(hass, mock_config_entry, _vehicle())
    short = {**_LIVE_CONFIG["iceServers"][0], "ttl": 5}
    coordinator.api.subscribe_gear_guard_live_config = _subscribe_returning(
        {**_LIVE_CONFIG, "iceServers": [short]}
    )
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())

    await entity.async_prepare_live()

    assert entity._valid_cached_ice() == []
    cfg = entity._async_get_webrtc_client_configuration()
    assert cfg.configuration.ice_servers == []


async def test_offer_refuses_when_unavailable(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Park/offline/zone gates must apply to live view, not only the UI."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    coordinator.connectivity_state = MagicMock(return_value=ConnectivityState.OFFLINE)
    coordinator.send_vehicle_command = AsyncMock()
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    messages: list = []
    await entity.async_handle_async_webrtc_offer("v=0", "sess-1", messages.append)
    coordinator.send_vehicle_command.assert_not_called()
    assert any(getattr(m, "code", None) == "webrtc_offer_failed" for m in messages)


async def test_ws_connect_error_does_not_log_signed_url(
    hass: HomeAssistant, mock_config_entry: ConfigEntry, caplog
) -> None:
    """aiohttp includes the request URL in ClientError; that URL is a credential."""
    signed = (
        "wss://v-secret.kinesisvideo.us-east-1.amazonaws.com/"
        "?X-Amz-Signature=deadbeefsignature"
    )
    arn = "arn:aws:kinesisvideo:us-east-1:1:channel/secret-channel"

    class UrlError(ClientConnectionError):
        def __str__(self) -> str:
            return f"Cannot connect to host {signed}"

    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    coordinator.send_vehicle_command = AsyncMock(return_value="cmd-1")
    coordinator.api.subscribe_gear_guard_live_config = _subscribe_returning(
        {**_LIVE_CONFIG, "endpoint": signed, "channelArn": arn, "iceServers": []}
    )
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    session = MagicMock()
    session.ws_connect = AsyncMock(side_effect=UrlError())
    messages: list = []
    with (
        patch(
            "custom_components.rivian.camera.async_get_clientsession",
            return_value=session,
        ),
        caplog.at_level(logging.ERROR),
    ):
        await entity.async_handle_async_webrtc_offer("v=0", "sess-1", messages.append)
    assert "deadbeefsignature" not in caplog.text
    assert "v-secret" not in caplog.text
    assert "secret-channel" not in caplog.text
    assert any(getattr(m, "code", None) == "webrtc_offer_failed" for m in messages)


async def test_ice_before_answer_is_queued(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """HA can send candidates before the signaling websocket is open."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    live = _LiveSession("sess-1", lambda _m: None)
    entity._sessions["sess-1"] = live
    cand = RTCIceCandidateInit(candidate="candidate:1", sdp_mid="0", sdp_m_line_index=0)
    await entity.async_on_webrtc_candidate("sess-1", cand)
    assert live.pending_ice == [cand]


async def test_ice_is_sent_without_master_client_id(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Live 2026-08-26: master senderClientId is ''; gating on it drops TURN."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    live = _LiveSession("sess-1", lambda _m: None)
    live.ws = AsyncMock()
    live.ws.closed = False
    live.recipient_client_id = ""
    entity._sessions["sess-1"] = live
    cand = RTCIceCandidateInit(candidate="candidate:1", sdp_mid="0", sdp_m_line_index=0)
    await entity.async_on_webrtc_candidate("sess-1", cand)
    assert live.pending_ice == []
    live.ws.send_json.assert_awaited()
    sent = live.ws.send_json.await_args.args[0]
    assert sent["action"] == "ICE_CANDIDATE"
    assert sent["recipientClientId"] == ""


async def test_flush_pending_ice_after_socket_opens(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Candidates queued while connecting must go out with the SDP offer."""
    live = _LiveSession("sess-1", lambda _m: None)
    live.ws = AsyncMock()
    live.ws.closed = False
    cand = RTCIceCandidateInit(candidate="candidate:1", sdp_mid="0", sdp_m_line_index=0)
    live.pending_ice.append(cand)
    await live.flush_pending_ice()
    assert live.pending_ice == []
    live.ws.send_json.assert_awaited()


async def test_hold_skips_teardown_so_data_channel_can_switch(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Custom card hold must not VAS-restart when the picker changes."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    coordinator.gear_guard_camera = "left"
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    messages: list = []
    live = _LiveSession("sess-1", messages.append)
    entity._sessions["sess-1"] = live
    entity._session_camera = "left"
    entity.set_live_switch_hold(True)
    coordinator.gear_guard_camera = "front"
    entity._handle_coordinator_update()
    await hass.async_block_till_done()
    assert "sess-1" in entity._sessions
    assert not any(getattr(m, "code", None) == "webrtc_offer_failed" for m in messages)


async def test_selector_change_tells_frontend_why_session_ended(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Silent teardown left the card idle and blank after a camera change."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    coordinator.gear_guard_camera = "left"
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    messages: list = []
    live = _LiveSession("sess-1", messages.append)
    entity._sessions["sess-1"] = live
    entity._session_camera = "left"
    coordinator.gear_guard_camera = "front"
    entity._handle_coordinator_update()
    await hass.async_block_till_done()
    assert any(getattr(m, "code", None) == "webrtc_offer_failed" for m in messages)
    assert any("front" in getattr(m, "message", "") for m in messages)
    assert "sess-1" not in entity._sessions


async def test_close_during_config_wait_does_not_connect(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Frontend unsub during the config wait must not open a leftover KVS socket."""
    unsub_calls: list[bool] = []
    started = asyncio.Event()

    async def subscribe(_vid, _cid, _callback):
        started.set()

        async def unsub() -> None:
            unsub_calls.append(True)

        return unsub

    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    coordinator.send_vehicle_command = AsyncMock(return_value="cmd-1")
    coordinator.api.subscribe_gear_guard_live_config = AsyncMock(side_effect=subscribe)
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    session = MagicMock()
    session.ws_connect = AsyncMock()
    messages: list = []
    with patch(
        "custom_components.rivian.camera.async_get_clientsession",
        return_value=session,
    ):
        offer = hass.async_create_task(
            entity.async_handle_async_webrtc_offer("v=0", "sess-1", messages.append)
        )
        await started.wait()
        entity.close_webrtc_session("sess-1")
        await asyncio.wait_for(asyncio.shield(offer), timeout=2)
    session.ws_connect.assert_not_called()
    assert unsub_calls
    assert "sess-1" not in entity._sessions


async def test_lovelace_resource_is_a_no_op_when_lovelace_is_missing(
    hass: HomeAssistant,
) -> None:
    """Rivian often sets up before Lovelace; a missing registry must not fail setup."""
    from custom_components.rivian import _async_ensure_lovelace_resource

    await _async_ensure_lovelace_resource(
        hass, "/rivian-static/gear-guard-card.js?v=test"
    )


async def test_lovelace_resource_is_created_once(hass: HomeAssistant) -> None:
    """Storage-mode dashboards only load custom: cards from the resource list."""
    from custom_components.rivian import _async_ensure_lovelace_resource
    from homeassistant.components.lovelace.const import LOVELACE_DATA

    resources = MagicMock()
    resources.async_get_info = AsyncMock()
    resources.async_items = MagicMock(return_value=[])
    resources.async_create_item = AsyncMock()
    resources.async_update_item = AsyncMock()
    hass.data[LOVELACE_DATA] = MagicMock(resources=resources)
    url = "/rivian-static/gear-guard-card.js?v=1"
    await _async_ensure_lovelace_resource(hass, url)
    resources.async_create_item.assert_awaited_once_with(
        {"res_type": "module", "url": url}
    )
    resources.async_items.return_value = [{"id": "res-1", "url": url}]
    await _async_ensure_lovelace_resource(hass, url)
    resources.async_create_item.assert_awaited_once()
    # Without an explicit AsyncMock here a spurious update would await a bare
    # MagicMock, raise TypeError, and be swallowed by this function's own
    # except clause -- the test would pass either way.
    resources.async_update_item.assert_not_called()


async def test_lovelace_resource_url_is_repointed_not_duplicated(
    hass: HomeAssistant,
) -> None:
    """The URL carries ?v=<version>, so every upgrade would otherwise add a
    second registration and the browser would load the card twice under two
    module identities — two custom element definitions, one of which throws."""
    from custom_components.rivian import _async_ensure_lovelace_resource
    from homeassistant.components.lovelace.const import LOVELACE_DATA

    stale = {"id": "res-1", "url": "/rivian-static/gear-guard-card.js?v=old"}
    resources = MagicMock()
    resources.async_get_info = AsyncMock()
    resources.async_items = MagicMock(return_value=[stale])
    resources.async_create_item = AsyncMock()
    resources.async_update_item = AsyncMock()
    hass.data[LOVELACE_DATA] = MagicMock(resources=resources)

    url = "/rivian-static/gear-guard-card.js?v=new"
    await _async_ensure_lovelace_resource(hass, url)

    resources.async_update_item.assert_awaited_once_with("res-1", {"url": url})
    resources.async_create_item.assert_not_called()


async def test_only_the_first_stale_registration_is_repointed(
    hass: HomeAssistant,
) -> None:
    """Two upgrades leave two old registrations beside the current one.
    Repointing them all to the same URL makes Lovelace hold duplicates of one
    resource -- the same double-load this walk exists to prevent -- and the
    entry already equal to the URL must be skipped, not rewritten to itself."""
    from custom_components.rivian import _async_ensure_lovelace_resource
    from homeassistant.components.lovelace.const import LOVELACE_DATA

    url = "/rivian-static/gear-guard-card.js?v=new"
    resources = MagicMock()
    resources.async_get_info = AsyncMock()
    resources.async_items = MagicMock(
        return_value=[
            {"id": "res-0", "url": url},
            {"id": "res-1", "url": "/rivian-static/gear-guard-card.js?v=old"},
            {"id": "res-2", "url": "/rivian-static/gear-guard-card.js?v=older"},
        ]
    )
    resources.async_create_item = AsyncMock()
    resources.async_update_item = AsyncMock()
    hass.data[LOVELACE_DATA] = MagicMock(resources=resources)

    await _async_ensure_lovelace_resource(hass, url)

    resources.async_update_item.assert_awaited_once_with("res-1", {"url": url})
    resources.async_create_item.assert_not_called()


async def test_lovelace_resource_update_failure_is_swallowed(
    hass: HomeAssistant,
) -> None:
    """A resource dict without an id is a YAML-mode entry; setup must survive."""
    from custom_components.rivian import _async_ensure_lovelace_resource
    from homeassistant.components.lovelace.const import LOVELACE_DATA

    resources = MagicMock()
    resources.async_get_info = AsyncMock()
    resources.async_items = MagicMock(
        return_value=[{"url": "/rivian-static/gear-guard-card.js?v=old"}]
    )
    resources.async_create_item = AsyncMock()
    resources.async_update_item = AsyncMock()
    hass.data[LOVELACE_DATA] = MagicMock(resources=resources)

    await _async_ensure_lovelace_resource(
        hass, "/rivian-static/gear-guard-card.js?v=new"
    )
    resources.async_update_item.assert_not_called()


async def test_lovelace_resource_create_failure_is_swallowed(
    hass: HomeAssistant,
) -> None:
    """YAML-mode resources raise; setup must still succeed."""
    from custom_components.rivian import _async_ensure_lovelace_resource
    from homeassistant.components.lovelace.const import LOVELACE_DATA
    from homeassistant.exceptions import HomeAssistantError

    resources = MagicMock()
    resources.async_get_info = AsyncMock()
    resources.async_items = MagicMock(return_value=[])
    resources.async_create_item = AsyncMock(side_effect=HomeAssistantError("yaml"))
    hass.data[LOVELACE_DATA] = MagicMock(resources=resources)
    await _async_ensure_lovelace_resource(hass, "/rivian-static/gear-guard-card.js")


async def test_register_frontend_no_ops_without_http(hass: HomeAssistant) -> None:
    """test_init fixtures have hass.http is None; setup must not crash."""
    from custom_components.rivian import _async_register_frontend

    hass.http = None
    await _async_register_frontend(hass)
    assert not hass.data.get(f"{DOMAIN}_frontend")


async def test_register_frontend_serves_card_js(hass: HomeAssistant) -> None:
    """A real HA http component gets the static path and Lovelace hook."""
    from custom_components.rivian import VERSION, _async_register_frontend

    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    with (
        patch("custom_components.rivian.add_extra_js_url") as extra,
        patch("custom_components.rivian.async_when_setup") as when,
    ):
        await _async_register_frontend(hass)
        await _async_register_frontend(hass)
    hass.http.async_register_static_paths.assert_awaited_once()
    extra.assert_called_once()
    assert f"v={VERSION}" in extra.call_args.args[1]
    when.assert_called_once()
    assert hass.data.get(f"{DOMAIN}_frontend") is True


def test_live_config_accepts_unwrapped_data_key() -> None:
    """Some Apollo frames put gearGuardLiveConfig under data, not payload.data."""
    cfg = {
        "endpoint": "https://v-test.kinesisvideo.us-east-1.amazonaws.com/",
        "channelArn": "arn:aws:kinesisvideo:us-east-1:1:channel/x",
    }
    assert _live_config_from_frame({"data": {"gearGuardLiveConfig": cfg}}) == cfg
    assert (
        _live_config_from_frame({"data": {"gearGuardLiveConfig": {"endpoint": "x"}}})
        is None
    )
    assert _live_config_from_frame({"payload": {}}) is None


async def test_unsub_config_swallows_teardown_errors() -> None:
    """A failed GraphQL unsub must not block closing the KVS socket."""

    def boom() -> None:
        raise RuntimeError("gone")

    await _unsub_config(None)
    await _unsub_config(boom)

    async def async_unsub() -> None:
        return None

    await _unsub_config(async_unsub)


async def test_no_still_image_or_empty_ice_config(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Live view has no JPEG; ICE servers come from the last KVS config."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    assert await entity.async_camera_image() is None
    cfg = entity._async_get_webrtc_client_configuration()
    assert cfg.configuration.ice_servers == []
    entity._cached_ice = [{"urls": "stun:example", "username": "u", "credential": "c"}]
    entity._cached_ice_expires = hass.loop.time() + 60
    cfg = entity._async_get_webrtc_client_configuration()
    assert cfg.configuration.ice_servers[0].urls == "stun:example"
    assert entity.extra_state_attributes["camera"] == "left"


async def test_expired_ice_is_not_handed_to_the_browser(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """KVS stops honouring the TURN credential at its ttl; a stale relay is
    worse than none, because the browser waits on it instead of failing."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    entity._cached_ice = [{"urls": "turn:example", "username": "u", "credential": "c"}]
    entity._cached_ice_expires = hass.loop.time() - 1
    assert (
        entity._async_get_webrtc_client_configuration().configuration.ice_servers == []
    )
    assert entity._cached_ice == []


async def test_candidate_for_unknown_session_is_dropped(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """HA can deliver ICE after the viewer already closed."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    await entity.async_on_webrtc_candidate(
        "gone",
        RTCIceCandidateInit(candidate="candidate:1", sdp_mid="0", sdp_m_line_index=0),
    )
    await entity._async_close_session("gone")


async def test_empty_ice_candidate_is_not_sent(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """End-of-candidates is an empty string; do not wrap it as KVS JSON."""
    live = _LiveSession("sess-1", lambda _m: None)
    live.ws = AsyncMock()
    live.ws.closed = False
    await live.send_ice(
        RTCIceCandidateInit(candidate="", sdp_mid="0", sdp_m_line_index=0)
    )
    live.ws.send_json.assert_not_called()
    await live.flush_pending_ice()
    live.ws.send_json.assert_not_called()


class _FakeWsMsg:
    def __init__(self, msg_type, data=None) -> None:
        self.type = msg_type
        self.data = data


class _FakeWs:
    def __init__(self, messages) -> None:
        self._messages = list(messages)
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)

    async def close(self) -> None:
        self.closed = True


def _kvs_event(message_type: str, inner: dict, sender: str = "master-1") -> str:
    return json.dumps(
        {
            "messageType": message_type,
            "senderClientId": sender,
            "messagePayload": encode_payload(inner),
        }
    )


async def test_pump_relays_answer_and_ice_then_closes(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """SDP_ANSWER and ICE_CANDIDATE must reach the HA frontend as native events."""
    from homeassistant.components.camera import WebRTCAnswer, WebRTCCandidate

    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    messages: list = []
    live = _LiveSession("sess-1", messages.append)
    live.ws = _FakeWs(
        [
            _FakeWsMsg(WSMsgType.BINARY, b"x"),
            _FakeWsMsg(WSMsgType.TEXT, "{}"),
            _FakeWsMsg(
                WSMsgType.TEXT,
                _kvs_event(
                    "SDP_ANSWER", {"type": "answer", "sdp": "v=0\r\n"}, sender=""
                ),
            ),
            _FakeWsMsg(
                WSMsgType.TEXT,
                _kvs_event(
                    "ICE_CANDIDATE",
                    {"candidate": "candidate:1", "sdpMid": "0", "sdpMLineIndex": 0},
                ),
            ),
            _FakeWsMsg(WSMsgType.CLOSED),
        ]
    )
    entity._sessions["sess-1"] = live
    await entity._pump_signaling(live)
    assert any(isinstance(m, WebRTCAnswer) and m.answer == "v=0\r\n" for m in messages)
    assert any(isinstance(m, WebRTCCandidate) for m in messages)
    assert live.recipient_client_id == "master-1"
    assert "sess-1" not in entity._sessions


async def test_pump_error_does_not_raise(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """A dropped KVS socket must log a type, not the signed URL."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    live = _LiveSession("sess-1", lambda _m: None)

    class BoomWs:
        closed = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise ClientConnectionError("gone")

        async def close(self) -> None:
            self.closed = True

    live.ws = BoomWs()
    entity._sessions["sess-1"] = live
    await entity._pump_signaling(live)
    assert "sess-1" not in entity._sessions


async def test_close_cancels_an_in_flight_pump(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """Selector teardown must cancel the reader, not wait for KVS to hang up."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    live = _LiveSession("sess-1", lambda _m: None)
    started = asyncio.Event()

    class HangWs:
        closed = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            started.set()
            await asyncio.Event().wait()
            raise StopAsyncIteration

        async def close(self) -> None:
            self.closed = True

    live.ws = HangWs()
    entity._sessions["sess-1"] = live
    live.pump_task = hass.async_create_task(entity._pump_signaling(live))
    await started.wait()
    await entity._async_close_session("sess-1")
    assert live.pump_task.done()
    assert "sess-1" not in entity._sessions


async def test_the_pump_closing_its_own_session_still_releases_everything(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """KVS hanging up is how a normal view ends, so aclose runs inside
    pump_task itself -- the one path where the session tearing itself down is
    also the task doing the tearing. If it returns early there, every view
    leaks its GraphQL subscription and its websocket."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    entity = _live_entity(hass, mock_config_entry, coordinator, _vehicle())
    unsubbed: list[bool] = []

    async def unsub() -> None:
        unsubbed.append(True)

    gate = asyncio.Event()

    class _GatedWs(_FakeWs):
        async def __anext__(self):
            # The pump must suspend at least once, or the task completes
            # eagerly and live.pump_task is still None when aclose reads it.
            await gate.wait()
            return await super().__anext__()

    live = _LiveSession("sess-1", lambda _m: None)
    live.ws = _GatedWs([_FakeWsMsg(WSMsgType.CLOSED)])
    live.unsub_config = unsub
    entity._sessions["sess-1"] = live
    live.pump_task = hass.async_create_task(entity._pump_signaling(live))
    gate.set()

    await live.pump_task

    assert unsubbed == [True]
    assert live.ws is None
    assert "sess-1" not in entity._sessions


async def test_select_option_updates_coordinator_and_rejects_unknown(
    hass: HomeAssistant, mock_config_entry: ConfigEntry
) -> None:
    """The picker is coordinator state; a bogus option must not stick."""
    coordinator = _hass_entry(hass, mock_config_entry, _vehicle())
    coordinator.gear_guard_camera = "left"
    coordinator.async_update_listeners = MagicMock()
    added: list = []
    await select_setup(hass, mock_config_entry, added.extend)
    sel = next(e for e in added if isinstance(e, RivianGearGuardCameraSelect))
    sel.async_write_ha_state = MagicMock()
    await sel.async_select_option("front")
    assert coordinator.gear_guard_camera == "front"
    coordinator.async_update_listeners.assert_called()
    await sel.async_select_option("roof")
    assert coordinator.gear_guard_camera == "front"
    coordinator.gear_guard_camera = "nope"
    assert sel.current_option == "left"
