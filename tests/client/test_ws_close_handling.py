"""How the monitor reacts to the server's close codes.

All four codes below were MEASURED against wss://api.rivian.com, not taken from
the spec:

  4401 Unauthorized                     -- sent when we subscribe before the ack
  4403 Forbidden                        -- sent ~0.5s after a malformed u-sess
  4408 Connection initialization timeout -- sent when no connection_init arrives
  4420 Connection TTL expired           -- sent to a healthy idle connection

The old code recognised only the reason string "Unauthenticated", which is none
of these. So an auth rejection was treated as a transient drop and retried
forever -- and because `attempt` was reset to 0 whenever the socket merely
OPENED, a 4403 arriving half a second later never reached the backoff. That is a
tight reconnect loop against Rivian's API.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from aiohttp import WSMsgType
import pytest

from custom_components.rivian.rivian_client.ws_monitor import (
    AUTH_CLOSE_CODES,
    TTL_CLOSE_CODE,
    WebSocketMonitor,
)


def _close(code: int, reason: str) -> MagicMock:
    msg = MagicMock()
    msg.type = WSMsgType.CLOSE
    msg.data = code
    msg.extra = reason
    return msg


def _monitor(close_msg) -> WebSocketMonitor:
    account = MagicMock()
    account.request_timeout = 0.05
    account._session = MagicMock()
    ws = MagicMock()
    ws.closed = False
    ws.receive = AsyncMock(return_value=close_msg)
    monitor = WebSocketMonitor(account, "wss://example.invalid", AsyncMock())
    monitor._ws = ws
    return monitor


class TestAuthCloseCodesStopTheLoop:
    @pytest.mark.parametrize(
        ("code", "reason"), [(4401, "Unauthorized"), (4403, "Forbidden")]
    )
    async def test_auth_rejection_sets_disconnect(self, code, reason) -> None:
        # Without this the monitor reconnects into the same rejection forever.
        monitor = _monitor(_close(code, reason))
        await monitor._receiver()
        assert monitor._disconnect is True

    async def test_the_legacy_reason_string_is_still_honoured(self) -> None:
        # Upstream keyed on this exact string; keep it working.
        monitor = _monitor(_close(1000, "Unauthenticated"))
        await monitor._receiver()
        assert monitor._disconnect is True


class TestTtlIsRoutine:
    async def test_ttl_expiry_does_not_stop_the_monitor(self) -> None:
        # 4420 arrives on every healthy connection roughly every three minutes.
        # Treating it as fatal would take the integration down on a timer.
        monitor = _monitor(_close(TTL_CLOSE_CODE, "Connection TTL expired"))
        await monitor._receiver()
        assert monitor._disconnect is False

    async def test_an_ordinary_close_does_not_stop_the_monitor(self) -> None:
        monitor = _monitor(_close(1006, "Abnormal closure"))
        await monitor._receiver()
        assert monitor._disconnect is False


class _RejectedSocket:
    """A socket the server accepts and then rejects.

    Reports open for the monitor's first `closed` check -- which is what made the
    old code reset its backoff counter -- and closed on every check after,
    standing in for the 4403 that lands about half a second later.
    """

    def __init__(self) -> None:
        self._checks = 0

    @property
    def closed(self) -> bool:
        self._checks += 1
        return self._checks > 1


class TestBackoffIsNotResetByAMereOpen:
    async def test_attempts_keep_climbing_when_the_ack_never_arrives(
        self, monkeypatch
    ) -> None:
        """The storm's real cause: `attempt = 0` on connection, not on success.

        The server accepts the upgrade and only then rejects, so the socket looks
        open when the monitor inspects it. If backoff keys on "opened" rather than
        "acknowledged", every rejection resets the counter and the monitor
        reconnects flat out. Asserting the ATTEMPT SEQUENCE rather than wall-clock
        sleeps keeps this test fast and honest.
        """
        import custom_components.rivian.rivian_client.ws_monitor as mod

        account = MagicMock()
        account.request_timeout = 0.01  # the ack never arrives
        monitor = mod.WebSocketMonitor(account, "wss://example.invalid", AsyncMock())
        monitor._resubscribe_all = AsyncMock()

        reconnects = 0

        async def fake_new_connection(start_monitor: bool = False) -> None:
            # Bound the loop from the RECONNECT side, not the backoff side.
            # Without the ack gate the monitor never reaches an await that yields
            # to the event loop, so asyncio.wait_for can never fire and the
            # regression shows up as a hung test rather than a failing one.
            nonlocal reconnects
            reconnects += 1
            if reconnects >= 6:
                monitor._disconnect = True
            monitor._ws = _RejectedSocket()
            await asyncio.sleep(0)

        monitor.new_connection = fake_new_connection

        attempts: list[int] = []

        def record(attempt: int) -> float:
            attempts.append(attempt)
            return 0.0  # no real waiting

        # Patch OUR module's symbol, never asyncio.sleep: assigning to
        # rivian.ws_monitor.asyncio.sleep patches the global asyncio module and
        # breaks asyncio.wait_for for the whole session.
        monkeypatch.setattr(mod, "backoff_delay", record)

        await asyncio.wait_for(monitor._monitor(), timeout=5)

        assert attempts, "never backed off at all"
        assert attempts == sorted(attempts), f"attempts not monotonic: {attempts}"
        assert attempts[-1] > attempts[0], (
            f"backoff counter reset instead of climbing: {attempts}"
        )

    def test_backoff_is_capped(self) -> None:
        from custom_components.rivian.rivian_client.ws_monitor import backoff_delay

        assert backoff_delay(0) < 3
        assert backoff_delay(50) == 300


def test_the_measured_codes_are_the_ones_encoded() -> None:
    """Guards the constants against a well-meaning edit."""
    assert AUTH_CLOSE_CODES == frozenset({4401, 4403})
    assert TTL_CLOSE_CODE == 4420
