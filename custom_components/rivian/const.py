"""Rivian (Unofficial)"""

from __future__ import annotations

from typing import Any, Final

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    EntityCategory,
    UnitOfDataRate,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)

from .data_classes import (
    RivianBinarySensorEntityDescription,
    RivianSensorEntityDescription,
)

NAME = "Rivian (Unofficial)"
DOMAIN = "rivian"
VERSION = "1.6.0-beta15"
ISSUE_URL = "https://github.com/bretterer/home-assistant-rivian/issues"

# Attributes
ATTR_API = "api"
ATTR_COORDINATOR = "coordinator"
ATTR_SUPPORTED_FEATURES = "supported_features"
ATTR_USER = "user"
ATTR_VEHICLE = "vehicle"
ATTR_WALLBOX = "wallbox"

# Config properties
CONF_ACCESS_TOKEN = "access_token"
CONF_OTP = "otp"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_USER_SESSION_TOKEN = "user_session_token"
CONF_VEHICLE_CONTROL = "vehicle_control"
CONF_VEHICLE_IMAGE_STYLE = "vehicle_image_style"

# Event names
EVENT_COMMAND_INITIATED = f"{DOMAIN}_command_initiated"
EVENT_COMMAND_SUCCESS = f"{DOMAIN}_command_success"
EVENT_COMMAND_FAILED = f"{DOMAIN}_command_failed"

IMAGE_STYLE_CEL = "cel"
IMAGE_STYLE_PHOTO = "photo"
IMAGE_STYLE_NONE = "none"

LOCK_STATE_ENTITIES = {
    "closureFrunkLocked",
    "closureLiftgateLocked",
    "closureSideBinLeftLocked",
    "closureSideBinRightLocked",
    "closureTailgateLocked",
    "closureTonneauLocked",
    "doorFrontLeftLocked",
    "doorFrontRightLocked",
    "doorRearLeftLocked",
    "doorRearRightLocked",
}

DOOR_STATE_ENTITIES = {
    "doorFrontLeftClosed",
    "doorFrontRightClosed",
    "doorRearLeftClosed",
    "doorRearRightClosed",
}

CLOSURE_STATE_ENTITIES = {
    "closureFrunkClosed",
    "closureLiftgateClosed",
    "closureSideBinLeftClosed",
    "closureSideBinRightClosed",
    "closureTailgateClosed",
    "closureTonneauClosed",
}

# Compared as str(value).lower() in coordinator.py, so entries are lowercase.
# "sna" is the vehicle's own abbreviation for signal-not-available: a live boot
# showed the rear seat heating sensors reporting a literal "SNA", which this set
# was meant to suppress and did not, because it only listed the long form.
INVALID_SENSOR_STATES = {"fault", "signal_not_available", "sna", "undefined"}


DRIVE_MODE_MAP = {
    "everyday": "All-Purpose",
    "sport": "Sport",
    "distance": "Conserve",
    "winter": "Snow",
    "towing": "Towing",
    "off_road_auto": "All-Terrain",
    "off_road_sand": "Soft Sand",
    "off_road_rocks": "Rock Crawl",
    "off_road_sport_auto": "Rally",
    "off_road_sport_drift": "Drift",
}

GEAR_STATUS_MAP = {
    "park": "Park",
    "drive": "Drive",
    "neutral": "Neutral",
    "reverse": "Reverse",
    "low": "Low",
    "autonomous": "Autonomous",
    "not_defined": "Not Defined",
}


def _to_pascal_case(value: str) -> str:
    """Convert snake_case to PascalCase.

    Examples:
        charging_active -> ChargingActive
        signal_not_available -> SignalNotAvailable
    """
    if not value:
        return ""
    return "".join(word.capitalize() for word in value.split("_"))


def _to_title_case(value: str) -> str:
    """Convert snake_case to Title Case with spaces.

    Examples:
        trailer_present -> Trailer Present
        not_defined -> Not Defined
    """
    if not value:
        return ""
    return value.replace("_", " ").title()


def _charger_status_transform(value: str) -> str:
    """Transform charger status API values to enum names.

    Examples:
        chrgr_sts_not_connected -> Not Connected
        chrgr_sts_connected_no_chrg -> Connected No Chrg
    """
    if not value:
        return "NA"
    # Handle the chrgr_sts_ prefix
    if value.startswith("chrgr_sts_"):
        value = value.replace("chrgr_sts_", "")
    return _to_title_case(value)


