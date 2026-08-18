"""Tests for the BLE pairing entry points.

This module was 139 statements at 0% -- untested in the client repo too -- and it
is the path every HMAC-signed vehicle command depends on: without a completed
pairing, no command works at all.

What is worth pinning here is the ROUTING, not the radio. Picking the wrong
generation, or silently returning False, is the difference between "pairing
failed with a reason" and "the button does nothing".
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.rivian.rivian_client import ble

GEN1_UUIDS = [
    ble.GEN1_PHONE_ID_VEHICLE_ID_UUID,
    ble.GEN1_PHONE_NONCE_VEHICLE_NONCE_UUID,
]
GEN2_UUIDS = [ble.GEN2_PLAIN_DATA_IN_UUID, ble.GEN2_ENCRYPTED_DATA_OUT_UUID]


def _client_with(uuids: list[str]) -> MagicMock:
    """A BleakClient context manager advertising exactly these characteristics."""
    chars = [MagicMock(uuid=u) for u in uuids]
    service = MagicMock(characteristics=chars)
    client = MagicMock()
    client.services = [service]
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestDetectVehicleGeneration:
    async def test_gen2_characteristics_report_generation_2(self) -> None:
        with patch.object(ble, "BleakClient", return_value=_client_with(GEN2_UUIDS)):
            assert await ble.detect_vehicle_generation(MagicMock()) == 2

    async def test_gen1_characteristics_report_generation_1(self) -> None:
        with patch.object(ble, "BleakClient", return_value=_client_with(GEN1_UUIDS)):
            assert await ble.detect_vehicle_generation(MagicMock()) == 1

    async def test_gen2_wins_when_both_are_present(self) -> None:
        # Gen 2 vehicles can expose legacy characteristics too; picking Gen 1
        # there would drive the wrong protocol against a Gen 2 car.
        both = _client_with(GEN1_UUIDS + GEN2_UUIDS)
        with patch.object(ble, "BleakClient", return_value=both):
            assert await ble.detect_vehicle_generation(MagicMock()) == 2

    async def test_unrecognised_characteristics_report_zero(self) -> None:
        with patch.object(
            ble, "BleakClient", return_value=_client_with(["0000-unknown"])
        ):
            assert await ble.detect_vehicle_generation(MagicMock()) == 0

    async def test_uuid_matching_is_case_insensitive(self) -> None:
        # bleak reports lowercase UUIDs; the constants are uppercase. A
        # case-sensitive comparison silently detects nothing.
        with patch.object(
            ble,
            "BleakClient",
            return_value=_client_with([u.lower() for u in GEN2_UUIDS]),
        ):
            assert await ble.detect_vehicle_generation(MagicMock()) == 2

    async def test_a_connection_failure_propagates(self) -> None:
        # The caller decides how to surface this; swallowing it here would make a
        # dead radio look like an unknown vehicle.
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("no radio"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        with (
            patch.object(ble, "BleakClient", return_value=ctx),
            pytest.raises(RuntimeError),
        ):
            await ble.detect_vehicle_generation(MagicMock())


class TestPairPhoneRouting:
    ARGS = (MagicMock(), "phone-id", "vas-id", "vehicle-key", "private-key")

    async def test_forced_generation_1_uses_the_legacy_protocol(self) -> None:
        with patch.object(ble, "_pair_phone_gen1", AsyncMock(return_value=True)) as g1:
            assert await ble.pair_phone(*self.ARGS, force_generation=1) is True
            g1.assert_awaited_once()

    async def test_forced_generation_2_uses_the_pre_ccc_protocol(self) -> None:
        with patch(
            "custom_components.rivian.rivian_client.ble_gen2.pair_phone_gen2",
            AsyncMock(return_value=True),
        ) as g2:
            assert await ble.pair_phone(*self.ARGS, force_generation=2) is True
            g2.assert_awaited_once()

    async def test_an_invalid_forced_generation_raises(self) -> None:
        # Loudly, because silently picking one would pair against the wrong protocol.
        with pytest.raises(ValueError, match="Invalid generation"):
            await ble.pair_phone(*self.ARGS, force_generation=3)

    async def test_autodetect_routes_to_the_detected_generation(self) -> None:
        with (
            patch.object(ble, "detect_vehicle_generation", AsyncMock(return_value=1)),
            patch.object(ble, "_pair_phone_gen1", AsyncMock(return_value=True)) as g1,
        ):
            assert await ble.pair_phone(*self.ARGS) is True
            g1.assert_awaited_once()

    async def test_an_unknown_generation_fails_without_guessing(self) -> None:
        with (
            patch.object(ble, "detect_vehicle_generation", AsyncMock(return_value=0)),
            patch.object(ble, "_pair_phone_gen1", AsyncMock()) as g1,
        ):
            assert await ble.pair_phone(*self.ARGS) is False
            g1.assert_not_awaited()

    async def test_a_detection_failure_fails_the_pairing(self) -> None:
        with patch.object(
            ble, "detect_vehicle_generation", AsyncMock(side_effect=RuntimeError("x"))
        ):
            assert await ble.pair_phone(*self.ARGS) is False


class TestSetBluezPairable:
    async def test_refuses_on_non_linux(self) -> None:
        # BlueZ is Linux-only; on macOS this must say so rather than fail obscurely
        # deep inside dbus.
        with (
            patch.object(ble.platform, "system", return_value="Darwin"),
            pytest.raises(OSError, match="BlueZ is not available"),
        ):
            await ble.set_bluez_pairable(MagicMock())

    async def test_a_dbus_failure_returns_false_rather_than_raising(self) -> None:
        # The caller treats False as "could not make the adapter pairable" and
        # reports it; an exception here would abort the whole pairing button.
        device = MagicMock()
        device.details = {"props": {"Adapter": "/org/bluez/hci0"}}
        with (
            patch.object(ble.platform, "system", return_value="Linux"),
            patch.dict(
                "sys.modules",
                {
                    "dbus_fast": MagicMock(),
                    "dbus_fast.aio": MagicMock(
                        MessageBus=MagicMock(side_effect=RuntimeError("no bus"))
                    ),
                },
            ),
        ):
            assert await ble.set_bluez_pairable(device) is False
