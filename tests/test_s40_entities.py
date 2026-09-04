"""The s40 entities, driven by the same committed frames the decoders were built on.

s34 wrote four Parallax decoders, verified them against frames captured off this
project's own truck, and wired them to nothing. s40 gave them entities. These
tests run the real fixture -> real decoder -> real entity description path, so a
description that reads the wrong key, or a value_lambda that quietly reshapes
what the vehicle said, fails here rather than on a live install.

Deliberately NOT a re-test of the decoders: `test_parallax_s34_decoders.py`
already pins their output value-by-value. What is new here is the join between
that output and `const.py`'s descriptions, which nothing checked before.
"""

from __future__ import annotations

import base64
import json
import pathlib
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.rivian.binary_sensor import RivianBinarySensorEntity
from custom_components.rivian.const import (
    BINARY_SENSORS,
    SENSORS,
    _epoch_seconds_to_utc,
)
from custom_components.rivian.coordinator import SUBSCRIBED_RVMS, VehicleCoordinator
from custom_components.rivian.rivian_client.parallax import RVM_DECODERS
from custom_components.rivian.sensor import RivianSensorEntity
from homeassistant.config_entries import ConfigEntry

FIXTURES = pathlib.Path(__file__).resolve().parent / "client" / "fixtures" / "parallax"

CABIN_VENT = "comfort.cabin.cabin_ventilation_setting"
CONSENT = "gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent"
DAILY_LIMIT = "gearguard_streaming.privacy.gearguard_streaming_daily_limit"
PARKED_ENERGY = "energy_edge_compute.graphs.parked_energy_distributions"


def decoded(topic: str) -> dict[str, Any]:
    """What the committed frame for `topic` actually decodes to."""
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    payload = base64.b64encode((FIXTURES / manifest[topic]["file"]).read_bytes())
    return RVM_DECODERS[topic](payload.decode())


def _coordinator(values: dict[str, Any]) -> MagicMock:
    """A coordinator holding `values` in the shape the Parallax path writes.

    coordinator.py wraps each Parallax key as {"value": ..., "history": ...} --
    and for an unhashable value (the parked-energy windows are dicts) `history`
    is an EMPTY set, not {value}. Reproduced here rather than simplified,
    because the envelope is what `RivianDataUpdateCoordinator.get` unwraps.
    """
    coordinator = MagicMock(spec=VehicleCoordinator)
    data: dict[str, Any] = {}
    for key, value in values.items():
        try:
            history = {value}
        except TypeError:
            history = set()
        data[key] = {"value": value, "history": history}
    coordinator.data = data
    coordinator.get = lambda key, default=None: VehicleCoordinator.get(
        coordinator, key, default
    )
    return coordinator


def _sensor(key: str, coordinator: MagicMock, entry: ConfigEntry, vehicle: dict):
    description = next(d for d in SENSORS if d.key == key)
    return RivianSensorEntity(
        coordinator=coordinator,
        config_entry=entry,
        description=description,
        vehicle=vehicle,
    )


