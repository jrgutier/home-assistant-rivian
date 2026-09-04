"""Asynchronous Python client for the Rivian API."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable, Set as AbstractSet
import logging
import socket
import sys
import time
from typing import Any
import uuid
from warnings import warn

import aiohttp
from aiohttp import ClientResponse, ClientWebSocketResponse

from .const import (
    CORE_VEHICLE_STATE_FIELDS,
    LIVE_SESSION_PROPERTIES,
    TIRE_PRESSURE_SUBSCRIPTION_PROPERTIES,
    VEHICLE_STATES_SUBSCRIPTION_PROPERTIES,
    VehicleCommand,
)
from .exceptions import (
    RivianApiException,
    RivianApiRateLimitError,
    RivianBadRequestError,
    RivianDataError,
    RivianInvalidCredentials,
    RivianInvalidOTP,
    RivianPhoneLimitReachedError,
    RivianTemporarilyLockedError,
    RivianUnauthenticated,
)
from .parallax import PARALLAX_RVMS, ParallaxCommand
from .proto.vehicle_operation import (
    Metadata,
    Operation,
    PhoneInfo,
    VehicleOperationRequest,
)
from .utils import generate_vehicle_command_hmac
from .ws_monitor import WebSocketMonitor

if sys.version_info >= (3, 11):
    import asyncio as async_timeout
    from typing import Self
else:
    import async_timeout
    from typing_extensions import Self


_LOGGER = logging.getLogger(__name__)

GRAPHQL_BASEPATH = "https://rivian.com/api/gql"
GRAPHQL_GATEWAY = GRAPHQL_BASEPATH + "/gateway/graphql"
GRAPHQL_CHARGING = GRAPHQL_BASEPATH + "/chrg/user/graphql"
GRAPHQL_WEBSOCKET = "wss://api.rivian.com/gql-consumer-subscriptions/graphql"

# 3.15.0 dj8.java:19 — Gear Guard live-stream signaling config.
GEAR_GUARD_LIVE_CONFIG_QUERY = (
    "subscription gearGuardRemoteConfig($vehicleId: String!, "
    "$commandId: String!) { gearGuardLiveConfig(vehicleId: "
    "$vehicleId, commandId: $commandId) { endpoint channelArn "
    "role iceServers { url username credential ttl } } }"
)

APOLLO_CLIENT_NAME = "com.rivian.ios.consumer-apollo-ios"

BASE_HEADERS = {
    "User-Agent": "RivianApp/707 CFNetwork/1237 Darwin/20.4.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Apollographql-Client-Name": APOLLO_CLIENT_NAME,
}

CLOUD_CONNECTION_TEMPLATE = "{ lastSync isOnline }"
LOCATION_TEMPLATE = "{ latitude longitude timeStamp isAuthorized }"
LOCATION_ERROR_TEMPLATE = (
    "{ timeStamp positionVertical positionHorizontal speed bearing }"
)
VALUE_TEMPLATE = "{ timeStamp value }"
TEMPLATE_MAP = {
    "cloudConnection": CLOUD_CONNECTION_TEMPLATE,
    "gnssLocation": LOCATION_TEMPLATE,
    "gnssError": LOCATION_ERROR_TEMPLATE,
}

LIVE_SESSION_VALUE_RECORD_KEYS = {
    "current",
    "currentMiles",
    "kilometersChargedPerHour",
    "power",
    "rangeAddedThisSession",
    "soc",
    "timeRemaining",
    "totalChargedEnergy",
    "vehicleChargerState",
}
VALUE_RECORD_TEMPLATE = "{ __typename value updatedAt }"

ERROR_CODE_CLASS_MAP: dict[str, type[RivianApiException]] = {
    "BAD_CURRENT_PASSWORD": RivianInvalidCredentials,
    "BAD_REQUEST_ERROR": RivianBadRequestError,
    "DATA_ERROR": RivianDataError,
    "INTERNAL_SERVER_ERROR": RivianApiException,
    "RATE_LIMIT": RivianApiRateLimitError,
    "SESSION_MANAGER_ERROR": RivianTemporarilyLockedError,
    "UNAUTHENTICATED": RivianUnauthenticated,
}


def send_deprecation_warning(old_name: str, new_name: str) -> None:  # pragma: no cover
    """Send a deprecation warning."""
    message = f"{old_name} has been deprecated in favor of {new_name}, the alias will be removed in the future"
    warn(
        message,
        DeprecationWarning,
        stacklevel=2,
    )
    _LOGGER.warning(message)


class Rivian:
    """Main class for the Rivian API Client"""

    def __init__(
        self,
        request_timeout: int = 10,
        session: aiohttp.client.ClientSession | None = None,
        *,
        access_token: str = "",
        refresh_token: str = "",
        csrf_token: str = "",
        app_session_token: str = "",
        user_session_token: str = "",
    ) -> None:
        self._session = session
        self._close_session = False

        self._access_token = access_token
        self._refresh_token = refresh_token
        self._csrf_token = csrf_token
        self._app_session_token = app_session_token
        self._user_session_token = user_session_token

        self.request_timeout = request_timeout

        self._otp_needed = False
        self._otp_token = ""

        self._ws_monitor: WebSocketMonitor | None = None
        self._subscriptions: dict[str, str] = {}
        self._option_codes_available: bool | None = None

    async def create_csrf_token(self) -> None:
        """Create cross-site-request-forgery (csrf) token."""
        url = GRAPHQL_GATEWAY

        headers = {**BASE_HEADERS}

        graphql_json = {
            "operationName": "CreateCSRFToken",
            "query": "mutation CreateCSRFToken {\n  createCsrfToken {\n    __typename\n    csrfToken\n    appSessionToken\n  }\n}",
            "variables": None,
        }

        response = await self.__graphql_query(headers, url, graphql_json)

        response_json = await response.json()

        csrf_data = response_json["data"]["createCsrfToken"]
        self._csrf_token = csrf_data["csrfToken"]
        self._app_session_token = csrf_data["appSessionToken"]

    async def authenticate(self, username: str, password: str) -> None:
        """Authenticate against the Rivian GraphQL API with Username and Password"""
        url = GRAPHQL_GATEWAY

        headers = BASE_HEADERS | {
            "Csrf-Token": self._csrf_token,
            "A-Sess": self._app_session_token,
            "Apollographql-Client-Name": APOLLO_CLIENT_NAME,
        }

        graphql_json = {
            "operationName": "Login",
            "query": "mutation Login($email: String!, $password: String!) {\n  login(email: $email, password: $password) {\n    __typename\n    ... on MobileLoginResponse {\n      __typename\n      accessToken\n      refreshToken\n      userSessionToken\n    }\n    ... on MobileMFALoginResponse {\n      __typename\n      otpToken\n    }\n  }\n}",
            "variables": {"email": username, "password": password},
        }

        response = await self.__graphql_query(headers, url, graphql_json)

        response_json = await response.json()

        login_data = response_json["data"]["login"]

        if "otpToken" in login_data:
            self._otp_needed = True
            self._otp_token = login_data["otpToken"]
        else:
            self._access_token = login_data["accessToken"]
            self._refresh_token = login_data["refreshToken"]
            self._user_session_token = login_data["userSessionToken"]

    async def authenticate_graphql(
        self, username: str, password: str
    ) -> None:  # pragma: no cover
        """### DEPRECATED (use `authenticate` instead)

        Authenticate against the Rivian GraphQL API with Username and Password.
        """
        send_deprecation_warning("authenticate_graphql", "authenticate")
        return await self.authenticate(username=username, password=password)

    async def validate_otp(self, username: str, otp_code: str) -> None:
        """Validates OTP against the Rivian GraphQL API with Username, OTP Code, and OTP Token"""
        url = GRAPHQL_GATEWAY

        headers = BASE_HEADERS | {
            "Csrf-Token": self._csrf_token,
            "A-Sess": self._app_session_token,
            "Apollographql-Client-Name": APOLLO_CLIENT_NAME,
        }

        graphql_json = {
            "operationName": "LoginWithOTP",
            "query": "mutation LoginWithOTP($email: String!, $otpCode: String!, $otpToken: String!) {\n  loginWithOTP(email: $email, otpCode: $otpCode, otpToken: $otpToken) {\n    __typename\n    ... on MobileLoginResponse {\n      __typename\n      accessToken\n      refreshToken\n      userSessionToken\n    }\n  }\n}",
            "variables": {
                "email": username,
                "otpCode": otp_code,
                "otpToken": self._otp_token,
            },
        }

        response = await self.__graphql_query(headers, url, graphql_json)

        response_json = await response.json()

        login_data = response_json["data"]["loginWithOTP"]

        self._access_token = login_data["accessToken"]
        self._refresh_token = login_data["refreshToken"]
        self._user_session_token = login_data["userSessionToken"]

    async def validate_otp_graphql(
        self, username: str, otpCode: str
    ) -> None:  # pragma: no cover
        """### DEPRECATED (use `validate_otp` instead)

        Validates OTP against the Rivian GraphQL API with Username, OTP Code, and OTP Token.
        """
        send_deprecation_warning("validate_otp_graphql", "validate_otp")
        return await self.validate_otp(username=username, otp_code=otpCode)

    async def disenroll_phone(self, identity_id: str) -> bool:
        """Disenroll a phone."""
        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "Csrf-Token": self._csrf_token,
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }
        graphql_json = {
            "operationName": "DisenrollPhone",
            "variables": {"attrs": {"enrollmentId": identity_id}},
            "query": "mutation DisenrollPhone($attrs: DisenrollPhoneAttributes!) { disenrollPhone(attrs: $attrs) { __typename success } }",
        }

        response = await self.__graphql_query(headers, url, graphql_json)
        if response.status == 200:
            data = await response.json()
            return data.get("data", {}).get("disenrollPhone", {}).get("success")
        return False

    async def enroll_phone(
        self,
        user_id: str,
        vehicle_id: str,
        device_type: str,
        device_name: str,
        public_key: str,
    ) -> bool:
        """Enroll a phone.

        To generate a public/private key for enrollment, use the `utils.generate_key_pair` function.
        The private key will need to be retained to sign commands sent via the `send_vehicle_command` method.
        To enable vehicle control, the phone will then also need to be paired locally via BLE,
        which can be done via `ble.pair_phone`.
        """
        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "Csrf-Token": self._csrf_token,
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }
        graphql_json = {
            "operationName": "EnrollPhone",
            "variables": {
                "attrs": {
                    "userId": user_id,
                    "vehicleId": vehicle_id,
                    "publicKey": public_key,
                    "type": device_type,
                    "name": device_name,
                }
            },
            "query": "mutation EnrollPhone($attrs: EnrollPhoneAttributes!) { enrollPhone(attrs: $attrs) { __typename success } }",
        }
        response = await self.__graphql_query(headers, url, graphql_json)
        if response.status == 200:
            data = await response.json()
            if data.get("data", {}).get("enrollPhone", {}).get("success"):
                return True
        return False

    async def get_drivers_and_keys(self, vehicle_id: str) -> ClientResponse:
        """Get drivers and keys."""
        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }

        graphql_json = {
            "operationName": "DriversAndKeys",
            "query": "query DriversAndKeys($vehicleId:String){getVehicle(id:$vehicleId){__typename id vin invitedUsers{__typename...on ProvisionedUser{firstName lastName email roles userId devices{type mappedIdentityId id hrid deviceName isPaired isEnabled}}...on UnprovisionedUser{email inviteId status}}}}",
            "variables": {"vehicleId": vehicle_id},
        }

        return await self.__graphql_query(headers, url, graphql_json)

    async def get_user_information(
        self, include_phones: bool = False
    ) -> ClientResponse:
        """Get user information.

        S19: the vehicle fragment also asks for `mobileConfiguration {
        tonneauOption wheelOption }`, which is how the app learns a vehicle's
        factory option codes (`java_src/.../UserVehicle.java:616-618` gates the
        powered tonneau with `tonneauOptionId.contains(TONNEAU_POWER_OPTION_ID)`
        -- substring, not equality; `get_vehicles()` in coordinator.py builds
        `option_codes` for that same containment check, never `==`).

        This rides on `getUserInfo`, which is setup-critical -- folding it in here
        instead of a separate `vehicleOrders` query costs zero extra round trips
        but means a schema drift in either new field would otherwise take the
        whole login down with it. So: try the extended fragment first; if the
        gateway rejects it, retry ONCE with the base fragment (no
        mobileConfiguration) and let setup succeed without option codes rather
        than not at all. `option_codes_available` records which one won so
        get_vehicles()/diagnostics can tell "asked and got none" (accepted,
        empty) apart from "never asked" (rejected, retried).
        """
        url = GRAPHQL_GATEWAY

        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }

        vehicle_fields = "__typename id vin modelYear make model expectedBuildDate plannedBuildDate expectedGeneralAssemblyStartDate actualGeneralAssemblyDate vehicleState { supportedFeatures { __typename name status } }"
        option_codes_fragment = "mobileConfiguration { tonneauOption { optionId optionName } wheelOption { optionId optionName } }"
        phones_fragment = "enrolledPhones { __typename vas { __typename vasPhoneId publicKey } enrolled { __typename deviceType deviceName vehicleId identityId shortName } }"
        _2fa_fragment = "registrationChannels { type }"

        def _query(*, with_option_codes: bool) -> dict[str, Any]:
            inner = vehicle_fields + (
                f" {option_codes_fragment}" if with_option_codes else ""
            )
            vehicles_fragment = (
                "vehicles { id vin name vas { __typename vasVehicleId "
                f"vehiclePublicKey }} roles state createdAt updatedAt vehicle {{ {inner} }} }}"
            )
            return {
                "operationName": "getUserInfo",
                "query": (
                    f"query getUserInfo {{ currentUser {{ __typename id {vehicles_fragment} "
                    f"{_2fa_fragment} {phones_fragment if include_phones else ''} }} }}"
                ),
                "variables": None,
            }

        try:
            response = await self.__graphql_query(
                headers, url, _query(with_option_codes=True)
            )
            self._option_codes_available = True
            return response
        except RivianApiException as ex:
            # Narrow on purpose: RATE_LIMIT, UNAUTHENTICATED, DATA_ERROR,
            # SESSION_MANAGER_ERROR and the rest of ERROR_CODE_CLASS_MAP are all
            # RivianApiException SUBCLASSES and must propagate immediately --
            # retrying a rate limit or an auth failure with a smaller query is
            # nonsensical and would double the damage. `type(ex) is
            # RivianApiException` (not isinstance) matches only the fallback raise
            # for a response the map has no class for -- which is what an unknown
            # field name in the query produces. INTERNAL_SERVER_ERROR also maps to
            # the bare class, so a genuine 500 retries once too; that costs one
            # extra request, not a wrong result, so it is accepted rather than
            # disambiguated further.
            if type(ex) is not RivianApiException:
                raise
            _LOGGER.warning(
                "getUserInfo: mobileConfiguration option-code fragment rejected; "
                "retrying once without it"
            )
            self._option_codes_available = False
            return await self.__graphql_query(
                headers, url, _query(with_option_codes=False)
            )

    def option_codes_available(self) -> bool | None:
        """Whether the last getUserInfo response included option codes.

        True once the extended (mobileConfiguration) fragment has been
        accepted; False after a rejection forced the fallback retry; None
        before get_user_information() has ever been called. Mirrors
        subscription_document()'s three-state signal so diagnostics can tell
        "never asked" apart from "asked and rejected".
        """
        return self._option_codes_available

    async def get_supported_features(self) -> ClientResponse:
        """Get the SupportedFeatures feed: every vehicle's capability list.

        The app fetches this as its own standalone query rather than relying
        on the supportedFeatures fragment embedded in getUserInfo's
        vehicleState (get_user_information above, `vehicles_fragment`).
        operationName "SupportedFeatures", sent byte-identical to
        com.rivian.android.consumer/java_src/sh/C19514J9.java:48 as given by
        the caller -- that decompile tree is not checked into this repo and
        was not present in the environment this method was written in, so
        the query below could not be independently verified against it.

        `status` is documented as taking only AVAILABLE or UPDATE_FIRMWARE.
        This is one additive capability signal among several, never a
        filter: feature absence here is not evidence of absent capability
        (see coordinator.py's SupportedFeaturesCoordinator docstring).
        """
        url = GRAPHQL_GATEWAY

        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }

        graphql_json = {
            "operationName": "SupportedFeatures",
            "query": "query SupportedFeatures { currentUser { vehicles { id vehicle { vehicleState { supportedFeatures { name status } } } } } }",
            "variables": None,
        }

        return await self.__graphql_query(headers, url, graphql_json)

    async def get_registered_wallboxes(self) -> ClientResponse:
        """Get registered wallboxes."""
        url = GRAPHQL_CHARGING

        headers = BASE_HEADERS | {
            "Csrf-Token": self._csrf_token,
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }

        graphql_json = {
            "operationName": "getRegisteredWallboxes",
            "query": "query getRegisteredWallboxes {\n  getRegisteredWallboxes {\n    __typename\n    wallboxId\n    userId\n    wifiId\n    name\n    linked\n    latitude\n    longitude\n    chargingStatus\n    power\n    currentVoltage\n    currentAmps\n    softwareVersion\n    model\n    serialNumber\n    maxAmps\n    maxVoltage\n    maxPower\n  }\n}",
            "variables": None,
        }

        return await self.__graphql_query(headers, url, graphql_json)

    async def get_vehicle_command_state(self, command_id: str) -> ClientResponse:
        """Get vehicle command state."""
        url = GRAPHQL_GATEWAY

        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }

        graphql_query = "query getVehicleCommand($id: String!) { getVehicleCommand(id: $id) { __typename id command createdAt state responseCode statusCode } }"

        graphql_json = {
            "operationName": "getVehicleCommand",
            "query": graphql_query,
            "variables": {"id": command_id},
        }

        return await self.__graphql_query(headers, url, graphql_json)

    async def get_vehicle_images(
        self,
        *,
        extension: str | None = None,
        resolution: str | None = None,
        vehicle_version: str | None = None,
        preorder_version: str | None = None,
    ) -> ClientResponse:
        """Get vehicle images.

        Known parameter values:
          - extension: `png`, `webp`
          - resolution: `@1x`, `@2x`, `@3x` (for png); `hdpi`, `xhdpi`, `xxhdpi`, `xxxhdpi` (for webp)
          - vehicle_version/preorder_version: `1`, `2` (all other values return v1 images)
        """
        url = GRAPHQL_GATEWAY

        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }

        graphql_query = "query getVehicleImages( $extension: String $resolution: String $versionForVehicle: String $versionForPreOrder: String ) { getVehicleOrderMobileImages( resolution: $resolution extension: $extension version: $versionForPreOrder ) { ...image } getVehicleMobileImages( resolution: $resolution extension: $extension version: $versionForVehicle ) { ...image } } fragment image on VehicleMobileImage { orderId vehicleId url extension resolution size design placement overlays { url overlay zIndex } }"

        graphql_json = {
            "operationName": "getVehicleImages",
            "query": graphql_query,
            "variables": {
                "extension": extension,
                "resolution": resolution,
                "versionForVehicle": vehicle_version,
                "versionForPreOrder": preorder_version,
            },
        }

        return await self.__graphql_query(headers, url, graphql_json)

    # get_vehicle_state was deleted by f4.
    #
    # It had no caller: coordinator.py's VehicleCoordinator._fetch_data raises
    # NotImplementedError("Polling VehicleState no longer allowed") because vehicle
    # state arrives over the subscription, and nothing else called it.
    #
    # It was also an unsound oracle. A field valid on the subscription and rejected
    # by the poll is not an invalid field, it is the wrong channel -- so answering
    # "does the server know this name?" with this method gave the wrong answer.
    #
    # If it is ever revived, fix this first: the elif branch called
    # `properties.difference_update(...)` on the caller's own set, stripping eleven
    # names -- including all four tire pressures -- from whatever was passed in.
    # (It never reached the module-level VEHICLE_STATE_PROPERTIES: that assignment
    # is in the `if` branch and the mutation in the `elif`.)

    async def get_charging_schedules(self, vehicle_id: str) -> ClientResponse:
        """Get charging schedules for a vehicle."""
        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }
        graphql_json = {
            "operationName": "getVehicleChargingSchedules",
            "query": "query getVehicleChargingSchedules($vehicleId: String!) {\n  getVehicle(id: $vehicleId) {\n    chargingSchedules {\n      weekDays\n      startTime\n      duration\n      location {\n        latitude\n        longitude\n      }\n      amperage\n      enabled\n    }\n  }\n}",
            "variables": {"vehicleId": vehicle_id},
        }
        return await self.__graphql_query(headers, url, graphql_json)

    async def set_charging_schedules(
        self, vehicle_id: str, schedules: list[dict[str, Any]]
    ) -> ClientResponse:
        """Set charging schedules for a vehicle."""
        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "Csrf-Token": self._csrf_token,
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }
        graphql_json = {
            "operationName": "setChargingSchedules",
            "query": "mutation setChargingSchedules($vehicleId: String!, $chargingSchedules: [InputChargingSchedule!]!) {\n  setChargingSchedules(vehicleId: $vehicleId, chargingSchedules: $chargingSchedules) {\n    __typename\n    success\n  }\n}",
            "variables": {
                "vehicleId": vehicle_id,
                "chargingSchedules": schedules,
            },
        }
        return await self.__graphql_query(headers, url, graphql_json)

    async def get_vehicle_ota_update_details(self, vehicle_id: str) -> ClientResponse:
        """Get vehicle OTA update details."""
        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }

        graphql_query = "query getOTAUpdateDetails($vehicleId:String!){getVehicle(id:$vehicleId){availableOTAUpdateDetails{url version locale}currentOTAUpdateDetails{url version locale}}}"

        graphql_json = {
            "operationName": "getOTAUpdateDetails",
            "query": graphql_query,
            "variables": {"vehicleId": vehicle_id},
        }

        return await self.__graphql_query(headers, url, graphql_json)

    async def get_live_charging_session(
        self, vin: str, properties: set[str] | None = None
    ) -> ClientResponse:
        """Get live charging session data."""
        if not properties:
            properties = LIVE_SESSION_PROPERTIES

        url = GRAPHQL_CHARGING
        headers = BASE_HEADERS | {"U-Sess": self._user_session_token}

        fragment = " ".join(
            f"{p} {VALUE_RECORD_TEMPLATE if p in LIVE_SESSION_VALUE_RECORD_KEYS else ''}"
            for p in properties
        )
        graphql_query = f"""
            query getLiveSessionData($vehicleId: ID!) {{
                getLiveSessionData(vehicleId: $vehicleId) {{
                    __typename
                    {fragment}
                }}
            }}"""

        graphql_json = {
            "operationName": "getLiveSessionData",
            "query": graphql_query,
            "variables": {"vehicleId": vin},
        }

        return await self.__graphql_query(headers, url, graphql_json)

    def _validate_vehicle_command(
        self, command: VehicleCommand | str, params: dict[str, Any] | None = None
    ) -> None:
        """Validate certian vehicle command/param combos."""
        if command == VehicleCommand.CHARGING_LIMITS and not (
            params
            and isinstance((limit := params.get("SOC_limit")), int)
            and 50 <= limit <= 100
        ):
            raise RivianBadRequestError(
                "Charging limit must include parameter `SOC_limit` with a valid value between 50 and 100"
            )
        if command in (
            VehicleCommand.CABIN_HVAC_DEFROST_DEFOG,
            VehicleCommand.CABIN_HVAC_LEFT_SEAT_HEAT,
            VehicleCommand.CABIN_HVAC_LEFT_SEAT_VENT,
            VehicleCommand.CABIN_HVAC_REAR_LEFT_SEAT_HEAT,
            VehicleCommand.CABIN_HVAC_REAR_RIGHT_SEAT_HEAT,
            VehicleCommand.CABIN_HVAC_RIGHT_SEAT_HEAT,
            VehicleCommand.CABIN_HVAC_RIGHT_SEAT_VENT,
            VehicleCommand.CABIN_HVAC_STEERING_HEAT,
        ) and not (
            params
            and isinstance((level := params.get("level")), int)
            and 0 <= level <= 4
        ):
            raise RivianBadRequestError(
                "HVAC setting must include parameter `level` with a valid value between 0 and 4"
            )
        if command == VehicleCommand.CABIN_PRECONDITIONING_SET_TEMP:
            if not (
                params
                and isinstance((temp := params.get("HVAC_set_temp")), (float, int))
                and (16 <= temp <= 29 or temp in (0, 63.5))
            ):
                raise RivianBadRequestError(
                    "HVAC setting must include parameter `HVAC_set_temp` with a valid value between 16 and 29 or 0/63.5 for LO/HI, respectively"
                )
            params["HVAC_set_temp"] = str(params["HVAC_set_temp"])

    async def send_vehicle_command(
        self,
        command: VehicleCommand | str,
        vehicle_id: str,
        phone_id: str,
        identity_id: str,
        vehicle_key: str,
        private_key: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> str | None:
        """Send a command to the vehicle.

        To generate a public/private key for commands, use the `utils.generate_key_pair` function.
        The public key will first need to be enrolled via the `enroll_phone` method, otherwise commands will fail.

        Certain commands may require additional details via the `params` mapping.
        Some known examples include:
          - `CABIN_HVAC_*`: params = {"level": 0..4} where 0 is off, 1 is on, 2 is low/level_1, 3 is medium/level_2 and 4 is high/level_3
          - `CABIN_PRECONDITIONING_SET_TEMP`: params = {"HVAC_set_temp": "deg_C"} where `deg_C` is a string value between 16 and 29 or 0/63.5 for LO/HI, respectively
          - `CHARGING_LIMITS`: params = {"SOC_limit": 50..100}
        """
        self._validate_vehicle_command(command, params)

        command = str(command)
        timestamp = str(int(time.time()))
        hmac = generate_vehicle_command_hmac(
            command, timestamp, vehicle_key, private_key
        )

        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "Csrf-Token": self._csrf_token,
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }
        graphql_json = {
            "operationName": "sendVehicleCommand",
            "variables": {
                "attrs": {
                    "command": command,
                    "hmac": hmac,
                    "timestamp": str(timestamp),
                    "vasPhoneId": phone_id,
                    "deviceId": identity_id,
                    "vehicleId": vehicle_id,
                }
                | ({"params": params} if params else {})
            },
            "query": "mutation sendVehicleCommand($attrs: VehicleCommandAttributes!) { sendVehicleCommand(attrs: $attrs) { __typename id command state } }",
        }

        response = await self.__graphql_query(headers, url, graphql_json)
        if response.status == 200:
            data = await response.json()
            if status := data.get("data", {}).get("sendVehicleCommand", {}):
                return status.get("id")
        return None

    async def subscribe_for_vehicle_updates(
        self,
        vehicle_id: str,
        callback: Callable[[dict[str, Any]], None],
        properties: AbstractSet[str] | None = None,
        *,
        allow_core_fallback: bool = True,
    ) -> Callable | None:
        """Open a web socket connection to receive updates.

        S1 mitigation, default ON: a subscription the gateway rejects is
        retried ONCE against CORE_VEHICLE_STATE_FIELDS (~15 names) before the
        failure is raised -- regardless of whether `properties` was left to
        its default or supplied explicitly, because the whole point of this
        mitigation is to survive a caller-supplied field set going bad. Pass
        `allow_core_fallback=False` to disable it (for a test or probe that
        wants strict, no-retry behaviour). One renamed/unknown field then
        costs a degraded-but-working integration rather than every
        vehicleState entity going unknown at once (const.py:2121: one
        unknown name rejects the whole document). This reduces that
        failure's blast radius; it does not eliminate it -- if the renamed
        field is itself one of the 15 core names, the core document is
        rejected identically and this still raises. Which document ended up
        live is readable afterwards via `subscription_document(vehicle_id)`.
        """
        if not properties:
            properties = VEHICLE_STATES_SUBSCRIPTION_PROPERTIES

        try:
            unsubscribe = await self._subscribe_vehicle_state_once(
                vehicle_id, callback, properties
            )
        except RivianApiException:
            if not allow_core_fallback:
                raise
            _LOGGER.warning(
                "%s: vehicleState subscription rejected; retrying once with "
                "the core field set",
                vehicle_id,
            )
            unsubscribe = await self._subscribe_vehicle_state_once(
                vehicle_id, callback, CORE_VEHICLE_STATE_FIELDS
            )
            self._subscriptions[vehicle_id] = "core"
            return unsubscribe

        self._subscriptions[vehicle_id] = "full"
        return unsubscribe

    async def _subscribe_vehicle_state_once(
        self,
        vehicle_id: str,
        callback: Callable[[dict[str, Any]], None],
        properties: AbstractSet[str],
    ) -> Callable | None:
        """The single-attempt body subscribe_for_vehicle_updates() retries."""
        payload = {
            "operationName": "VehicleState",
            "query": f"subscription VehicleState($vehicleID: String!) {{ vehicleState(id: $vehicleID) {self._build_vehicle_state_fragment(properties)} }}",
            "variables": {"vehicleID": vehicle_id},
        }
        return await self._start_subscription(
            payload, callback, "%s subscribed to updates", vehicle_id
        )

    def subscription_document(self, vehicle_id: str) -> str | None:
        """Which vehicleState document is live for `vehicle_id`.

        "full" or "core" once subscribe_for_vehicle_updates() has succeeded
        for that vehicle; None before that -- and None is NOT the same as
        "core": it means no successful subscribe has happened yet (never
        connected, or still connecting). Diagnostics must not collapse the
        two, or a never-connected vehicle would read as merely degraded.
        This is the S1 fallback's signal for the coordinator/diagnostics to
        report which document is live (see subscribe_for_vehicle_updates()'s
        docstring).

        Backed by `self._subscriptions`, declared in `__init__` but unwritten
        since the client was vendored in (s07) -- this method is its first
        reader and `subscribe_for_vehicle_updates()` its first writer, so
        there is no prior semantics for either to preserve.
        """
        return self._subscriptions.get(vehicle_id)

    async def subscribe_for_tire_pressure_updates(
        self,
        vehicle_id: str,
        callback: Callable[[dict[str, Any]], None],
        properties: AbstractSet[str] | None = None,
    ) -> Callable | None:
        """Open a web socket connection to receive tyre-pressure updates.

        A sibling of subscribe_for_vehicle_updates(), on its own subscription
        because that is what the app itself does: its "tirePressureState"
        operation (com.rivian.android.consumer/java_src/sh/C19721Z9.java:59,
        operationName at :81) selects only the 8 tirePressure* names, none of
        which appear in its main vehicleState document. Both subscriptions
        select the SAME root -- vehicleState(id:) -- which is what lets the
        coordinator merge their frames into one vehicle_info dict.

        The split halves the blast radius of the S1 failure mode
        (subscribe_for_vehicle_updates()'s docstring): an unknown field name
        in THIS document costs the 12 tyre-pressure entities, not every
        vehicleState entity, because the gateway rejects each document
        independently.

        Observation, deliberately not "fixed": subscribe_for_vehicle_updates()
        sends operationName "VehicleState" for a document also named
        "vehicleState" -- the gateway tolerates the mismatch today. This
        method instead sends the app's own operation name, "tirePressureState",
        byte-identical to C19721Z9.java. The two methods are inconsistent with
        each other on purpose: this one matches what the app actually sends,
        the older one is left alone because nothing suggests the gateway cares.
        """
        if not properties:
            properties = TIRE_PRESSURE_SUBSCRIPTION_PROPERTIES

        payload = {
            "operationName": "tirePressureState",
            "query": f"subscription tirePressureState($vehicleID: String!) {{ vehicleState(id: $vehicleID) {self._build_vehicle_state_fragment(properties)} }}",
            "variables": {"vehicleID": vehicle_id},
        }
        return await self._start_subscription(
            payload, callback, "%s subscribed to tire pressure updates", vehicle_id
        )

    async def subscribe_for_parallax_messages(
        self,
        vehicle_id: str,
        callback: Callable[[dict[str, Any]], None],
        rvms: list[str] | None = None,
    ) -> Callable[[], Awaitable[None]] | None:
        """Open a web socket connection to receive Parallax message updates."""
        if not rvms:
            rvms = PARALLAX_RVMS

        payload = {
            "operationName": "ParallaxMessages",
            "query": "subscription ParallaxMessages($vehicleId: String!, $rvms: [String!]) { parallaxMessages(vehicleId: $vehicleId, rvms: $rvms) { payload timestamp rvm } }",
            "variables": {
                "vehicleId": vehicle_id,
                "rvms": rvms,
            },
        }
        return await self._start_subscription(
            payload,
            callback,
            "%s subscribed to %d Parallax RVMs",
            vehicle_id,
            len(rvms),
        )

    async def _ws_connect(self) -> ClientWebSocketResponse[bool]:
        """Initiate a websocket connection."""

        async def connection_init(websocket: ClientWebSocketResponse[bool]) -> None:
            await websocket.send_json(
                {
                    "payload": {
                        "client-name": APOLLO_CLIENT_NAME,
                        "client-version": "1.13.0-1494",
                        "dc-cid": f"m-ios-{uuid.uuid4()}",
                        "u-sess": self._user_session_token,
                    },
                    "type": "connection_init",
                }
            )

        if not self._ws_monitor:
            self._ws_monitor = WebSocketMonitor(
                self, GRAPHQL_WEBSOCKET, connection_init
            )
        ws_monitor = self._ws_monitor
        if ws_monitor.websocket is None or ws_monitor.websocket.closed:
            await ws_monitor.new_connection(True)
            assert ws_monitor.websocket
        if ws_monitor.monitor is None or ws_monitor.monitor.done():
            await ws_monitor.start_monitor()
        return ws_monitor.websocket

    async def _start_subscription(
        self,
        payload: dict[str, Any],
        callback: Callable[[dict[str, Any]], None],
        log_message: str,
        *log_args: Any,
    ) -> Callable | None:
        """Connect, wait for the ack, and start `payload`'s subscription.

        The single body every subscribe_for_* shares. The except pair is the
        point: a RivianApiException is re-raised UNCHANGED so the coordinator's
        per-type handling (expired token, unauthenticated, rate limit) still
        sees the specific subclass rather than the base class; anything else
        becomes a RivianApiException, because returning None here made a dead
        subscription indistinguishable from a healthy one at every call site.
        """
        try:
            await self._ws_connect()
            assert self._ws_monitor
            async with async_timeout.timeout(self.request_timeout):
                await self._ws_monitor.connection_ack.wait()
            unsubscribe = await self._ws_monitor.start_subscription(payload, callback)
            _LOGGER.debug(log_message, *log_args)
            return unsubscribe
        except RivianApiException:
            raise
        except Exception as ex:
            raise RivianApiException("Failed to establish subscription") from ex

    async def __graphql_query(
        self, headers: dict[str, str], url: str, body: dict[str, Any]
    ) -> ClientResponse:
        """Execute and return arbitrary graphql query."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._close_session = True

        if "dc-cid" not in headers:
            headers["dc-cid"] = f"m-ios-{uuid.uuid4()}"

        try:
            async with async_timeout.timeout(self.request_timeout):
                response = await self._session.request(
                    "POST",
                    url,
                    json=body,
                    headers=headers,
                )
        except asyncio.TimeoutError as exception:
            raise RivianApiException(
                "Timeout occurred while connecting to Rivian API."
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            raise RivianApiException(
                "Error occurred while communicating with Rivian."
            ) from exception

        response_json = await response.json()
        if errors := response_json.get("errors"):
            for error in errors:
                if extensions := error.get("extensions"):
                    code = extensions.get("code")
                    if (code, extensions.get("reason")) in (
                        ("BAD_USER_INPUT", "INVALID_OTP"),
                        ("UNAUTHENTICATED", "OTP_TOKEN_EXPIRED"),
                    ):
                        raise RivianInvalidOTP(
                            response.status, response_json, headers, body
                        )
                    if (code, extensions.get("reason")) == (
                        "CONFLICT",
                        "ENROLL_PHONE_LIMIT_REACHED",
                    ):
                        raise RivianPhoneLimitReachedError(
                            response.status, response_json, headers, body
                        )
                    if err_cls := ERROR_CODE_CLASS_MAP.get(code):
                        raise err_cls(response.status, response_json, headers, body)
            raise RivianApiException(
                "Error occurred while reading the graphql response from Rivian.",
                response.status,
                response_json,
                headers,
                body,
            )

        return response

    # ------------------------------------------------------------------
    # Parallax write path and subscriptions carried over from this fork.
    #
    # Upstream 2.1.0 is Parallax read-only: it decodes telemetry but has no way
    # to send an operation, and it lacks the charging/cloud/command-state
    # subscriptions and the navigation share. Everything below is the half
    # upstream does not have, ported onto its plain-string transport.
    #
    # The gql DSL is gone. Of the 13 methods carried over, 11 never touched it
    # (the subscriptions already spoke raw aiohttp, and the Parallax setters just
    # delegate to send_parallax_command); only send_vehicle_operation and
    # send_location_to_vehicle were DSL and are rewritten as plain queries here.
    # ------------------------------------------------------------------

    async def send_vehicle_operation(
        self,
        vehicle_id: str,
        rvm_type: str,
        payload: bytes,
        phone_id: bytes,
        request_id: str | None = None,
    ) -> dict:
        """Send a vehicle operation via sendVehicleOperation mutation.

        This is the newer mutation used by the iOS app for climate hold and other
        RVM (Remote Vehicle Module) operations. It requires phone enrollment.

        Args:
            vehicle_id: Vehicle ID (format: "01-XXXXXXXX")
            rvm_type: RVM type string (e.g., "comfort.cabin.climate_hold_setting")
            payload: Serialized protobuf payload for the operation
            phone_id: 16-byte phone identifier from enrollment (UUID bytes)
            request_id: Optional request UUID (generated if not provided)
            operation_type: Operation type (1 = SET/write, 0 = GET/read)

        Returns:
            dict with 'success' (bool) key

        Raises:
            RivianApiException: For network or API errors
            RivianUnauthenticated: If authentication is invalid

        Example:
            >>> from rivian.parallax import encode_climate_hold_setting
            >>> # Get phone_id from enrollment -- 16 RAW BYTES, not the string
            >>> user_info = await client.get_user_information(include_phones=True)
            >>> phone_id_str = user_info["enrolledPhones"][0]["vas"]["vasPhoneId"]
            >>> import uuid
            >>> phone_id = uuid.UUID(phone_id_str).bytes
            >>> # Build payload (2 hours -> 08a038)
            >>> payload = encode_climate_hold_setting(7200)
            >>> # Send operation
            >>> result = await client.send_vehicle_operation(
            ...     vehicle_id="01-276948064",
            ...     rvm_type="comfort.cabin.climate_hold_setting",
            ...     payload=payload,
            ...     phone_id=phone_id
            ... )
            >>> print(f"Success: {result['success']}")
        """
        # Determine operation type based on payload - empty payload = GET, otherwise SET
        op_type = 0 if not payload else 1

        # Build VehicleOperationRequest
        phone_info = PhoneInfo(version=1, phone_id=phone_id)
        metadata = Metadata(
            phone_info=phone_info,
            request_id=request_id or str(uuid.uuid4()),
        )
        operation = Operation(
            rvm_type=rvm_type,
            operation_type=op_type,  # 0 = GET, 1 = SET
            payload=payload,
        )
        request = VehicleOperationRequest(metadata=metadata, operation=operation)
        request_b64 = base64.b64encode(request.SerializeToString()).decode("utf-8")

        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }
        graphql_query = (
            "mutation SendVehicleOperation($vehicleId:String!,$payload:String!){"
            "sendVehicleOperation(vehicleId:$vehicleId,payload:$payload){"
            "__typename ... on SendVehicleOperationSuccess{success}}}"
        )
        graphql_json = {
            "operationName": "SendVehicleOperation",
            "query": graphql_query,
            "variables": {"vehicleId": vehicle_id, "payload": request_b64},
        }

        response = await self.__graphql_query(headers, url, graphql_json)
        data = await response.json()
        return data.get("data", {}).get("sendVehicleOperation", {}) or {}

    async def send_parallax_command(
        self,
        vehicle_id: str,
        parallax_cmd: ParallaxCommand,
        phone_id: bytes,
    ) -> dict:
        """Send a Parallax command to a vehicle via sendVehicleOperation.

        Parallax commands use the sendVehicleOperation mutation which wraps
        the protobuf payload with phone enrollment info. This requires
        Bluetooth pairing to have been completed.

        Args:
            vehicle_id: Vehicle ID (format: "01-XXXXXXXX")
            parallax_cmd: ParallaxCommand instance with RVM type and payload
            phone_id: 16-byte phone identifier from enrollment

        Returns:
            dict with 'success' (bool) key

        Raises:
            RivianApiException: For network or API errors
            RivianUnauthenticated: If authentication is invalid

        Example:
            >>> from rivian.parallax import build_climate_hold_command
            >>> # Get phone_id from enrollment
            >>> user_info = await client.get_user_information(include_phones=True)
            >>> phone_id_hex = user_info["enrolledPhones"][0]["vas"]["vasPhoneId"]
            >>> phone_id = bytes.fromhex(phone_id_hex)
            >>> # Send command
            >>> cmd = build_climate_hold_command(duration_minutes=120)
            >>> result = await client.send_parallax_command("01-276948064", cmd, phone_id)
            >>> print(f"Success: {result['success']}")
        """
        # Decode the base64 payload from ParallaxCommand
        payload = (
            base64.b64decode(parallax_cmd.payload_b64)
            if parallax_cmd.payload_b64
            else b""
        )

        # Use sendVehicleOperation which wraps payload with phone info
        return await self.send_vehicle_operation(
            vehicle_id=vehicle_id,
            rvm_type=str(parallax_cmd.rvm),
            payload=payload,
            phone_id=phone_id,
        )

    async def set_climate_hold(
        self,
        vehicle_id: str,
        phone_id: bytes,
        duration_minutes: int = 120,
    ) -> dict:
        """Set climate hold via sendVehicleOperation.

        RVM: comfort.cabin.climate_hold_setting

        Args:
            vehicle_id: Vehicle ID (format: "01-XXXXXXXX")
            phone_id: 16-byte phone identifier from enrollment
                (uuid.UUID(vasPhoneId).bytes)
            duration_minutes: Hold duration in minutes

        Returns:
            dict with success status

        Note:
            ClimateHoldSetting carries exactly one field, hold_time_duration_seconds
            -- confirmed on the wire as 08a038 (7200s). `enabled` and `temp_celsius`
            parameters used to be accepted here and silently discarded; temp_celsius
            was even validated, so a caller could get a RivianBadRequestError for a
            value that was never sent. Both are removed rather than kept for
            "API compatibility" with behaviour that never existed. Enable state and
            target temperature are controlled through separate vehicle commands.

        Example:
            >>> # Get phone_id from enrollment
            >>> user_info = await client.get_user_information(include_phones=True)
            >>> phone_id_hex = user_info["enrolledPhones"][0]["vas"]["vasPhoneId"]
            >>> phone_id = bytes.fromhex(phone_id_hex)
            >>> # Set climate hold for 8 hours
            >>> result = await client.set_climate_hold(
            ...     vehicle_id="01-276948064",
            ...     phone_id=phone_id,
            ...     duration_minutes=480,
            ... )
            >>> print(f"Success: {result['success']}")
        """
        from .parallax import build_climate_hold_command

        cmd = build_climate_hold_command(duration_minutes=duration_minutes)
        return await self.send_parallax_command(vehicle_id, cmd, phone_id)

    async def subscribe_for_charging_session(
        self,
        vehicle_id: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> Callable | None:
        """Open a web socket connection to receive real-time charging session updates.

        Args:
            vehicle_id: The vehicle ID to subscribe to
            callback: Function called when subscription data is received

        Returns:
            Unsubscribe function or None if connection fails
        """
        payload = {
            "operationName": "ChargingSession",
            "query": "subscription ChargingSession($vehicleID: String!) { chargingSession(vehicleId: $vehicleID) { chartData { soc powerKW startTime endTime timeEstimationValidityStatus vehicleChargerState } liveData { powerKW kilometersChargedPerHour rangeAddedThisSession totalChargedEnergy timeElapsed timeRemaining price currency isFreeSession vehicleChargerState startTime } } }",
            "variables": {"vehicleID": vehicle_id},
        }
        return await self._start_subscription(
            payload,
            callback,
            "Vehicle %s subscribed to charging session updates",
            vehicle_id,
        )

    async def subscribe_for_cloud_connection(
        self,
        vehicle_id: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> Callable | None:
        """Open a web socket connection to receive vehicle cloud connectivity updates.

        Args:
            vehicle_id: The vehicle ID to subscribe to
            callback: Function called when subscription data is received

        Returns:
            Unsubscribe function or None if connection fails
        """
        payload = {
            "operationName": "VehicleCloudConnection",
            "query": "subscription VehicleCloudConnection($vehicleID: String!) { vehicleCloudConnection(id: $vehicleID) { isOnline lastSync } }",
            "variables": {"vehicleID": vehicle_id},
        }
        return await self._start_subscription(
            payload,
            callback,
            "Vehicle %s subscribed to cloud connection updates",
            vehicle_id,
        )

    async def subscribe_for_command_state(
        self,
        command_id: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> Callable | None:
        """Open a web socket connection to receive real-time vehicle command state updates.

        Args:
            command_id: The command ID to subscribe to
            callback: Function called when subscription data is received

        Returns:
            Unsubscribe function or None if connection fails
        """
        payload = {
            "operationName": "VehicleCommandState",
            "query": "subscription VehicleCommandState($id: String!) { vehicleCommandState(id: $id) { __typename id command createdAt state responseCode statusCode } }",
            "variables": {"id": command_id},
        }
        return await self._start_subscription(
            payload, callback, "Command %s subscribed to state updates", command_id
        )

    async def subscribe_gear_guard_live_config(
        self,
        vehicle_id: str,
        command_id: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> Callable | None:
        """Subscribe to the app's Gear Guard live-stream signaling config.

        Exact document: 3.15.0 `dj8.java:19` (`gearGuardRemoteConfig` /
        `gearGuardLiveConfig`). Frame carries KVS WebRTC signaling
        (`endpoint`, `channelArn`, `role`, `iceServers`). Callers must not
        log those fields; they are session credentials.
        """
        payload = {
            "operationName": "gearGuardRemoteConfig",
            "query": GEAR_GUARD_LIVE_CONFIG_QUERY,
            "variables": {"vehicleId": vehicle_id, "commandId": command_id},
        }
        return await self._start_subscription(
            payload,
            callback,
            "Vehicle %s command %s subscribed to gearGuardLiveConfig",
            vehicle_id,
            command_id,
        )

    async def send_location_to_vehicle(
        self,
        location_str: str,
        vehicle_id: str,
    ) -> dict[str, Any]:
        """Send a location or address to the vehicle's navigation system.

        Requires neither phone enrollment nor HMAC signing -- it is cloud-only and
        fire-and-forget. Success means Rivian's cloud accepted the message, not
        that the vehicle received it; the vehicle picks the destination up when it
        next connects.

        Args:
            location_str: Address ("123 Main St, Springfield, IL") or
                "latitude,longitude" ("40.7128,-74.0060").
            vehicle_id: Vehicle to send the location to.

        Returns:
            The parseAndShareLocationToVehicle payload; publishResponse.result is
            0 on success.
        """
        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }
        graphql_query = (
            "mutation parseAndShareLocationToVehicle($str:String!,$vehicleId:String!){"
            "parseAndShareLocationToVehicle(str:$str,vehicleId:$vehicleId){"
            "publishResponse{result}}}"
        )
        graphql_json = {
            "operationName": "parseAndShareLocationToVehicle",
            "query": graphql_query,
            "variables": {"str": location_str, "vehicleId": vehicle_id},
        }

        response = await self.__graphql_query(headers, url, graphql_json)
        data = await response.json()
        return data.get("data", {}).get("parseAndShareLocationToVehicle", {}) or {}

    async def close(self) -> None:
        """Close open client session."""
        if self._ws_monitor:
            await self._ws_monitor.close()
        if self._session and self._close_session:
            await self._session.close()

    async def __aenter__(self) -> Self:
        """Async enter.
        Returns:
            The Rivian object.
        """
        return self

    async def __aexit__(self, *_exc_info) -> None:
        """Async exit.
        Args:
            _exc_info: Exec type.
        """
        await self.close()

    def _build_vehicle_state_fragment(self, properties: AbstractSet[str]) -> str:
        """Build GraphQL vehicle state fragment from properties."""
        frag = " ".join(
            f"{p} {TEMPLATE_MAP.get(p, VALUE_TEMPLATE)}" for p in properties
        )
        return f"{{ {frag} }}"
