from __future__ import annotations

import asyncio
import asyncio as async_timeout
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import inspect
from json import loads
import logging
from random import uniform
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from aiohttp import ClientError, ClientWebSocketResponse, WSMessage, WSMsgType

if TYPE_CHECKING:
    from aiohttp.http_websocket import WSMessageTextBytes

    from .rivian import Rivian

_LOGGER = logging.getLogger(__name__)

AUTH_CLOSE_CODES = frozenset({4401, 4403})
TTL_CLOSE_CODE = 4420


def backoff_delay(attempt: int) -> float:
    return min(1 * 2**attempt + uniform(0, 1), 300)


async def cancel_task(*tasks: asyncio.Task | None) -> None:
    for task in tasks:
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


class WebSocketMonitor:
    def __init__(
        self,
        account: Rivian,
        url: str,
        connection_init: Callable[[ClientWebSocketResponse[bool]], Awaitable[None]],
    ) -> None:
        self._account = account
        self._url = url
        self._connection_init = connection_init

        self._connection_ack: asyncio.Event = asyncio.Event()
        self._disconnect = False
        self._ws: ClientWebSocketResponse[bool] | None = None
        self._monitor_task: asyncio.Task | None = None
        self._receiver_task: asyncio.Task | None = None
        self._last_received: datetime | None = None
        self._subscriptions: dict[
            str, tuple[Callable[[dict[str, Any]], None], dict[str, Any]]
        ] = {}

    @property
    def connected(self) -> bool:
        if self._disconnect:
            return False
        return False if self._ws is None else not self._ws.closed

    @property
    def connection_ack(self) -> asyncio.Event:
        return self._connection_ack

    @property
    def websocket(self) -> ClientWebSocketResponse[bool] | None:
        return self._ws

    @property
    def monitor(self) -> asyncio.Task | None:
        return self._monitor_task

    async def new_connection(self, start_monitor: bool = False) -> None:
        await cancel_task(self._receiver_task)
        self._disconnect = False
        assert self._account._session
        self._ws = await self._account._session.ws_connect(
            url=self._url, headers={"sec-websocket-protocol": "graphql-transport-ws"}
        )
        await self._connection_init(self._ws)
        self._receiver_task = asyncio.ensure_future(self._receiver())
        if start_monitor:
            await self.start_monitor()

    async def start_subscription(
        self, payload: dict[str, Any], callback: Callable[[dict[str, Any]], None]
    ) -> Callable[[], Awaitable[None]] | None:
        if not self.connected:
            return None
        _id = str(uuid4())
        self._subscriptions[_id] = (callback, payload)
        await self._subscribe(_id, payload)

        async def unsubscribe() -> None:
            if _id in self._subscriptions:
                del self._subscriptions[_id]
                if self.connected:
                    assert self._ws
                    await self._ws.send_json({"id": _id, "type": "complete"})

        return unsubscribe

    async def _subscribe(self, _id: str, payload: dict[str, Any]) -> None:
        assert self._ws
        await self._ws.send_json({"id": _id, "payload": payload, "type": "subscribe"})

    async def _resubscribe_all(self) -> None:
        try:
            async with async_timeout.timeout(self._account.request_timeout):
                await self.connection_ack.wait()
        except TimeoutError:
            _LOGGER.error("A timeout occurred while attempting to resubscribe")
            return
        for _id, (_, payload) in self._subscriptions.items():
            await self._subscribe(_id, payload)

    async def _receiver(self) -> None:
        if not (websocket := self._ws):
            return
        while not websocket.closed:
            try:
                msg = await websocket.receive(timeout=60)
                if msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                    code = msg.data if isinstance(msg.data, int) else None
                    if code in AUTH_CLOSE_CODES or msg.extra == "Unauthenticated":
                        _LOGGER.error(
                            "Web socket rejected by the server: %s (code %s). "
                            "Not reconnecting.",
                            msg.extra,
                            code,
                        )
                        self._disconnect = True
                    elif code == TTL_CLOSE_CODE:
                        _LOGGER.debug("Web socket recycled by the server (TTL)")
                    else:
                        self._log_message(msg)
                    break
                self._last_received = datetime.now(UTC)
                if msg.type == WSMsgType.TEXT:
                    data = loads(msg.data)
                    if (data_type := data.get("type")) == "connection_ack":
                        self._connection_ack.set()
                    elif data_type == "next":
                        if (_id := data.get("id")) in self._subscriptions:
                            _fn = self._subscriptions[_id][0]
                            if inspect.iscoroutinefunction(_fn):
                                await _fn(data)
                            else:
                                _fn(data)
                    else:
                        self._log_message(msg)
                elif msg.type == WSMsgType.ERROR:
                    self._log_message(msg, True)
                    continue
            except TimeoutError:
                await self._resubscribe_all()
        self._connection_ack.clear()
        self._log_message("web socket stopped")

    async def _monitor(self) -> None:
        attempt = 0
        while not self._disconnect:
            while self.connected:
                if self._receiver_task and self._receiver_task.done():
                    self._receiver_task = asyncio.ensure_future(self._receiver())
                await asyncio.sleep(1)
            if not self._disconnect:
                try:
                    await self.new_connection()
                except (ClientError, OSError, TimeoutError) as ex:
                    self._log_message(ex, True)
                except Exception:
                    _LOGGER.exception("Web socket reconnect failed")
                if not self._ws or self._ws.closed:
                    await asyncio.sleep(backoff_delay(attempt))
                    attempt += 1
                    continue
                try:
                    async with async_timeout.timeout(self._account.request_timeout):
                        await self._connection_ack.wait()
                except TimeoutError:
                    if self._disconnect:
                        break
                    await asyncio.sleep(backoff_delay(attempt))
                    attempt += 1
                    continue
                attempt = 0
                self._log_message("web socket connection reopened")
                await self._resubscribe_all()

    async def start_monitor(self) -> None:
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.ensure_future(self._monitor())

    async def stop_monitor(self) -> None:
        await cancel_task(self._monitor_task)

    async def close(self) -> None:
        self._disconnect = True
        if self._ws:
            await self._ws.close()
        await cancel_task(self._monitor_task, self._receiver_task)

    def _log_message(
        self,
        message: str | Exception | WSMessage | WSMessageTextBytes,
        is_error: bool = False,
    ) -> None:
        log_method = _LOGGER.error if is_error else _LOGGER.debug
        log_method(message)