class TestCabinVentilation:
    """The two-byte frame carried field 1 and nothing else."""

    async def test_the_binary_sensor_is_on_from_the_real_frame(
        self, hass, mock_config_entry: ConfigEntry, mock_vehicle: dict
    ) -> None:
        coordinator = _coordinator(decoded(CABIN_VENT))
        description = next(
            d for d in BINARY_SENSORS if d.key == "cabin_ventilation_enabled"
        )
        entity = RivianBinarySensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle,
        )

        assert entity.is_on is True

    async def test_a_false_reading_is_off_not_unknown(
        self, hass, mock_config_entry: ConfigEntry, mock_vehicle: dict
    ) -> None:
        """`str(False).lower()` is "false", which is not in INVALID_SENSOR_STATES,
        and `coordinator.get` must return False rather than falling through to
        its default -- both are easy to break and neither is visible from the
        True case above."""
        coordinator = _coordinator({"cabinVentilationEnabled": False})
        description = next(
            d for d in BINARY_SENSORS if d.key == "cabin_ventilation_enabled"
        )
        entity = RivianBinarySensorEntity(
            coordinator=coordinator,
            config_entry=mock_config_entry,
            description=description,
            vehicle=mock_vehicle,
        )

        assert entity.is_on is False

    @pytest.mark.parametrize(
        "key",
        [
            "cabin_ventilation_mode",
            "cabin_ventilation_windows_open",
            "cabin_ventilation_sunroof_open",
            "cabin_ventilation_duration",
        ],
    )
    async def test_the_optional_four_are_unavailable_not_zero(
        self, key: str, hass, mock_config_entry: ConfigEntry, mock_vehicle: dict
    ) -> None:
        """proto3 omits defaults, so an absent field is unset, not zero.

        The captured frame carries none of these four. Rendering 0% open, or
        AUTO, from a frame that said nothing would be a confident lie; the
        entity going unavailable is the honest outcome and is what
        `RivianVehicleEntity.available` already produces.
        """
        coordinator = _coordinator(decoded(CABIN_VENT))
        entity = _sensor(key, coordinator, mock_config_entry, mock_vehicle)

        assert entity.available is False


class TestGearGuardStreaming:
    async def test_consent_reads_the_decoded_vocabulary(
        self, hass, mock_config_entry: ConfigEntry, mock_vehicle: dict
    ) -> None:
        coordinator = _coordinator(decoded(CONSENT))
        entity = _sensor(
            "gear_guard_streaming_consent",
            coordinator,
            mock_config_entry,
            mock_vehicle,
        )

        assert entity.native_value == "not_consented"

    async def test_daily_limit_reads_the_decoded_vocabulary(
        self, hass, mock_config_entry: ConfigEntry, mock_vehicle: dict
    ) -> None:
        coordinator = _coordinator(decoded(DAILY_LIMIT))
        entity = _sensor(
            "gear_guard_streaming_daily_limit",
            coordinator,
            mock_config_entry,
            mock_vehicle,
        )

        assert entity.native_value == "not_hit"

    async def test_undefined_resolves_to_unknown_not_to_a_state(
        self, hass, mock_config_entry: ConfigEntry, mock_vehicle: dict
    ) -> None:
        """`undefined` is one of the four daily-limit arms AND a member of
        INVALID_SENSOR_STATES, so sensor.py suppresses it. That is why this
        description ships no `options` list -- an arm that can never be a state
        does not belong in one."""
        coordinator = _coordinator({"gearGuardStreamingDailyLimit": "undefined"})
        entity = _sensor(
            "gear_guard_streaming_daily_limit",
            coordinator,
            mock_config_entry,
            mock_vehicle,
        )

        assert entity.native_value is None

    async def test_the_reset_time_becomes_an_aware_datetime(
        self, hass, mock_config_entry: ConfigEntry, mock_vehicle: dict
    ) -> None:
        """SensorDeviceClass.TIMESTAMP rejects a naive datetime and an int."""
        coordinator = _coordinator(decoded(DAILY_LIMIT))
        entity = _sensor(
            "gear_guard_streaming_limit_reset_time",
            coordinator,
            mock_config_entry,
            mock_vehicle,
        )
        value = entity.native_value

        assert value is not None
        assert value.tzinfo is not None
        assert value.timestamp() == 1767852000


class TestEpochConversion:
    """Guards on `_epoch_seconds_to_utc` that no fixture can reach."""

    def test_a_bool_is_not_an_epoch(self) -> None:
        """isinstance(True, int) is True, so without the explicit bool check
        this would render 1970-01-01T00:00:01Z from a flag."""
        assert _epoch_seconds_to_utc(True) is None

    @pytest.mark.parametrize("value", [None, "1767852000", {}, []])
    def test_non_numbers_are_rejected(self, value: Any) -> None:
        assert _epoch_seconds_to_utc(value) is None

    def test_an_out_of_range_number_does_not_raise(self) -> None:
        """A corrupt frame must not take the entity down with an exception."""
        assert _epoch_seconds_to_utc(10**18) is None


