"""Decoders transcribed from the app's protobuf classes.

## Where the schema came from, and why the first look said there wasn't one

R8 renames `GeneratedMessageLite` to `com.google.protobuf.e` and every message
class to two or three letters (`hk8`, `gxf`, `xq`). So grepping the decompilation
for `GeneratedMessageLite`, `ProtoAdapter` or `parseFrom` finds nothing outside
Google's own code, and the app looks as though it ships no protobuf schema. It
ships **326 message classes**.

What R8 leaves untouched is exactly what a decoder needs:

  * `<FIELD>_FIELD_NUMBER` constants, original names and numbers
  * the `<field>_` instance members, with Java types
  * protobuf enum constants, original names and numbers

The topic → message binding is read off the app's own decoder dispatch
(`b7h.java` and ten siblings): each decoder guards on `l6e.<TOPIC>` and parses
`<MessageClass>.<method>(Base64.decode(payload, 0))` in the same method body.

## What these tests are, and are not

The payloads below are **constructed** from the transcribed schema, not captured
from a vehicle. That makes them transcription tests: they prove the decoder reads
the field numbers and enum values the app's classes declare. They do **not** prove
the vehicle emits those numbers — capture needs sole-subscriber access to the
websocket, which means stopping the production integration (see
`docs/development/WS_CONTENTION.md`), and that is f8's protocol.

Said plainly rather than left implied, because a synthetic fixture that reads like
a captured one is how a decoder gets believed before it has been seen to work.
"""

from __future__ import annotations

import base64

import pytest

from custom_components.rivian.rivian_client.parallax import (
    RVM_DECODERS,
    decode_alarm_state,
    decode_battery_characteristics,
    decode_btm_diagnosis,
    decode_drive_mode,
    decode_gear,
    decode_immobilizer_state,
    decode_known_location,
    decode_low_voltage_battery,
    decode_parallax_message,
    decode_passive_entry_debug,
    decode_pet_mode_status,
    decode_range,
    decode_trailer_state,
    decode_vas_fault,
    decode_video_monitoring,
)


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def payload(**fields: int) -> str:
    """Encode {field_number: value} as a base64 protobuf message of varints."""
    data = b"".join(
        _varint((int(num) << 3) | 0) + _varint(value) for num, value in fields.items()
    )
    return base64.b64encode(data).decode()


class TestGear:
    @pytest.mark.parametrize(
        ("wire", "expected"),
        [(0, "not_defined"), (1, "park"), (2, "reverse"), (3, "neutral"), (4, "drive")],
    )
    def test_every_declared_value(self, wire: int, expected: str) -> None:
        assert decode_gear(payload(**{"1": wire})) == {"gearStatus": expected}

    def test_the_vocabulary_matches_what_the_sensor_already_maps(self) -> None:
        """The strings must be the SUBSCRIPTION's, not the app enum's.

        GEAR_STATUS_MAP was built from live subscription values, so emitting
        `park` rather than `GEAR_PARK` is what lets this topic feed the existing
        sensor instead of appending a new option to it.
        """
        from custom_components.rivian.const import GEAR_STATUS_MAP

        for wire in range(5):
            value = decode_gear(payload(**{"1": wire}))["gearStatus"]
            assert value in GEAR_STATUS_MAP, value

    def test_an_unmapped_value_is_dropped_not_invented(self) -> None:
        """New firmware must not become a new sensor option behind our back."""
        assert decode_gear(payload(**{"1": 99})) == {}


class TestDriveMode:
    def test_field_numbers_skip_two_through_seven(self) -> None:
        """The message really does jump 1 -> 8 -> 9.

        A hand-guessed layout would put the two booleans at 2 and 3 and silently
        decode nothing; this is the assertion that catches that.
        """
        assert decode_drive_mode(payload(**{"1": 2, "8": 1, "9": 0})) == {
            "driveMode": "everyday",
            "limitedAccelCold": 1,
            "limitedRegenCold": 0,
        }
        assert decode_drive_mode(payload(**{"2": 1, "3": 1})) == {}

    def test_the_vocabulary_matches_the_existing_sensor_map(self) -> None:
        from custom_components.rivian.const import DRIVE_MODE_MAP

        for wire in (2, 8, 9, 10, 11, 12, 13, 15):
            value = decode_drive_mode(payload(**{"1": wire}))["driveMode"]
            assert value in DRIVE_MODE_MAP, value


