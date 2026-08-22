"""The seam between `pair_phone` and the Gen 2 diagnostic trace.

This file exists because this exact wiring broke once and NOTHING caught it. An
earlier revision carried `vehicle_id` into `ble_gen2` through a module-level
ContextVar plus a `set_trace_vehicle_id()` hook. A concurrent edit removed the
hook from `ble_gen2.py` while leaving the call in `ble.py`, which imported it
inside a `try/except` that logged at DEBUG and continued. The result: pairing
worked, the whole suite passed, and the trace recorded NOTHING -- silently, and
in production, forever.

That matters more than a normal wiring bug. Nobody involved owns a Gen 2
vehicle, so a beta tester's trace is the only evidence that will ever settle the
UNPROVEN parts of this protocol (chiefly which characteristic carries the
handshake). A silently inert trace does not degrade diagnostics; it removes the
entire feedback channel while every signal says the change is healthy.

The unit tests in `test_ble_gen2.py` cannot catch this: they call
`pair_phone_gen2` directly and so never exercise the threading. `test_ble.py`
cannot either -- its routing tests never pass a `vehicle_id`. The gap is exactly
between the two files, which is where lane-by-lane verification stops looking.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.rivian.rivian_client import ble, ble_trace

ARGS = (MagicMock(), "phone-id", "vas-id", "vehicle-key", "private-key")


class TestVehicleIdReachesTheTrace:
    """`vehicle_id` must survive every hop, or the trace is inert."""

    async def test_vehicle_id_reaches_pair_phone_gen2(self) -> None:
        """The hop that actually broke.

        Asserted positionally against the real call site rather than by
        `assert_awaited_once()`, because the failure mode was not "never
        called" -- `pair_phone_gen2` was called perfectly happily, just without
        the id it needed.
        """
        gen2 = AsyncMock(return_value=True)
        with patch(
            "custom_components.rivian.rivian_client.ble_gen2.pair_phone_gen2", gen2
        ):
            assert await ble.pair_phone(*ARGS, force_generation=2, vehicle_id="v1")

        assert gen2.await_args is not None
        assert gen2.await_args.args[5] == "v1", (
            "vehicle_id did not reach pair_phone_gen2; the trace will silently "
            "record nothing while every test still passes"
        )

    async def test_vehicle_id_reaches_generation_detection(self) -> None:
        """The GATT characteristic dump is captured during detection, not pairing.

        `detect_vehicle_generation` skips capture entirely when `vehicle_id` is
        None, so losing it here costs the single highest-value unknown in the
        delta report: whether the four Gen 2 UUIDs are even correct.
        """
        detect = AsyncMock(return_value=1)
        with (
            patch.object(ble, "detect_vehicle_generation", detect),
            patch.object(ble, "_pair_phone_gen1", AsyncMock(return_value=True)),
        ):
            assert await ble.pair_phone(*ARGS, vehicle_id="v1")

        assert detect.await_args is not None
        assert detect.await_args.kwargs.get("vehicle_id") == "v1"

    async def test_omitting_vehicle_id_is_a_clean_no_op(self) -> None:
        """Tracing must stay optional: every existing caller omits it."""
        gen2 = AsyncMock(return_value=True)
        with patch(
            "custom_components.rivian.rivian_client.ble_gen2.pair_phone_gen2", gen2
        ):
            assert await ble.pair_phone(*ARGS, force_generation=2)

        assert gen2.await_args is not None
        assert gen2.await_args.args[5] is None


class TestTraceIsolationBetweenVehicles:
    """One trace per vehicle, because two can pair at once.

    `_pairing` guards a single button ENTITY (button.py:167) and
    `async_setup_entry` builds one pair button PER VEHICLE, so a multi-vehicle
    account can run two pairings concurrently. A shared trace would interleave
    their frames and either one's `reset()` would erase the other's evidence --
    corrupting diagnostics for the two-vehicle tester, who is the most valuable
    reporter available.
    """

    async def test_two_vehicles_do_not_share_a_trace(self) -> None:
        a = ble_trace.get_trace("vehicle-a")
        b = ble_trace.get_trace("vehicle-b")
        assert a is not b

        a.record_frame("write", "UUID-A", b"\xaa")
        assert len(a.frames) == 1
        assert b.frames == [], "vehicle B saw vehicle A's frames"

        b.reset()
        assert len(a.frames) == 1, "vehicle B's reset erased vehicle A's evidence"

    async def test_the_same_vehicle_id_returns_the_same_trace(self) -> None:
        """Otherwise each hop would record into its own throwaway object."""
        assert ble_trace.get_trace("vehicle-c") is ble_trace.get_trace("vehicle-c")


class TestGattDiscoveryIsCaptured:
    """The GATT dump is the single highest-value unknown in the delta report.

    `detect_vehicle_generation` already enumerates every service and
    characteristic to tell a Gen 2 vehicle from a Gen 1 one, and before this
    change it threw that list away. It is what settles whether the four Gen 2
    UUIDs this integration writes to and reads from are even the right ones --
    GEN2_BLE_DELTA.md's UNPROVEN items 1, 2 and 5, none of which any amount of
    local testing can close.

    Without this pin the capture can be deleted and the whole suite stays green,
    which would silently remove the most valuable thing a tester's bundle
    carries.
    """

    @staticmethod
    def _client(uuids: list[str], mtu: int = 185) -> MagicMock:
        chars = [MagicMock(uuid=u, properties=["read", "notify"]) for u in uuids]
        client = MagicMock(services=[MagicMock(characteristics=chars)], mtu_size=mtu)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    async def test_characteristics_and_mtu_are_recorded(self) -> None:
        trace = ble_trace.get_trace("gatt-vehicle")
        trace.reset()
        uuids = [
            ble.GEN2_PLAIN_DATA_IN_UUID,
            ble.GEN2_ENCRYPTED_DATA_OUT_UUID,
        ]
        with patch.object(ble, "BleakClient", return_value=self._client(uuids)):
            assert (
                await ble.detect_vehicle_generation(
                    MagicMock(), vehicle_id="gatt-vehicle"
                )
                == 2
            )

        rendered = trace.as_dict()
        recorded = {s["uuid"] for s in rendered["services"]}
        assert recorded == {u.upper() for u in uuids}
        # Properties too: "which characteristic is writable" is half the answer
        # to the write-target question (UNPROVEN item 1).
        assert all("properties" in s for s in rendered["services"])
        # MTU distinguishes fragmentation from a wrong characteristic.
        assert rendered["mtu"] == 185

    async def test_no_capture_without_a_vehicle_id(self) -> None:
        """Tracing stays opt-in: the Gen 1 path calls this without a vehicle_id."""
        trace = ble_trace.get_trace("untraced-vehicle")
        trace.reset()
        with patch.object(
            ble,
            "BleakClient",
            return_value=self._client(
                [
                    ble.GEN1_PHONE_ID_VEHICLE_ID_UUID,
                    ble.GEN1_PHONE_NONCE_VEHICLE_NONCE_UUID,
                ]
            ),
        ):
            assert await ble.detect_vehicle_generation(MagicMock()) == 1
        assert trace.as_dict()["services"] == []
