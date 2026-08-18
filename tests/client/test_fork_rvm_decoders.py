"""Decoders for the RVMs this fork ships, checked against real captured payloads.

Upstream's RVM_DECODERS covers 14 telemetry topics and none of these three, so
decode_parallax_message returned None for every one of them and the entities read
as unavailable forever. That is the defect the whole Parallax effort exists to
fix, so these tests assert against payloads captured from a real vehicle rather
than against hand-written bytes -- see docs/development/RVM_FIXTURES.md.

Each decoder is ALSO cross-checked against the generated protobuf class. The
hand-rolled implementation is what ships (the protobuf dependency is being
removed), and the generated one is the independent reference that keeps it
honest.
"""

import base64
import pathlib

import pytest

from custom_components.rivian.rivian_client.parallax import (
    RVM_DECODERS,
    decode_climate_hold_setting,
    decode_climate_hold_status,
    decode_parallax_message,
    decode_vehicle_wheels,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "parallax"


def _payload(name: str) -> str:
    return base64.b64encode((FIXTURES / f"{name}.bin").read_bytes()).decode()


class TestClimateHoldSetting:
    """The one server-verified WRITE. Captured by setting a 5-minute hold."""

    def test_decodes_the_captured_duration(self) -> None:
        assert (
            decode_climate_hold_setting(_payload("climate_hold_setting"))[
                "climateHoldDurationSeconds"
            ]
            == 300
        )

    def test_matches_the_generated_protobuf(self) -> None:
        from custom_components.rivian.rivian_client.proto.rivian_climate_pb2 import (
            ClimateHoldSetting,
        )

        msg = ClimateHoldSetting()
        msg.ParseFromString((FIXTURES / "climate_hold_setting.bin").read_bytes())
        assert (
            decode_climate_hold_setting(_payload("climate_hold_setting"))[
                "climateHoldDurationSeconds"
            ]
            == msg.hold_time_duration_seconds
        )

    def test_an_empty_payload_means_no_hold_not_no_data(self) -> None:
        # The live vehicle returns 0 bytes when no hold is configured. Reporting
        # {} would leave the entity unavailable; 0 makes it read as off.
        assert decode_climate_hold_setting("") == {"climateHoldDurationSeconds": 0}

    def test_the_documented_two_hour_encoding(self) -> None:
        # 08a038 == 7200s, recorded independently in SENDVEHICLEOPERATION_TEST_RESULTS
        assert decode_climate_hold_setting(
            base64.b64encode(bytes.fromhex("08a038")).decode()
        ) == {"climateHoldDurationSeconds": 7200}


class TestClimateHoldStatus:
    def test_decodes_the_captured_status(self) -> None:
        out = decode_climate_hold_status(_payload("climate_hold_status"))
        # Captured while no hold was running.
        assert out["climateHoldStatus"] == "off"
        assert out["climateHoldAvailability"] == "available"
        # An empty hold_end_time submessage must not invent a timestamp.
        assert "climateHoldEndTime" not in out

    def test_matches_the_generated_protobuf(self) -> None:
        from custom_components.rivian.rivian_client.proto.rivian_climate_pb2 import (
            ClimateHoldStatus,
        )

        msg = ClimateHoldStatus()
        msg.ParseFromString((FIXTURES / "climate_hold_status.bin").read_bytes())
        out = decode_climate_hold_status(_payload("climate_hold_status"))
        assert (
            out["climateHoldStatus"]
            == ClimateHoldStatus.Status.Name(msg.status).removeprefix("STATUS_").lower()
        )
        assert (
            out["climateHoldAvailability"]
            == ClimateHoldStatus.Availability.Name(msg.availability)
            .removeprefix("AVAILABILITY_")
            .lower()
        )

    def test_an_active_hold_exposes_its_end_time(self) -> None:
        # Built with the generated class rather than hand-rolled bytes, so the
        # timestamp submessage is encoded by the reference implementation.
        from custom_components.rivian.rivian_client.proto.rivian_climate_pb2 import (
            ClimateHoldStatus,
        )

        msg = ClimateHoldStatus(status=3, availability=1)
        msg.hold_end_time.seconds = 1800000000
        out = decode_climate_hold_status(
            base64.b64encode(msg.SerializeToString()).decode()
        )
        assert out["climateHoldStatus"] == "on"
        assert out["climateHoldEndTime"] == 1800000000


class TestVehicleWheels:
    def test_decodes_every_wheel_in_the_captured_payload(self) -> None:
        out = decode_vehicle_wheels(_payload("vehicle_wheels"))
        assert len(out["wheels"]) == 2
        assert out["wheels"][0]["wheelPackage"] == 1
        assert out["wheels"][0]["isInstalled"] is True
        assert out["wheels"][1]["isInstalled"] is False
        assert out["wheelsInstalled"] == 1

    def test_matches_the_generated_protobuf(self) -> None:
        from custom_components.rivian.rivian_client.proto.rivian_vehicle_pb2 import (
            VehicleWheels,
        )

        msg = VehicleWheels()
        msg.ParseFromString((FIXTURES / "vehicle_wheels.bin").read_bytes())
        out = decode_vehicle_wheels(_payload("vehicle_wheels"))
        assert len(out["wheels"]) == len(msg.wheels_list)
        for decoded, ref in zip(out["wheels"], msg.wheels_list, strict=True):
            assert decoded["wheelPackage"] == ref.wheel_package
            assert decoded["tireOdometerMeters"] == ref.tire_odometer_mileage_meters
            assert decoded["isInstalled"] == ref.is_installed
            assert decoded["tires"] == ref.tires


class TestRegistration:
    @pytest.mark.parametrize(
        "rvm",
        [
            "comfort.cabin.climate_hold_setting",
            "comfort.cabin.climate_hold_status",
            "vehicle.wheels.vehicle_wheels",
        ],
    )
    def test_the_rvm_is_registered(self, rvm: str) -> None:
        assert rvm in RVM_DECODERS

    def test_decode_parallax_message_no_longer_returns_none(self) -> None:
        """The actual defect: the router asked for these and got nothing back."""
        for name, rvm in (
            ("climate_hold_status", "comfort.cabin.climate_hold_status"),
            ("climate_hold_setting", "comfort.cabin.climate_hold_setting"),
            ("vehicle_wheels", "vehicle.wheels.vehicle_wheels"),
        ):
            out = decode_parallax_message(
                rvm=rvm, payload=_payload(name), timestamp="t"
            )
            assert out, f"{rvm} still decodes to nothing"


class TestMalformedInput:
    @pytest.mark.parametrize(
        "decoder", [decode_climate_hold_status, decode_vehicle_wheels]
    )
    def test_garbage_does_not_raise(self, decoder) -> None:
        assert decoder(base64.b64encode(b"\xff\xff\xff").decode()) == {}

    @pytest.mark.parametrize(
        "decoder",
        [decode_climate_hold_status, decode_vehicle_wheels],
    )
    def test_empty_payload_returns_empty(self, decoder) -> None:
        assert decoder("") == {}
