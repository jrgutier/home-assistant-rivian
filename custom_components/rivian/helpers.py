"""Rivian helpers."""

from __future__ import annotations

from typing import Any

from rivian import Rivian

from homeassistant.components.diagnostics.util import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN, CONF_USER_SESSION_TOKEN

TO_REDACT = {
    # The three token constants are imported above and were NOT listed here.
    # Today that is latent rather than live: async_get_config_entry_diagnostics
    # dumps coordinator data only, never entry.data, so no token reaches a
    # diagnostics download. Listed anyway, because the day someone adds
    # entry.data to that payload the omission becomes a credential leak, and the
    # import already implied they were covered.
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_USER_SESSION_TOKEN,
    CONF_EMAIL,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    "hrid",
    "id",
    "identityId",
    "inviteId",
    "mappedIdentityId",
    "orderId",
    "serialNumber",
    "userId",
    "vas",
    "vehicleId",
    "vin",
    "wallboxId",
}


def get_rivian_api_from_entry(hass: HomeAssistant, entry: ConfigEntry) -> Rivian:
    """Get Rivian API from a config entry."""
    return Rivian(
        request_timeout=30,
        session=async_get_clientsession(hass),
        access_token=entry.data.get(CONF_ACCESS_TOKEN),
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
        user_session_token=entry.data.get(CONF_USER_SESSION_TOKEN),
    )


def redact(data: Any) -> dict:
    """Redact sensitive data."""
    return async_redact_data(data, TO_REDACT)
