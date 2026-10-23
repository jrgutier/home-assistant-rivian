from __future__ import annotations

import base64
from typing import Any
from uuid import uuid4

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.camera.const import DATA_COMPONENT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .m2v import encode_switch_camera


def _live_entity(hass: HomeAssistant, entity_id: str):
    component = hass.data.get(DATA_COMPONENT)
    if component is None:
        return None
    entity = component.get_entity(entity_id)
    if entity is None or not hasattr(entity, "set_live_switch_hold"):
        return None
    return entity


@websocket_api.websocket_command(
    {
        vol.Required("type"): "rivian/gear_guard_prepare",
        vol.Required("entity_id"): cv.entity_id,
    }
)
@websocket_api.async_response
async def ws_gear_guard_prepare(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    entity = _live_entity(hass, msg["entity_id"])
    if entity is None:
        connection.send_error(
            msg["id"], "not_found", "Gear Guard live camera not found"
        )
        return
    await entity.async_prepare_live()
    connection.send_result(
        msg["id"], entity.async_get_webrtc_client_configuration().to_frontend_dict()
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "rivian/gear_guard_hold",
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("hold"): bool,
    }
)
@websocket_api.async_response
async def ws_gear_guard_hold(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    entity = _live_entity(hass, msg["entity_id"])
    if entity is None:
        connection.send_error(
            msg["id"], "not_found", "Gear Guard live camera not found"
        )
        return
    entity.set_live_switch_hold(bool(msg["hold"]))
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): "rivian/gear_guard_switch_payload",
        vol.Required("camera"): str,
    }
)
@websocket_api.async_response
async def ws_gear_guard_switch_payload(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        payload = encode_switch_camera(msg["camera"], str(uuid4()))
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_camera", str(err))
        return
    connection.send_result(
        msg["id"],
        {"payload_b64": base64.b64encode(payload).decode("ascii")},
    )


@callback
def async_setup_camera_ws(hass: HomeAssistant) -> None:
    key = f"{DOMAIN}_camera_ws"
    if hass.data.get(key):
        return
    websocket_api.async_register_command(hass, ws_gear_guard_prepare)
    websocket_api.async_register_command(hass, ws_gear_guard_hold)
    websocket_api.async_register_command(hass, ws_gear_guard_switch_payload)
    hass.data[key] = True
