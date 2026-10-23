from __future__ import annotations

import asyncio as async_timeout
import base64
from collections.abc import Awaitable, Callable, Set as AbstractSet
import logging
import socket
import time
from typing import Any, Self
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
    RivianGraphQLError,
    RivianInvalidCredentials,
    RivianInvalidOTP,
    RivianPhoneLimitReachedError,
    RivianTemporarilyLockedError,
    RivianUnauthenticated,
)
from .parallax import PARALLAX_RVMS, ParallaxCommand, build_climate_hold_command
from .proto.vehicle_operation import (
    Metadata,
    Operation,
    PhoneInfo,
    VehicleOperationRequest,
)
from .utils import base64_encode, generate_vehicle_command_hmac
from .ws_monitor import WebSocketMonitor

_LOGGER = logging.getLogger(__name__)

GRAPHQL_BASEPATH = "https://rivian.com/api/gql"
GRAPHQL_GATEWAY = GRAPHQL_BASEPATH + "/gateway/graphql"
GRAPHQL_CHARGING = GRAPHQL_BASEPATH + "/chrg/user/graphql"
GRAPHQL_WEBSOCKET = "wss://api.rivian.com/gql-consumer-subscriptions/graphql"

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
    "INTERNAL_SERVER_ERROR": RivianGraphQLError,
    "RATE_LIMIT": RivianApiRateLimitError,
    "SESSION_MANAGER_ERROR": RivianTemporarilyLockedError,
    "UNAUTHENTICATED": RivianUnauthenticated,
}


def send_deprecation_warning(old_name: str, new_name: str) -> None:  # pragma: no cover
    message = f"{old_name} has been deprecated in favor of {new_name}, the alias will be removed in the future"
    warn(
        message,
        DeprecationWarning,
        stacklevel=2,
    )
    _LOGGER.warning(message)


