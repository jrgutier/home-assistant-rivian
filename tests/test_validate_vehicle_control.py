"""validate_vehicle_control: the gate to vehicle control working at all.

Enabling control here is what enrolls the phone and generates the signing key
pair. If it half-succeeds quietly, the user gets an integration that looks
configured for control and then fails every command -- so the interesting
behaviour is what happens when enrolment DOESN'T work.

It was 0% covered, which for the function that provisions the credentials behind
every HMAC-signed command is the wrong place to have no tests.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.rivian.config_flow import validate_vehicle_control
from homeassistant.helpers.schema_config_entry_flow import SchemaFlowError

VEHICLE_ID = "01-2769"
DEVICE_ID = "device-abc"


def _handler(hass, entry) -> MagicMock:
    handler = MagicMock()
    handler.parent_handler.hass = hass
    handler.parent_handler.config_entry = entry
    return handler


def _entry(options: dict | None = None) -> MagicMock:
    entry = MagicMock()
    entry.options = options if options is not None else {}
    return entry


def _user(*, registration_channels=True, enrolled=None, vehicles=None) -> MagicMock:
    user = MagicMock()
    user.async_refresh = AsyncMock()
    user.data = {
        "id": "user-1",
        "registrationChannels": ["EMAIL"] if registration_channels else [],
    }
    user.get_vehicles = MagicMock(
        return_value=vehicles
        if vehicles is not None
        else {VEHICLE_ID: {"id": VEHICLE_ID, "name": "R1T"}}
    )
    user.get_enrolled_phone_data = MagicMock(return_value=enrolled)
    return user


def _device_registry() -> MagicMock:
    device = MagicMock()
    device.identifiers = {("rivian", VEHICLE_ID)}
    registry = MagicMock()
    registry.async_get = MagicMock(return_value=device)
    return registry


async def _run(hass, entry, user_input, user, api):
    with (
        patch(
            "custom_components.rivian.config_flow.get_rivian_api_from_entry",
            return_value=api,
        ),
        patch(
            "custom_components.rivian.config_flow.UserCoordinator", return_value=user
        ),
        patch(
            "custom_components.rivian.config_flow.dr.async_get",
            return_value=_device_registry(),
        ),
    ):
        return await validate_vehicle_control(_handler(hass, entry), user_input)


@pytest.fixture
def api() -> MagicMock:
    api = MagicMock()
    api.enroll_phone = AsyncMock(return_value=True)
    api.disenroll_phone = AsyncMock(return_value=True)
    api.close = AsyncMock()
    return api


class TestPreconditions:
    async def test_enabling_control_without_2fa_is_refused(self, hass, api) -> None:
        """Vehicle control requires 2FA on the Rivian account. Proceeding without
        it would enroll a phone that can never sign a command."""
        with pytest.raises(SchemaFlowError, match="2fa_missing"):
            await _run(
                hass,
                _entry(),
                {"vehicle_control": [DEVICE_ID]},
                _user(registration_channels=False),
                api,
            )
        api.close.assert_awaited()

    async def test_no_2fa_is_fine_when_control_is_not_requested(
        self, hass, api
    ) -> None:
        out = await _run(
            hass,
            _entry(),
            {"vehicle_control": []},
            _user(registration_channels=False),
            api,
        )
        assert out == {"vehicle_control": []}


class TestKeyPair:
    async def test_a_key_pair_is_generated_on_first_enable(self, hass, api) -> None:
        """The private key signs every vehicle command; without one, control is
        configured but inert."""
        user_input = {"vehicle_control": [DEVICE_ID]}
        with patch(
            "custom_components.rivian.config_flow.generate_key_pair",
            return_value=("PUB", "PRIV"),
        ):
            out = await _run(hass, _entry(), user_input, _user(), api)
        assert out["public_key"] == "PUB"
        assert out["private_key"] == "PRIV"

    async def test_an_existing_key_pair_is_not_regenerated(self, hass, api) -> None:
        """Regenerating would invalidate the enrolment already on the vehicle."""
        entry = _entry({"private_key": "EXISTING", "public_key": "EXISTING_PUB"})
        with patch(
            "custom_components.rivian.config_flow.generate_key_pair",
            side_effect=AssertionError("must not regenerate"),
        ):
            out = await _run(
                hass, entry, {"vehicle_control": [DEVICE_ID]}, _user(), api
            )
        assert "private_key" not in out


class TestEnrolment:
    async def test_the_phone_is_enrolled_for_a_selected_vehicle(
        self, hass, api
    ) -> None:
        with patch(
            "custom_components.rivian.config_flow.generate_key_pair",
            return_value=("PUB", "PRIV"),
        ):
            await _run(hass, _entry(), {"vehicle_control": [DEVICE_ID]}, _user(), api)
        api.enroll_phone.assert_awaited_once()
        assert api.enroll_phone.await_args.kwargs["vehicle_id"] == VEHICLE_ID

    async def test_a_failed_enrolment_deselects_the_vehicle(self, hass, api) -> None:
        """Otherwise the options would claim control is enabled for a vehicle whose
        phone was never enrolled, and every command would fail later."""
        api.enroll_phone = AsyncMock(return_value=False)
        user_input = {"vehicle_control": [DEVICE_ID]}
        with patch(
            "custom_components.rivian.config_flow.generate_key_pair",
            return_value=("PUB", "PRIV"),
        ):
            out = await _run(hass, _entry(), user_input, _user(), api)
        assert out["vehicle_control"] == []

    async def test_the_phone_limit_is_reported_not_swallowed(self, hass, api) -> None:
        """Rivian caps enrolled phones; the user must be told to free a slot rather
        than see control silently not work."""
        from custom_components.rivian.rivian_client.exceptions import (
            RivianPhoneLimitReachedError,
        )

        api.enroll_phone = AsyncMock(side_effect=RivianPhoneLimitReachedError("limit"))
        with (
            patch(
                "custom_components.rivian.config_flow.generate_key_pair",
                return_value=("PUB", "PRIV"),
            ),
            pytest.raises(SchemaFlowError, match="phone_limit"),
        ):
            await _run(hass, _entry(), {"vehicle_control": [DEVICE_ID]}, _user(), api)
        api.close.assert_awaited()


class TestDisenrolment:
    async def test_deselecting_a_vehicle_disenrolls_the_phone(self, hass, api) -> None:
        entry = _entry({"private_key": "P", "public_key": "PUB"})
        user = _user(enrolled=("PUB", {VEHICLE_ID: "identity-1"}))
        await _run(hass, entry, {"vehicle_control": []}, user, api)
        api.disenroll_phone.assert_awaited_once_with(identity_id="identity-1")


class TestSessionHygiene:
    async def test_the_api_session_is_always_closed(self, hass, api) -> None:
        """Every exit path closes it -- a leaked aiohttp session outlives the flow."""
        entry = _entry({"private_key": "P", "public_key": "PUB"})
        await _run(
            hass, entry, {"vehicle_control": []}, _user(enrolled=("PUB", {})), api
        )
        api.close.assert_awaited()
