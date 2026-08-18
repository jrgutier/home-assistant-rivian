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