class TestParkedEnergy:
    WINDOWS = {
        "parked_energy_last_24_hours": "parkedEnergyLast24Hours",
        "parked_energy_last_8_hours": "parkedEnergyLast8Hours",
        "parked_energy_last_park_session": "parkedEnergyLastParkSession",
    }

    @pytest.mark.parametrize("key,field", WINDOWS.items())
    async def test_the_state_is_the_vehicles_own_total(
        self,
        key: str,
        field: str,
        hass,
        mock_config_entry: ConfigEntry,
        mock_vehicle: dict,
    ) -> None:
        windows = decoded(PARKED_ENERGY)
        entity = _sensor(key, _coordinator(windows), mock_config_entry, mock_vehicle)

        assert entity.native_value == windows[field]["totalKwh"]

    async def test_the_state_is_not_a_sum_of_the_components(
        self, hass, mock_config_entry: ConfigEntry, mock_vehicle: dict
    ) -> None:
        """The specific refactor this must survive.

        Summing thermal + outlets + system happens to land within 0.05 of the
        total on the captured 24-hour window, so a test that only compared
        against a hand-typed number would not tell the two apart. This one
        feeds a window whose parts deliberately do NOT add up: if the entity
        ever starts summing, it reports 9.0 instead of the 1.0 the vehicle sent.
        """
        coordinator = _coordinator(
            {
                "parkedEnergyLast24Hours": {
                    "totalKwh": 1.0,
                    "thermalKwh": 3.0,
                    "outletsKwh": 3.0,
                    "systemKwh": 3.0,
                }
            }
        )
        entity = _sensor(
            "parked_energy_last_24_hours",
            coordinator,
            mock_config_entry,
            mock_vehicle,
        )

        assert entity.native_value == 1.0

    @pytest.mark.parametrize("key,field", WINDOWS.items())
    async def test_every_other_measurement_rides_along_as_an_attribute(
        self,
        key: str,
        field: str,
        hass,
        mock_config_entry: ConfigEntry,
        mock_vehicle: dict,
    ) -> None:
        """Exactly the window's own keys minus the one that became the state.

        Not asserted as "nine": the committed frame sends no gearGuard figures
        at all, and the park-session window omits outletsKwh too. The invariant
        is that nothing is dropped and nothing is invented, whatever the vehicle
        chose to send.
        """
        windows = decoded(PARKED_ENERGY)
        entity = _sensor(key, _coordinator(windows), mock_config_entry, mock_vehicle)

        assert entity.extra_state_attributes == {
            k: v for k, v in windows[field].items() if k != "totalKwh"
        }

    async def test_a_window_the_vehicle_did_not_send_is_unavailable(
        self, hass, mock_config_entry: ConfigEntry, mock_vehicle: dict
    ) -> None:
        entity = _sensor(
            "parked_energy_last_8_hours",
            _coordinator({}),
            mock_config_entry,
            mock_vehicle,
        )

        assert entity.available is False
        assert entity.extra_state_attributes is None


def test_s40_added_no_decoder_and_so_no_subscription() -> None:
    """The live-behaviour guard.

    SUBSCRIBED_RVMS is derived from RVM_DECODERS (coordinator.py), so adding a
    decoder opens a new subscription on the vehicle -- a hardware-verifiable
    change. s40 added ENTITIES over decoders that already ship, which is why it
    needed no hardware pass. This pins that: every subscribed topic is a decoded
    topic, and the four s34 topics were already among them before this story.
    """
    assert set(SUBSCRIBED_RVMS) <= set(RVM_DECODERS)
    for topic in (CABIN_VENT, CONSENT, DAILY_LIMIT, PARKED_ENERGY):
        assert topic in SUBSCRIBED_RVMS
