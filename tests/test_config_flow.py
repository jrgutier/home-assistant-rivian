"""Tests for Rivian config flow."""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
import voluptuous as vol

from custom_components.rivian.config_flow import (
    RivianFlowHandler,
    _get_schema_credential_fields,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant


class TestGetSchemaCredentialFields:
    """Test _get_schema_credential_fields function."""

    DEFAULTS = {CONF_USERNAME: "default@example.com", CONF_PASSWORD: "default"}

    @pytest.mark.parametrize(
        ("user_input", "expected"),
        [
            (None, {"username": "default@example.com", "password": "default"}),
            ({}, {"username": "default@example.com", "password": "default"}),
            (
                {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "userpass"},
                {"username": "user@example.com", "password": "userpass"},
            ),
        ],
        ids=["none", "empty", "user-input"],
    )
    def test_user_input_wins_over_the_defaults(self, user_input, expected) -> None:
        """None and {} fall back to default_dict; a supplied value overrides it.

        The old three tests asserted only `isinstance(schema, vol.Schema)`, which
        the function's return statement guarantees for every input -- so they could
        not tell the None branch from the override branch, the only thing this
        function decides.
        """
        schema = _get_schema_credential_fields(user_input, self.DEFAULTS)

        assert isinstance(schema, vol.Schema)
        assert {str(key): key.default() for key in schema.schema} == expected


class TestRivianFlowHandler:
    """Test RivianFlowHandler class."""

    def test_initialization(self, hass: HomeAssistant) -> None:
        """Test flow handler initialization."""
        flow = RivianFlowHandler()

        # Should initialize with empty data
        assert flow._data == {}
        assert flow._errors == {}
        assert flow._access_token is None
        assert flow._refresh_token is None
        assert flow._user_session_token is None

    def test_version(self) -> None:
        """Test flow handler version."""
        flow = RivianFlowHandler()

        assert flow.VERSION == 1

    def test_rivian_property_creates_client(self, hass: HomeAssistant) -> None:
        """Test rivian property creates client lazily."""
        flow = RivianFlowHandler()
        flow.hass = hass

        # First access should create client
        with patch("custom_components.rivian.config_flow.Rivian") as mock_rivian_class:
            mock_client = MagicMock()
            mock_rivian_class.return_value = mock_client

            with patch(
                "custom_components.rivian.config_flow.async_get_clientsession"
            ) as mock_get_session:
                mock_session = MagicMock()
                mock_get_session.return_value = mock_session

                client = flow.rivian

                # Should have called Rivian with session
                mock_rivian_class.assert_called_once_with(session=mock_session)
                assert client == mock_client

    def test_rivian_property_reuses_client(self, hass: HomeAssistant) -> None:
        """Test rivian property reuses existing client."""
        flow = RivianFlowHandler()
        flow.hass = hass

        mock_client = MagicMock()
        flow._rivian = mock_client

        # Should return existing client
        assert flow.rivian == mock_client

    def test_async_get_options_flow(self) -> None:
        """Test async_get_options_flow returns SchemaOptionsFlowHandler."""
        from homeassistant.helpers.schema_config_entry_flow import (
            SchemaOptionsFlowHandler,
        )

        mock_entry = MagicMock(spec=ConfigEntry)
        # Mock the options property
        type(mock_entry).options = PropertyMock(return_value={})

        flow_handler = RivianFlowHandler.async_get_options_flow(mock_entry)

        # Should return SchemaOptionsFlowHandler instance
        assert isinstance(flow_handler, SchemaOptionsFlowHandler)

    def test_vehicle_control_filter_includes_r1s_r1t_r2(self) -> None:
        """Enrollment/pairing widening, not the zone picker (CONF_ZONE)."""
        from custom_components.rivian.config_flow import OPTIONS_SCHEMA, R1S, R1T, R2
        from custom_components.rivian.const import CONF_VEHICLE_CONTROL

        key = next(
            k
            for k in OPTIONS_SCHEMA.schema
            if getattr(k, "schema", None) == CONF_VEHICLE_CONTROL
        )
        selector = OPTIONS_SCHEMA.schema[key]
        models = {item["model"] for item in selector.config["filter"]}
        assert models == {"R1S", "R1T", "R2"}
        assert selector.config["filter"] == [R1S, R1T, R2]

    async def test_show_credential_fields(self, hass: HomeAssistant) -> None:
        """Test _show_credential_fields method."""
        flow = RivianFlowHandler()
        flow.hass = hass

        result = await flow._show_credential_fields()

        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert "data_schema" in result
        assert result["errors"] == {}

    async def test_show_credential_fields_with_errors(
        self, hass: HomeAssistant
    ) -> None:
        """Test _show_credential_fields with errors."""
        flow = RivianFlowHandler()
        flow.hass = hass
        flow._errors = {"base": "test_error"}

        result = await flow._show_credential_fields()

        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert result["errors"] == {"base": "test_error"}

    async def test_show_otp_field(self, hass: HomeAssistant) -> None:
        """Test _show_otp_field method."""
        flow = RivianFlowHandler()
        flow.hass = hass

        result = await flow._show_otp_field()

        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert "data_schema" in result

    async def test_async_step_user_no_input(self, hass: HomeAssistant) -> None:
        """Test async_step_user with no input shows form."""
        flow = RivianFlowHandler()
        flow.hass = hass

        result = await flow.async_step_user(None)

        assert result["type"] == "form"
        assert result["step_id"] == "user"

    async def test_async_step_reauth(self, hass: HomeAssistant) -> None:
        """Test async_step_reauth shows credential form."""
        flow = RivianFlowHandler()
        flow.hass = hass

        user_input = {CONF_USERNAME: "test@example.com"}
        result = await flow.async_step_reauth(user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert flow._data[CONF_USERNAME] == "test@example.com"
