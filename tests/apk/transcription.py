"""Transcribed from the Rivian Android app, class by class.

This module is DATA, not logic. Every entry was read out of a decompiled class
and is asserted against the integration in `tests/test_apk_transcription.py`,
and back against the classes themselves by `scripts/gates/f1.sh` whenever the
pre-flight copies are present (they are gitignored -- see
`docs/development/apk/REGENERATION.md`).

Source: `com.rivian.android.consumer` 3.15.0, jadx.

Deliberately **no line numbers**. Line numbers drift with every app release and
an earlier revision of this work cited several that were already wrong. Members
and field values are stable; positions are not.
"""

from __future__ import annotations

from typing import Final

# --- VehicleFeature ---------------------------------------------------------
#
# (member, featureName). TWO columns, because 19 of the 64 differ and the SERVER
# EMITS THE featureName. Gating on a member name silently never matches -- which
# is a control that is never created, with nothing logged.
VEHICLE_FEATURES: Final[tuple[tuple[str, str], ...]] = (
    ("ACTIVE_USR", "ACTV_USR"),  # member != featureName
    ("TAILGATE_CMD", "TAILGATE_CMD"),
    ("LIFTGATE_CMD", "LIFTGATE_CMD"),
    ("CHARGING_TRIP_TARGET", "CHARG_TRIP_TARGET"),  # member != featureName
    ("SAVED_LOCATIONS", "SAVED_LOCATIONS"),
    ("MOBILE_WHEEL_SWAP", "MOBILE_WHEEL_SWAP"),
    ("TAILGATE_NXT_ACT", "TAILGATE_NXT_ACT"),
    ("WINDOWS_CMD", "WINDOWS_CMD"),
    ("SIDE_BIN_NXT_ACT", "SIDE_BIN_NXT_ACT"),
    ("TRIP_NAV_PX", "TRIP_NAV_PX"),
    ("TRAILER_STATUS", "TRAILER_STATUS"),
    ("CAR_WASH_MODE", "CAR_WASH_MODE"),
    ("SCHED_DPRT", "SCHED_DPRT"),
    ("SCHED_OTA", "SCHED_OTA"),
    ("HMAC_TIMEOUT_90S", "HMAC_TIMEOUT_90S"),
    ("HLWN_25", "HLWN_25"),
    ("HLWN_25_G2", "HLWN_25_G2"),
    ("SD_CHARG_ENDS_AT", "SD_CHARG_ENDS_AT"),
    ("TESLA_NACS", "TESLA_NACS"),
    ("ACTIVE_TRIP", "ACTIVE_TRIP"),
    ("V_SATMAP", "V_SATMAP"),
    ("HEATED_SEATS_THIRD", "HEATED_SEATS_THIRD"),
    ("SCHED_DPRT_3RD_ROW", "SCHED_DPRT_3RD_ROW"),
    ("TRIP_PLANNER_TRAILERS", "TRIP_PLANNER_TRAILERS"),
    ("CONN_SUB", "CONN_SUB"),
    ("LIVE_CAM", "LIVE_CAM"),
    ("MOTION_CAM", "MOTION_CAM"),
    ("GEAR_GUARD_STREAMING", "V_GGVS"),  # member != featureName
    ("GEAR_GUARD_VIDEO_DOWNLOADING", "V_GGVD"),  # member != featureName
    ("SEARCH_PLUS", "V_SRCH_PLUS"),  # member != featureName
    ("ACTIVE_TRIP_PLUS", "V_TRIP"),  # member != featureName
    ("LOWER_PET_MODE_TEMPERATURE", "PET_MODE_LOW_TEMP"),  # member != featureName
    ("PARKED_ENERGY_MONITOR", "ENRG_MONTR_PARK"),  # member != featureName
    ("ACTIVE_ENERGY_MONITOR", "ENRG_MONTR_ACTIVE"),  # member != featureName
    ("COLD_WEATHER_BAR", "ENRG_CLD_WTHR"),  # member != featureName
    ("CHARGING_SESSION_OVER_PARALLAX", "CHARG_DATA_PX"),  # member != featureName
    ("SMART_CHARG", "SMART_CHARG"),
    ("TWO_FACTOR_DRIVE", "TWO_FACTOR_DRIVE"),
    ("KEY_FOB_2", "KEY_FOB_2"),
    ("CHARGE_PORT_DOOR_COMMAND", "CHARG_PORT_DOOR_COMMAND"),  # member != featureName
    ("HONK_AND_FLASH_COMMAND", "HONK_AND_FLASH_COMMAND"),
    ("ORPHANED_PHONE_KEY_RECOVERY_HANDLING", "ORPHANED_PHONE_KEY_RECOVERY_HANDLING"),
    ("CLM_HOLD", "CLM_HOLD"),
    ("AUTO_VENT", "AUTO_VENT"),
    ("CHARG_NTW_IONNA", "CHARG_NTW_IONNA"),
    ("CHARG_NTW_EA", "CHARG_NTW_EA"),
    ("PARALLAX_BODY_COMMAND", "PVS_BD_CMD"),  # member != featureName
    ("PARALLAX_COMFORT_COMMAND", "PVS_COMF_CMD"),  # member != featureName
    ("PARALLAX_SECURITY_COMMAND", "PVS_SEC_CMD"),  # member != featureName
    ("PARALLAX_ENERGY_COMMAND", "PVS_ENRG_CMD"),  # member != featureName
    ("PARALLAX_VEHICLE_STATE", "PX_STATE_ALL"),  # member != featureName
    ("ICE_RESTART", "ICE_RESTART"),
    ("PASSIVE_ENTRY_PROTO_V2", "PASSIVE_ENTRY_PROTO_V2"),
    ("PARALLAX_OTA_COMMAND", "PVS_OTA_CMD"),  # member != featureName
    ("VEHICLE_CONNECTIVITY_PARALLAX", "VEHICLE_CONNECTIVITY_PARALLAX"),
    ("VIDEO_DOWNLOADING_FW_SUPPORT", "VIDEO_DOWNLOADING"),  # member != featureName
    ("AUTONOMY_PLUS", "AUTONOMY_PLUS"),
    ("PIN_PROFILE", "PIN_PROFILE"),
    ("RVA", "RVA"),
    ("KEY_PAAK", "KEY_PAAK"),
    ("RVA_MEM", "RVA_MEM"),
    ("INTERIOR_CAMERA", "INTERIOR_CAMERA"),
    ("PET_COMFORT_CONTROL", "PET_COMFORT_CONTROL"),
    ("PRIV_PREF", "PRIV_PREF"),
)

