from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.setup import async_when_setup

from .const import (
    ATTR_API,
    ATTR_COORDINATOR,
    ATTR_SUPPORTED_FEATURES,
    ATTR_USER,
    ATTR_VEHICLE,
    ATTR_WALLBOX,
    CONF_VEHICLE_CONTROL,
    DOMAIN,
    ISSUE_URL,
    VERSION,
)
from .coordinator import (
    SupportedFeaturesCoordinator,
    UserCoordinator,
    VehicleCoordinator,
    WallboxCoordinator,
)
from .helpers import get_rivian_api_from_entry, redact_text
from .rivian_client import Rivian

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.DEVICE_TRACKER,
    Platform.IMAGE,
    Platform.LOCK,
    Platform.NOTIFY,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
    Platform.UPDATE,
]

GEN2_PAIRING_ISSUE_URL = (
    "https://github.com/jrgutier/home-assistant-rivian/issues/new"
    "?template=gen2_beta.yml"
)


async def _async_register_frontend(hass: HomeAssistant) -> None:
    key = f"{DOMAIN}_frontend"
    if hass.data.get(key):
        return
    if hass.http is None:
        return
    www = Path(__file__).parent / "www"
    await hass.http.async_register_static_paths(
        [StaticPathConfig("/rivian-static", str(www), cache_headers=False)]
    )
    url = f"/rivian-static/gear-guard-card.js?v={VERSION}"
    add_extra_js_url(hass, url)

    async def _when_lovelace(_hass: HomeAssistant, _component: str) -> None:
        await _async_ensure_lovelace_resource(_hass, url)

    async_when_setup(hass, "lovelace", _when_lovelace)
    hass.data[key] = True