class TestRange:
    def test_all_three_fields(self) -> None:
        assert decode_range(payload(**{"1": 412, "2": 2, "3": 3})) == {
            "distanceToEmpty": 412,
            "rangeThreshold": "low",
            "coldRangeNotification": "cold_impact",
        }

    def test_range_is_not_converted(self) -> None:
        """km on the wire, km on the sensor. decode_odometer converts because its
        sensor is in metres; this one must not."""
        assert decode_range(payload(**{"1": 300}))["distanceToEmpty"] == 300


class TestAlarmState:
    @pytest.mark.parametrize(
        ("wire", "expected"),
        [(1, "false"), (2, "true"), (3, "signal_not_available")],
    )
    def test_values(self, wire: int, expected: str) -> None:
        assert (
            decode_alarm_state(payload(**{"1": wire}))["alarmSoundStatus"] == expected
        )

    def test_sna_is_a_value_the_integration_already_suppresses(self) -> None:
        """So it reports unknown rather than a confident Inactive."""
        from custom_components.rivian.const import INVALID_SENSOR_STATES

        value = decode_alarm_state(payload(**{"1": 3}))["alarmSoundStatus"]
        assert value in INVALID_SENSOR_STATES


class TestRemainingDecoders:
    def test_trailer(self) -> None:
        assert decode_trailer_state(payload(**{"1": 3})) == {
            "trailerStatus": "trailer_present_with_brakes"
        }

    def test_pet_mode(self) -> None:
        assert decode_pet_mode_status(payload(**{"1": 1, "2": 2})) == {
            "petModeStatus": "on",
            "petModeTemperatureStatus": "hot",
        }

    def test_low_voltage_battery(self) -> None:
        assert decode_low_voltage_battery(payload(**{"1": 2})) == {
            "twelveVoltBatteryHealth": "low"
        }

    def test_video_monitoring(self) -> None:
        assert decode_video_monitoring(payload(**{"1": 2, "2": 2, "3": 2})) == {
            "gearGuardVideoStatus": "enabled",
            "gearGuardVideoMode": "away_from_home",
            "gearGuardVideoTermsAccepted": "accepted",
        }

    def test_battery_characteristics(self) -> None:
        assert decode_battery_characteristics(payload(**{"2": 2})) == {
            "batteryCellType": "53g"
        }

    def test_btm_shares_one_enum_across_six_fields(self) -> None:
        got = decode_btm_diagnosis(
            payload(**{"1": 1, "2": 0, "3": 1, "4": 0, "5": 1, "6": 1})
        )
        assert got == {
            "btmFfHardwareFailureStatus": "set",
            "btmIcHardwareFailureStatus": "unspecified",
            "btmLfdHardwareFailureStatus": "set",
            "btmRfHardwareFailureStatus": "unspecified",
            "btmRfdHardwareFailureStatus": "set",
            "btmOcHardwareFailureStatus": "set",
        }

    def test_vas_fault(self) -> None:
        assert decode_vas_fault(payload(**{"1": 2, "2": 2})) == {
            "vasSecureElementFaulted": "lost_communication",
            "vasAccessCanFaulted": "failure",
        }

    def test_passive_entry_debug_covers_the_high_numbered_reasons(self) -> None:
        """Thirteen reasons, and the last five are double-digit values."""
        for wire, expected in (
            (1, "not_in_park"),
            (9, "show_and_tell_mode"),
            (13, "slept_immediate"),
        ):
            assert decode_passive_entry_debug(payload(**{"1": wire})) == {
                "passiveEntryUnlockFailReason": expected
            }

    def test_immobilizer_treats_zero_as_a_real_value(self) -> None:
        """SecureImmoStatus has no UNSPECIFIED sentinel: 0 means NOT_ASSIGNED."""
        assert decode_immobilizer_state(payload(**{"1": 0})) == {
            "secureImmobilizerStatus": "not_assigned"
        }

    def test_known_location(self) -> None:
        assert decode_known_location(payload(**{"1": 2})) == {"knownLocation": "home"}


