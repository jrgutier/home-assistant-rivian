"""The decoder registry, and the line between a schema and a subscription.

`RVM_DECODERS` is what goes live: `coordinator.SUBSCRIBED_RVMS` is derived from
its keys, so each key is a subscription the vehicle opens. The registry
(`RVMDecoder`) is how a decoder is attached to its message class. This file keeps
the two in step, and keeps the schema-only topics on the right side of the line.
"""

from __future__ import annotations

import ast
import importlib
import pathlib

import pytest

from custom_components.rivian.rivian_client import parallax
from custom_components.rivian.rivian_client.parallax.core import RVMDecoder
from custom_components.rivian.rivian_client.parallax.proto import body_pb2

PACKAGE = pathlib.Path(parallax.__file__).parent

# Topics bretterer/rivian-python-client PR 205 decodes and this integration does
# not. Their messages are in the schemas; no decoder is registered for them, so
# nothing subscribes. Turning one on is its own, hardware-verified change.
SCHEMA_ONLY_TOPICS: dict[str, tuple[str, str]] = {
    "body.wipers.fluid_level": ("body", "WiperFluidLevel"),
    "charging.energy.state": ("charging", "EnergyState"),
    "charging.session.power": ("charging", "SessionPower"),
    "charging.smart_charging.settings": ("charging", "SmartChargingSettings"),
    "charging.smart_charging.smart_charging_info": ("charging", "SmartChargingInfo"),
    "charging.smart_charging.weighted_charging_forecast": (
        "charging",
        "WeightedChargingForecast",
    ),
    "departure.schedule.schedule": ("departure", "DepartureSchedules"),
    "device_table.vas_keyper.devices": ("device_table", "VasKeyperDevices"),
    "dynamics.brakes.fluid_level": ("dynamics", "BrakeFluidLevel"),
    "dynamics.vehicle.efficiency": ("dynamics", "Efficiency"),
    "dynamics.vehicle.mass_estimate": ("dynamics", "MassEstimate"),
    "holiday_celebration.car_costume.holiday_celebration_enabled": (
        "holiday_celebration",
        "HolidayCelebrationEnabled",
    ),
    "holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings": (
        "holiday_celebration",
        "HalloweenCelebrationSettings",
    ),
    "navigation.navigation_service.trip_info": ("navigation", "TripInfo"),
    "parallax.wakeup.heartbeat": ("parallax", "Heartbeat"),
    "security.access.passive_entry": ("security", "PassiveEntry"),
    "vehicle.profiles.active_user": ("vehicle", "ActiveUserProfile"),
    "vehicle.setting.network": ("vehicle", "NetworkState"),
}


class TestRegistryAndTableAgree:
    def test_same_topics(self) -> None:
        assert set(parallax.RVM_DECODERS) == set(RVMDecoder.decoders)

    def test_same_functions(self) -> None:
        for topic, func in parallax.RVM_DECODERS.items():
            assert func is RVMDecoder.decoders[topic], topic

    def test_every_topic_has_a_message_class(self) -> None:
        assert set(RVMDecoder.messages) == set(RVMDecoder.decoders)

    def test_the_table_is_a_literal(self) -> None:
        """scripts/apk_corpus_sweep.py reads the keys out of the syntax tree."""
        tree = ast.parse((PACKAGE / "__init__.py").read_text())
        (table,) = [
            node.value
            for node in tree.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "RVM_DECODERS"
        ]
        assert isinstance(table, ast.Dict)
        keys = [key.value for key in table.keys if isinstance(key, ast.Constant)]
        assert keys == list(parallax.RVM_DECODERS)


class TestRegistration:
    def test_a_topic_cannot_be_registered_twice(self) -> None:
        with pytest.raises(ValueError, match="already registered"):

            @RVMDecoder.register(body_pb2.TrailerState, "body.trailer.state")
            def decode_again(m: body_pb2.TrailerState) -> dict:
                return {}

    def test_a_refused_registration_changes_nothing(self) -> None:
        before = dict(RVMDecoder.decoders)
        with pytest.raises(ValueError):
            RVMDecoder.register(body_pb2.TrailerState, "body.trailer.state")(
                lambda m: {}
            )
        assert RVMDecoder.decoders == before

    def test_the_decoder_takes_the_payload_not_the_message(self) -> None:
        """What `register` returns is called with base64, as callers always have."""
        assert parallax.decode_trailer_state("CAI=") == {
            "trailerStatus": "trailer_present"
        }

    def test_a_bad_frame_is_an_empty_result_not_an_exception(self) -> None:
        # Field 1 declared length 5 with one byte following: not a message.
        assert parallax.decode_closures("CgUB") == {}
        assert parallax.decode_closures("not base64 at all !!") == {}


class TestSchemaOnlyTopics:
    def test_there_are_eighteen(self) -> None:
        assert len(SCHEMA_ONLY_TOPICS) == 18

    @pytest.mark.parametrize("topic", sorted(SCHEMA_ONLY_TOPICS))
    def test_not_decoded_so_not_subscribed(self, topic: str) -> None:
        assert topic not in parallax.RVM_DECODERS
        assert topic not in RVMDecoder.decoders

    @pytest.mark.parametrize("topic", sorted(SCHEMA_ONLY_TOPICS))
    def test_its_message_compiles(self, topic: str) -> None:
        prefix, name = SCHEMA_ONLY_TOPICS[topic]
        module = importlib.import_module(f"{parallax.__name__}.proto.{prefix}_pb2")
        getattr(module, name)().SerializeToString()
