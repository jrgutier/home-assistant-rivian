"""Defence in depth: nothing token-shaped reaches the log, even if an exception
slips past the constructor.

The real fix lives in the client: RivianApiException redacts headers and request
bodies as it is built, and that is verified against the live API. This is the
second line -- the coordinator logs exceptions with exc_info=1, and an exception
raised somewhere that does NOT go through that constructor (a bare aiohttp error
carrying a URL with a token in it, say) would otherwise render in full.

It exists because the disclosure it guards was live for the whole of this project's
history and nobody noticed until an exception was read closely.
"""

from contextlib import suppress
import logging

from custom_components.rivian.helpers import redact_text

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abcdefghijklmnopqrstuvwxyz012345"
SESSION = "0123456789abcdef0123456789abcdef0123"


class TestRedactText:
    def test_a_long_token_like_run_is_masked(self) -> None:
        assert TOKEN not in redact_text(f"failed with A-Sess={TOKEN}")

    def test_a_session_id_is_masked(self) -> None:
        assert SESSION not in redact_text(f"u-sess {SESSION} rejected")

    def test_ordinary_diagnostics_survive(self) -> None:
        """Redaction that eats the message is useless -- the point is to keep the
        error readable."""
        text = redact_text("HTTP 401 UNAUTHENTICATED while calling getUserInfo")
        assert "401" in text
        assert "UNAUTHENTICATED" in text
        assert "getUserInfo" in text

    def test_short_identifiers_are_not_eaten(self) -> None:
        # Vehicle ids and command names are short and diagnostic; masking them
        # would make every log line useless.
        assert "01-276948064" in redact_text("vehicle 01-276948064 is asleep")

    def test_it_is_marked_not_silently_dropped(self) -> None:
        assert "REDACTED" in redact_text(f"token={TOKEN}").upper()

    def test_none_and_empty_are_safe(self) -> None:
        assert redact_text("") == ""


class TestDiagnosticsPayloadRedaction:
    """The dict-level counterpart to redact_text: TO_REDACT / redact() in
    helpers.py, which diagnostics.py runs over the whole coordinator-data
    payload it dumps.

    wifiSsid and geoLocation are literal field names in that payload.
    gnssError's four sub-fields (rivian_client/schemas/gateway.graphql:545-551)
    have no sensor description yet -- nothing publishes them into coordinator
    data today -- so this only proves the mechanism: async_redact_data
    recurses into nested Mapping/list values and matches by bare key name at
    any depth, not a dotted path, so listing the bare sub-field names in
    TO_REDACT is what will catch them the moment a description exists.
    """

    def test_wifi_ssid_and_geo_location_are_redacted(self) -> None:
        from custom_components.rivian.helpers import redact

        payload = {"wifiSsid": {"value": "MyHomeNetwork"}, "geoLocation": "secret"}
        redacted = redact(payload)
        assert "MyHomeNetwork" not in str(redacted)
        assert "secret" not in str(redacted)

    def test_a_nested_gnss_error_field_is_redacted_by_bare_key(self) -> None:
        """Proves the mechanism ahead of the sensors: a bare sub-field name in
        TO_REDACT reaches into a nested dict without any dotted-path syntax."""
        from custom_components.rivian.helpers import redact

        payload = {
            "gnssError": {
                "timeStamp": "2024-01-01T00:00:00Z",
                "bearing": 12.3,
                "speed": 4.5,
                "positionHorizontal": 1.1,
                "positionVertical": 2.2,
            }
        }
        redacted = redact(payload)["gnssError"]
        assert redacted["bearing"] == "**REDACTED**"
        assert redacted["speed"] == "**REDACTED**"
        assert redacted["positionHorizontal"] == "**REDACTED**"
        assert redacted["positionVertical"] == "**REDACTED**"
        # Untouched: only the four sensitive sub-fields are named in TO_REDACT.
        assert redacted["timeStamp"] == "2024-01-01T00:00:00Z"


class TestTheCoordinatorUsesIt:
    async def test_an_unredacted_exception_does_not_reach_the_log(
        self, hass, mock_config_entry, caplog
    ) -> None:
        """An exception built OUTSIDE the client's constructor still must not
        render a token."""
        from unittest.mock import AsyncMock, MagicMock

        from custom_components.rivian.coordinator import UserCoordinator

        api = MagicMock()
        api.get_user_information = AsyncMock(
            side_effect=RuntimeError(f"connect failed: A-Sess={TOKEN}")
        )
        coordinator = UserCoordinator(
            hass=hass, config_entry=mock_config_entry, client=api
        )
        # Whether it raises is not what is under test -- the log content is.
        with caplog.at_level(logging.ERROR), suppress(Exception):
            await coordinator._async_update_data()
        assert TOKEN not in caplog.text
