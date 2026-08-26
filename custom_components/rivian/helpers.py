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

# GateEvidence: every source that grants an entity to a vehicle, as a set of
# names rather than a bool. A subset of {"ungated", "feature", "option"} --
# plain alias, not a NewType, so see TestNoBoolComparisonLint in
# tests/test_vehicle_supports.py for why nothing may compare its result to a
# bool.
GateEvidence = frozenset[str]


def vehicle_supports(description: Any, vehicle: dict[str, Any]) -> GateEvidence:
    """Every source that grants `description` to `vehicle`. Non-empty -> create it.

    Sensor, binary-sensor, and SELECTS setup call this as the creation
    predicate. Covers and buttons stay dict-key gated and do not.

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

    An "empty gate" -- a description with both fields unset, i.e. it
    carries no gating criteria to evaluate at all -- yields {"ungated"}:
    unconditional creation. That is different from a description WITH gating
    fields set that simply do not match this vehicle, which yields the empty
    frozenset (excluded).
    """
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
    # Gen 2 BLE pairing (ble_trace.py) surfaces a raw pairing trace through
    # diagnostics for beta testers to attach to a PUBLIC, PERMANENT GitHub
    # issue. NOTE the fingerprints are stored under "_fp"-suffixed keys
    # ("phone_id_fp" etc.) precisely so these entries do NOT clobber them --
    # async_redact_data matches by key name without inspecting the value, so a
    # fingerprint under a bare name would be replaced by a placeholder and the
    # within-bundle correlation it exists for would be lost. Do not "tidy" the
    # suffix away; tests/test_ble_trace_redaction.py pins this.
    # `BleTrace.record_identifiers()` already fingerprints "phone_id",
    # "vas_vehicle_id" and "address" (blake2s, per-process salt, never
    # serialized -- see ble_trace.py's THE SALT INVARIANT) before they ever
    # reach `identifiers` / `as_dict()`, so listing the same key names here
    # is a second, independent line of defence, not a substitute for that
    # one: it is what catches a future record_* call that forgets to
    # fingerprint, or a raw value that reaches diagnostics some other way
    # (e.g. logged and re-attached) -- the exact "forgot to redact" case the
    # token-constant comment above already describes. Currently LATENT for
    # that reason: as of this writing every path that puts one of these
    # under its own key name has already hashed it first, so there is no
    # live leak, only pre-emptive coverage for the day that stops being true.
    #   - "phone_id": the enrolled phone's UUID (verbatim param name across
    #     ble.py, ble_gen2.py, rivian.py, and the ble_trace.py identifiers
    #     key) -- resolvable to one person's phone.
    #   - "vas_vehicle_id" / "vas_id": the VAS vehicle id (the former is
    #     both the pair_phone*() parameter name and the ble_trace.py
    #     identifiers key; the latter is the flattened key button.py reads
    #     the same value under as vehicle["vas_id"]) -- broadcast in the BLE
    #     advertisement's service_uuids, so it is resolvable by anyone near
    #     the vehicle, unlike the internal `vehicleId` above.
    #   - "address": the Rivian Phone Key's BLE MAC (bleak's
    #     `service_info.address`, button.py:207; same key name in
    #     ble_trace.py's identifiers dict) -- sniffable at short range and
    #     only 48 bits, so it would be trivially enumerable if it ever
    #     reached a bundle unhashed. NOTE this key name is not BLE-specific:
    #     it also matches the unrelated charging-station and user postal
    #     address fields in gateway.graphql / charging.graphql, which are
    #     not otherwise redacted today. Redacting those too is a strict
    #     privacy improvement, not a regression, so the collision is
    #     accepted rather than worked around with a narrower key.
    # MECHANIC, not just a footnote: async_redact_data (helpers.redact) only
    # matches by key NAME, at any depth -- it never inspects or redacts dict
    # KEYS. A payload keyed BY one of these raw identifiers (e.g. a trace
    # dict of the form {vas_vehicle_id: {...}}) leaks that identifier
    # regardless of what is listed here. That is exactly why the trace in
    # ble_trace.py is keyed by the internal `vehicle_id` and not by
    # `vas_vehicle_id`, VIN, or the BLE MAC -- see get_trace()'s docstring
    # and diagnostics.py's own per-vehicle_id filtering of "ble_trace".
    "phone_id",
    "vas_vehicle_id",
    "vas_id",
    "address",
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
