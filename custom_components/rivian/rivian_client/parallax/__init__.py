"""Parallax protocol: telemetry decoding and vehicle-operation commands.

READ -- every topic the vehicle publishes on the Parallax WebSocket subscription
arrives as a base64 protobuf payload. Each is parsed with a class generated from
the `.proto` schemas in `proto/` and turned into a dict of the gateway's field
names by a decoder in the module named for the topic's prefix (`body.py` for
`body.*`, and so on).

WRITE -- `commands.py` builds outbound operations. Only one RVM is accepted as a
write, `comfort.cabin.climate_hold_setting`.

Layout:
    core.py      the registry, and the helpers the topic modules share
    proto/       .proto schemas and the *_pb2 modules generated from them
    <prefix>.py  one module per topic prefix
    commands.py  RVMType, ParallaxCommand and the build_* helpers
    _wire.py     a hand-rolled wire walker; a debugging tool no decoder uses

To add a topic: docs/development/PARALLAX_SCHEMAS.md. Registering a decoder is
not enough to ship one -- it also has to be added to RVM_DECODERS below, and
that is deliberate.

Until s49 this was one module of hand-rolled varint parsing. The names it
exported are all still exported from here, private ones included, because
callers, tests and tooling import them.
"""

# Every name below is re-exported on purpose, the underscored ones too:
# tests/ imports the value maps, and tests/test_parallax_gap_fill.py walks every
# module-level dict of this package.
# ruff: noqa: F401

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ._wire import _decode_protobuf_fields, _decode_varint
from .body import (
    _TRAILER_PRESENCE_MAP,
    _WINDOW_CALIBRATION,
    _WINDOW_CALIBRATION_FIELDS,
    CLOSURE_MAP,
    LOCK_MAP,
    decode_closures,
    decode_locks,
    decode_trailer_state,
    decode_window_states,
)
from .charging import (
    _DERATE_STATUS,
    _FAULT_CHIME,
    _START_AVAILABLE,
    _TIME_ESTIMATE_INVALID,
    _TRIP_TARGET_SOC_RANGE,
    decode_charging_notification,
    decode_charging_schedule_time_window,
    decode_charging_session_status,
    decode_remote_command,
    decode_soc_slider,
    decode_time_estimation,
    decode_trip_target,
)
from .comfort import (
    _CLIMATE_HOLD_AVAILABILITY,
    _CLIMATE_HOLD_STATUS,
    _CLIMATE_HOLD_UNAVAILABILITY_REASON,
    _PET_MODE_STATE_MAP,
    _PET_MODE_TEMPERATURE_MAP,
    _USER_MODE_FIELDS,
    DEFROST_DEFOG_MAP,
    PRECONDITIONING_STATE_MAP,
    SEAT_DEVICES,
    SEAT_FIELDS,
    SEAT_INSTANCES,
    SEAT_LEVELS,
    decode_cabin_temperatures,
    decode_cabin_ventilation_setting,
    decode_climate_hold_setting,
    decode_climate_hold_status,
    decode_defrost,
    decode_hvac_settings_status,
    decode_pet_mode_status,
    decode_preconditioning,
    decode_seat_conditioning_status,
    decode_user_modes,
)
from .commands import (
    ParallaxCommand,
    RVMType,
    SupportsSerializeToString,
    build_climate_hold_command,
    build_climate_status_query,
    build_ota_schedule_query,
    build_vehicle_wheels_query,
    encode_climate_hold_setting,
)
from .core import _LOGGER, RVMDecoder
from .dynamics import (
    _DRIVE_MODE_MAP,
    _GEAR_MAP,
    _KNOWN_LOCATION_MAP,
    _RANGE_THRESHOLD_MAP,
    _TEMPERATURE_IMPACT_MAP,
    TIRE_POSITION_MAP,
    decode_drive_mode,
    decode_gear,
    decode_gnss,
    decode_known_location,
    decode_odometer,
    decode_range,
    decode_tires,
)
from .energy import (
    _BATTERY_CELL_TYPE_MAP,
    _LOW_VOLTAGE_HEALTH_MAP,
    decode_battery_characteristics,
    decode_battery_state,
    decode_low_voltage_battery,
)
from .energy_edge_compute import (
    _ENERGY_DISTRIBUTION,
    decode_charge_session_breakdown,
    decode_charging_graph_global,
    decode_cold_weather_soc,
    decode_parked_energy_distributions,
)
from .gearguard_streaming import (
    _GEAR_GUARD_CONSENT,
    _GEAR_GUARD_DAILY_LIMIT,
    decode_gear_guard_streaming_consent,
    decode_gear_guard_streaming_daily_limit,
)
from .geofence import _GEOFENCE_TYPE, decode_favorite_geofences
from .holiday_celebration import (
    _COSTUME_AVAILABILITY_MAP,
    _COSTUME_EFFECT_MAP,
    _COSTUME_EFFECT_TRIGGER_MAP,
    _COSTUME_LIGHTS_COLOR_MAP,
    _COSTUME_THEME_MAP,
    decode_car_costume_settings,
    decode_car_costume_state,
)
from .navigation import decode_trip_progress
from .ota import (
    _OTA_CURRENT_STATUS,
    _OTA_SOFTWARE_CATEGORY_FIRMWARE,
    _OTA_STATUS,
    decode_ota_config,
    decode_ota_deployment_state,
    decode_vehicle_ota_state,
)
from .secure_file_transfer import _PET_SNAPSHOT_FILE_TYPE, decode_pet_snapshot
from .security import (
    _ACCESS_CAN_FAULTED_MAP,
    _ALARM_SOUND_MAP,
    _HARDWARE_FAILURE_MAP,
    _IMMOBILIZER_MAP,
    _PASSIVE_ENTRY_FAIL_MAP,
    _SECURE_ELEMENT_FAULTED_MAP,
    _TOS_ACCEPTANCE_MAP,
    _VIDEO_MODE_MAP,
    _VIDEO_MONITORING_STATUS_MAP,
    decode_alarm_state,
    decode_btm_diagnosis,
    decode_immobilizer_state,
    decode_passive_entry_debug,
    decode_vas_fault,
    decode_video_monitoring,
)
from .user_passcodes import _DRIVE_AUTH_SETTING_MAP, decode_drive_auth
from .vehicle import (
    _CELLULAR_SPEC,
    _CONNECTIVITY_LEVEL_MAP,
    _WIFI_SECURITY_MAP,
    _WIFI_SPEC,
    _WPA_STATUS_MAP,
    POWER_STATE_MAP,
    decode_network_state,
    decode_power_state,
    decode_vehicle_wheels,
)
from .vehicle_access import _CCC_PASSIVE_PERMISSION, decode_passive_entry_state

