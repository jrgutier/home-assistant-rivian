from __future__ import annotations

import re
from typing import Any

from homeassistant.components.diagnostics.util import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN, CONF_USER_SESSION_TOKEN
from .rivian_client import Rivian

GateEvidence = frozenset[str]


def vehicle_supports(description: Any, vehicle: dict[str, Any]) -> GateEvidence:
    evidence: set[str] = set()

    feature = getattr(description, "feature", None)
    if feature is not None:
        wanted = (feature,) if isinstance(feature, str) else feature
        supported = vehicle.get("supported_features") or []
        if any(f in supported for f in wanted):
            evidence.add("feature")

    option_code = getattr(description, "option_code", None)
    if option_code is not None:
        option_codes = vehicle.get("option_codes") or []
        if option_code in option_codes:
            evidence.add("option")

    if feature is None and option_code is None:
        return frozenset({"ungated"})

    return frozenset(evidence)


TO_REDACT = {
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_USER_SESSION_TOKEN,
    CONF_EMAIL,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    "bearing",
    "geoLocation",
    "hrid",
    "id",
    "identityId",
    "inviteId",
    "mappedIdentityId",
    "orderId",
    "positionHorizontal",
    "positionVertical",
    "serialNumber",
    "speed",
    "userId",
    "vas",
    "vehicleId",
    "vin",
    "wallboxId",
    "wifiSsid",
    "channelArn",
    "iceServers",
    "credential",
    "endpoint",
    "phone_id",
    "vas_vehicle_id",
    "vas_id",
    "address",
}


_TOKEN_SHAPED = re.compile(r"[A-Za-z0-9_\-]{24,}(?:\.[A-Za-z0-9_\-]{8,}){0,2}")


def redact_text(text: str) -> str:
    return _TOKEN_SHAPED.sub("<REDACTED>", text)


def get_rivian_api_from_entry(hass: HomeAssistant, entry: ConfigEntry) -> Rivian:
    return Rivian(
        request_timeout=30,
        session=async_get_clientsession(hass),
        access_token=entry.data.get(CONF_ACCESS_TOKEN),
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
        user_session_token=entry.data.get(CONF_USER_SESSION_TOKEN),
    )


def redact(data: Any) -> dict:
    return async_redact_data(data, TO_REDACT)
