"""Rivian helpers."""

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

# Which entity groups a vehicle model receives.
#
# This replaces `if model in vehicle["model"]`, a SUBSTRING test over the group
# keys that happened to work for the two models it was written against:
#
#     "R1"  in "R1T"  -> True     (intended)
#     "R1"  in "R2"   -> False    <-- an R2 got ZERO entities, silently
#     "R1T" in "R1S"  -> False    (intended)
#
# Deliberately no "ALL" key populated from "R1". The platform comprehensions
# build LISTS (binary_sensor.py:30-36, sensor.py:71-78) and every description
# shares unique_id = f"{vin}-{key}" (entity.py:49), so ALL + R1 + R1T would add
# the shared group twice: 114 duplicate-unique-id errors per vehicle.
VEHICLE_MODEL_GROUPS: dict[str, tuple[str, ...]] = {
    "R1T": ("R1", "R1T"),
    "R1S": ("R1", "R1S"),
    "R2": ("R1",),
}

# An exact map is less forgiving than the substring test it replaces, so an
# unrecognised or missing model must NOT raise: a KeyError here removes every
# sensor and binary sensor for that vehicle, which is a worse failure than
# handing it the shared group and letting per-field availability sort it out.
DEFAULT_MODEL_GROUPS: tuple[str, ...] = ("R1",)


def groups_for_model(model: str | None) -> tuple[str, ...]:
    """Return the entity groups a vehicle of this model receives."""
    if not model:
        return DEFAULT_MODEL_GROUPS
    return VEHICLE_MODEL_GROUPS.get(model, DEFAULT_MODEL_GROUPS)


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


# Any run of 24+ token-ish characters. Long enough to miss vehicle ids
# ("01-276948064"), command names and HTTP status text, all of which are the
# diagnostic content worth keeping.
_TOKEN_SHAPED = re.compile(r"[A-Za-z0-9_\-]{24,}(?:\.[A-Za-z0-9_\-]{8,}){0,2}")


def redact_text(text: str) -> str:
    """Mask anything token-shaped in a string bound for a log.

    Defence in depth ONLY. The real fix is in the client: RivianApiException
    redacts headers and request bodies as it is constructed, verified against the
    live API. This catches what that cannot -- an exception raised somewhere that
    never goes through that constructor, such as a bare transport error carrying a
    signed URL.

    Deliberately conservative: it masks long opaque runs and leaves short
    identifiers alone, because a redactor that eats the message makes the log
    useless and gets turned off.
    """
    return _TOKEN_SHAPED.sub("<REDACTED>", text)


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
