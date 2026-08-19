"""Rivian (Unofficial)"""

from __future__ import annotations

from typing import Any, Final

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
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
VERSION = "1.6.0-beta3"
ISSUE_URL = "https://github.com/bretterer/home-assistant-rivian/issues"

# Attributes
ATTR_API = "api"
ATTR_COORDINATOR = "coordinator"
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
        RivianSensorEntityDescription(
            key="gear_guard_video_terms_accepted",
            translation_key="gear_guard_video_terms_accepted",
            field="gearGuardVideoTermsAccepted",
            icon="mdi:cctv",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
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
    "R1S": (
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

# Fields a sensor reads but the GraphQL VehicleState type does not have.
#
# VEHICLE_STATE_API_FIELDS below is DERIVED from every sensor's `field`, so any
# sensor fed by Parallax rather than by the vehicle-state subscription silently
# adds its field to the subscription query. Rivian's gateway rejects the whole
# subscription on the first unknown field:
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
PARALLAX_ONLY_FIELDS: Final[set[str]] = {
    "wheelsInstalled",
}

VEHICLE_STATE_API_FIELDS: Final[set[str]] = {
    *(description.field for sensor in SENSORS.values() for description in sensor),
    *(
        field
        for sensors in BINARY_SENSORS.values()
        for sensor in sensors
        for field in ([sensor.field] if isinstance(sensor.field, str) else sensor.field)
    ),
    "gnssLocation",
    "otaCurrentVersion",
    "otaCurrentVersionYear",
    "otaCurrentVersionWeek",
    "otaCurrentVersionNumber",
    "otaCurrentVersionGitHash",
    "otaAvailableVersion",
    "otaAvailableVersionYear",
    "otaAvailableVersionWeek",
    "otaAvailableVersionNumber",
    "otaAvailableVersionGitHash",
    "otaInstallProgress",
    # Front seat vent fields (removed from binary sensors, but still needed for combined enum sensors)
    "seatFrontLeftVent",
    "seatFrontRightVent",
} - PARALLAX_ONLY_FIELDS

# `-`, not `^`. Symmetric difference behaved as subtraction only while all four
# tire names happened to be in the base set; the moment one left, `^` would ADD it
# back, producing exactly the unknown-field subscription kill documented at
# const.py:1441-1455 -- where a single name the server does not know took down the
# entire subscription and the integration delivered nothing.
#
# f2 and f4 both edit the tire field set, so this is converted before either does.
VEHICLE_STATE_SANS_TPMS_API_FIELDS: Final[set[str]] = VEHICLE_STATE_API_FIELDS - {
    "tirePressureFrontLeft",
    "tirePressureFrontRight",
    "tirePressureRearLeft",
    "tirePressureRearRight",
}

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
