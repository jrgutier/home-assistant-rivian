"""Custom-card websocket: ICE prefetch, hold VAS teardown, SWITCH_CAMERA."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

from custom_components.rivian.camera import CAMERAS, RivianLiveCameraEntity
from custom_components.rivian.camera_ws import (
    ws_gear_guard_hold,
    ws_gear_guard_prepare,
    ws_gear_guard_switch_payload,
)
from custom_components.rivian.coordinator import VehicleCoordinator
from homeassistant.components.camera.const import DATA_COMPONENT
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_hold = inspect.unwrap(ws_gear_guard_hold)
_prepare = inspect.unwrap(ws_gear_guard_prepare)
_payload = inspect.unwrap(ws_gear_guard_switch_payload)


def _entity(hass, entry, vehicle) -> RivianLiveCameraEntity:
    coordinator = MagicMock(spec=VehicleCoordinator)
    coordinator.data = {}
    coordinator.get = MagicMock(return_value="park")
    entity = RivianLiveCameraEntity(coordinator, entry, CAMERAS[0], vehicle)
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()
    return entity


def _conn() -> MagicMock:
    conn = MagicMock()
    conn.send_error = MagicMock()
    conn.send_result = MagicMock()
    return conn


async def test_hold_not_found(hass: HomeAssistant) -> None:
    """A stale entity_id must not 500 the websocket."""
    conn = _conn()
    await _hold(hass, conn, {"id": 1, "entity_id": "camera.missing", "hold": True})
    conn.send_error.assert_called_once()
    assert conn.send_error.call_args.args[1] == "not_found"


async def test_hold_sets_flag_on_live_camera(
    hass: HomeAssistant, mock_config_entry: ConfigEntry, mock_vehicle_paired
) -> None:
    """The custom card owns SWITCH_CAMERA; the picker must not VAS-restart."""
    entity = _entity(hass, mock_config_entry, mock_vehicle_paired)
    component = MagicMock()
    component.get_entity = MagicMock(return_value=entity)
    hass.data[DATA_COMPONENT] = component
    conn = _conn()
    await _hold(
        hass, conn, {"id": 7, "entity_id": "camera.gear_guard_live", "hold": True}
    )
    assert entity._live_switch_hold is True
    conn.send_result.assert_called_once_with(7)


async def test_switch_payload_is_base64_protobuf() -> None:
    """Browser DataChannel needs the APK bytes, not a new VAS."""
    conn = _conn()
    hass = MagicMock()
    await _payload(hass, conn, {"id": 3, "camera": "front"})
    conn.send_result.assert_called_once()
    payload = conn.send_result.call_args.args[1]
    assert "payload_b64" in payload
    assert payload["payload_b64"]


async def test_switch_payload_rejects_unknown_camera() -> None:
    """Unknown names must not become a default enum value."""
    conn = _conn()
    await _payload(MagicMock(), conn, {"id": 4, "camera": "roof"})
    conn.send_error.assert_called_once()
    assert conn.send_error.call_args.args[1] == "invalid_camera"


async def test_hold_ignores_non_live_camera(hass: HomeAssistant) -> None:
    """A stock HA camera on the same component must not get a hold flag."""
    component = MagicMock()
    component.get_entity = MagicMock(return_value=object())
    hass.data[DATA_COMPONENT] = component
    conn = _conn()
    await _hold(hass, conn, {"id": 8, "entity_id": "camera.other", "hold": True})
    conn.send_error.assert_called_once()
    assert conn.send_error.call_args.args[1] == "not_found"


async def test_prepare_not_found(hass: HomeAssistant) -> None:
    """The card prepares before it plays; a stale entity_id must not 500."""
    conn = _conn()
    await _prepare(hass, conn, {"id": 2, "entity_id": "camera.missing"})
    conn.send_error.assert_called_once()
    assert conn.send_error.call_args.args[1] == "not_found"


async def test_prepare_returns_the_ice_servers(
    hass: HomeAssistant, mock_config_entry: ConfigEntry, mock_vehicle_paired
) -> None:
    """The browser must know the relay before it builds its peer connection."""
    entity = _entity(hass, mock_config_entry, mock_vehicle_paired)
    servers = [{"urls": "turn:example", "username": "u", "credential": "c"}]
    entity.async_prepare_live = AsyncMock(return_value=servers)
    component = MagicMock()
    component.get_entity = MagicMock(return_value=entity)
    hass.data[DATA_COMPONENT] = component
    conn = _conn()
    await _prepare(hass, conn, {"id": 9, "entity_id": "camera.gear_guard_live"})
    conn.send_result.assert_called_once_with(9, {"iceServers": servers})


async def test_prepare_ignores_non_live_camera(hass: HomeAssistant) -> None:
    """A stock HA camera has no vehicle session to start."""
    component = MagicMock()
    component.get_entity = MagicMock(return_value=object())
    hass.data[DATA_COMPONENT] = component
    conn = _conn()
    await _prepare(hass, conn, {"id": 10, "entity_id": "camera.other"})
    conn.send_error.assert_called_once()
    assert conn.send_error.call_args.args[1] == "not_found"