SENSORS: Final[dict[str, tuple[RivianSensorEntityDescription, ...]]] = {
    "R1": (
        RivianSensorEntityDescription(
            key="active_driver_name",
            translation_key="active_driver_name",
            field="activeDriverName",
        ),
        RivianSensorEntityDescription(
            key="gnss_altitude",
            translation_key="gnss_altitude",
            field="gnssAltitude",
            icon="mdi:altimeter",
            device_class=SensorDeviceClass.DISTANCE,
            native_unit_of_measurement=UnitOfLength.METERS,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
        ),
        RivianSensorEntityDescription(
            key="alarm_sound_status",
            translation_key="alarm_sound_status",
            field="alarmSoundStatus",
            icon="mdi:alarm-light",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Active",
                "Inactive",
                "Signal Not Available",
            ],
            value_lambda=lambda v: (
                "Active"
                if v == "true"
                else "Inactive"
                if v == "false"
                else _to_title_case(v)
                if v
                else "Inactive"
            ),
        ),
        RivianSensorEntityDescription(
            key="battery_hv_thermal_event",
            translation_key="battery_hv_thermal_event",
            field="batteryHvThermalEvent",
            icon="mdi:battery-alert",
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="battery_hv_thermal_event_propagation",
            translation_key="battery_hv_thermal_event_propagation",
            field="batteryHvThermalEventPropagation",
            icon="mdi:battery-alert",
        ),
        RivianSensorEntityDescription(
            key="battery_level",
            translation_key="battery_level",
            field="batteryLevel",
            device_class=SensorDeviceClass.BATTERY,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
        ),
        RivianSensorEntityDescription(
            key="battery_limit",
            translation_key="battery_limit",
            field="batteryLimit",
            icon="mdi:battery-charging-80",
            native_unit_of_measurement=PERCENTAGE,
        ),
        RivianSensorEntityDescription(
            key="battery_capacity",
            translation_key="battery_capacity",
            field="batteryCapacity",
            device_class=SensorDeviceClass.ENERGY_STORAGE,
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:battery-check",
            suggested_display_precision=2,
        ),
        RivianSensorEntityDescription(
            key="gnss_bearing",
            translation_key="gnss_bearing",
            field="gnssBearing",
            icon="mdi:compass",
            native_unit_of_measurement=DEGREE,
            suggested_display_precision=0,
        ),
        RivianSensorEntityDescription(
            key="brake_fluid_low",
            translation_key="brake_fluid_low",
            field="brakeFluidLow",
            icon="mdi:car-brake-fluid-level",
        ),
        RivianSensorEntityDescription(
            key="cabin_climate_driver_temperature",
            translation_key="cabin_climate_driver_temperature",
            field="cabinClimateDriverTemperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            suggested_display_precision=1,
        ),
        RivianSensorEntityDescription(
            key="defrost_defog_status",
            translation_key="defrost_defog_status",
            field="defrostDefogStatus",
            icon="mdi:car-defrost-front",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Unknown",
                "Fault",
                "Defog",
                "Defrost",
                "Off",
            ],
            value_lambda=lambda v: _to_title_case(v) if v else "Unknown",
        ),
        RivianSensorEntityDescription(
            key="cabin_climate_interior_temperature",
            translation_key="cabin_climate_interior_temperature",
            field="cabinClimateInteriorTemperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
        ),
        RivianSensorEntityDescription(
            key="cabin_preconditioning_type",
            translation_key="cabin_preconditioning_type",
            field="cabinPreconditioningType",
            icon="mdi:thermostat",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "None",
                "User Selected",
                "Screen Protection",
                "Scheduled",
                "Auto Cabin Ventilation",
            ],
            value_lambda=lambda v: v.replace("_", " ").title() if v else "None",
        ),
        RivianSensorEntityDescription(
            key="cabin_preconditioning_status",
            translation_key="cabin_preconditioning_status",
            field="cabinPreconditioningStatus",
            icon="mdi:thermostat",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Undefined",
                "Initiate",
                "Active",
                "Active Warning",
                "Complete Maintain",
                "Timeout Complete",
                "Error SOC Low",
                "Error System Fault",
                "Timeout Temperature Not Achieved",
                "Unavailable",
                # decode_preconditioning (rivian_client/parallax.py) emits exactly
                # "active" | "initiate" | "off". The rest of this list is the
                # GraphQL vocabulary; "Off" was missing, so a live boot logged
                # "provides state value 'Off', which is not in the list of known
                # options" on every start and appended it at runtime.
                "Off",
            ],
            value_lambda=lambda v: _to_title_case(v) if v else "Undefined",
        ),
        RivianSensorEntityDescription(
            key="seat_front_left_heat",
            translation_key="seat_front_left_heat",
            field="seatFrontLeftHeat",
            icon="mdi:car-seat-heater",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Off",
                "Level 1",
                "Level 2",
                "Level 3",
            ],
            value_lambda=lambda v: v.replace("_", " ") if v else "Off",
        ),
        RivianSensorEntityDescription(
            key="seat_front_left_vent",
            translation_key="seat_front_left_vent",
            field="seatFrontLeftVent",
            icon="mdi:car-seat-cooler",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Off",
                "Level 1",
                "Level 2",
                "Level 3",
            ],
            value_lambda=lambda v: v.replace("_", " ") if v else "Off",
        ),
        RivianSensorEntityDescription(
            key="seat_front_right_heat",
            translation_key="seat_front_right_heat",
            field="seatFrontRightHeat",
            icon="mdi:car-seat-heater",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Off",
                "Level 1",
                "Level 2",
                "Level 3",
            ],
            value_lambda=lambda v: v.replace("_", " ") if v else "Off",
        ),
        RivianSensorEntityDescription(
            key="seat_front_right_vent",
            translation_key="seat_front_right_vent",
            field="seatFrontRightVent",
            icon="mdi:car-seat-cooler",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Off",
                "Level 1",
                "Level 2",
                "Level 3",
            ],
            value_lambda=lambda v: v.replace("_", " ") if v else "Off",
        ),
        RivianSensorEntityDescription(
            key="charger_derate_status",
            translation_key="charger_derate_status",
            field="chargerDerateStatus",
            icon="mdi:ev-station",
        ),
        RivianSensorEntityDescription(
            key="charger_state",
            translation_key="charger_state",
            field="chargerState",
            icon="mdi:ev-station",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Waiting On Charger",
                "Charging Ready",
                "Charging Active",
                "Charging Connecting",
                "Charging Complete",
                "Charging Stopped By User",
                "Charging Stopped By Station",
                "Charging Scheduled",
                "Charging Vehicle Error",
                "Charging Station Error",
                "Charging Payment Error",
                "Charging Cert Error",
                "Charging Error AC Adapter Used On DC",
                "Charging Error DC Adapter Used On AC",
                "Charging Error Incompatible Charger",
                "Charging Error Not Ready Or Incompatible Charger",
                "Charging SD Compensation",
                "Signal Not Available",
            ],
            value_lambda=lambda v: _to_title_case(v) if v else "Signal Not Available",
        ),
        RivianSensorEntityDescription(
            key="charger_status",
            translation_key="charger_status",
            field="chargerStatus",
            icon="mdi:ev-plug-type2",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "NA",
                "Not Connected",
                "Connected No Chrg",
                "Connected Charging",
                "Evse Exit",
                "User Exit",
                "Eoc Met",
                "Fault",
            ],
            value_lambda=lambda v: _charger_status_transform(v),
        ),
        RivianSensorEntityDescription(
            key="distance_to_empty",
            translation_key="distance_to_empty",
            field="distanceToEmpty",
            icon="mdi:map-marker-distance",
            device_class=SensorDeviceClass.DISTANCE,
            native_unit_of_measurement=UnitOfLength.KILOMETERS,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
        ),
        RivianSensorEntityDescription(
            key="drive_mode",
            translation_key="drive_mode",
            field="driveMode",
            icon="mdi:car-speed-limiter",
            device_class=SensorDeviceClass.ENUM,
            options=list(DRIVE_MODE_MAP.values()),
            value_lambda=lambda v: DRIVE_MODE_MAP.get(v, v),
        ),
        RivianSensorEntityDescription(
            key="gear_status",
            translation_key="gear_status",
            field="gearStatus",
            icon="mdi:car-shift-pattern",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Not Defined",
                "Park",
                "Reverse",
                "Neutral",
                "Drive",
                "Low",
                "Autonomous",
            ],
            value_lambda=lambda v: GEAR_STATUS_MAP.get(
                v.lower() if v else "", "Not Defined"
            ),
        ),
        RivianSensorEntityDescription(
            key="trailer_status",
            translation_key="trailer_status",
            field="trailerStatus",
            icon="mdi:truck-trailer",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Trailer Not Present",
                "Trailer Present",
                "Trailer Present With Brakes",
                "Trailer Invalid",
            ],
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="gear_guard_video_mode",
            translation_key="gear_guard_video_mode",
            field="gearGuardVideoMode",
            icon="mdi:cctv",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Away From Home",
                "Everywhere",
            ],
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="gear_guard_video_status",
            translation_key="gear_guard_video_status",
            field="gearGuardVideoStatus",
            icon="mdi:cctv",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Disabled",
                "Enabled",
                "Engaged",
            ],
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        # DISABLED, deliberately. Populated (reads `true`) and not duplicated by
        # anything, unlike the ota_* block below -- but it is a one-time consent
        # flag that changes once in the life of the vehicle. Recorded here because
        # it previously carried no reason at all.
        RivianSensorEntityDescription(
            key="gear_guard_video_terms_accepted",
            translation_key="gear_guard_video_terms_accepted",
            field="gearGuardVideoTermsAccepted",
            icon="mdi:cctv",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        # The twelve ota_* version-component sensors below ship DISABLED because
        # update.rivian_* already carries all of it and carries it better:
        # installed_version, latest_version, the year/week/number attributes, a
        # release-notes URL and an install button, with device_class=update. See
        # update.py:71-93. Enabling these would add twelve worse duplicates of one
        # good entity.
        #
        # They are populated -- otaCurrentVersion reads 2026.23.0 on the owner's
        # R1T -- so "no data" is NOT the reason, and the reason was previously
        # written down nowhere at all, which is what made this need investigating.
        RivianSensorEntityDescription(
            key="ota_available_version",
            translation_key="ota_available_version",
            field="otaAvailableVersion",
            icon="mdi:package",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_available_version_git_hash",
            translation_key="ota_available_version_git_hash",
            field="otaAvailableVersionGitHash",
            icon="mdi:source-commit",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_available_version_number",
            translation_key="ota_available_version_number",
            field="otaAvailableVersionNumber",
            icon="mdi:numeric",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_available_version_week",
            translation_key="ota_available_version_week",
            field="otaAvailableVersionWeek",
            icon="mdi:calendar-week",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_available_version_year",
            translation_key="ota_available_version_year",
            field="otaAvailableVersionYear",
            icon="mdi:calendar",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_current_status",
            translation_key="ota_current_status",
            field="otaCurrentStatus",
            icon="mdi:package",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="ota_current_version",
            translation_key="ota_current_version",
            field="otaCurrentVersion",
            icon="mdi:package",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_current_version_git_hash",
            translation_key="ota_current_version_git_hash",
            field="otaCurrentVersionGitHash",
            icon="mdi:source-commit",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_current_version_number",
            translation_key="ota_current_version_number",
            field="otaCurrentVersionNumber",
            icon="mdi:numeric",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_current_version_week",
            translation_key="ota_current_version_week",
            field="otaCurrentVersionWeek",
            icon="mdi:calendar-week",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_current_version_year",
            translation_key="ota_current_version_year",
            field="otaCurrentVersionYear",
            icon="mdi:calendar",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_download_progress",
            translation_key="ota_download_progress",
            field="otaDownloadProgress",
            icon="mdi:progress-download",
            entity_category=EntityCategory.DIAGNOSTIC,
            native_unit_of_measurement=PERCENTAGE,
        ),
        RivianSensorEntityDescription(
            key="ota_install_duration",
            translation_key="ota_install_duration",
            field="otaInstallDuration",
            icon="mdi:wrench-clock",
            device_class=SensorDeviceClass.DURATION,
            entity_category=EntityCategory.DIAGNOSTIC,
            native_unit_of_measurement=UnitOfTime.MINUTES,
        ),
        RivianSensorEntityDescription(
            key="ota_install_progress",
            translation_key="ota_install_progress",
            field="otaInstallProgress",
            icon="mdi:progress-clock",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            native_unit_of_measurement=PERCENTAGE,
        ),
        RivianSensorEntityDescription(
            key="ota_install_ready",
            translation_key="ota_install_ready",
            field="otaInstallReady",
            icon="mdi:progress-check",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_lambda=lambda v: v.replace("_", " ").title().replace("Ota", "OTA"),
        ),
        RivianSensorEntityDescription(
            key="ota_install_time",
            translation_key="ota_install_time",
            field="otaInstallTime",
            icon="mdi:clock",
            device_class=SensorDeviceClass.DURATION,
            entity_category=EntityCategory.DIAGNOSTIC,
            native_unit_of_measurement=UnitOfTime.MINUTES,
        ),
        RivianSensorEntityDescription(
            key="ota_install_type",
            translation_key="ota_install_type",
            field="otaInstallType",
            icon="mdi:package",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="ota_status",
            translation_key="ota_status",
            field="otaStatus",
            icon="mdi:package",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Idle",
                "Ready To Download",
                "Downloading",
                "Preparing",
                "Ready To Install",
                "Scheduled To Install",
                "Install Countdown",
                "Awaiting Install",
                "Installing",
                "Install Success",
                "Download Failed",
                "Install Failed",
                "Fault",
                "Connection Lost",
            ],
            entity_category=EntityCategory.DIAGNOSTIC,
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="pet_mode_temperature_status",
            translation_key="pet_mode_temperature_status",
            field="petModeTemperatureStatus",
            icon="mdi:dog-side",
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="pet_mode_status",
            translation_key="pet_mode_status",
            field="petModeStatus",
            icon="mdi:dog-side",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "On",
                "Off",
                "Disabled",
                "Faulty",
            ],
            value_lambda=lambda v: _to_title_case(v) if v else "Off",
        ),
        RivianSensorEntityDescription(
            key="wheels_installed",
            translation_key="wheels_installed",
            field="wheelsInstalled",
            icon="mdi:tire",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="cabin_hold_status",
            translation_key="cabin_hold_status",
            field="cabinHoldStatus",
            icon="mdi:hvac",
            value_lambda=lambda v: v.replace("_", " ").title() if v else "Off",
        ),
        RivianSensorEntityDescription(
            key="cabin_hold_notification",
            translation_key="cabin_hold_notification",
            field="cabinHoldNotification",
            icon="mdi:hvac",
            value_lambda=lambda v: v.replace("_", " ").title() if v else "None",
        ),
        RivianSensorEntityDescription(
            key="power_state",
            translation_key="power_state",
            field="powerState",
            icon="mdi:power",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Sleep",
                "Standby",
                "Ready",
                "Go",
                "Unknown",
            ],
            value_lambda=lambda v: (
                _to_title_case(v) if v and v.lower() != "sna" else "Unknown"
            ),
        ),
        RivianSensorEntityDescription(
            key="range_threshold",
            translation_key="range_threshold",
            field="rangeThreshold",
            icon="mdi:map-marker-distance",
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="remote_charging_available",
            translation_key="remote_charging_available",
            field="remoteChargingAvailable",
            icon="mdi:battery-charging-wireless-80",
        ),
        RivianSensorEntityDescription(
            key="service_mode",
            translation_key="service_mode",
            field="serviceMode",
            icon="mdi:account-wrench",
        ),
        RivianSensorEntityDescription(
            key="gnss_speed",
            translation_key="gnss_speed",
            field="gnssSpeed",
            device_class=SensorDeviceClass.SPEED,
            native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
        ),
        RivianSensorEntityDescription(
            key="time_to_end_of_charge",
            translation_key="time_to_end_of_charge",
            field="timeToEndOfCharge",
            device_class=SensorDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.MINUTES,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        RivianSensorEntityDescription(
            key="tire_pressure_front_left",
            translation_key="tire_pressure_front_left",
            field="tirePressureFrontLeft",
            icon="mdi:tire",
            device_class=SensorDeviceClass.PRESSURE,
            native_unit_of_measurement=UnitOfPressure.BAR,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        RivianSensorEntityDescription(
            key="tire_pressure_front_right",
            translation_key="tire_pressure_front_right",
            field="tirePressureFrontRight",
            icon="mdi:tire",
            device_class=SensorDeviceClass.PRESSURE,
            native_unit_of_measurement=UnitOfPressure.BAR,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        RivianSensorEntityDescription(
            key="tire_pressure_rear_left",
            translation_key="tire_pressure_rear_left",
            field="tirePressureRearLeft",
            icon="mdi:tire",
            device_class=SensorDeviceClass.PRESSURE,
            native_unit_of_measurement=UnitOfPressure.BAR,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        RivianSensorEntityDescription(
            key="tire_pressure_rear_right",
            translation_key="tire_pressure_rear_right",
            field="tirePressureRearRight",
            icon="mdi:tire",
            device_class=SensorDeviceClass.PRESSURE,
            native_unit_of_measurement=UnitOfPressure.BAR,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        RivianSensorEntityDescription(
            key="tire_pressure_status_front_left",
            translation_key="tire_pressure_status_front_left",
            field="tirePressureStatusFrontLeft",
            icon="mdi:tire",
        ),
        RivianSensorEntityDescription(
            key="tire_pressure_status_front_right",
            translation_key="tire_pressure_status_front_right",
            field="tirePressureStatusFrontRight",
            icon="mdi:tire",
        ),
        RivianSensorEntityDescription(
            key="tire_pressure_status_rear_left",
            translation_key="tire_pressure_status_rear_left",
            field="tirePressureStatusRearLeft",
            icon="mdi:tire",
        ),
        RivianSensorEntityDescription(
            key="tire_pressure_status_rear_right",
            translation_key="tire_pressure_status_rear_right",
            field="tirePressureStatusRearRight",
            icon="mdi:tire",
        ),
        RivianSensorEntityDescription(
            key="vehicle_mileage",
            translation_key="vehicle_mileage",
            field="vehicleMileage",
            icon="mdi:counter",
            device_class=SensorDeviceClass.DISTANCE,
            native_unit_of_measurement=UnitOfLength.METERS,
            state_class=SensorStateClass.TOTAL_INCREASING,
            suggested_display_precision=1,
            suggested_unit_of_measurement=UnitOfLength.MILES,
        ),
        RivianSensorEntityDescription(
            key="window_front_left_calibrated",
            translation_key="window_front_left_calibrated",
            field="windowFrontLeftCalibrated",
            icon="mdi:window-closed",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="window_front_right_calibrated",
            translation_key="window_front_right_calibrated",
            field="windowFrontRightCalibrated",
            icon="mdi:window-closed",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="window_rear_left_calibrated",
            translation_key="window_rear_left_calibrated",
            field="windowRearLeftCalibrated",
            icon="mdi:window-closed",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="window_rear_right_calibrated",
            translation_key="window_rear_right_calibrated",
            field="windowRearRightCalibrated",
            icon="mdi:window-closed",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="windows_next_action",
            translation_key="windows_next_action",
            field="windowsNextAction",
            icon="mdi:window-closed",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Sna",
                "Open Allowed",
                "Close Allowed",
                "Opening",
                "Closing",
                "Moving",
                "Open Not Available",
                "Close Not Available",
                "Open Not Allowed Faulted",
                "Close Not Allowed Faulted",
                "Obstructed While Closing Close Allowed",
                "Close Not Allowed Uncalibrated",
                "Open Not Allowed Uncalibrated",
            ],
            entity_category=EntityCategory.DIAGNOSTIC,
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="twelve_volt_battery_health",
            translation_key="twelve_volt_battery_health",
            field="twelveVoltBatteryHealth",
            icon="mdi:car-battery",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="wiper_fluid_state",
            translation_key="wiper_fluid_state",
            field="wiperFluidState",
            icon="mdi:wiper-wash",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Normal",
                "Low",
                "Empty",
            ],
            value_lambda=lambda v: _to_title_case(v) if v else "Normal",
        ),
        RivianSensorEntityDescription(
            key="steering_wheel_heat",
            translation_key="steering_wheel_heat",
            field="steeringWheelHeat",
            icon="mdi:steering",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Off",
                "Level 1",
                "Level 2",
                "Level 3",
            ],
            value_lambda=lambda v: v.replace("_", " ") if v else "Off",
        ),
        RivianSensorEntityDescription(
            key="seat_rear_left_heat",
            translation_key="seat_rear_left_heat",
            field="seatRearLeftHeat",
            icon="mdi:car-seat-heater",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Off",
                "Level 1",
                "Level 2",
                "Level 3",
            ],
            value_lambda=lambda v: v.replace("_", " ") if v else "Off",
        ),
        RivianSensorEntityDescription(
            key="seat_rear_right_heat",
            translation_key="seat_rear_right_heat",
            field="seatRearRightHeat",
            icon="mdi:car-seat-heater",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Off",
                "Level 1",
                "Level 2",
                "Level 3",
            ],
            value_lambda=lambda v: v.replace("_", " ") if v else "Off",
        ),
        RivianSensorEntityDescription(
            key="limited_accel_cold",
            translation_key="limited_accel_cold",
            field="limitedAccelCold",
            icon="mdi:snowflake-thermometer",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="limited_regen_cold",
            translation_key="limited_regen_cold",
            field="limitedRegenCold",
            icon="mdi:snowflake-thermometer",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="btm_ff_hardware_failure_status",
            translation_key="btm_ff_hardware_failure_status",
            field="btmFfHardwareFailureStatus",
            icon="mdi:bluetooth",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        # The nine fields Parallax is the ONLY source for.
        #
        # The f5 decoders read these out of the app's protobuf messages, and the
        # vehicleState subscription never names them -- so without a description
        # here they would be decoded into the coordinator and read by nothing.
        # That is exactly what happened when the gap-fill rule landed: fourteen
        # new decoders, and not one new entity.
        #
        # Five ship ENABLED and four disabled, and the line between them is
        # whether the message is PROVEN TO ARRIVE -- not whether a field happened
        # to hold a value in one diagnostics snapshot. A snapshot criterion flips
        # with the weather: knownLocation reads `home` because the truck is parked
        # at home, and coldRangeNotification reads `normal_range` because it is not
        # cold.
        #
        # Arrival is only witnessable where a sibling field of the SAME message is
        # unsubscribed. coordinator.py discards any Parallax key the subscription
        # also supplies, so for most of these an absent value cannot be told apart
        # from the RVM never arriving at all. Of the five RVMs behind these nine,
        # exactly one is witnessed: security.access.vas_fault, because
        # vasAccessCanFaulted arrived populated and neither of its fields is
        # subscribed.
        #
        # A NOTE ON WHAT ABSENCE MEANS, because an earlier version of this comment
        # got it wrong in the other direction. Proto3 omits zero values, but that
        # only implies "healthy" where healthy IS zero. It is not, for the vas
        # pair: _SECURE_ELEMENT_FAULTED_MAP and _ACCESS_CAN_FAULTED_MAP start at
        # 1 = no_failure and have no 0 entry at all. vasAccessCanFaulted arrived AS
        # no_failure -- an explicit non-zero value -- so a healthy secure element
        # should have sent one too. Its absence means the field was left unset,
        # i.e. UNSPECIFIED. Unknown, not healthy. The zero-means-healthy reading
        # holds only for _HARDWARE_FAILURE_MAP, where 0 IS "unspecified".
        # REVERSED (field-parity release). The three points below justified
        # entity_registry_enabled_default=False and a raw name for one release;
        # both were an artefact of how this field arrived, not of the field
        # itself, and both are now stale.
        #
        # btmOcHardwareFailureStatus is IN the app's own vehicleState document
        # (sh/C19779dc.java:59) and is now subscribed alongside its five
        # siblings (PARALLAX_ONLY_FIELDS shrunk 10 -> 7; see the comment there).
        # The "can never report healthy" / _HARDWARE_FAILURE_MAP-only vocabulary
        # was true only of the Parallax decode path: that decoder is proto3, and
        # proto3 omits a zero value on the wire, so the ENABLED->0 case never
        # arrived through it. The vehicleState subscription is not proto3 -- it
        # is the same gateway document its siblings already read `dtc_not_set`
        # from -- so this field now gets the same vocabulary as btm_ff/btm_rf/
        # btm_ic/btm_rfd/btm_lfd and the naming/vocabulary objections both fall
        # away with it. The Parallax decoder and _HARDWARE_FAILURE_MAP stay as a
        # fallback source; they are simply no longer this field's only one.
        RivianSensorEntityDescription(
            key="btm_oc_hardware_failure_status",
            translation_key="btm_oc_hardware_failure_status",
            field="btmOcHardwareFailureStatus",
            icon="mdi:bluetooth",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        # ENABLED. Its message is proven to arrive (see above), and a fault
        # sensor is worthless unless armed BEFORE the fault -- Home Assistant
        # does not backfill, so a disabled entity records nothing at the moment
        # one fires. It currently reads unknown; that is honest, not healthy.
        RivianSensorEntityDescription(
            key="vas_secure_element_faulted",
            translation_key="vas_secure_element_faulted",
            field="vasSecureElementFaulted",
            icon="mdi:key-alert",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        # ENABLED. The witness: this arrived populated as no_failure, which is
        # what proves security.access.vas_fault reaches us at all.
        RivianSensorEntityDescription(
            key="vas_access_can_faulted",
            translation_key="vas_access_can_faulted",
            field="vasAccessCanFaulted",
            icon="mdi:key-alert",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        # DISABLED: arrival UNWITNESSED. Its message has no unsubscribed sibling,
        # so an absent value cannot be told apart from the decoder never firing.
        # The arming argument that enabled vas_secure_element_faulted applies only
        # where delivery is proven; here it is not, and an entity that may never
        # populate on any vehicle loses to the clutter it adds to every install.
        # The RVM arrival counters in diagnostics settle this.
        RivianSensorEntityDescription(
            key="passive_entry_unlock_fail_reason",
            translation_key="passive_entry_unlock_fail_reason",
            field="passiveEntryUnlockFailReason",
            icon="mdi:lock-alert",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        # DISABLED: arrival UNWITNESSED. Its message has no unsubscribed sibling,
        # so an absent value cannot be told apart from the decoder never firing.
        # The arming argument that enabled vas_secure_element_faulted applies only
        # where delivery is proven; here it is not, and an entity that may never
        # populate on any vehicle loses to the clutter it adds to every install.
        # The RVM arrival counters in diagnostics settle this.
        RivianSensorEntityDescription(
            key="secure_immobilizer_status",
            translation_key="secure_immobilizer_status",
            field="secureImmobilizerStatus",
            icon="mdi:car-key",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        # DISABLED: arrival UNWITNESSED. Its message has no unsubscribed sibling,
        # so an absent value cannot be told apart from the decoder never firing.
        # The arming argument that enabled vas_secure_element_faulted applies only
        # where delivery is proven; here it is not, and an entity that may never
        # populate on any vehicle loses to the clutter it adds to every install.
        # The RVM arrival counters in diagnostics settle this.
        RivianSensorEntityDescription(
            key="consecutive_alarm_disabled_notification",
            translation_key="consecutive_alarm_disabled_notification",
            field="consecutiveAlarmDisabledNotification",
            icon="mdi:alarm-light-off",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        # ENABLED. A static hardware fact, present in every sample to date --
        # which is n=1, one 2022 R1T.
        RivianSensorEntityDescription(
            key="battery_cell_type",
            translation_key="battery_cell_type",
            field="batteryCellType",
            icon="mdi:battery-heart-variant",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        # ENABLED. User-facing, and one of only two of the nine with no
        # entity_category. `normal_range` today; the value worth having is the
        # cold one.
        RivianSensorEntityDescription(
            key="cold_range_notification",
            translation_key="cold_range_notification",
            field="coldRangeNotification",
            icon="mdi:snowflake-alert",
        ),
        # ENABLED. User-facing. Reads unknown where the owner has configured no
        # known locations in the Rivian app, which is an honest state.
        RivianSensorEntityDescription(
            key="known_location",
            translation_key="known_location",
            field="knownLocation",
            icon="mdi:map-marker-check",
        ),
        RivianSensorEntityDescription(
            key="btm_rf_hardware_failure_status",
            translation_key="btm_rf_hardware_failure_status",
            field="btmRfHardwareFailureStatus",
            icon="mdi:bluetooth",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="btm_ic_hardware_failure_status",
            translation_key="btm_ic_hardware_failure_status",
            field="btmIcHardwareFailureStatus",
            icon="mdi:bluetooth",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="btm_rfd_hardware_failure_status",
            translation_key="btm_rfd_hardware_failure_status",
            field="btmRfdHardwareFailureStatus",
            icon="mdi:bluetooth",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="btm_lfd_hardware_failure_status",
            translation_key="btm_lfd_hardware_failure_status",
            field="btmLfdHardwareFailureStatus",
            icon="mdi:bluetooth",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="wifi_signal",
            translation_key="wifi_signal",
            field="wifiSignal",
            icon="mdi:wifi",
            device_class=SensorDeviceClass.SIGNAL_STRENGTH,
            native_unit_of_measurement="dBm",
            state_class=SensorStateClass.MEASUREMENT,
        ),
        RivianSensorEntityDescription(
            key="closure_charge_port_door_next_action",
            translation_key="closure_charge_port_door_next_action",
            field="closureChargePortDoorNextAction",
            icon="mdi:ev-plug-type2",
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.DIAGNOSTIC,
            options=[
                "Sna",
                "Open Allowed",
                "Open Not Available",
                "Open Not Allowed Faulted",
                "Opening",
                "Close Allowed",
                "Obstructed While Opening Close Allowed",
                "Obstructed While Opening Open Allowed",
                "Obstructed While Closing Close Allowed",
                "Close Not Available",
                "Close Not Allowed Faulted",
                "Closing",
            ],
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="closure_frunk_next_action",
            translation_key="closure_frunk_next_action",
            field="closureFrunkNextAction",
            icon="mdi:car-door",
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.DIAGNOSTIC,
            options=[
                "Sna",
                "Open Allowed",
                "Close Allowed",
                "Opening",
                "Closing",
                "Open Not Available",
                "Close Not Available",
                "Open Not Allowed Faulted",
                "Close Not Allowed Faulted",
                "Open Allowed No Powered Operation",
                "Close Not Allowed No Powered Operation",
                "Obstructed While Opening Close Allowed",
                "Obstructed While Closing Open Allowed",
            ],
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        # The 25 fields the app's document has and this integration did not read
        # (field-parity release, §E). 21 direct descriptions plus the 4-way split
        # of gnssError below; batteryCellType, btmOcHardwareFailureStatus and
        # coldRangeNotification are NOT here -- they already have descriptions
        # above and only gained a second (subscribed) source.
        #
        # NO device_class=ENUM anywhere in this group. sensor.py appends an
        # unrecognised value to the entity's `options` list permanently for the
        # life of the process (observed live for cabinPreconditioningStatus and
        # both rear seat heaters) -- promote a field once a live boot has
        # recorded its real vocabulary, not before.
        RivianSensorEntityDescription(
            key="cellular_antenna_bars",
            translation_key="cellular_antenna_bars",
            field="cellularAntennaBars",
            icon="mdi:antenna",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="cellular_carrier",
            translation_key="cellular_carrier",
            field="cellularCarrier",
            icon="mdi:sim",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="cellular_mode",
            translation_key="cellular_mode",
            field="cellularMode",
            icon="mdi:signal",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        # Mirrors wifi_signal above field-for-field.
        RivianSensorEntityDescription(
            key="cellular_signal_strength",
            translation_key="cellular_signal_strength",
            field="cellularSignalStrength",
            icon="mdi:signal-cellular-3",
            device_class=SensorDeviceClass.SIGNAL_STRENGTH,
            native_unit_of_measurement="dBm",
            state_class=SensorStateClass.MEASUREMENT,
        ),
        RivianSensorEntityDescription(
            key="wifi_antenna_bars",
            translation_key="wifi_antenna_bars",
            field="wifiAntennaBars",
            icon="mdi:wifi-strength-outline",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        # FREQUENCY/MHz: the 2026-08-22 live probe recorded `wifiFreq = 5200`,
        # settling it as a `5200`-style MHz reading rather than a `2`/`5` band
        # selector -- `wifiLinkSpeed = 260` on its sibling independently
        # confirmed Mbps the same run. Evidence is n=1 (one vehicle, one
        # moment), and a unit is not reversible once HA statistics have
        # recorded it, so value_lambda guards against a band-index reading
        # slipping through as a bogus "5 MHz": below ~1000 is not a frequency,
        # and reads as unknown instead of corrupting long-run history.
        RivianSensorEntityDescription(
            key="wifi_freq",
            translation_key="wifi_freq",
            field="wifiFreq",
            icon="mdi:wifi",
            device_class=SensorDeviceClass.FREQUENCY,
            native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_lambda=lambda v: v if v is not None and v >= 1000 else None,
        ),
        # DATA_RATE / Mbps: Android's WifiInfo.getLinkSpeed(), which this field
        # almost certainly mirrors, is documented in Mbps. Flagged for live
        # confirmation same as wifi_freq.
        RivianSensorEntityDescription(
            key="wifi_link_speed",
            translation_key="wifi_link_speed",
            field="wifiLinkSpeed",
            icon="mdi:speedometer",
            device_class=SensorDeviceClass.DATA_RATE,
            native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="wifi_secure_status",
            translation_key="wifi_secure_status",
            field="wifiSecureStatus",
            icon="mdi:wifi-lock",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="wifi_ssid",
            translation_key="wifi_ssid",
            field="wifiSsid",
            icon="mdi:wifi-settings",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="wifi_sta_disabled_reason",
            translation_key="wifi_sta_disabled_reason",
            field="wifiStaDisabledReason",
            icon="mdi:wifi-off",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="wifi_wpa_status",
            translation_key="wifi_wpa_status",
            field="wifiWpaStatus",
            icon="mdi:wifi-lock-outline",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        # User-facing: what the trip planner set as its target, mirroring
        # battery_limit's PERCENTAGE-with-no-device_class shape above.
        RivianSensorEntityDescription(
            key="charging_trip_target_soc",
            translation_key="charging_trip_target_soc",
            field="chargingTripTargetSoc",
            icon="mdi:battery-charging-high",
            native_unit_of_measurement=PERCENTAGE,
        ),
        RivianSensorEntityDescription(
            key="charging_trip_target_mins_remaining",
            translation_key="charging_trip_target_mins_remaining",
            field="chargingTripTargetMinsRemaining",
            icon="mdi:timer-sand",
            device_class=SensorDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.MINUTES,
        ),
        RivianSensorEntityDescription(
            key="charging_disabled_ac_fault_state",
            translation_key="charging_disabled_ac_fault_state",
            field="chargingDisabledACFaultState",
            icon="mdi:alert-circle-outline",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="charging_disabled_all",
            translation_key="charging_disabled_all",
            field="chargingDisabledAll",
            icon="mdi:battery-off-outline",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="charging_time_estimation_validity",
            translation_key="charging_time_estimation_validity",
            field="chargingTimeEstimationValidity",
            icon="mdi:clock-alert-outline",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="battery_needs_lfp_calibration",
            translation_key="battery_needs_lfp_calibration",
            field="batteryNeedsLfpCalibration",
            icon="mdi:battery-sync",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="ota_deployment_intent",
            translation_key="ota_deployment_intent",
            field="otaDeploymentIntent",
            icon="mdi:package-up",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="ota_software_category",
            translation_key="ota_software_category",
            field="otaSoftwareCategory",
            icon="mdi:cog-outline",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        # User-facing, beside trailer_status above.
        RivianSensorEntityDescription(
            key="rear_hitch_status",
            translation_key="rear_hitch_status",
            field="rearHitchStatus",
            icon="mdi:trailer",
        ),
        RivianSensorEntityDescription(
            key="geo_location",
            translation_key="geo_location",
            field="geoLocation",
            icon="mdi:map-marker",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        # gnssError has no `value` key -- it is
        # {timeStamp, positionVertical, positionHorizontal, speed, bearing} -- so
        # it becomes four descriptions, dotted through coordinator.get(), rather
        # than one. All four share one `last_update` (sensor.py looks it up by
        # the envelope key, not the leaf) since they describe one arrival.
        RivianSensorEntityDescription(
            key="gnss_error_position_vertical",
            translation_key="gnss_error_position_vertical",
            field="gnssError.positionVertical",
            icon="mdi:arrow-up-down",
            device_class=SensorDeviceClass.DISTANCE,
            native_unit_of_measurement=UnitOfLength.METERS,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="gnss_error_position_horizontal",
            translation_key="gnss_error_position_horizontal",
            field="gnssError.positionHorizontal",
            icon="mdi:arrow-expand-horizontal",
            device_class=SensorDeviceClass.DISTANCE,
            native_unit_of_measurement=UnitOfLength.METERS,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="gnss_error_speed",
            translation_key="gnss_error_speed",
            field="gnssError.speed",
            icon="mdi:speedometer",
            device_class=SensorDeviceClass.SPEED,
            native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="gnss_error_bearing",
            translation_key="gnss_error_bearing",
            field="gnssError.bearing",
            icon="mdi:compass-outline",
            native_unit_of_measurement=DEGREE,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    "R1T": (
        RivianSensorEntityDescription(
            key="closure_tailgate_next_action",
            translation_key="closure_tailgate_next_action",
            field="closureTailgateNextAction",
            icon="mdi:truck-cargo-container",
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.DIAGNOSTIC,
            options=[
                "Sna",
                "Open Allowed",
                "Opening",
                "Open Not Available",
                "Open Not Allowed Faulted",
                "Stuck Ajar While Opening Open Allowed",
                "Open Already No Action Available",
                "Open Allowed Confirm Vehicle Angle",
                "Open Allowed Obstacle Detected",
                "Open Allowed Trailer Detected",
            ],
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="closure_side_bin_left_next_action",
            translation_key="closure_side_bin_left_next_action",
            field="closureSideBinLeftNextAction",
            icon="mdi:toolbox",
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.DIAGNOSTIC,
            options=[
                "Sna",
                "Open Allowed",
                "Opening",
                "Open Not Available",
                "Open Not Allowed Faulted",
                "Stuck Ajar While Opening Open Allowed",
                "Open Already No Action Available",
                "Open Allowed Confirm Vehicle Angle",
            ],
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="closure_side_bin_right_next_action",
            translation_key="closure_side_bin_right_next_action",
            field="closureSideBinRightNextAction",
            icon="mdi:toolbox",
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.DIAGNOSTIC,
            options=[
                "Sna",
                "Open Allowed",
                "Opening",
                "Open Not Available",
                "Open Not Allowed Faulted",
                "Stuck Ajar While Opening Open Allowed",
                "Open Already No Action Available",
                "Open Allowed Confirm Vehicle Angle",
            ],
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
    ),
    "R1S": (
        RivianSensorEntityDescription(
            key="seat_third_row_left_heat",
            translation_key="seat_third_row_left_heat",
            field="seatThirdRowLeftHeat",
            icon="mdi:car-seat-heater",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Off",
                "Level 1",
                "Level 2",
                "Level 3",
            ],
            value_lambda=lambda v: v.replace("_", " ") if v else "Off",
        ),
        RivianSensorEntityDescription(
            key="seat_third_row_right_heat",
            translation_key="seat_third_row_right_heat",
            field="seatThirdRowRightHeat",
            icon="mdi:car-seat-heater",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Off",
                "Level 1",
                "Level 2",
                "Level 3",
            ],
            value_lambda=lambda v: v.replace("_", " ") if v else "Off",
        ),
    ),
    # Liftgate STATE, not the R1S model. Both R1S and R2 are SUVs with a
    # liftgate; an R1T has none. Keyed on the capability rather than folded
    # into "R1S" so an R2 can receive it without also receiving the R1S-only
    # third-row seat heaters above, which an R2 does not have (no third-row
    # seat option exists on any R2 configuration). See legacy_grants.py's
    # VEHICLE_MODEL_GRANTS for which models get this group.
    "LIFTGATE": (
        RivianSensorEntityDescription(
            key="closure_liftgate_next_action",
            translation_key="closure_liftgate_next_action",
            field="closureLiftgateNextAction",
            icon="mdi:gesture-tap-button",
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.DIAGNOSTIC,
            options=[
                "Sna",
                "Open Allowed",
                "Close Allowed",
                "Opening",
                "Closing",
                "Open Not Available",
                "Close Not Available",
                "Open Allowed Trailer Detected",
                "Close Allowed Trailer Detected",
                "Open Not Allowed Faulted",
                "Close Not Allowed Faulted",
                "Open Allowed No Powered Operation",
                "Close Not Allowed No Powered Operation",
                "Obstructed While Opening Close Allowed",
                "Obstructed While Closing Close Allowed",
                "Lower Gate Open Close Not Allowed",
                "Opening Pause Not Allowed",
                "Closing Pause Not Allowed",
                "Open Allowed Obstacle Detected",
                "Close Allowed Obstacle Detected",
                "Processing",
            ],
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
    ),
}
BINARY_SENSORS: Final[dict[str, tuple[RivianBinarySensorEntityDescription, ...]]] = {
    "R1": (
        RivianBinarySensorEntityDescription(
            key="charge_port_state",
            translation_key="charge_port_state",
            field="chargePortState",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_frunk_closed",
            translation_key="closure_frunk_closed",
            field="closureFrunkClosed",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_frunk_locked",
            translation_key="closure_frunk_locked",
            field="closureFrunkLocked",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_tailgate_closed",
            translation_key="closure_tailgate_closed",
            field="closureTailgateClosed",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_tailgate_locked",
            translation_key="closure_tailgate_locked",
            field="closureTailgateLocked",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="door_front_left_closed",
            translation_key="door_front_left_closed",
            field="doorFrontLeftClosed",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="door_front_left_locked",
            translation_key="door_front_left_locked",
            field="doorFrontLeftLocked",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="door_front_right_closed",
            translation_key="door_front_right_closed",
            field="doorFrontRightClosed",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="door_front_right_locked",
            translation_key="door_front_right_locked",
            field="doorFrontRightLocked",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="door_rear_left_closed",
            translation_key="door_rear_left_closed",
            field="doorRearLeftClosed",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="door_rear_left_locked",
            translation_key="door_rear_left_locked",
            field="doorRearLeftLocked",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="door_rear_right_closed",
            translation_key="door_rear_right_closed",
            field="doorRearRightClosed",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="door_rear_right_locked",
            translation_key="door_rear_right_locked",
            field="doorRearRightLocked",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="gear_guard_locked",
            translation_key="gear_guard_locked",
            field="gearGuardLocked",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="tire_pressure_status_valid_front_left",
            translation_key="tire_pressure_status_valid_front_left",
            field="tirePressureStatusValidFrontLeft",
            device_class=BinarySensorDeviceClass.PROBLEM,
            on_value="invalid",
        ),
        RivianBinarySensorEntityDescription(
            key="tire_pressure_status_valid_front_right",
            translation_key="tire_pressure_status_valid_front_right",
            field="tirePressureStatusValidFrontRight",
            device_class=BinarySensorDeviceClass.PROBLEM,
            on_value="invalid",
        ),
        RivianBinarySensorEntityDescription(
            key="tire_pressure_status_valid_rear_left",
            translation_key="tire_pressure_status_valid_rear_left",
            field="tirePressureStatusValidRearLeft",
            device_class=BinarySensorDeviceClass.PROBLEM,
            on_value="invalid",
        ),
        RivianBinarySensorEntityDescription(
            key="tire_pressure_status_valid_rear_right",
            translation_key="tire_pressure_status_valid_rear_right",
            field="tirePressureStatusValidRearRight",
            device_class=BinarySensorDeviceClass.PROBLEM,
            on_value="invalid",
        ),
        RivianBinarySensorEntityDescription(
            key="window_front_left_closed",
            translation_key="window_front_left_closed",
            field="windowFrontLeftClosed",
            device_class=BinarySensorDeviceClass.WINDOW,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="window_front_right_closed",
            translation_key="window_front_right_closed",
            field="windowFrontRightClosed",
            device_class=BinarySensorDeviceClass.WINDOW,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="window_rear_left_closed",
            translation_key="window_rear_left_closed",
            field="windowRearLeftClosed",
            device_class=BinarySensorDeviceClass.WINDOW,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="window_rear_right_closed",
            translation_key="window_rear_right_closed",
            field="windowRearRightClosed",
            device_class=BinarySensorDeviceClass.WINDOW,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="locked_state",
            translation_key="locked_state",
            field=LOCK_STATE_ENTITIES,
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="door_state",
            translation_key="door_state",
            field=DOOR_STATE_ENTITIES,
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_state",
            translation_key="closure_state",
            field=CLOSURE_STATE_ENTITIES,
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="use_state",
            translation_key="use_state",
            field="powerState",
            device_class=BinarySensorDeviceClass.MOVING,
            on_value="go",
        ),
        RivianBinarySensorEntityDescription(
            key="car_wash_mode",
            translation_key="car_wash_mode",
            field="carWashMode",
            icon="mdi:car-wash",
            on_value="on",
        ),
    ),
    "R1T": (
        RivianBinarySensorEntityDescription(
            key="closure_side_bin_left_closed",
            translation_key="closure_side_bin_left_closed",
            field="closureSideBinLeftClosed",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_side_bin_left_locked",
            translation_key="closure_side_bin_left_locked",
            field="closureSideBinLeftLocked",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_side_bin_right_closed",
            translation_key="closure_side_bin_right_closed",
            field="closureSideBinRightClosed",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_side_bin_right_locked",
            translation_key="closure_side_bin_right_locked",
            field="closureSideBinRightLocked",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_tonneau_closed",
            translation_key="closure_tonneau_closed",
            field="closureTonneauClosed",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_tonneau_locked",
            translation_key="closure_tonneau_locked",
            field="closureTonneauLocked",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
    ),
    # Liftgate binary state moved to the "LIFTGATE" capability group -- see the
    # comment on SENSORS["LIFTGATE"] above. "R1S" has no binary sensors of its
    # own left: both of its former entries were liftgate state. The key stays
    # out of this dict entirely rather than as an empty tuple; the R1S model
    # still appears in SENSORS (third-row seat heaters), which is what
    # test_every_returned_group_actually_exists checks for.
    "LIFTGATE": (
        RivianBinarySensorEntityDescription(
            key="closure_liftgate_closed",
            translation_key="closure_liftgate_closed",
            field="closureLiftgateClosed",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_liftgate_locked",
            translation_key="closure_liftgate_locked",
            field="closureLiftgateLocked",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
    ),
}

# Fields a sensor reads but the GraphQL VehicleState type does not have, or that
# are declared by the schema but must never be requested in a subscription
# document.
#
# The wire lists just below (VEHICLE_STATE_SUBSCRIPTION_FIELDS and
# TIRE_PRESSURE_SUBSCRIPTION_FIELDS) used to be one set, DERIVED from every
# sensor's `field`. That meant any sensor fed by Parallax rather than by the
# vehicle-state subscription silently added its field to the subscription query.
# Rivian's gateway rejects the whole subscription on the first unknown field:
#
#   {"type":"error","payload":[{"message":
#     "Cannot query field \"wheelsInstalled\" on type \"VehicleState\"."}]}
#
# and the subscription then delivers nothing at all -- no battery level, no
# odometer, no tire pressures. Every test passed, because no test speaks to the
# real gateway; it took a live boot to see it.
#
# wheelsInstalled is computed by decode_vehicle_wheels (rivian_client/parallax.py)
# from the vehicle.wheels.vehicle_wheels RVM, so excluding it here costs nothing:
# the sensor still reads it out of the coordinator, which Parallax populates.
#
# Shrunk 10 -> 7 (batteryCellType, coldRangeNotification and
# btmOcHardwareFailureStatus removed): all three are in the app's own
# vehicleState document (sh/C19779dc.java:59) and are schema-declared, so
# subscribing to them is exactly what the app does. The reason they were
# excluded -- "a subscribed field is recorded in
# VehicleCoordinator._subscription_keys, which blocks Parallax's only source for
# it" -- rests on a misreading: `_subscription_keys` is populated from frames the
# gateway actually DELIVERS, never from the set of fields requested, and
# `test_parallax_gap_fill.py::test_falsy_entries_are_not_recorded_as_supplied`
# already pins that. The remaining seven have no such document to point to.
PARALLAX_ONLY_FIELDS: Final[set[str]] = {
    "consecutiveAlarmDisabledNotification",
    "knownLocation",
    "passiveEntryUnlockFailReason",
    "secureImmobilizerStatus",
    "vasAccessCanFaulted",
    "vasSecureElementFaulted",
    "wheelsInstalled",
}

# The app's own vehicleState subscription document, transcribed field-for-field
# from com.rivian.android.consumer/java_src/sh/C19779dc.java:59 (operationName
# "vehicleState") by parsing the GraphQL selection set by brace depth -- not
# hand-typed. 127 scalar-shaped fields plus 2 structured ones (gnssLocation,
# gnssError); geoLocation is selected as `{ value timeStamp }` and is
# scalar-shaped like the rest. Zero duplicates, zero tirePressure* names -- the
# app requests those separately (see TIRE_PRESSURE_SUBSCRIPTION_FIELDS below).
APP_VEHICLE_STATE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "activeDriverName",
        "alarmSoundStatus",
        "batteryCellType",
        "batteryHvThermalEvent",
        "batteryHvThermalEventPropagation",
        "batteryLevel",
        "batteryLimit",
        "batteryNeedsLfpCalibration",
        "btmFfHardwareFailureStatus",
        "btmIcHardwareFailureStatus",
        "btmLfdHardwareFailureStatus",
        "btmOcHardwareFailureStatus",
        "btmRfHardwareFailureStatus",
        "btmRfdHardwareFailureStatus",
        "cabinClimateDriverTemperature",
        "cabinClimateInteriorTemperature",
        "cabinHoldNotification",
        "cabinHoldStatus",
        "cabinPreconditioningStatus",
        "cabinPreconditioningType",
        "carWashMode",
        "cellularAntennaBars",
        "cellularCarrier",
        "cellularMode",
        "cellularSignalStrength",
        "chargePortState",
        "chargerDerateStatus",
        "chargerState",
        "chargerStatus",
        "chargingDisabledACFaultState",
        "chargingDisabledAll",
        "chargingTimeEstimationValidity",
        "chargingTripTargetMinsRemaining",
        "chargingTripTargetSoc",
        "closureChargePortDoorNextAction",
        "closureFrunkClosed",
        "closureFrunkLocked",
        "closureFrunkNextAction",
        "closureLiftgateClosed",
        "closureLiftgateLocked",
        "closureLiftgateNextAction",
        "closureSideBinLeftClosed",
        "closureSideBinLeftLocked",
        "closureSideBinLeftNextAction",
        "closureSideBinRightClosed",
        "closureSideBinRightLocked",
        "closureSideBinRightNextAction",
        "closureTailgateClosed",
        "closureTailgateLocked",
        "closureTailgateNextAction",
        "closureTonneauClosed",
        "closureTonneauLocked",
        "coldRangeNotification",
        "defrostDefogStatus",
        "distanceToEmpty",
        "doorFrontLeftClosed",
        "doorFrontLeftLocked",
        "doorFrontRightClosed",
        "doorFrontRightLocked",
        "doorRearLeftClosed",
        "doorRearLeftLocked",
        "doorRearRightClosed",
        "doorRearRightLocked",
        "driveMode",
        "gearGuardLocked",
        "gearGuardVideoMode",
        "gearGuardVideoStatus",
        "gearGuardVideoTermsAccepted",
        "gearStatus",
        "geoLocation",
        "gnssAltitude",
        "gnssBearing",
        "gnssError",
        "gnssLocation",
        "gnssSpeed",
        "limitedAccelCold",
        "limitedRegenCold",
        "otaAvailableVersion",
        "otaAvailableVersionGitHash",
        "otaCurrentStatus",
        "otaCurrentVersion",
        "otaCurrentVersionGitHash",
        "otaDeploymentIntent",
        "otaDownloadProgress",
        "otaInstallDuration",
        "otaInstallProgress",
        "otaInstallReady",
        "otaInstallTime",
        "otaInstallType",
        "otaSoftwareCategory",
        "otaStatus",
        "petModeStatus",
        "petModeTemperatureStatus",
        "powerState",
        "rangeThreshold",
        "rearHitchStatus",
        "remoteChargingAvailable",
        "seatFrontLeftHeat",
        "seatFrontLeftVent",
        "seatFrontRightHeat",
        "seatFrontRightVent",
        "seatRearLeftHeat",
        "seatRearRightHeat",
        "seatThirdRowLeftHeat",
        "seatThirdRowRightHeat",
        "serviceMode",
        "steeringWheelHeat",
        "timeToEndOfCharge",
        "trailerStatus",
        "twelveVoltBatteryHealth",
        "vehicleMileage",
        "wifiAntennaBars",
        "wifiFreq",
        "wifiLinkSpeed",
        "wifiSecureStatus",
        "wifiSignal",
        "wifiSsid",
        "wifiStaDisabledReason",
        "wifiWpaStatus",
        "windowFrontLeftCalibrated",
        "windowFrontLeftClosed",
        "windowFrontRightCalibrated",
        "windowFrontRightClosed",
        "windowRearLeftCalibrated",
        "windowRearLeftClosed",
        "windowRearRightCalibrated",
        "windowRearRightClosed",
        "windowsNextAction",
        "wiperFluidState",
    }
)

# Fields this integration reads that are not in the app's own document:
# batteryCapacity and brakeFluidLow feed existing sensors, and the six
# ota{Current,Available}Version{Year,Week,Number} fields feed the update
# entity's version-string parsing. Disjoint from APP_VEHICLE_STATE_FIELDS.
EXTRA_VEHICLE_STATE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "batteryCapacity",
        "brakeFluidLow",
        "otaAvailableVersionNumber",
        "otaAvailableVersionWeek",
        "otaAvailableVersionYear",
        "otaCurrentVersionNumber",
        "otaCurrentVersionWeek",
        "otaCurrentVersionYear",
    }
)

# The main vehicleState subscription document -- THE WIRE. Guarded by the same
# subtraction that used to sit on VEHICLE_STATE_API_FIELDS: that symbol is
# labelled below as never sent as a document, so subtracting from it protected
# nothing. This is where the guard belongs, because this is what
# coordinator.py sends.
VEHICLE_STATE_SUBSCRIPTION_FIELDS: Final[frozenset[str]] = (
    APP_VEHICLE_STATE_FIELDS | EXTRA_VEHICLE_STATE_FIELDS
) - PARALLAX_ONLY_FIELDS  # 137, the wire

# The TPMS subscription document -- THE WIRE. The app's own 8 names, transcribed
# from com.rivian.android.consumer/java_src/sh/C19721Z9.java:59 (operationName
# "tirePressureState" at :81), plus our 4 tirePressureStatusValid* names
# (gateway.graphql:884-895) -- already accepted on today's wire but not
# requested by this APK build.
TIRE_PRESSURE_SUBSCRIPTION_FIELDS: Final[frozenset[str]] = (
    frozenset(
        {
            "tirePressureFrontLeft",
            "tirePressureFrontRight",
            "tirePressureRearLeft",
            "tirePressureRearRight",
            "tirePressureStatusFrontLeft",
            "tirePressureStatusFrontRight",
            "tirePressureStatusRearLeft",
            "tirePressureStatusRearRight",
            "tirePressureStatusValidFrontLeft",
            "tirePressureStatusValidFrontRight",
            "tirePressureStatusValidRearLeft",
            "tirePressureStatusValidRearRight",
        }
    )
    - PARALLAX_ONLY_FIELDS
)  # 12, the wire

# The union of both documents. Kept under its historical name because eight test
# modules and several scripts import it -- but it is NEVER sent as a document;
# coordinator.py and the TPMS subscribe send the two WIRE symbols above. The
# subtraction on those two symbols is inert today: (APP | EXTRA | TPMS) and
# PARALLAX_ONLY_FIELDS do not intersect, so this union already excludes nothing
# PARALLAX_ONLY_FIELDS would have removed. It stays anyway -- not because it is
# load-bearing today, but because it is what stops the next person adding a name
# like knownLocation to one of the literal lists above without noticing it is
# Parallax-only.
VEHICLE_STATE_API_FIELDS: Final[frozenset[str]] = (
    VEHICLE_STATE_SUBSCRIPTION_FIELDS | TIRE_PRESSURE_SUBSCRIPTION_FIELDS
)  # 149, never sent as a document


CHARGING_STATE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "currentCurrency",
        "currentPrice",
        "displayStatus",
        "evseType",
        "kilometersChargedPerHour",
        "plugConnectionStatus",
        "power",
        "rangeAddedThisSession",
        "startTime",
        "timeElapsed",
        "timeToEndOfCharge",
        "totalChargedEnergy",
    }
)

WEEK_DAYS_ORDERED: Final[tuple[str, ...]] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

MINUTES_PER_DAY: Final[int] = 1440
MINUTES_PER_HOUR: Final[int] = 60

CHARGING_SCHEDULE_AMPERAGE_MINIMUM: Final[int] = 8
CHARGING_SCHEDULE_AMPERAGE_MAXIMUM: Final[int] = 48
CHARGING_SCHEDULE_AMPERAGE_STEP: Final[int] = 2

DEFAULT_CHARGING_SCHEDULE_START: Final[int] = 1320  # 10:00 PM
DEFAULT_CHARGING_SCHEDULE_DURATION: Final[int] = 480  # 8 hours
DEFAULT_CHARGING_SCHEDULE_AMPERAGE: Final[int] = 48
DEFAULT_CHARGING_SCHEDULE: Final[dict[str, Any]] = {
    "startTime": DEFAULT_CHARGING_SCHEDULE_START,
    "duration": DEFAULT_CHARGING_SCHEDULE_DURATION,
    "amperage": DEFAULT_CHARGING_SCHEDULE_AMPERAGE,
    "enabled": True,
    "weekDays": list(WEEK_DAYS_ORDERED),
}