class TestRegistration:
    NEW_TOPICS = (
        "body.trailer.state",
        "comfort.cabin.pet_mode_status",
        "dynamics.vehicle.drive_mode",
        "dynamics.vehicle.gear",
        "dynamics.vehicle.location",
        "dynamics.vehicle.range",
        "energy.high_voltage.battery_characteristics",
        "energy.low_voltage.battery_state",
        "security.access.btm",
        "security.access.immobilizer_state",
        "security.access.passive_entry_debug",
        "security.access.vas_fault",
        "security.alarm.state",
        "security.video_monitoring.state",
    )

    @pytest.mark.parametrize("topic", NEW_TOPICS)
    def test_each_is_registered(self, topic: str) -> None:
        assert topic in RVM_DECODERS

    @pytest.mark.parametrize("topic", NEW_TOPICS)
    def test_each_is_therefore_subscribed(self, topic: str) -> None:
        """SUBSCRIBED_RVMS is the intersection of the wanted topics with the ones
        that have a decoder, so writing a decoder is what subscribes its topic.
        Nothing else had to change."""
        from custom_components.rivian.coordinator import SUBSCRIBED_RVMS

        assert topic in SUBSCRIBED_RVMS

    def test_no_previously_working_decoder_was_replaced(self) -> None:
        """dynamics.tires.state and vehicle.wheels.vehicle_wheels were already
        decoded. Naming them in f5's queue would have sent someone to rewrite
        working code."""
        from custom_components.rivian.rivian_client.parallax import (
            decode_tires,
            decode_vehicle_wheels,
        )

        assert RVM_DECODERS["dynamics.tires.state"] is decode_tires
        assert RVM_DECODERS["vehicle.wheels.vehicle_wheels"] is decode_vehicle_wheels


class TestUnknownTopicLogging:
    def test_an_unknown_topic_warns_once_not_once_per_message(self, caplog) -> None:
        """SUBSCRIBED_RVMS only asks for decodable topics, so reaching the warning
        means the server pushed something unrequested -- which it does at telemetry
        rates. A warning per message buries the log."""
        from custom_components.rivian.rivian_client import parallax

        parallax._WARNED_UNKNOWN_RVMS.discard("made.up.topic")
        caplog.clear()
        with caplog.at_level("WARNING"):
            for _ in range(5):
                assert decode_parallax_message("made.up.topic", "") is None
        assert sum("made.up.topic" in r.message for r in caplog.records) == 1
        parallax._WARNED_UNKNOWN_RVMS.discard("made.up.topic")

    def test_a_known_topic_never_warns(self, caplog) -> None:
        caplog.clear()
        with caplog.at_level("WARNING"):
            decode_parallax_message("dynamics.vehicle.gear", payload(**{"1": 1}))
        assert not caplog.records


def test_the_double_consumer_flag_is_recorded_and_not_acted_on() -> None:
    """CLIMATE_HOLD_STATUS is the only topic with needDoubleConsumerSubscription.

    The plan said to honour it. Its getter -- `getNeedDoubleConsumerSubscription`
    -- has **no caller anywhere in the 32,941 decompiled files**, so app 3.15.0
    sets the flag and acts on it nowhere. Duplicating the topic in the rvms list
    would also contradict what the subscription code already documents: a
    duplicated topic is delivered twice.

    So it is transcribed and left alone. If a live capture ever shows
    climate_hold_status arriving only for a second consumer, this test is where to
    record the change.
    """
    from custom_components.rivian.coordinator import SUBSCRIBED_RVMS

    from tests.apk.transcription import RVM_TOPICS

    doubled = [t for t in RVM_TOPICS if t["need_double_consumer_subscription"]]
    assert [t["member"] for t in doubled] == ["CLIMATE_HOLD_STATUS"]

    topic = doubled[0]["rvm_name"]
    assert topic in RVM_DECODERS
    assert SUBSCRIBED_RVMS.count(topic) == 1