VEHICLE_FEATURE_NAMES: Final[frozenset[str]] = frozenset(f for _, f in VEHICLE_FEATURES)

# --- l6e: the Parallax RVM table --------------------------------------------
#
# Fields come from the synthetic constructor's default-argument mask, not from
# the literal arguments:
#
#     isVehicleState                 = (mask & 2) ? false   : given
#     subscriptionScope              = (mask & 4) ? fug.App : given
#     needDoubleConsumerSubscription = (mask & 8) ? false   : given
#
# So `null` in the scope position means **App**, not "no scope" -- reading the
# literal would record 55 nulls and lose the one entry that differs.
#
# Five members are declared bare at the top of the class and initialised in the
# static block, because jadx could not restore the enum. They are indices 9, 19,
# 29, 39 and 49; the contiguity assertion in the test is what proves none was
# missed.
RVM_TOPICS: Final[tuple[dict[str, object], ...]] = (
    {
        "member": "PARKED_ENERGY_MONITOR",
        "index": 0,
        "rvm_name": "energy_edge_compute.graphs.parked_energy_distributions",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "CHARGING_SESSION_CHART_DATA",
        "index": 1,
        "rvm_name": "energy_edge_compute.graphs.charging_graph_global",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "CHARGING_SESSION_LIVE_DATA",
        "index": 2,
        "rvm_name": "energy_edge_compute.graphs.charge_session_breakdown",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "CHARGING_BATTERY_SOC_DATA",
        "index": 3,
        "rvm_name": "energy_edge_compute.graphs.cold_weather_soc",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "VEHICLE_GEO_FENCES",
        "index": 4,
        "rvm_name": "geofence.geofence_service.favoriteGeofences",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "OTA_SCHEDULE_CONFIGURATION",
        "index": 5,
        "rvm_name": "ota.user_schedule.ota_config",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "OTA_STATE",
        "index": 6,
        "rvm_name": "ota.ota_state.vehicle_ota_state",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "GEAR_GUARD_CONSENTS",
        "index": 7,
        "rvm_name": "gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "GEAR_GUARD_DAILY_LIMITS",
        "index": 8,
        "rvm_name": "gearguard_streaming.privacy.gearguard_streaming_daily_limit",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "VEHICLE_WHEELS",
        "index": 9,
        "rvm_name": "vehicle.wheels.vehicle_wheels",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "TRIP_INFO",
        "index": 10,
        "rvm_name": "navigation.navigation_service.trip_info",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "TRIP_PROGRESS",
        "index": 11,
        "rvm_name": "navigation.navigation_service.trip_progress",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "CLIMATE_HOLD_SETTING",
        "index": 12,
        "rvm_name": "comfort.cabin.climate_hold_setting",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "CABIN_VENTILATION_SETTING",
        "index": 13,
        "rvm_name": "comfort.cabin.cabin_ventilation_setting",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "PASSIVE_ENTRY_SETTING",
        "index": 14,
        "rvm_name": "vehicle_access.passive_entry.passive_entry",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "CHARGING_SCHEDULE_TIME_WINDOW",
        "index": 15,
        "rvm_name": "charging.schedule.time_window",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "PASSIVE_ENTRY_STATUS",
        "index": 16,
        "rvm_name": "vehicle_access.state.passive_entry",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "DEVICE_TABLE_VAS_KEYPER_DEVICES",
        "index": 17,
        "rvm_name": "device_table.vas_keyper.devices",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "PET_CAM_SNAPSHOT",
        "index": 18,
        "rvm_name": "secure_file_transfer.pet_snapshot.secure_file",
        "is_vehicle_state": False,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "BODY_LOCKS_STATES",
        "index": 19,
        "rvm_name": "body.locks.states",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "BODY_TRAILER_STATES",
        "index": 20,
        "rvm_name": "body.trailer.state",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "BODY_CLOSURES_STATES",
        "index": 21,
        "rvm_name": "body.closures.states",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "BODY_WINDOW_STATES",
        "index": 22,
        "rvm_name": "body.windows.states",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "DYNAMICS_VEHICLE_DRIVE_MODE",
        "index": 23,
        "rvm_name": "dynamics.vehicle.drive_mode",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "DYNAMICS_VEHICLE_GEAR",
        "index": 24,
        "rvm_name": "dynamics.vehicle.gear",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "DYNAMICS_VEHICLE_GNSS",
        "index": 25,
        "rvm_name": "dynamics.vehicle.gnss",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "DYNAMICS_VEHICLE_KNOWN_LOCATION",
        "index": 26,
        "rvm_name": "dynamics.vehicle.location",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "DYNAMICS_VEHICLE_ODOMETER",
        "index": 27,
        "rvm_name": "dynamics.vehicle.odometer",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "DYNAMICS_VEHICLE_RANGE",
        "index": 28,
        "rvm_name": "dynamics.vehicle.range",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "DYNAMICS_TIRES_STATE",
        "index": 29,
        "rvm_name": "dynamics.tires.state",
        "is_vehicle_state": False,
        "subscription_scope": "Feature",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "ENERGY_HIGH_VOLTAGE_BATTERY_STATE",
        "index": 30,
        "rvm_name": "energy.high_voltage.battery_state",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "ENERGY_HIGH_VOLTAGE_BATTERY_CHARACTERISTICS",
        "index": 31,
        "rvm_name": "energy.high_voltage.battery_characteristics",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "CHARGING_SESSION_STATUS",
        "index": 32,
        "rvm_name": "charging.session.status",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "CHARGING_SESSION_TIME_ESTIMATION",
        "index": 33,
        "rvm_name": "charging.session.time_estimation",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "CHARGING_SESSION_NOTIFICATION",
        "index": 34,
        "rvm_name": "charging.session.notification",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "CHARGING_SESSION_SOC_SLIDER",
        "index": 35,
        "rvm_name": "charging.session.soc_slider",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "CHARGING_SESSION_TRIP_TARGET",
        "index": 36,
        "rvm_name": "charging.session.trip_target",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "CHARGING_SESSION_REMOTE_COMMAND",
        "index": 37,
        "rvm_name": "charging.session.remote_command",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "ENERGY_LOW_VOLTAGE_BATTERY_STATE",
        "index": 38,
        "rvm_name": "energy.low_voltage.battery_state",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "SECURITY_ALARM_STATE",
        "index": 39,
        "rvm_name": "security.alarm.state",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "SECURITY_IMMOBILIZER_STATE",
        "index": 40,
        "rvm_name": "security.access.immobilizer_state",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "SECURITY_VIDEO_MONITORING_STATE",
        "index": 41,
        "rvm_name": "security.video_monitoring.state",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "SECURITY_BTM_DIAGNOSIS",
        "index": 42,
        "rvm_name": "security.access.btm",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "SECURITY_PASSIVE_ENTRY_DEBUG",
        "index": 43,
        "rvm_name": "security.access.passive_entry_debug",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "SECURITY_VAS_FAULT",
        "index": 44,
        "rvm_name": "security.access.vas_fault",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "COMFORT_USER_MODES_STATE",
        "index": 45,
        "rvm_name": "comfort.user_modes.state",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "COMFORT_CABIN_PET_MODE_STATUS",
        "index": 46,
        "rvm_name": "comfort.cabin.pet_mode_status",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "COMFORT_CABIN_PRECONDITIONING_STATUS",
        "index": 47,
        "rvm_name": "comfort.cabin.cabin_preconditioning_status",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "CLIMATE_HOLD_STATUS",
        "index": 48,
        "rvm_name": "comfort.cabin.climate_hold_status",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": True,
    },
    {
        "member": "COMFORT_CABIN_TEMPERATURES",
        "index": 49,
        "rvm_name": "comfort.cabin.cabin_temperatures",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "COMFORT_CABIN_DEFROST_DEFOG_STATUS",
        "index": 50,
        "rvm_name": "comfort.cabin.defrost_defog_status",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "COMFORT_CABIN_SEAT_CONDITIONING_STATUS",
        "index": 51,
        "rvm_name": "comfort.cabin.seat_conditioning_status",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "COMFORT_CABIN_HVAC_SETTINGS_STATUS",
        "index": 52,
        "rvm_name": "comfort.cabin.hvac_settings_status",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "VEHICLE_POWER_STATE",
        "index": 53,
        "rvm_name": "vehicle.power.state",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "OTA_DEPLOYMENT_STATE",
        "index": 54,
        "rvm_name": "ota.deployment.state",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
    {
        "member": "VEHICLE_NETWORK",
        "index": 55,
        "rvm_name": "vehicle.network.state",
        "is_vehicle_state": True,
        "subscription_scope": "App",
        "need_double_consumer_subscription": False,
    },
)

RVM_NAMES: Final[frozenset[str]] = frozenset(r["rvm_name"] for r in RVM_TOPICS)

# --- VASCommand -------------------------------------------------------------
#
# `wrapper` is which factory builds the subclass's cloudData:
#
#   "cloud"   generateCloudDataWrapper -- appName defaults to "rshell".
#   "invalid" generateInvalidCloudDataWrapper -- appName is "". An APP-SIDE
#             ROUTING choice, and a weaker signal than the one the tonneau
#             already falsified: it does NOT establish the cloud refuses these.
#   None      no cloudData at all (ParallaxCommand and the three Pause*).
#
# "Sendable" is defined here rather than assumed: wrapper == "cloud" and not the
# INVALID_COMMAND sentinel. That is 45 of 57.
VAS_COMMANDS: Final[tuple[dict[str, object], ...]] = (
    {
        "cls": "CabinPreconditioningSetTemperature",
        "wrapper": "cloud",
        "command": "CABIN_PRECONDITIONING_SET_TEMP",
    },
    {
        "cls": "CloseAllWindows",
        "wrapper": "cloud",
        "command": "CLOSE_ALL_WINDOWS",
    },
    {
        "cls": "CloseChargePortDoor",
        "wrapper": "cloud",
        "command": "CLOSE_CHARGE_PORT_DOOR",
    },
    {
        "cls": "CloseFrunk",
        "wrapper": "cloud",
        "command": "CLOSE_FRUNK",
    },
    {
        "cls": "CloseLiftgate",
        "wrapper": "cloud",
        "command": "CLOSE_LIFTGATE",
    },
    {
        "cls": "CloseTonneauCover",
        "wrapper": "cloud",
        "command": "CLOSE_TONNEAU_COVER",
    },
    {
        "cls": "DisableCabinPreconditioning",
        "wrapper": "cloud",
        "command": "VEHICLE_CABIN_PRECONDITION_DISABLE",
    },
    {
        "cls": "DisableClimateHold",
        "wrapper": "cloud",
        "command": "CLIMATE_HOLD_OFF",
    },
    {
        "cls": "DisableGearGuard",
        "wrapper": "cloud",
        "command": "DISABLE_GEAR_GUARD",
    },
    {
        "cls": "DisableGearGuardVideo",
        "wrapper": "cloud",
        "command": "DISABLE_GEAR_GUARD_VIDEO",
    },
    {
        "cls": "DisablePetComfort",
        "wrapper": "invalid",
        "command": "PET_COMFORT_OFF",
    },
    {
        "cls": "EnableCabinPreconditioning",
        "wrapper": "cloud",
        "command": "VEHICLE_CABIN_PRECONDITION_ENABLE",
    },
    {
        "cls": "EnableClimateHold",
        "wrapper": "cloud",
        "command": "CLIMATE_HOLD_ON",
    },
    {
        "cls": "EnableGearGuard",
        "wrapper": "cloud",
        "command": "ENABLE_GEAR_GUARD",
    },
    {
        "cls": "EnableGearGuardVideo",
        "wrapper": "cloud",
        "command": "ENABLE_GEAR_GUARD_VIDEO",
    },
    {
        "cls": "EnablePetComfort",
        "wrapper": "invalid",
        "command": "PET_COMFORT_ON",
    },
    {
        "cls": "FlashLights",
        "wrapper": "cloud",
        "command": "FLASH_EXTERNAL_LIGHTS",
    },
    {
        "cls": "HonkHorn",
        "wrapper": "cloud",
        "command": "ACTIVATE_EXTERNAL_SOUND",
    },
    {
        "cls": "InstallNow",
        "wrapper": "cloud",
        "command": "OTA_INSTALL_NOW_ACKNOWLEDGE",
    },
    {
        "cls": "InvalidCommand",
        "wrapper": "cloud",
        "command": "INVALID_COMMAND",
    },
    {
        "cls": "LockAllClosuresFeedback",
        "wrapper": "cloud",
        "command": "LOCK_ALL_CLOSURES_FEEDBACK",
    },
    {
        "cls": "OpenAllWindows",
        "wrapper": "cloud",
        "command": "OPEN_ALL_WINDOWS",
    },
    {
        "cls": "OpenChargePortDoor",
        "wrapper": "cloud",
        "command": "OPEN_CHARGE_PORT_DOOR",
    },
    {
        "cls": "OpenFrunk",
        "wrapper": "cloud",
        "command": "OPEN_FRUNK",
    },
    {
        "cls": "OpenLiftgate",
        "wrapper": "cloud",
        "command": "OPEN_LIFTGATE",
    },
    {
        "cls": "OpenLiftgateUnlatchTailgate",
        "wrapper": "cloud",
        "command": "OPEN_LIFTGATE_UNLATCH_TAILGATE",
    },
    {
        "cls": "OpenTonneauCover",
        "wrapper": "cloud",
        "command": "OPEN_TONNEAU_COVER",
    },
    {
        "cls": "ParallaxCommand",
        "wrapper": None,
        "command": None,
    },
    {
        "cls": "PauseFrunk",
        "wrapper": None,
        "command": None,
    },
    {
        "cls": "PauseLiftgate",
        "wrapper": None,
        "command": None,
    },
    {
        "cls": "PauseTonneauCover",
        "wrapper": None,
        "command": None,
    },
    {
        "cls": "ReleaseLeftSideBin",
        "wrapper": "cloud",
        "command": "RELEASE_LEFT_SIDE_BIN",
    },
    {
        "cls": "ReleaseRightSideBin",
        "wrapper": "cloud",
        "command": "RELEASE_RIGHT_SIDE_BIN",
    },
    {
        "cls": "SetCabinHvacDefrostDefog",
        "wrapper": "cloud",
        "command": "CABIN_HVAC_DEFROST_DEFOG",
    },
    {
        "cls": "SetCabinHvacLeftFrontSeatHeat",
        "wrapper": "cloud",
        "command": "CABIN_HVAC_LEFT_SEAT_HEAT",
    },
    {
        "cls": "SetCabinHvacLeftSeatVent",
        "wrapper": "cloud",
        "command": "CABIN_HVAC_LEFT_SEAT_VENT",
    },
    {
        "cls": "SetCabinHvacRearLeftSeatHeat",
        "wrapper": "cloud",
        "command": "CABIN_HVAC_REAR_LEFT_SEAT_HEAT",
    },
    {
        "cls": "SetCabinHvacRearRightSeatHeat",
        "wrapper": "cloud",
        "command": "CABIN_HVAC_REAR_RIGHT_SEAT_HEAT",
    },
    {
        "cls": "SetCabinHvacRightFrontSeatHeat",
        "wrapper": "cloud",
        "command": "CABIN_HVAC_RIGHT_SEAT_HEAT",
    },
    {
        "cls": "SetCabinHvacRightSeatVent",
        "wrapper": "cloud",
        "command": "CABIN_HVAC_RIGHT_SEAT_VENT",
    },
    {
        "cls": "SetCabinHvacSteeringHeat",
        "wrapper": "cloud",
        "command": "CABIN_HVAC_STEERING_HEAT",
    },
    {
        "cls": "SetCabinHvacThirdRowLeftSeatHeat",
        "wrapper": "cloud",
        "command": "CABIN_HVAC_3RD_ROW_REAR_LEFT_SEAT_HEAT",
    },
    {
        "cls": "SetCabinHvacThirdRowRightSeatHeat",
        "wrapper": "cloud",
        "command": "CABIN_HVAC_3RD_ROW_REAR_RIGHT_SEAT_HEAT",
    },
    {
        "cls": "SetChargingLimit",
        "wrapper": "cloud",
        "command": "CHARGING_LIMITS",
    },
    {
        "cls": "StartCharging",
        "wrapper": "cloud",
        "command": "START_CHARGING",
    },
    {
        "cls": "StartGearGuardMasterSession",
        "wrapper": "cloud",
        "command": "START_GEAR_GUARD_MASTER_SESSION",
    },
    {
        "cls": "StartVideoDownloadingSession",
        "wrapper": "invalid",
        "command": "START_VIDEO_DOWNLOADING_SESSION",
    },
    {
        "cls": "StopCharging",
        "wrapper": "cloud",
        "command": "STOP_CHARGING",
    },
    {
        "cls": "TurnPanicOff",
        "wrapper": "cloud",
        "command": "PANIC_OFF",
    },
    {
        "cls": "TurnPanicOn",
        "wrapper": "cloud",
        "command": "PANIC_ON",
    },
    {
        "cls": "TwoFactorDriveAllow",
        "wrapper": "invalid",
        "command": "TWO_FACTOR_DRIVE_ALLOW",
    },
    {
        "cls": "TwoFactorDriveDeny",
        "wrapper": "invalid",
        "command": "TWO_FACTOR_DRIVE_DENY",
    },
    {
        "cls": "TwoFactorDriveDisable",
        "wrapper": "invalid",
        "command": "TWO_FACTOR_DRIVE_DISABLE",
    },
    {
        "cls": "TwoFactorDriveEnable",
        "wrapper": "invalid",
        "command": "TWO_FACTOR_DRIVE_ENABLE",
    },
    {
        "cls": "UnlatchTailgate",
        "wrapper": "cloud",
        "command": "OPEN_TAILGATE",
    },
    {
        "cls": "UnlockAllClosures",
        "wrapper": "cloud",
        "command": "UNLOCK_ALL_CLOSURES",
    },
    {
        "cls": "WakeVehicle",
        "wrapper": "cloud",
        "command": "WAKE_VEHICLE",
    },
)

SENTINEL_COMMAND: Final[str] = "INVALID_COMMAND"

SENDABLE_COMMANDS: Final[frozenset[str]] = frozenset(
    str(v["command"])
    for v in VAS_COMMANDS
    if v["wrapper"] == "cloud" and v["command"] not in (None, SENTINEL_COMMAND)
)

# The seven built with generateInvalidCloudDataWrapper. Recorded, NOT deprecated:
# the tonneau result shows the server accepts more than the app asks for, so this
# is a list to test, not a list to delete.
INVALID_WRAPPER_COMMANDS: Final[frozenset[str]] = frozenset(
    str(v["command"]) for v in VAS_COMMANDS if v["wrapper"] == "invalid"
)

# --- VASCommandKt -----------------------------------------------------------
#
# 24 constants. 18 are command NAMES; the other 6 are parameter keys and
# defaults ("level", "SOC_limit", "HVAC_set_temp", "camera", "left", "").
VAS_COMMAND_KT_CONSTANTS: Final[tuple[tuple[str, str, str], ...]] = (
    (
        "private",
        "CABIN_HVAC_3RD_ROW_REAR_LEFT_SEAT_HEAT",
        "CABIN_HVAC_3RD_ROW_REAR_LEFT_SEAT_HEAT",
    ),
    (
        "private",
        "CABIN_HVAC_3RD_ROW_REAR_RIGHT_SEAT_HEAT",
        "CABIN_HVAC_3RD_ROW_REAR_RIGHT_SEAT_HEAT",
    ),
    ("private", "CABIN_HVAC_DEFROST_DEFOG", "CABIN_HVAC_DEFROST_DEFOG"),
    ("private", "CABIN_HVAC_LEFT_SEAT_HEAT", "CABIN_HVAC_LEFT_SEAT_HEAT"),
    ("private", "CABIN_HVAC_LEFT_SEAT_VENT", "CABIN_HVAC_LEFT_SEAT_VENT"),
    ("private", "CABIN_HVAC_PARAM", "level"),
    ("private", "CABIN_HVAC_REAR_LEFT_SEAT_HEAT", "CABIN_HVAC_REAR_LEFT_SEAT_HEAT"),
    ("private", "CABIN_HVAC_REAR_RIGHT_SEAT_HEAT", "CABIN_HVAC_REAR_RIGHT_SEAT_HEAT"),
    ("private", "CABIN_HVAC_RIGHT_SEAT_HEAT", "CABIN_HVAC_RIGHT_SEAT_HEAT"),
    ("private", "CABIN_HVAC_RIGHT_SEAT_VENT", "CABIN_HVAC_RIGHT_SEAT_VENT"),
    ("private", "CABIN_HVAC_STEERING_HEAT", "CABIN_HVAC_STEERING_HEAT"),
    ("private", "CAMERA", "camera"),
    ("private", "CHARGING_LIMIT_PARAM", "SOC_limit"),
    (
        "public",
        "CLOUD_CABIN_PRECONDITION_SET_TEMPERATURE",
        "CABIN_PRECONDITIONING_SET_TEMP",
    ),
    ("public", "CLOUD_GEAR_GUARD_VIDEO_DISABLE", "DISABLE_GEAR_GUARD_VIDEO"),
    ("public", "CLOUD_GEAR_GUARD_VIDEO_ENABLE", "ENABLE_GEAR_GUARD_VIDEO"),
    ("private", "CLOUD_SET_CHARGING_LIMIT", "CHARGING_LIMITS"),
    ("private", "CLOUD_START_CHARGING", "START_CHARGING"),
    (
        "public",
        "CLOUD_START_GEAR_GUARD_MASTER_SESSION",
        "START_GEAR_GUARD_MASTER_SESSION",
    ),
    ("private", "CLOUD_STOP_CHARGING", "STOP_CHARGING"),
    ("public", "DEFAULT_MOTION_CAMERA", "left"),
    ("public", "EMPTY_DEVICE_IDENTITY", ""),
    (
        "public",
        "INVALID_CLOUD_START_VIDEO_DOWNLOADING_SESSION",
        "START_VIDEO_DOWNLOADING_SESSION",
    ),
    ("public", "PRECONDITIONING_TEMPERATURE_PARAM", "HVAC_set_temp"),
)

# The six that are parameters or defaults rather than command names.
VAS_COMMAND_KT_NON_NAMES: Final[frozenset[str]] = frozenset(
    {
        "CABIN_HVAC_PARAM",
        "CAMERA",
        "CHARGING_LIMIT_PARAM",
        "DEFAULT_MOTION_CAMERA",
        "EMPTY_DEVICE_IDENTITY",
        "PRECONDITIONING_TEMPERATURE_PARAM",
    }
)

VAS_COMMAND_KT_NAMES: Final[frozenset[str]] = frozenset(
    value
    for _, name, value in VAS_COMMAND_KT_CONSTANTS
    if name not in VAS_COMMAND_KT_NON_NAMES
)