# The topics this integration decodes -- and therefore subscribes to:
# coordinator.SUBSCRIBED_RVMS is derived from these keys, so adding a line here
# makes the vehicle open one more subscription. That is why this is written out
# rather than read off RVMDecoder.decoders. A decoder can be registered, tested
# and merged without going live; it goes live here, in a line a reviewer sees,
# after it has been verified on hardware.
#
# A dict literal in this file, by name: scripts/apk_corpus_sweep.py reads the
# keys out of the syntax tree.
RVM_DECODERS: dict[str, Callable[[str], dict[str, Any]]] = {
    "body.closures.states": decode_closures,
    "body.locks.states": decode_locks,
    "charging.session.status": decode_charging_session_status,
    # s44: APK-bound, previously undecoded
    "charging.session.notification": decode_charging_notification,
    "charging.session.remote_command": decode_remote_command,
    "charging.session.soc_slider": decode_soc_slider,
    "charging.session.trip_target": decode_trip_target,
    "ota.deployment.state": decode_ota_deployment_state,
    # s45: name-matched (uncalled parse wrapper), not dispatch-bound
    "body.windows.states": decode_window_states,
    "comfort.cabin.hvac_settings_status": decode_hvac_settings_status,
    "comfort.user_modes.state": decode_user_modes,
    "energy_edge_compute.graphs.cold_weather_soc": decode_cold_weather_soc,
    "geofence.geofence_service.favoriteGeofences": decode_favorite_geofences,
    "navigation.navigation_service.trip_progress": decode_trip_progress,
    "ota.ota_state.vehicle_ota_state": decode_vehicle_ota_state,
    "ota.user_schedule.ota_config": decode_ota_config,
    "secure_file_transfer.pet_snapshot.secure_file": decode_pet_snapshot,
    "vehicle_access.state.passive_entry": decode_passive_entry_state,
    "vehicle_access.passive_entry.passive_entry": decode_passive_entry_state,
    "charging.session.time_estimation": decode_time_estimation,
    "comfort.cabin.cabin_preconditioning_status": decode_preconditioning,
    "comfort.cabin.cabin_temperatures": decode_cabin_temperatures,
    "comfort.cabin.seat_conditioning_status": decode_seat_conditioning_status,
    "comfort.cabin.defrost_defog_status": decode_defrost,
    "dynamics.tires.state": decode_tires,
    "dynamics.vehicle.gnss": decode_gnss,
    "dynamics.vehicle.odometer": decode_odometer,
    "energy.high_voltage.battery_state": decode_battery_state,
    "energy_edge_compute.graphs.charge_session_breakdown": decode_charge_session_breakdown,
    "energy_edge_compute.graphs.charging_graph_global": decode_charging_graph_global,
    "vehicle.power.state": decode_power_state,
    # s34: written from the named .proto schemas, each verified against a
    # captured frame. charging.schedule.time_window was deliberately absent at
    # s34 -- its frame carries a GPS coordinate and the fixture was withheld, so
    # the decoder had nothing to verify against. A 3.17.0 app capture now supplies
    # a verified frame; its location field is zeroed in the committed fixture and
    # the decoder never emits coordinates, so the original reason is resolved.
    "charging.schedule.time_window": decode_charging_schedule_time_window,
    # 3.17.0-new topics, transcribed from the app's protobuf-lite field-info
    # descriptors (vg2/sg2/q97) + enum classes, each verified against a captured
    # frame. The DTO field ORDER disagrees with the wire numbers, so these rest on
    # the descriptor, not a guess. They are named by the 3.17.0 RVM table (zff.java)
    # rather than the 3.15.0 l6e transcription, so they are grounded via
    # RVM_NAMES_317 in tests/apk/transcription.py.
    "holiday_celebration.car_costume.state": decode_car_costume_state,
    "holiday_celebration.car_costume.settings": decode_car_costume_settings,
    "user_passcodes.passcode_types.drive_auth": decode_drive_auth,
    "comfort.cabin.cabin_ventilation_setting": decode_cabin_ventilation_setting,
    "gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent": (
        decode_gear_guard_streaming_consent
    ),
    "gearguard_streaming.privacy.gearguard_streaming_daily_limit": (
        decode_gear_guard_streaming_daily_limit
    ),
    "energy_edge_compute.graphs.parked_energy_distributions": (
        decode_parked_energy_distributions
    ),
    # This fork's RVMs, captured and verified against a real vehicle.
    "comfort.cabin.climate_hold_setting": decode_climate_hold_setting,
    "comfort.cabin.climate_hold_status": decode_climate_hold_status,
    "vehicle.wheels.vehicle_wheels": decode_vehicle_wheels,
    # Transcribed from the app's protobuf classes (f5). Every one of these feeds a
    # field the gateway schema already declares, so the existing sensors pick them
    # up with no entity changes -- and four of them (btmOcHardwareFailureStatus,
    # vasSecureElementFaulted, vasAccessCanFaulted, passiveEntryUnlockFailReason)
    # are declared but NOT subscribed, so Parallax is their only source.
    "body.trailer.state": decode_trailer_state,
    "comfort.cabin.pet_mode_status": decode_pet_mode_status,
    "dynamics.vehicle.drive_mode": decode_drive_mode,
    "dynamics.vehicle.gear": decode_gear,
    "dynamics.vehicle.location": decode_known_location,
    "dynamics.vehicle.range": decode_range,
    "energy.high_voltage.battery_characteristics": decode_battery_characteristics,
    "energy.low_voltage.battery_state": decode_low_voltage_battery,
    "security.access.btm": decode_btm_diagnosis,
    "security.access.immobilizer_state": decode_immobilizer_state,
    "security.access.passive_entry_debug": decode_passive_entry_debug,
    "security.access.vas_fault": decode_vas_fault,
    "security.alarm.state": decode_alarm_state,
    "security.video_monitoring.state": decode_video_monitoring,
    # Inference, not a read binding -- see the block comment on
    # decode_network_state. Owner decision.
    "vehicle.network.state": decode_network_state,
}