class Rivian:
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

    @property
    def access_token(self) -> str:
        return self._access_token

    @property
    def refresh_token(self) -> str:
        return self._refresh_token

    @property
    def user_session_token(self) -> str:
        return self._user_session_token

    @property
    def otp_needed(self) -> bool:
        return self._otp_needed

    def _session_headers(self, *, csrf: bool = False) -> dict[str, str]:
        return (
            BASE_HEADERS
            | ({"Csrf-Token": self._csrf_token} if csrf else {})
            | {
                "A-Sess": self._app_session_token,
                "U-Sess": self._user_session_token,
            }
        )

    async def create_csrf_token(self) -> None:
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
        url = GRAPHQL_GATEWAY

        headers = BASE_HEADERS | {
            "Csrf-Token": self._csrf_token,
            "A-Sess": self._app_session_token,
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
        send_deprecation_warning("authenticate_graphql", "authenticate")
        return await self.authenticate(username=username, password=password)

    async def validate_otp(self, username: str, otp_code: str) -> None:
        url = GRAPHQL_GATEWAY

        headers = BASE_HEADERS | {
            "Csrf-Token": self._csrf_token,
            "A-Sess": self._app_session_token,
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
        send_deprecation_warning("validate_otp_graphql", "validate_otp")
        return await self.validate_otp(username=username, otp_code=otpCode)

    async def disenroll_phone(self, identity_id: str) -> bool:
        url = GRAPHQL_GATEWAY
        headers = self._session_headers(csrf=True)
        graphql_json = {
            "operationName": "DisenrollPhone",
            "variables": {"attrs": {"enrollmentId": identity_id}},
            "query": "mutation DisenrollPhone($attrs: DisenrollPhoneAttributes!) { disenrollPhone(attrs: $attrs) { __typename success } }",
        }

        response = await self.__graphql_query(headers, url, graphql_json)
        if response.status == 200:
            data = await response.json()
            return ((data.get("data") or {}).get("disenrollPhone") or {}).get("success")
        return False

    async def enroll_phone(
        self,
        user_id: str,
        vehicle_id: str,
        device_type: str,
        device_name: str,
        public_key: str,
    ) -> bool:
        url = GRAPHQL_GATEWAY
        headers = self._session_headers(csrf=True)
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
            if ((data.get("data") or {}).get("enrollPhone") or {}).get("success"):
                return True
        return False

    async def get_drivers_and_keys(self, vehicle_id: str) -> ClientResponse:
        url = GRAPHQL_GATEWAY
        headers = self._session_headers()

        graphql_json = {
            "operationName": "DriversAndKeys",
            "query": "query DriversAndKeys($vehicleId:String){getVehicle(id:$vehicleId){__typename id vin invitedUsers{__typename...on ProvisionedUser{firstName lastName email roles userId devices{type mappedIdentityId id hrid deviceName isPaired isEnabled}}...on UnprovisionedUser{email inviteId status}}}}",
            "variables": {"vehicleId": vehicle_id},
        }

        return await self.__graphql_query(headers, url, graphql_json)

    async def get_user_information(
        self, include_phones: bool = False
    ) -> ClientResponse:
        url = GRAPHQL_GATEWAY

        headers = self._session_headers()

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
        except RivianGraphQLError:
            _LOGGER.warning(
                "getUserInfo: mobileConfiguration option-code fragment rejected; "
                "retrying once without it"
            )
            self._option_codes_available = False
            return await self.__graphql_query(
                headers, url, _query(with_option_codes=False)
            )

    def option_codes_available(self) -> bool | None:
        return self._option_codes_available

    async def get_supported_features(self) -> ClientResponse:
        url = GRAPHQL_GATEWAY

        headers = self._session_headers()

        graphql_json = {
            "operationName": "SupportedFeatures",
            "query": "query SupportedFeatures { currentUser { vehicles { id vehicle { vehicleState { supportedFeatures { name status } } } } } }",
            "variables": None,
        }

        return await self.__graphql_query(headers, url, graphql_json)

    async def get_registered_wallboxes(self) -> ClientResponse:
        url = GRAPHQL_CHARGING

        headers = self._session_headers(csrf=True)

        graphql_json = {
            "operationName": "getRegisteredWallboxes",
            "query": "query getRegisteredWallboxes {\n  getRegisteredWallboxes {\n    __typename\n    wallboxId\n    userId\n    wifiId\n    name\n    linked\n    latitude\n    longitude\n    chargingStatus\n    power\n    currentVoltage\n    currentAmps\n    softwareVersion\n    model\n    serialNumber\n    maxAmps\n    maxVoltage\n    maxPower\n  }\n}",
            "variables": None,
        }

        return await self.__graphql_query(headers, url, graphql_json)

    async def get_vehicle_command_state(self, command_id: str) -> ClientResponse:
        url = GRAPHQL_GATEWAY

        headers = self._session_headers()

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
        url = GRAPHQL_GATEWAY

        headers = self._session_headers()

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

    async def get_charging_schedules(self, vehicle_id: str) -> ClientResponse:
        url = GRAPHQL_GATEWAY
        headers = self._session_headers()
        graphql_json = {
            "operationName": "getVehicleChargingSchedules",
            "query": "query getVehicleChargingSchedules($vehicleId: String!) {\n  getVehicle(id: $vehicleId) {\n    chargingSchedules {\n      weekDays\n      startTime\n      duration\n      location {\n        latitude\n        longitude\n      }\n      amperage\n      enabled\n    }\n  }\n}",
            "variables": {"vehicleId": vehicle_id},
        }
        return await self.__graphql_query(headers, url, graphql_json)

    async def set_charging_schedules(
        self, vehicle_id: str, schedules: list[dict[str, Any]]
    ) -> ClientResponse:
        url = GRAPHQL_GATEWAY
        headers = self._session_headers(csrf=True)
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
        url = GRAPHQL_GATEWAY
        headers = self._session_headers()

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
        self._validate_vehicle_command(command, params)

        command = str(command)
        timestamp = str(int(time.time()))
        hmac = generate_vehicle_command_hmac(
            command, timestamp, vehicle_key, private_key
        )

        url = GRAPHQL_GATEWAY
        headers = self._session_headers(csrf=True)
        graphql_json = {
            "operationName": "sendVehicleCommand",
            "variables": {
                "attrs": {
                    "command": command,
                    "hmac": hmac,
                    "timestamp": timestamp,
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
            if status := (data.get("data") or {}).get("sendVehicleCommand"):
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
        payload = {
            "operationName": "VehicleState",
            "query": f"subscription VehicleState($vehicleID: String!) {{ vehicleState(id: $vehicleID) {self._build_vehicle_state_fragment(properties)} }}",
            "variables": {"vehicleID": vehicle_id},
        }
        return await self._start_subscription(
            payload, callback, "%s subscribed to updates", vehicle_id
        )

    def subscription_document(self, vehicle_id: str) -> str | None:
        return self._subscriptions.get(vehicle_id)

    async def subscribe_for_tire_pressure_updates(
        self,
        vehicle_id: str,
        callback: Callable[[dict[str, Any]], None],
        properties: AbstractSet[str] | None = None,
    ) -> Callable | None:
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
                response_json = await response.json()
        except TimeoutError as exception:
            raise RivianApiException(
                "Timeout occurred while connecting to Rivian API."
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            raise RivianApiException(
                "Error occurred while communicating with Rivian."
            ) from exception
        except ValueError as exception:
            raise RivianApiException(
                "Rivian returned a response that is not valid JSON."
            ) from exception

        if not isinstance(response_json, dict):
            raise RivianApiException(
                "Rivian returned a response that is not a JSON object."
            )

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
            raise RivianGraphQLError(
                "Error occurred while reading the graphql response from Rivian.",
                response.status,
                response_json,
                headers,
                body,
            )

        return response

    async def send_vehicle_operation(
        self,
        vehicle_id: str,
        rvm_type: str,
        payload: bytes,
        phone_id: bytes,
        request_id: str | None = None,
    ) -> dict:
        op_type = 0 if not payload else 1

        phone_info = PhoneInfo(version=1, phone_id=phone_id)
        metadata = Metadata(
            phone_info=phone_info,
            request_id=request_id or str(uuid.uuid4()),
        )
        operation = Operation(
            rvm_type=rvm_type,
            operation_type=op_type,
            payload=payload,
        )
        request = VehicleOperationRequest(metadata=metadata, operation=operation)
        request_b64 = base64_encode(request.SerializeToString())

        url = GRAPHQL_GATEWAY
        headers = self._session_headers()
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
        return (data.get("data") or {}).get("sendVehicleOperation") or {}

    async def send_parallax_command(
        self,
        vehicle_id: str,
        parallax_cmd: ParallaxCommand,
        phone_id: bytes,
    ) -> dict:
        payload = (
            base64.b64decode(parallax_cmd.payload_b64)
            if parallax_cmd.payload_b64
            else b""
        )

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
        cmd = build_climate_hold_command(duration_minutes=duration_minutes)
        return await self.send_parallax_command(vehicle_id, cmd, phone_id)

    async def subscribe_for_charging_session(
        self,
        vehicle_id: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> Callable | None:
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
        url = GRAPHQL_GATEWAY
        headers = self._session_headers()
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
        return (data.get("data") or {}).get("parseAndShareLocationToVehicle") or {}

    async def close(self) -> None:
        if self._ws_monitor:
            await self._ws_monitor.close()
        if self._session and self._close_session:
            await self._session.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc_info) -> None:
        await self.close()

    def _build_vehicle_state_fragment(self, properties: AbstractSet[str]) -> str:
        frag = " ".join(
            f"{p} {TEMPLATE_MAP.get(p, VALUE_TEMPLATE)}" for p in properties
        )
        return f"{{ {frag} }}"
