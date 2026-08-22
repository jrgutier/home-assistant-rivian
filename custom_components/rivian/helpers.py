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
# build LISTS (binary_sensor.py:40, sensor.py:71-78) and every description
# shares unique_id = f"{vin}-{key}" (entity.py:54), so ALL + R1 + R1T would add
# the shared group twice: 114 duplicate-unique-id errors per vehicle.
#
# R2 also carries "LIFTGATE": an R2 is an SUV with a liftgate, but the three
# liftgate state descriptions (const.py:1537 SENSORS["LIFTGATE"],
# const.py:1814 BINARY_SENSORS["LIFTGATE"]) used to live in "R1S" only. R2 was
# ("R1",), so it got the liftgate CONTROL (cover.py:114, button.py:88 -- gated
# on the LIFTGATE_CMD feature flag, not on this map) with no way to read
# whether the liftgate was open or locked: it could open a door it couldn't
# see the state of.
#
# Rejected: folding R2 into the "R1S" group outright (R2 -> ("R1", "R1S")).
# One line, but "R1S" also carries the third-row seat heaters
# (seat_third_row_left_heat / seat_third_row_right_heat), and no R2
# configuration has a third row -- that would fabricate two entities no R2
# owns. Pulling the liftgate descriptions into their own "LIFTGATE" group and
# giving it to both "R1S" and "R2" grants exactly the capability that's
# shared (liftgate) without the one that isn't (third row). "R1S"'s and
# "R1T"'s entity sets are unchanged by this: R1S trades "R1S" membership in
# the liftgate keys for "LIFTGATE" membership in the same keys, a relabel,
# not a removal. Pinned by tests/fixtures/entity_sets.json.
VEHICLE_MODEL_GROUPS: dict[str, tuple[str, ...]] = {
    "R1T": ("R1", "R1T"),
    "R1S": ("R1", "R1S", "LIFTGATE"),
    "R2": ("R1", "LIFTGATE"),
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
    "bearing",
    "geoLocation",
    "hrid",
    "id",
    "identityId",
    "inviteId",
    "mappedIdentityId",
    "orderId",
    # positionHorizontal/positionVertical/bearing/speed are the four gnssError
    # fields (rivian_client/schemas/gateway.graphql:545-551) -- no sensor
    # description reads them yet, but async_redact_data (checked: it recurses
    # into nested Mapping/list values and matches by bare key name at any
    # depth, not a dotted path) will already catch them by name the moment a
    # description exists, so the redaction can't be forgotten after the fact.
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