# Full list of Parallax RVMs subscribed for vehicle & charging telemetry
PARALLAX_RVMS: list[str] = list(RVM_DECODERS.keys())
CHARGING_RVMS: list[str] = [
    "charging.session.notification",
    "charging.session.remote_command",
    "charging.session.soc_slider",
    "charging.session.status",
    "charging.session.time_estimation",
    "energy.high_voltage.battery_state",
    "energy_edge_compute.graphs.charge_session_breakdown",
    "energy_edge_compute.graphs.charging_graph_global",
]


# Topics already reported as undecodable. Module-level rather than per-instance:
# decode_parallax_message is a free function and the set is small and bounded by
# the number of topics the server can push.
_WARNED_UNKNOWN_RVMS: set[str] = set()


def decode_parallax_message(
    rvm: str, payload: str, **kwargs: Any
) -> dict[str, Any] | None:
    """Decode a Parallax message payload given its RVM topic.

    Accepts the GraphQL message fields directly (rvm, payload, and optional kwargs/timestamp).
    Returns a dict of decoded fields, or None if no decoder exists for this RVM.
    """
    decoder = RVM_DECODERS.get(rvm)
    if decoder is None:
        # Once per topic, not once per message. SUBSCRIBED_RVMS only ever asks for
        # topics that have a decoder, so reaching here means the server pushed
        # something unrequested -- which it does repeatedly, at telemetry rates.
        # The warning is worth seeing; a warning per message buries the log.
        if rvm not in _WARNED_UNKNOWN_RVMS:
            _WARNED_UNKNOWN_RVMS.add(rvm)
            _LOGGER.warning(
                "Unknown Parallax RVM topic %s -- no decoder; further messages on "
                "this topic will not be logged",
                rvm,
            )
        return None
    return decoder(payload)
