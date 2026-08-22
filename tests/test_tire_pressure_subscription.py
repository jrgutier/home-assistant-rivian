"""Client-side tests for the `tirePressureState` subscription and the S1
core-document fallback on the main `vehicleState` subscription.

`subscribe_for_tire_pressure_updates()` is a sibling of
`subscribe_for_vehicle_updates()`: both select the same `vehicleState(id:)`
root over the same websocket, but the app puts tyre pressure in its own
document (com.rivian.android.consumer/java_src/sh/C19721Z9.java:59,
operationName at :81) so that one unknown field name there costs the 12 tyre
entities, not the whole vehicle. See both methods' docstrings in
`rivian_client/rivian.py`.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rivian.rivian_client import Rivian
from custom_components.rivian.rivian_client.const import (
    CORE_VEHICLE_STATE_FIELDS,
    TIRE_PRESSURE_SUBSCRIPTION_PROPERTIES,
    VEHICLE_STATES_SUBSCRIPTION_PROPERTIES,
)
from custom_components.rivian.rivian_client.exceptions import RivianApiException


def _extract_balanced_braces(text: str, start: int) -> str:
    """Return `text[start:]` up to (and including) the `}` that balances the
    `{` at `start`."""
    assert text[start] == "{"
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("unbalanced braces")  # pragma: no cover


def _selected_fields(query: str) -> list[str]:
    """Parse the field names selected at the outer level of `query`'s
    `vehicleState(id: $vehicleID) { ... }` selection set.

    A real parse, not a substring search: `"x" in query` would also pass for
    a field that never appears in the selection set but is a substring of
    one that does, or for a name mentioned only in the operation string.
    """
    marker = "vehicleState(id: $vehicleID) "
    selection_set = _extract_balanced_braces(query, query.index(marker) + len(marker))
    depth = 0
    fields: list[str] = []
    token = ""
    for ch in selection_set[1:-1]:
        if ch == "{":
            if depth == 0 and token.strip():
                fields.append(token.strip())
            depth += 1
            token = ""
        elif ch == "}":
            depth -= 1
            token = ""
        elif depth == 0:
            token += ch
    return fields


def _fake_monitor(start_subscription: AsyncMock | None = None) -> MagicMock:
    """A `_ws_monitor` double whose `connection_ack` is already set, so
    `subscribe_for_*` proceeds straight to sending its payload."""
    monitor = MagicMock()
    monitor.connection_ack = asyncio.Event()
    monitor.connection_ack.set()
    monitor.start_subscription = start_subscription or AsyncMock(
        return_value=lambda: None
    )
    return monitor


def _connect_with(rivian: Rivian, monitor: MagicMock) -> None:
    """Replace `rivian._ws_connect` so it "connects" straight to `monitor`,
    without opening a real websocket."""

    async def fake_ws_connect() -> None:
        rivian._ws_monitor = monitor

    rivian._ws_connect = fake_ws_connect


@pytest.fixture
def rivian() -> Rivian:
    return Rivian(
        csrf_token="token", app_session_token="token", user_session_token="token"
    )


async def _subscribed_payload(rivian: Rivian, method: str, **kwargs: Any) -> dict:
    """Call `method` against a fake, always-connected monitor and return the
    single payload it sent to `start_subscription`."""
    monitor = _fake_monitor()
    _connect_with(rivian, monitor)
    await getattr(rivian, method)(vehicle_id="v1", callback=lambda _: None, **kwargs)
    return monitor.start_subscription.await_args.args[0]


class TestTirePressureSubscriptionShape:
    """Requirement 1 in T3: match the app's own operation, verbatim."""

    async def test_query_matches_the_apps_operation(self, rivian: Rivian) -> None:
        payload = await _subscribed_payload(
            rivian, "subscribe_for_tire_pressure_updates"
        )
        assert "subscription tirePressureState($vehicleID: String!)" in payload["query"]
        assert "vehicleState(id: $vehicleID)" in payload["query"]

    async def test_operation_name_is_tire_pressure_state(self, rivian: Rivian) -> None:
        payload = await _subscribed_payload(
            rivian, "subscribe_for_tire_pressure_updates"
        )
        assert payload["operationName"] == "tirePressureState"

    async def test_selection_set_is_exactly_the_twelve_names(
        self, rivian: Rivian
    ) -> None:
        payload = await _subscribed_payload(
            rivian, "subscribe_for_tire_pressure_updates"
        )
        fields = _selected_fields(payload["query"])
        assert len(fields) == 12
        assert set(fields) == set(TIRE_PRESSURE_SUBSCRIPTION_PROPERTIES)

    async def test_a_dead_tire_pressure_stream_still_raises(
        self, rivian: Rivian
    ) -> None:
        """Mirrors subscribe_for_vehicle_updates()'s except pair: a caller
        must not see None where a subscription actually failed."""
        rivian._ws_connect = AsyncMock(side_effect=RuntimeError("gateway refused"))
        with pytest.raises(RivianApiException):
            await rivian.subscribe_for_tire_pressure_updates(
                vehicle_id="v1", callback=lambda _: None
            )


