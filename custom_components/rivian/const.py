"""Rivian (Unofficial)"""
from __future__ import annotations

from typing import Final

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
VERSION = "0.0.0"
ISSUE_URL = "https://github.com/bretterer/home-assistant-rivian/issues"

# Attributes
ATTR_API = "api"
ATTR_COORDINATOR = "coordinator"
ATTR_USER = "user"
ATTR_VEHICLE = "vehicle"
ATTR_WALLBOX = "wallbox"

# Config properties
CONF_OTP = "otp"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_USER_SESSION_TOKEN = "user_session_token"
CONF_VEHICLE_CONTROL = "vehicle_control"

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

INVALID_SENSOR_STATES = {"fault", "signal_not_available", "undefined"}


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


SENSORS: Final[dict[str, tuple[RivianSensorEntityDescription, ...]]] = {
    "R1": (
        RivianSensorEntityDescription(
            key="altitude",
            field="gnssAltitude",
            name="Altitude",
            icon="mdi:altimeter",
            device_class=SensorDeviceClass.DISTANCE,
            native_unit_of_measurement=UnitOfLength.METERS,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
        ),
        RivianSensorEntityDescription(
            key="battery_thermal_status",
            field="batteryHvThermalEvent",
            name="Battery Thermal Status",
            icon="mdi:battery-alert",
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="battery_thermal_runaway_propagation",
            field="batteryHvThermalEventPropagation",
            name="Battery Thermal Runaway Propagation",
            icon="mdi:battery-alert",
        ),
        RivianSensorEntityDescription(
            key="battery_level",
            field="batteryLevel",
            name="Battery State of Charge",
            device_class=SensorDeviceClass.BATTERY,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
        ),
        RivianSensorEntityDescription(
            key="battery_limit",
            field="batteryLimit",
            name="Battery State of Charge Limit",
            icon="mdi:battery-charging-80",
            native_unit_of_measurement=PERCENTAGE,
        ),
        RivianSensorEntityDescription(
            key="battery_capacity",
            field="batteryCapacity",
            name="Battery Capacity",
            device_class=SensorDeviceClass.ENERGY_STORAGE,
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:battery-check",
            suggested_display_precision=2,
        ),
        RivianSensorEntityDescription(
            key="bearing",
            field="gnssBearing",
            name="Bearing",
            icon="mdi:compass",
            native_unit_of_measurement=DEGREE,
            suggested_display_precision=0,
        ),
        RivianSensorEntityDescription(
            key="brake_fluid_low",
            field="brakeFluidLow",
            name="Brake Fluid Level Low",
            icon="mdi:car-brake-fluid-level",
        ),
        RivianSensorEntityDescription(
            key="driver_temperature",
            field="cabinClimateDriverTemperature",
            name="Driver Temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            suggested_display_precision=1,
        ),
        RivianSensorEntityDescription(
            key="cabin_temperature",
            field="cabinClimateInteriorTemperature",
            name="Cabin Temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
        ),
        RivianSensorEntityDescription(
            key="cabin_preconditioning_type",
            field="cabinPreconditioningType",
            name="Cabin Climate Preconditioning Type",
            icon="mdi:thermostat",
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="charger_derate_status",
            field="chargerDerateStatus",
            name="Charger Derate Status",
            icon="mdi:ev-station",
        ),
        RivianSensorEntityDescription(
            key="distance_to_empty",
            field="distanceToEmpty",
            name="Estimated Vehicle Range",
            icon="mdi:map-marker-distance",
            device_class=SensorDeviceClass.DISTANCE,
            native_unit_of_measurement=UnitOfLength.KILOMETERS,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
        ),
        RivianSensorEntityDescription(
            key="drive_mode",
            field="driveMode",
            name="Drive Mode",
            icon="mdi:car-speed-limiter",
            device_class=SensorDeviceClass.ENUM,
            options=list(DRIVE_MODE_MAP.values()),
            value_lambda=lambda v: DRIVE_MODE_MAP.get(v, v),
        ),
        RivianSensorEntityDescription(
            key="gear_status",
            field="gearStatus",
            name="Gear Selector",
            icon="mdi:car-shift-pattern",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Drive",
                "Neutral",
                "Park",
                "Reverse",
            ],
            value_lambda=lambda v: v.title(),
        ),
        RivianSensorEntityDescription(
            key="trailer_status",
            field="trailerStatus",
            name="Trailer Status",
            icon="mdi:truck-trailer",
        ),
        RivianSensorEntityDescription(
            key="gear_guard_video_mode",
            field="gearGuardVideoMode",
            name="Gear Guard Video Mode",
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
            field="gearGuardVideoStatus",
            name="Gear Guard Video Status",
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
            field="gearGuardVideoTermsAccepted",
            name="Gear Guard Video Terms Accepted",
            icon="mdi:cctv",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="ota_available_version",
            field="otaAvailableVersion",
            name="Software OTA - Available Version",
            icon="mdi:package",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_available_version_git_hash",
            field="otaAvailableVersionGitHash",
            name="Software OTA - Available Version Git Hash",
            icon="mdi:source-commit",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_available_version_number",
            field="otaAvailableVersionNumber",
            name="Software OTA - Available Version Number",
            icon="mdi:numeric",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_available_version_week",
            field="otaAvailableVersionWeek",
            name="Software OTA - Available Version Week",
            icon="mdi:calendar-week",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_available_version_year",
            field="otaAvailableVersionYear",
            name="Software OTA - Available Version Year",
            icon="mdi:calendar",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_current_status",
            field="otaCurrentStatus",
            name="Software OTA - Status Current",
            icon="mdi:package",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="ota_current_version",
            field="otaCurrentVersion",
            name="Software OTA - Current Version",
            icon="mdi:package",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_current_version_git_hash",
            field="otaCurrentVersionGitHash",
            name="Software OTA - Current Version Git Hash",
            icon="mdi:source-commit",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_current_version_number",
            field="otaCurrentVersionNumber",
            name="Software OTA - Current Version Number",
            icon="mdi:numeric",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_current_version_week",
            field="otaCurrentVersionWeek",
            name="Software OTA - Current Version Week",
            icon="mdi:calendar-week",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_current_version_year",
            field="otaCurrentVersionYear",
            name="Software OTA - Current Version Year",
            icon="mdi:calendar",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        RivianSensorEntityDescription(
            key="ota_download_progress",
            field="otaDownloadProgress",
            name="Software OTA - Download Progress",
            icon="mdi:progress-download",
            entity_category=EntityCategory.DIAGNOSTIC,
            native_unit_of_measurement=PERCENTAGE,
        ),
        RivianSensorEntityDescription(
            key="ota_install_duration",
            field="otaInstallDuration",
            name="Software OTA - Install Duration",
            icon="mdi:wrench-clock",
            device_class=SensorDeviceClass.DURATION,
            entity_category=EntityCategory.DIAGNOSTIC,
            native_unit_of_measurement=UnitOfTime.MINUTES,
        ),
        RivianSensorEntityDescription(
            key="ota_install_progress",
            field="otaInstallProgress",
            name="Software OTA - Install Progress",
            icon="mdi:progress-clock",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            native_unit_of_measurement=PERCENTAGE,
        ),
        RivianSensorEntityDescription(
            key="ota_install_ready",
            field="otaInstallReady",
            name="Software OTA - Install Ready",
            icon="mdi:progress-check",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_lambda=lambda v: v.replace("_", " ").title().replace("Ota", "OTA"),
        ),
        RivianSensorEntityDescription(
            key="ota_install_time",
            field="otaInstallTime",
            name="Software OTA - Install Time",
            icon="mdi:clock",
            device_class=SensorDeviceClass.DURATION,
            entity_category=EntityCategory.DIAGNOSTIC,
            native_unit_of_measurement=UnitOfTime.MINUTES,
        ),
        RivianSensorEntityDescription(
            key="ota_install_type",
            field="otaInstallType",
            name="Software OTA - Install Type",
            icon="mdi:package",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="ota_status",
            field="otaStatus",
            name="Software OTA - Status",
            icon="mdi:package",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Idle",
                "Ready To Download",
                "Downloading",
                "Preparing",
                "Ready To Install",
                "Install Countdown",
                "Awaiting Install",
                "Installing",
                "Install Success",
                "Connection Lost",
                "Install Failed",
            ],
            entity_category=EntityCategory.DIAGNOSTIC,
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="pet_mode_temperature_status",
            field="petModeTemperatureStatus",
            name="Pet Mode Temperature Status",
            icon="mdi:dog-side",
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="power_state",
            field="powerState",
            name="Power State",
            icon="mdi:power",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "Go",
                "Ready",
                "Sleep",
                "Standby",
            ],
            old_key="power_tate",  # to be removed 2024-06
            value_lambda=lambda v: v.title(),
        ),
        RivianSensorEntityDescription(
            key="range_threshold",
            field="rangeThreshold",
            name="Range Threshold",
            icon="mdi:map-marker-distance",
            value_lambda=lambda v: v.replace("_", " ").title(),
        ),
        RivianSensorEntityDescription(
            key="remote_charging_available",
            field="remoteChargingAvailable",
            name="Remote Charging Available",
            icon="mdi:battery-charging-wireless-80",
        ),
        RivianSensorEntityDescription(
            key="service_mode",
            field="serviceMode",
            name="Service Mode",
            icon="mdi:account-wrench",
        ),
        RivianSensorEntityDescription(
            key="speed",
            field="gnssSpeed",
            name="Speed",
            device_class=SensorDeviceClass.SPEED,
            native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
        ),
        RivianSensorEntityDescription(
            key="time_to_end_of_charge",
            field="timeToEndOfCharge",
            name="Charging Time Remaining",
            device_class=SensorDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.MINUTES,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        RivianSensorEntityDescription(
            key="tire_pressure_front_left",
            field="tirePressureFrontLeft",
            name="Tire Pressure Front Left",
            icon="mdi:tire",
            device_class=SensorDeviceClass.PRESSURE,
            native_unit_of_measurement=UnitOfPressure.BAR,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        RivianSensorEntityDescription(
            key="tire_pressure_front_right",
            field="tirePressureFrontRight",
            name="Tire Pressure Front Right",
            icon="mdi:tire",
            device_class=SensorDeviceClass.PRESSURE,
            native_unit_of_measurement=UnitOfPressure.BAR,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        RivianSensorEntityDescription(
            key="tire_pressure_rear_left",
            field="tirePressureRearLeft",
            name="Tire Pressure Rear Left",
            icon="mdi:tire",
            device_class=SensorDeviceClass.PRESSURE,
            native_unit_of_measurement=UnitOfPressure.BAR,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        RivianSensorEntityDescription(
            key="tire_pressure_rear_right",
            field="tirePressureRearRight",
            name="Tire Pressure Rear Right",
            icon="mdi:tire",
            device_class=SensorDeviceClass.PRESSURE,
            native_unit_of_measurement=UnitOfPressure.BAR,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        RivianSensorEntityDescription(
            key="tire_pressure_status_front_left",
            field="tirePressureStatusFrontLeft",
            name="Tire Pressure Front Left Status",
            icon="mdi:tire",
        ),
        RivianSensorEntityDescription(
            key="tire_pressure_status_front_right",
            field="tirePressureStatusFrontRight",
            name="Tire Pressure Front Right Status",
            icon="mdi:tire",
        ),
        RivianSensorEntityDescription(
            key="tire_pressure_status_rear_left",
            field="tirePressureStatusRearLeft",
            name="Tire Pressure Rear Left Status",
            icon="mdi:tire",
        ),
        RivianSensorEntityDescription(
            key="tire_pressure_status_rear_right",
            field="tirePressureStatusRearRight",
            name="Tire Pressure Rear Right Status",
            icon="mdi:tire",
        ),
        RivianSensorEntityDescription(
            key="vehicle_mileage",
            field="vehicleMileage",
            name="Odometer",
            icon="mdi:counter",
            device_class=SensorDeviceClass.DISTANCE,
            native_unit_of_measurement=UnitOfLength.METERS,
            state_class=SensorStateClass.TOTAL_INCREASING,
            suggested_display_precision=1,
            suggested_unit_of_measurement=UnitOfLength.MILES,
        ),
        RivianSensorEntityDescription(
            key="window_front_left_calibrated",
            field="windowFrontLeftCalibrated",
            name="Window Calibration Front Left State",
            icon="mdi:window-closed",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="window_front_right_calibrated",
            field="windowFrontRightCalibrated",
            name="Window Calibration Front Right State",
            icon="mdi:window-closed",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="window_rear_left_calibrated",
            field="windowRearLeftCalibrated",
            name="Window Calibration Rear Left State",
            icon="mdi:window-closed",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="window_rear_right_calibrated",
            field="windowRearRightCalibrated",
            name="Window Calibration Rear Right State",
            icon="mdi:window-closed",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="windows_next_action",
            field="windowsNextAction",
            name="Windows Next Action",
            icon="mdi:window-closed",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="twelve_volt_battery_health",
            field="twelveVoltBatteryHealth",
            name="12V Battery Health",
            icon="mdi:car-battery",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="limited_acceleration_cold",
            field="limitedAccelCold",
            name="Limited Acceleration (Cold)",
            icon="mdi:snowflake-thermometer",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="limited_regen_braking_cold",
            field="limitedRegenCold",
            name="Limited Regenerative Braking (Cold)",
            icon="mdi:snowflake-thermometer",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="bluetooth_front_fascia_hardware_failure_status",
            field="btmFfHardwareFailureStatus",
            name="Bluetooth Module Failure Status Fascia Front",
            icon="mdi:bluetooth",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="bluetooth_rear_fascia_hardware_failure_status",
            field="btmRfHardwareFailureStatus",
            name="Bluetooth Module Failure Status Fascia Rear",
            icon="mdi:bluetooth",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="bluetooth_instrument_controls_hardware_failure_status",
            field="btmIcHardwareFailureStatus",
            name="Bluetooth Module Failure Status Instrument Controls",
            icon="mdi:bluetooth",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="bluetooth_right_front_door_hardware_failure_status",
            field="btmRfdHardwareFailureStatus",
            name="Bluetooth Module Failure Status Door Front Right",
            icon="mdi:bluetooth",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        RivianSensorEntityDescription(
            key="bluetooth_left_front_door_hardware_failure_status",
            field="btmLfdHardwareFailureStatus",
            name="Bluetooth Module Failure Status Door Front Left",
            icon="mdi:bluetooth",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    "R1S": (
        RivianSensorEntityDescription(
            key="liftgate_next_action",
            field="closureLiftgateNextAction",
            name="Liftgate Next Action",
            icon="mdi:gesture-tap-button",
        ),
    ),
}
BINARY_SENSORS: Final[dict[str, tuple[RivianBinarySensorEntityDescription, ...]]] = {
    "R1": (
        RivianBinarySensorEntityDescription(
            key="alarm_sound_status",
            field="alarmSoundStatus",
            name="Gear Guard Alarm",
            device_class=BinarySensorDeviceClass.TAMPER,
            on_value="true",
        ),
        RivianBinarySensorEntityDescription(
            key="cabin_preconditioning_status",
            field="cabinPreconditioningStatus",
            name="Cabin Climate Preconditioning",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=["active", "complete_maintain", "initiate"],
        ),
        RivianBinarySensorEntityDescription(
            key="charge_port",
            field="chargePortState",
            name="Charge Port",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="charger_state",
            field="chargerState",
            name="Charging Status",
            device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
            on_value=["charging_active", "charging_connecting"],
        ),
        RivianBinarySensorEntityDescription(
            key="charger_status",
            field="chargerStatus",
            name="Charger Connection",
            device_class=BinarySensorDeviceClass.PLUG,
            on_value="chrgr_sts_not_connected",
            negate=True,
        ),
        RivianBinarySensorEntityDescription(
            key="closure_frunk_closed",
            field="closureFrunkClosed",
            name="Front Trunk",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_frunk_locked",
            field="closureFrunkLocked",
            name="Front Trunk Lock",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_tailgate_closed",
            field="closureTailgateClosed",
            name="Tailgate",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_tailgate_locked",
            field="closureTailgateLocked",
            name="Tailgate Lock",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="defrost_defog_status",
            field="defrostDefogStatus",
            name="Defrost/Defog",
            icon="mdi:car-defrost-front",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value="Off",
            negate=True,
        ),
        RivianBinarySensorEntityDescription(
            key="door_front_left_closed",
            field="doorFrontLeftClosed",
            name="Door Front Left",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="door_front_left_locked",
            field="doorFrontLeftLocked",
            name="Door Front Left Lock",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="door_front_right_closed",
            field="doorFrontRightClosed",
            name="Door Front Right",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="door_front_right_locked",
            field="doorFrontRightLocked",
            name="Door Front Right Lock",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="door_rear_left_closed",
            field="doorRearLeftClosed",
            name="Door Rear Left",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="door_rear_left_locked",
            field="doorRearLeftLocked",
            name="Door Rear Left Lock",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="door_rear_right_closed",
            field="doorRearRightClosed",
            name="Door Rear Right",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="door_rear_right_locked",
            field="doorRearRightLocked",
            name="Door Rear Right Lock",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="gear_guard_locked",
            field="gearGuardLocked",
            name="Gear Guard",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="pet_mode_status",
            field="petModeStatus",
            name="Pet Mode",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value="On",
        ),
        RivianBinarySensorEntityDescription(
            key="seat_front_left_heat",
            field="seatFrontLeftHeat",
            name="Heated Seat Front Left",
            icon="mdi:car-seat-heater",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=["Level_1", "Level_2", "Level_3"],
        ),
        RivianBinarySensorEntityDescription(
            key="seat_front_left_vent",
            field="seatFrontLeftVent",
            name="Vented Seat Front Left",
            icon="mdi:car-seat-cooler",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=["Level_1", "Level_2", "Level_3"],
        ),
        RivianBinarySensorEntityDescription(
            key="seat_front_right_heat",
            field="seatFrontRightHeat",
            name="Heated Seat Front Right",
            icon="mdi:car-seat-heater",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=["Level_1", "Level_2", "Level_3"],
        ),
        RivianBinarySensorEntityDescription(
            key="seat_front_right_vent",
            field="seatFrontRightVent",
            name="Vented Seat Front Right",
            icon="mdi:car-seat-cooler",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=["Level_1", "Level_2", "Level_3"],
        ),
        RivianBinarySensorEntityDescription(
            key="seat_rear_left_heat",
            field="seatRearLeftHeat",
            name="Heated Seat Rear Left",
            icon="mdi:car-seat-heater",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=["Level_1", "Level_2", "Level_3"],
        ),
        RivianBinarySensorEntityDescription(
            key="seat_rear_right_heat",
            field="seatRearRightHeat",
            name="Heated Seat Rear Right",
            icon="mdi:car-seat-heater",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=["Level_1", "Level_2", "Level_3"],
        ),
        RivianBinarySensorEntityDescription(
            key="steering_wheel_heat",
            field="steeringWheelHeat",
            name="Heated Steering Wheel",
            icon="mdi:steering",  # mdi:steering-heater, https://github.com/Templarian/MaterialDesign/issues/6925
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value="Level_1",
        ),
        RivianBinarySensorEntityDescription(
            key="tire_pressure_status_valid_front_left",
            field="tirePressureStatusValidFrontLeft",
            name="Tire Pressure Front Left Validity",
            device_class=BinarySensorDeviceClass.PROBLEM,
            on_value="invalid",
        ),
        RivianBinarySensorEntityDescription(
            key="tire_pressure_status_valid_front_right",
            field="tirePressureStatusValidFrontRight",
            name="Tire Pressure Front Right Validity",
            device_class=BinarySensorDeviceClass.PROBLEM,
            on_value="invalid",
        ),
        RivianBinarySensorEntityDescription(
            key="tire_pressure_status_valid_rear_left",
            field="tirePressureStatusValidRearLeft",
            name="Tire Pressure Rear Left Validity",
            device_class=BinarySensorDeviceClass.PROBLEM,
            on_value="invalid",
        ),
        RivianBinarySensorEntityDescription(
            key="tire_pressure_status_valid_rear_right",
            field="tirePressureStatusValidRearRight",
            name="Tire Pressure Rear Right Validity",
            device_class=BinarySensorDeviceClass.PROBLEM,
            on_value="invalid",
        ),
        RivianBinarySensorEntityDescription(
            key="window_front_left_closed",
            field="windowFrontLeftClosed",
            name="Window Front Left",
            device_class=BinarySensorDeviceClass.WINDOW,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="window_front_right_closed",
            field="windowFrontRightClosed",
            name="Window Front Right",
            device_class=BinarySensorDeviceClass.WINDOW,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="window_rear_left_closed",
            field="windowRearLeftClosed",
            name="Window Rear Left",
            device_class=BinarySensorDeviceClass.WINDOW,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="window_rear_right_closed",
            field="windowRearRightClosed",
            name="Window Rear Right",
            device_class=BinarySensorDeviceClass.WINDOW,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="wiper_fluid_state",
            field="wiperFluidState",
            name="Wiper Fluid Level",
            icon="mdi:wiper-wash",
            device_class=BinarySensorDeviceClass.PROBLEM,
            on_value="normal",
            negate=True,
        ),
        RivianBinarySensorEntityDescription(
            key="locked_state",
            field=LOCK_STATE_ENTITIES,
            name="Locked State",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="door_state",
            field=DOOR_STATE_ENTITIES,
            name="Door State",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_state",
            field=CLOSURE_STATE_ENTITIES,
            name="Closure State",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="use_state",
            field="powerState",
            name="In Use State",
            device_class=BinarySensorDeviceClass.MOVING,
            on_value="go",
        ),
        RivianBinarySensorEntityDescription(
            key="car_wash_mode",
            field="carWashMode",
            name="Car Wash Mode",
            icon="mdi:car-wash",
            on_value="on",
        ),
    ),
    "R1T": (
        RivianBinarySensorEntityDescription(
            key="closure_side_bin_left_closed",
            field="closureSideBinLeftClosed",
            name="Gear Tunnel Left",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_side_bin_left_locked",
            field="closureSideBinLeftLocked",
            name="Gear Tunnel Left Lock",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_side_bin_right_closed",
            field="closureSideBinRightClosed",
            name="Gear Tunnel Right",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_side_bin_right_locked",
            field="closureSideBinRightLocked",
            name="Gear Tunnel Right Lock",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_tonneau_closed",
            field="closureTonneauClosed",
            name="Tonneau",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_tonneau_locked",
            field="closureTonneauLocked",
            name="Tonneau Lock",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
    ),
    "R1S": (
        RivianBinarySensorEntityDescription(
            key="closure_liftgate_closed",
            field="closureLiftgateClosed",
            name="Liftgate",
            device_class=BinarySensorDeviceClass.DOOR,
            on_value="open",
        ),
        RivianBinarySensorEntityDescription(
            key="closure_liftgate_locked",
            field="closureLiftgateLocked",
            name="Liftgate Lock",
            device_class=BinarySensorDeviceClass.LOCK,
            on_value="unlocked",
        ),
        RivianBinarySensorEntityDescription(
            key="seat_third_row_left_heat",
            field="seatThirdRowLeftHeat",
            name="Heated Seat 3rd Row Left",
            icon="mdi:car-seat-heater",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=["Level_1", "Level_2", "Level_3"],
        ),
        RivianBinarySensorEntityDescription(
            key="seat_third_row_right_heat",
            field="seatThirdRowRightHeat",
            name="Heated Seat 3rd Row Right",
            icon="mdi:car-seat-heater",
            device_class=BinarySensorDeviceClass.RUNNING,
            on_value=["Level_1", "Level_2", "Level_3"],
        ),
    ),
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
}

VEHICLE_STATE_SANS_TPMS_API_FIELDS: Final[set[str]] = VEHICLE_STATE_API_FIELDS ^ {
    "tirePressureFrontLeft",
    "tirePressureFrontRight",
    "tirePressureRearLeft",
    "tirePressureRearRight",
}

CHARGING_API_FIELDS: Final[set[str]] = {
    "currentCurrency",
    "currentPrice",
    "kilometersChargedPerHour",
    "power",
    "rangeAddedThisSession",
    "startTime",
    "timeElapsed",
    "totalChargedEnergy",
}
