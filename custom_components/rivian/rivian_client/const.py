"""Rivian constants."""

from __future__ import annotations

import sys
from typing import Final

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from backports.strenum import StrEnum

LIVE_SESSION_PROPERTIES: Final[set[str]] = {
    "chargerId",
    "current",
    "currentCurrency",
    "currentMiles",
    "currentPrice",
    "isFreeSession",
    "isRivianCharger",
    "kilometersChargedPerHour",
    "locationId",
    "power",
    "rangeAddedThisSession",
    "soc",
    "startTime",
    "timeElapsed",
    "timeRemaining",
    "totalChargedEnergy",
    "vehicleChargerState",
}

VEHICLE_STATE_PROPERTIES: Final[set[str]] = {
    # VehicleCloudConnection
    "cloudConnection",
    # VehicleLocation
    "geoLocation",
    "gnssLocation",
    "gnssError",
    # Connectivity
    "cellularAntennaBars",
    "cellularCarrier",
    "cellularMode",
    "cellularSignalStrength",
    "wifiAntennaBars",
    "wifiFreq",
    "wifiLinkSpeed",
    "wifiSecureStatus",
    # "wifiSignal", not "wifiSignalStrength". Probed against the live gateway:
    # a query selecting wifiSignalStrength returns 400 GRAPHQL_VALIDATION_FAILED,
    # exactly like a field name invented for the control case, while wifiSignal
    # validates (200) and the vehicle-state subscription delivers values for it.
    # The typo made this whole default property set unusable with
    # get_vehicle_state, which is why nothing caught it: the integration
    # subscribes and never calls that method.
    "wifiSignal",
    "wifiSsid",
    "wifiStaDisabledReason",
    "wifiWpaStatus",
    # TimeStamped(String|[Nullable]Float|Int)
    "activeDriverName",
    "alarmSoundStatus",
    "batteryCapacity",
    "batteryCellType",
    "batteryHvThermalEvent",
    "batteryHvThermalEventPropagation",
    "batteryLevel",
    "batteryLimit",
    "batteryNeedsLfpCalibration",
    "brakeFluidLow",
    "btmFfHardwareFailureStatus",
    "btmIcHardwareFailureStatus",
    "btmLfdHardwareFailureStatus",
    "btmOcHardwareFailureStatus",
    "btmRfdHardwareFailureStatus",
    "btmRfHardwareFailureStatus",
    "cabinClimateDriverTemperature",
    "cabinClimateInteriorTemperature",
    "cabinHoldNotification",
    "cabinHoldStatus",
    "cabinPreconditioningStatus",
    "cabinPreconditioningType",
    "carWashMode",
    "chargerDerateStatus",
    "chargerState",
    "chargerStatus",
    "chargePortState",
    "chargingDisabledAll",
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
    "closureTonneauNextAction",
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
    "gnssAltitude",
    "gnssBearing",
    "gnssSpeed",
    "limitedRegenCold",
    "limitedAccelCold",
    "otaAvailableVersion",
    "otaAvailableVersionGitHash",
    "otaAvailableVersionNumber",
    "otaAvailableVersionWeek",
    "otaAvailableVersionYear",
    "otaCurrentStatus",
    "otaCurrentVersion",
    "otaCurrentVersionGitHash",
    "otaCurrentVersionNumber",
    "otaCurrentVersionWeek",
    "otaCurrentVersionYear",
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
    "tirePressureStatusFrontLeft",
    "tirePressureStatusFrontRight",
    "tirePressureStatusRearLeft",
    "tirePressureStatusRearRight",
    "tirePressureStatusValidFrontLeft",
    "tirePressureStatusValidFrontRight",
    "tirePressureStatusValidRearLeft",
    "tirePressureStatusValidRearRight",
    "trailerStatus",
    "twelveVoltBatteryHealth",
    "vehicleMileage",
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

VEHICLE_STATES_SUBSCRIPTION_ONLY_PROPERTIES: Final[set[str]] = {
    # TimeStamped(String|[Nullable]Float|Int)
    "activeDriverName",
    "chargingDisabledACFaultState",
    "chargingTimeEstimationValidity",
    "chargingTripTargetSoc",
    "chargingTripTargetMinsRemaining",
    "closureChargePortDoorNextAction",
    "coldRangeNotification",
    "tirePressureFrontLeft",
    "tirePressureFrontRight",
    "tirePressureRearLeft",
    "tirePressureRearRight",
}

VEHICLE_STATES_SUBSCRIPTION_PROPERTIES = (
    VEHICLE_STATE_PROPERTIES | VEHICLE_STATES_SUBSCRIPTION_ONLY_PROPERTIES
)

# The 12 fields of the TPMS subscription: the app's own 8, requested verbatim by
# its "subscription tirePressureState" operation
# (com.rivian.android.consumer/java_src/sh/C19721Z9.java:59, operationName at
# :81), plus the 4 tirePressureStatusValid* fields the server accepts but this
# APK build does not request (gateway.graphql:884-895) -- already on today's
# wire via VEHICLE_STATE_PROPERTIES.
TIRE_PRESSURE_SUBSCRIPTION_PROPERTIES: Final[frozenset[str]] = frozenset(
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

# The degraded document retried once when the full vehicleState subscription is
# rejected: one unknown field kills the whole document (const.py:1877 in
# the integration), so a single gateway field rename would otherwise take every
# sensor unknown at once. This ~15-name subset reduces the blast radius of that
# failure mode without eliminating it -- if the renamed field is itself one of
# these 15, the core document dies identically. Every name here must also exist
# in VEHICLE_STATE_PROPERTIES and be declared in gateway.graphql.
CORE_VEHICLE_STATE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "batteryLevel",
        "vehicleMileage",
        "powerState",
        "doorFrontLeftClosed",
        "doorFrontLeftLocked",
        "doorFrontRightClosed",
        "doorFrontRightLocked",
        "doorRearLeftClosed",
        "doorRearLeftLocked",
        "doorRearRightClosed",
        "doorRearRightLocked",
        "otaCurrentVersion",
        "gnssLocation",
        "chargerState",
        "distanceToEmpty",
    }
)