class TestNetworkState:
    """`vehicle.network.state` — the one decoder taken on an inference.

    `opl` is parsed in the app but its parser `ipf.e` has NO CALLER, so nothing in
    the decompilation says which topic feeds it. It is written anyway, on the
    owner's decision, because the identification is corroborated by a second
    independent source: its field names land one-to-one on the gateway schema f4
    rebuilt from the app's own vehicleState documents.

    The cost of being wrong is bounded and stated: every field here except
    `wifiSignal` is declared in the schema but NOT subscribed, so a bad decode
    mis-fills sensors that do not exist rather than corrupting a working one. And
    `wifiSignal` IS subscribed, so the gap-fill rule keeps the subscription's value
    and this decoder cannot touch it.
    """

    @staticmethod
    def _nested(field_num: int, inner: bytes) -> str:
        data = _varint((field_num << 3) | 2) + _varint(len(inner)) + inner
        return base64.b64encode(data).decode()

    @staticmethod
    def _msg(**fields) -> bytes:
        out = b""
        for num, value in fields.items():
            if isinstance(value, str):
                raw = value.encode()
                out += _varint((int(num) << 3) | 2) + _varint(len(raw)) + raw
            else:
                out += _varint((int(num) << 3) | 0) + _varint(value)
        return out

    def test_wifi_submessage(self) -> None:
        from custom_components.rivian.rivian_client.parallax import decode_network_state

        inner = self._msg(
            **{"1": 2, "3": "HomeNet", "7": 5, "9": 433, "10": 5180, "12": 4}
        )
        assert decode_network_state(self._nested(4, inner)) == {
            "wifiWpaStatus": "connected",
            "wifiSsid": "HomeNet",
            "wifiAntennaBars": "level_4",
            "wifiLinkSpeed": 433,
            "wifiFreq": 5180,
            "wifiSecureStatus": "wpa2_personal",
        }

    def test_cellular_submessage(self) -> None:
        from custom_components.rivian.rivian_client.parallax import decode_network_state

        inner = self._msg(**{"1": "Rivian", "2": "LTE", "3": 3, "4": 71})
        assert decode_network_state(self._nested(5, inner)) == {
            "cellularCarrier": "Rivian",
            "cellularMode": "LTE",
            "cellularAntennaBars": "level_2",
            "cellularSignalStrength": 71,
        }

    def test_it_is_registered(self) -> None:
        assert "vehicle.network.state" in RVM_DECODERS

    def test_every_field_it_writes_is_declared_in_the_schema(self) -> None:
        """The corroboration that made this worth taking.

        If a future schema edit drops one of these names, the inference weakens and
        this test says so.
        """
        import pathlib
        import re

        schema = (
            pathlib.Path(__file__).parents[2]
            / "custom_components/rivian/rivian_client/schemas/gateway.graphql"
        ).read_text()
        block = schema.split("type VehicleState {", 1)[1].split("\n}", 1)[0]
        declared = set(re.findall(r"^  (\w+):", block, re.MULTILINE))
        from custom_components.rivian.rivian_client.parallax import (
            _CELLULAR_SPEC,
            _WIFI_SPEC,
        )

        written = {key for key, _ in (*_WIFI_SPEC.values(), *_CELLULAR_SPEC.values())}
        assert written <= declared, sorted(written - declared)

    def test_only_wifi_signal_can_collide_with_the_subscription(self) -> None:
        """And the gap-fill rule means the subscription keeps it."""
        from custom_components.rivian.const import VEHICLE_STATE_API_FIELDS
        from custom_components.rivian.rivian_client.parallax import (
            _CELLULAR_SPEC,
            _WIFI_SPEC,
        )

        written = {key for key, _ in (*_WIFI_SPEC.values(), *_CELLULAR_SPEC.values())}
        assert written & VEHICLE_STATE_API_FIELDS == {"wifiSignal"}
