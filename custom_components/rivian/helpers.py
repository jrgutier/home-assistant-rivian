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
from .legacy_grants import DEFAULT_MODEL_GRANTS, VEHICLE_MODEL_GRANTS
from .rivian_client import Rivian


def groups_for_model(model: str | None) -> tuple[str, ...]:
    """Return the entity groups a vehicle of this model receives.

    See legacy_grants.py's VEHICLE_MODEL_GRANTS for the map and its reasoning
    -- this function is the one call path onto it, kept here (rather than
    moved alongside the map) because sensor.py and binary_sensor.py already
    import it from `helpers`.
    """
    if not model:
        return DEFAULT_MODEL_GRANTS
    return VEHICLE_MODEL_GRANTS.get(model, DEFAULT_MODEL_GRANTS)


# GateEvidence: every source that grants an entity to a vehicle, as a set of
# names rather than a bool. A subset of {"ungated", "legacy", "feature",
# "option"} -- plain alias, not a NewType, so see TestNoBoolComparisonLint in
# tests/test_vehicle_supports.py for why nothing may compare its result to a
# bool.
GateEvidence = frozenset[str]


def vehicle_supports(description: Any, vehicle: dict[str, Any]) -> GateEvidence:
    """Every source that grants `description` to `vehicle`. Non-empty -> create it.

    s19 SECTION A: plumbing only. Nothing calls this outside its own tests yet --
    sensor.py, binary_sensor.py and the other platforms keep calling
    groups_for_model() directly. Wiring a platform's async_setup_entry over
    to this predicate is a later story; this function's job today is only to
    exist correctly, proven by its own truth-table tests plus
    dump_entity_sets.py --check showing landing it moved zero entities.

    UNION, never intersection. Two recorded failures of this codebase, in
    opposite directions, are why:

      * `TONNEAU_CMD` gated a cover behind a supportedFeatures flag that
        appears in no vehicle's feed and in none of the app's 32,941
        decompiled files, while both tonneau commands are live-proven to
        move the physical cover (data_classes.py's RivianCoverEntityDescription
        docstring). Requiring that flag meant the cover existed for nobody.
      * The project's own live R1T advertises NONE of LIFTGATE_CMD,
        FRUNK_NXT_ACT, or HEATED_SEATS in supportedFeatures, yet the frunk,
        windows, and heated-seat controls all work on it. Requiring a feature
        flag present would delete working controls from a real vehicle.

    Intersecting evidence sources would reproduce one of those two failures
    for every description with more than one gating field set. Union means
    ANY source granting the entity is enough, and a source that stays silent
    (an unset field, or a vehicle that reports nothing for it) simply
    contributes nothing -- it can never veto a grant another source made.

    Evidence sources:

      * "legacy" -- description.legacy_group is one of the groups
        groups_for_model(vehicle.get("model")) returns. The permanent floor;
        see legacy_grants.py.
      * "feature" -- description.feature (a string, or a tuple of which ANY
        one counts) is present in vehicle.get("supported_features", []).
      * "option" -- description.option_code is a member of
        vehicle.get("option_codes", []) (coordinator.py's
        _extract_option_codes(), landed alongside this section). List
        MEMBERSHIP, not comparing the whole field with `==` -- the app's
        original check is Kotlin `contains` on a single optionId string
        (`tonneauOptionId.contains(TONNEAU_POWER_OPTION_ID)`), but
        _extract_option_codes() already flattens `mobileConfiguration` into
        a list of atomic optionId values (e.g. "TON-P01"), so the analogous
        check at THIS layer is "is this code one of the vehicle's codes",
        i.e. Python `in` on the list -- confirmed against
        test_coordinator_base.py's own `"TON-P01" in option_codes` assertion,
        not guessed. option_codes can be `None` (mobileConfiguration fragment
        rejected) as well as `[]` (accepted, no matches); both mean no
        evidence here.

    An "empty gate" -- a description with all three fields unset, i.e. it
    carries no gating criteria to evaluate at all -- yields {"ungated"}:
    unconditional creation, the same default behaviour an ungated description
    already has today. That is different from a description WITH gating
    fields set that simply do not match this vehicle, which yields the empty
    frozenset (excluded).
    """
    evidence: set[str] = set()

    legacy_group = getattr(description, "legacy_group", None)
    if legacy_group is not None and legacy_group in groups_for_model(
        vehicle.get("model")
    ):
        evidence.add("legacy")

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

    if legacy_group is None and feature is None and option_code is None:
        return frozenset({"ungated"})

    return frozenset(evidence)


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