class TestS1CoreDocumentFallback:
    """Requirement 2 in T3: a rejected MAIN document retries once against
    CORE_VEHICLE_STATE_FIELDS before the caller sees a failure."""

    async def test_a_rejected_full_document_retries_with_the_core_field_set(
        self, rivian: Rivian
    ) -> None:
        unsubscribe = object()
        monitor = _fake_monitor(
            start_subscription=AsyncMock(
                side_effect=[RivianApiException("Cannot query field"), unsubscribe]
            )
        )
        _connect_with(rivian, monitor)

        result = await rivian.subscribe_for_vehicle_updates(
            vehicle_id="v1", callback=lambda _: None
        )

        assert result is unsubscribe
        assert monitor.start_subscription.await_count == 2
        first_payload, second_payload = (
            call.args[0] for call in monitor.start_subscription.await_args_list
        )
        assert first_payload["operationName"] == "VehicleState"
        assert second_payload["operationName"] == "VehicleState"
        assert set(_selected_fields(first_payload["query"])) == set(
            VEHICLE_STATES_SUBSCRIPTION_PROPERTIES
        )
        assert set(_selected_fields(second_payload["query"])) == set(
            CORE_VEHICLE_STATE_FIELDS
        )
        assert rivian.subscription_document("v1") == "core"

    async def test_a_successful_full_document_is_recorded_as_full(
        self, rivian: Rivian
    ) -> None:
        await _subscribed_payload(rivian, "subscribe_for_vehicle_updates")
        assert rivian.subscription_document("v1") == "full"

    async def test_a_rejection_of_both_documents_still_raises(
        self, rivian: Rivian
    ) -> None:
        """The mitigation reduces the blast radius; it does not eliminate
        the failure mode -- if the renamed field is itself one of the core
        15, the fallback dies identically and this must still surface."""
        monitor = _fake_monitor(
            start_subscription=AsyncMock(
                side_effect=RivianApiException("Cannot query field")
            )
        )
        _connect_with(rivian, monitor)

        with pytest.raises(RivianApiException):
            await rivian.subscribe_for_vehicle_updates(
                vehicle_id="v1", callback=lambda _: None
            )
        assert monitor.start_subscription.await_count == 2

    async def test_an_explicit_property_set_also_retries_by_default(
        self, rivian: Rivian
    ) -> None:
        """The fallback's whole purpose is to survive a caller-supplied
        field set going bad, so it must not skip the retry just because
        `properties` was passed explicitly -- this is the production path:
        coordinator.py always passes an explicit set, so gating the retry
        on `properties is None` (an earlier version of this fix) made the
        mitigation dead code."""
        unsubscribe = object()
        monitor = _fake_monitor(
            start_subscription=AsyncMock(
                side_effect=[RivianApiException("Cannot query field"), unsubscribe]
            )
        )
        _connect_with(rivian, monitor)

        result = await rivian.subscribe_for_vehicle_updates(
            vehicle_id="v1",
            callback=lambda _: None,
            properties={"batteryLevel"},
        )

        assert result is unsubscribe
        assert monitor.start_subscription.await_count == 2
        assert rivian.subscription_document("v1") == "core"

    async def test_allow_core_fallback_false_suppresses_the_retry(
        self, rivian: Rivian
    ) -> None:
        """The opt-out: a test or probe that wants strict, no-retry
        behaviour."""
        monitor = _fake_monitor(
            start_subscription=AsyncMock(
                side_effect=RivianApiException("Cannot query field")
            )
        )
        _connect_with(rivian, monitor)

        with pytest.raises(RivianApiException):
            await rivian.subscribe_for_vehicle_updates(
                vehicle_id="v1",
                callback=lambda _: None,
                properties={"batteryLevel"},
                allow_core_fallback=False,
            )
        assert monitor.start_subscription.await_count == 1