async def _async_ensure_lovelace_resource(hass: HomeAssistant, url: str) -> None:
    from homeassistant.components.lovelace.const import LOVELACE_DATA

    ll = hass.data.get(LOVELACE_DATA)
    resources = getattr(ll, "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        return
    await resources.async_get_info()
    stem = "/rivian-static/gear-guard-card.js"
    matching = [
        item for item in resources.async_items() if stem in str(item.get("url") or "")
    ]
    stale = next((item for item in matching if str(item.get("url") or "") != url), None)
    try:
        if stale is not None:
            # A resource URL that differs from the extra_js_url one makes the
            # browser fetch the card twice under two module identities.
            await resources.async_update_item(stale["id"], {"url": url})
        elif not matching:
            await resources.async_create_item({"res_type": "module", "url": url})
    except (HomeAssistantError, AttributeError, TypeError, KeyError):
        _LOGGER.debug("Lovelace resource not persisted")


def _gen2_pairing_issue_id(vehicle_id: str) -> str:
    return f"gen2_pairing_failed_{vehicle_id}"


def async_create_gen2_pairing_issue(hass: HomeAssistant, vehicle_id: str) -> None:
    async_create_issue(
        hass,
        DOMAIN,
        _gen2_pairing_issue_id(vehicle_id),
        is_fixable=False,
        is_persistent=False,
        severity=IssueSeverity.WARNING,
        translation_key="gen2_pairing_failed",
        learn_more_url=GEN2_PAIRING_ISSUE_URL,
    )


def async_delete_gen2_pairing_issue(hass: HomeAssistant, vehicle_id: str) -> None:
    async_delete_issue(hass, DOMAIN, _gen2_pairing_issue_id(vehicle_id))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.info(
        "Rivian integration is starting under version %s. Please report issues at %s",
        VERSION,
        ISSUE_URL,
    )

    hass.data.setdefault(DOMAIN, {})
    await _async_register_frontend(hass)

    client = get_rivian_api_from_entry(hass, entry)
    try:
        await client.create_csrf_token()
    except Exception as err:
        _LOGGER.error("Could not update Rivian Data: %s", redact_text(str(err)))
        await client.close()
        raise ConfigEntryNotReady("Error communicating with API") from err

    coordinator = UserCoordinator(
        hass=hass, config_entry=entry, client=client, include_phones=True
    )
    await coordinator.async_config_entry_first_refresh()

    vehicle_control = entry.options.get(CONF_VEHICLE_CONTROL)
    if vehicle_control and not coordinator.data.get("registrationChannels"):
        vehicle_control = []
        async_create_issue(
            hass,
            DOMAIN,
            entry.entry_id,
            is_fixable=False,
            is_persistent=False,
            severity=IssueSeverity.WARNING,
            translation_key="2fa_missing",
        )
    else:
        async_delete_issue(hass, DOMAIN, entry.entry_id)

    vehicles = coordinator.get_vehicles()
    if vehicle_control and (
        enrolled := coordinator.get_enrolled_phone_data(entry.options.get("public_key"))
    ):
        for vehicle_id in vehicles:
            if vehicle_id in enrolled[1]:
                vehicles[vehicle_id]["phone_identity_id"] = enrolled[1][vehicle_id]

    vehicle_coordinators: dict[str, VehicleCoordinator] = {}
    for vehicle_id in vehicles:
        coor = VehicleCoordinator(
            hass=hass, config_entry=entry, client=client, vehicle_id=vehicle_id
        )
        await coor.async_config_entry_first_refresh()
        if not coor.data:
            raise ConfigEntryNotReady("Issue loading vehicle data")
        await coor.charging_coordinator.async_config_entry_first_refresh()
        await coor.drivers_coordinator.async_config_entry_first_refresh()
        vehicle_coordinators[vehicle_id] = coor

    wallbox_coordinator = WallboxCoordinator(
        hass=hass, config_entry=entry, client=client
    )
    await wallbox_coordinator.async_config_entry_first_refresh()

    features_coordinator = SupportedFeaturesCoordinator(
        hass=hass, config_entry=entry, client=client
    )
    await features_coordinator.async_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        ATTR_API: client,
        ATTR_VEHICLE: vehicles,
        ATTR_COORDINATOR: {
            ATTR_USER: coordinator,
            ATTR_VEHICLE: vehicle_coordinators,
            ATTR_WALLBOX: wallbox_coordinator,
            ATTR_SUPPORTED_FEATURES: features_coordinator,
        },
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    await async_setup_services(hass, entry)

    return True


def _parse_hhmm(value: str) -> tuple[int, int]:
    parts = value.split(":")
    return int(parts[0]), int(parts[1])


async def async_setup_services(hass: HomeAssistant, entry: ConfigEntry) -> None:

    def get_vehicle_coordinator_from_device(
        device_id: str,
    ) -> tuple[VehicleCoordinator, str]:
        device_registry = dr.async_get(hass)
        device_entry = device_registry.async_get(device_id)

        if not device_entry:
            raise ServiceValidationError(f"Device {device_id} not found")

        entry_data = hass.data[DOMAIN][entry.entry_id]
        vehicle_coordinators: dict[str, VehicleCoordinator] = entry_data[
            ATTR_COORDINATOR
        ][ATTR_VEHICLE]

        vehicle_id = next(
            (
                i
                for d, i in device_entry.identifiers
                if d == DOMAIN and i in vehicle_coordinators
            ),
            None,
        )
        if vehicle_id is None:
            raise ServiceValidationError(
                f"Could not find a vehicle for device {device_id}"
            )

        return vehicle_coordinators[vehicle_id], vehicle_id

    async def set_charging_schedule(call: ServiceCall) -> None:
        if not call.data.get("device_id"):
            raise ServiceValidationError("No device specified")

        device_id = call.data["device_id"]
        coordinator, vehicle_id = get_vehicle_coordinator_from_device(device_id)

        start_time = call.data.get("start_time")
        end_time = call.data.get("end_time")
        start_day = call.data.get("start_day", 0)
        end_day = call.data.get("end_day", 6)

        if not start_time or not end_time:
            raise ServiceValidationError("Both start_time and end_time are required")

        try:
            start_hour, start_minute = _parse_hhmm(start_time)
            end_hour, end_minute = _parse_hhmm(end_time)
        except (ValueError, IndexError) as err:
            raise ServiceValidationError(
                "Invalid time format. Use HH:MM format (e.g., '22:00')"
            ) from err

        if not (0 <= start_hour <= 23 and 0 <= start_minute <= 59):
            raise ServiceValidationError("Invalid start_time values")
        if not (0 <= end_hour <= 23 and 0 <= end_minute <= 59):
            raise ServiceValidationError("Invalid end_time values")
        if not (0 <= start_day <= 6 and 0 <= end_day <= 6):
            raise ServiceValidationError("Invalid day values (must be 0-6)")

        try:
            _LOGGER.debug(
                "Setting charging schedule for vehicle %s: %02d:%02d-%02d:%02d (days %d-%d)",
                vehicle_id,
                start_hour,
                start_minute,
                end_hour,
                end_minute,
                start_day,
                end_day,
            )

            result = await coordinator.send_parallax_command(
                "set_charging_schedule",
                start_hour=start_hour,
                start_minute=start_minute,
                end_hour=end_hour,
                end_minute=end_minute,
                start_day=start_day,
                end_day=end_day,
            )

            _LOGGER.info(
                "Successfully set charging schedule for vehicle %s: %s",
                vehicle_id,
                result,
            )

        except Exception as err:
            _LOGGER.exception(
                "Error setting charging schedule for vehicle %s", vehicle_id
            )
            raise ServiceValidationError(
                f"Failed to set charging schedule: {err}"
            ) from err

    if not hass.services.has_service(DOMAIN, "set_charging_schedule"):
        hass.services.async_register(
            DOMAIN,
            "set_charging_schedule",
            set_charging_schedule,
            supports_response=None,
        )
        _LOGGER.debug("Registered service: %s.set_charging_schedule", DOMAIN)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    api: Rivian = hass.data[DOMAIN][entry.entry_id][ATTR_API]
    await api.close()

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

        if not hass.data[DOMAIN] and hass.services.has_service(
            DOMAIN, "set_charging_schedule"
        ):
            hass.services.async_remove(DOMAIN, "set_charging_schedule")
            _LOGGER.debug("Unregistered service: %s.set_charging_schedule", DOMAIN)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    if public_key := entry.options.get("public_key"):
        client = get_rivian_api_from_entry(hass, entry)
        coordinator = UserCoordinator(
            hass=hass, config_entry=entry, client=client, include_phones=True
        )
        await coordinator.async_config_entry_first_refresh()

        if enrolled_data := coordinator.get_enrolled_phone_data(public_key=public_key):
            for identity_id in enrolled_data[1].values():
                await client.disenroll_phone(identity_id=identity_id)
        await client.close()


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
) -> bool:
    coordinators = hass.data[DOMAIN][config_entry.entry_id][ATTR_COORDINATOR]
    user_coordinator: UserCoordinator = coordinators[ATTR_USER]
    wallbox_coordinator: WallboxCoordinator = coordinators[ATTR_WALLBOX]

    known = user_coordinator.get_vehicles().keys() | {
        x["wallboxId"] for x in wallbox_coordinator.data
    }

    return not any(
        identifier
        for identifier in device_entry.identifiers
        if identifier[0] == DOMAIN and identifier[1] in known
    )