class VehicleCommand(StrEnum):
    """Supported vehicle commands."""

    WAKE_VEHICLE = "WAKE_VEHICLE"
    UNLOCK_USER_PREFERENCES_AND_DISABLE_ALARM = (
        "UNLOCK_USER_PREFERENCES_AND_DISABLE_ALARM"
    )

    HONK_AND_FLASH_LIGHTS = "HONK_AND_FLASH_LIGHTS"
    ACTIVATE_EXTERNAL_SOUND = "ACTIVATE_EXTERNAL_SOUND"
    FLASH_EXTERNAL_LIGHTS = "FLASH_EXTERNAL_LIGHTS"

    # Charging
    CHARGING_LIMITS = "CHARGING_LIMITS"
    START_CHARGING = "START_CHARGING"
    STOP_CHARGING = "STOP_CHARGING"

    # Climate
    CABIN_HVAC_DEFROST_DEFOG = "CABIN_HVAC_DEFROST_DEFOG"
    CABIN_HVAC_LEFT_SEAT_HEAT = "CABIN_HVAC_LEFT_SEAT_HEAT"
    CABIN_HVAC_LEFT_SEAT_VENT = "CABIN_HVAC_LEFT_SEAT_VENT"
    CABIN_HVAC_REAR_LEFT_SEAT_HEAT = "CABIN_HVAC_REAR_LEFT_SEAT_HEAT"
    CABIN_HVAC_REAR_RIGHT_SEAT_HEAT = "CABIN_HVAC_REAR_RIGHT_SEAT_HEAT"
    CABIN_HVAC_RIGHT_SEAT_HEAT = "CABIN_HVAC_RIGHT_SEAT_HEAT"
    CABIN_HVAC_RIGHT_SEAT_VENT = "CABIN_HVAC_RIGHT_SEAT_VENT"
    CABIN_HVAC_STEERING_HEAT = "CABIN_HVAC_STEERING_HEAT"
    CABIN_PRECONDITIONING_SET_TEMP = "CABIN_PRECONDITIONING_SET_TEMP"
    CLIMATE_HOLD_OFF = "CLIMATE_HOLD_OFF"
    CLIMATE_HOLD_ON = "CLIMATE_HOLD_ON"
    VEHICLE_CABIN_PRECONDITION_DISABLE = "VEHICLE_CABIN_PRECONDITION_DISABLE"
    VEHICLE_CABIN_PRECONDITION_ENABLE = "VEHICLE_CABIN_PRECONDITION_ENABLE"
    # Gen2 HVAC Controls
    CABIN_HVAC_THIRD_ROW_LEFT_SEAT_HEAT = "CABIN_HVAC_THIRD_ROW_LEFT_SEAT_HEAT"
    CABIN_HVAC_THIRD_ROW_RIGHT_SEAT_HEAT = "CABIN_HVAC_THIRD_ROW_RIGHT_SEAT_HEAT"
    # The spelling app 3.15.0 actually sends (VASCommandKt). ADDED ALONGSIDE the
    # THIRD_ROW pair above, not replacing it: the two names above appear in no
    # decompiled file of this build, which makes them a candidate for an older
    # firmware or an older app, and an app-side absence is the weakest evidence
    # there is -- the tonneau commands appear in no file either and physically
    # move the cover. Neither pair is wired to an entity yet; which one a given
    # vehicle accepts is a live question, and f6 answers it by testing.
    CABIN_HVAC_3RD_ROW_REAR_LEFT_SEAT_HEAT = "CABIN_HVAC_3RD_ROW_REAR_LEFT_SEAT_HEAT"
    CABIN_HVAC_3RD_ROW_REAR_RIGHT_SEAT_HEAT = "CABIN_HVAC_3RD_ROW_REAR_RIGHT_SEAT_HEAT"

    # Closures
    LOCK_ALL_CLOSURES_FEEDBACK = "LOCK_ALL_CLOSURES_FEEDBACK"
    UNLOCK_ALL_CLOSURES = "UNLOCK_ALL_CLOSURES"
    UNLOCK_DRIVER_DOOR = "UNLOCK_DRIVER_DOOR"
    UNLOCK_PASSENGER_DOOR = "UNLOCK_PASSENGER_DOOR"

    # Frunk
    CLOSE_FRUNK = "CLOSE_FRUNK"
    OPEN_FRUNK = "OPEN_FRUNK"

    # Gear guard
    ENABLE_GEAR_GUARD = "ENABLE_GEAR_GUARD"
    ENABLE_GEAR_GUARD_VIDEO = "ENABLE_GEAR_GUARD_VIDEO"
    DISABLE_GEAR_GUARD = "DISABLE_GEAR_GUARD"
    DISABLE_GEAR_GUARD_VIDEO = "DISABLE_GEAR_GUARD_VIDEO"
    # VASCommand.StartGearGuardMasterSession at :1350. Declared, not wired: it
    # starts a live camera session, which is a streaming feature this integration
    # has no surface for, not a control. Kept so the name is recorded.
    START_GEAR_GUARD_MASTER_SESSION = "START_GEAR_GUARD_MASTER_SESSION"

    # Liftgate (R1S only)
    CLOSE_LIFTGATE = "CLOSE_LIFTGATE"

    # Liftgate/tailgate
    OPEN_LIFTGATE_UNLATCH_TAILGATE = "OPEN_LIFTGATE_UNLATCH_TAILGATE"
    # The two the app also sends separately (VASCommand.OpenLiftgate at :710 and
    # VASCommand.UnlatchTailgate at :1560, both ordinary generateCloudDataWrapper
    # commands). The combined one above opens the liftgate AND unlatches the
    # tailgate; these two do one each, which is what an R1T owner wants for the
    # tailgate alone.
    OPEN_LIFTGATE = "OPEN_LIFTGATE"
    OPEN_TAILGATE = "OPEN_TAILGATE"

    # Chargeport door
    OPEN_CHARGE_PORT_DOOR = "OPEN_CHARGE_PORT_DOOR"
    CLOSE_CHARGE_PORT_DOOR = "CLOSE_CHARGE_PORT_DOOR"

    # OTA
    OTA_INSTALL_NOW_ACKNOWLEDGE = "OTA_INSTALL_NOW_ACKNOWLEDGE"

    # Panic
    PANIC_OFF = "PANIC_OFF"
    PANIC_ON = "PANIC_ON"

    # Side bin (R1T only)
    RELEASE_LEFT_SIDE_BIN = "RELEASE_LEFT_SIDE_BIN"
    RELEASE_RIGHT_SIDE_BIN = "RELEASE_RIGHT_SIDE_BIN"

    # Tonneau (Only for R1T with powered tonneau)
    CLOSE_TONNEAU_COVER = "CLOSE_TONNEAU_COVER"
    OPEN_TONNEAU_COVER = "OPEN_TONNEAU_COVER"

    # Windows
    CLOSE_ALL_WINDOWS = "CLOSE_ALL_WINDOWS"
    OPEN_ALL_WINDOWS = "OPEN_ALL_WINDOWS"
    UNLOCK_ALL_AND_OPEN_WINDOWS = "UNLOCK_ALL_AND_OPEN_WINDOWS"

    # Pet comfort
    PET_COMFORT_OFF = "PET_COMFORT_OFF"
    PET_COMFORT_ON = "PET_COMFORT_ON"

    # Video
    START_VIDEO_DOWNLOADING_SESSION = "START_VIDEO_DOWNLOADING_SESSION"

    # Two-factor drive
    TWO_FACTOR_DRIVE_ALLOW = "TWO_FACTOR_DRIVE_ALLOW"
    TWO_FACTOR_DRIVE_DENY = "TWO_FACTOR_DRIVE_DENY"
    TWO_FACTOR_DRIVE_DISABLE = "TWO_FACTOR_DRIVE_DISABLE"
    TWO_FACTOR_DRIVE_ENABLE = "TWO_FACTOR_DRIVE_ENABLE"
