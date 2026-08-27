"""KVS signaling encode/decode must match the APK, not a guessed AWS SDK."""

from __future__ import annotations

import base64
import json

import pytest

from custom_components.rivian.kvs_signaling import (
    client_id_from_endpoint,
    decode_payload,
    encode_payload,
    ice_candidate_message,
    ice_servers_from_config,
    ice_ttl_from_config,
    ice_usable_seconds,
    offer_message,
    parse_signaling_event,
    signaling_ws_url,
)


def test_payload_roundtrip_urlsafe_no_padding() -> None:
    """Android flags 11: URL_SAFE | NO_WRAP | NO_PADDING."""
    inner = {"type": "offer", "sdp": "v=0\r\n"}
    encoded = encode_payload(inner)
    assert "=" not in encoded
    assert decode_payload(encoded) == inner


def test_decode_accepts_standard_padded_base64() -> None:
    """Incoming KVS events use Event.parseSdpEvent DEFAULT decode (flags 0)."""
    inner = {"type": "answer", "sdp": "v=0"}
    padded = base64.b64encode(
        json.dumps(inner, separators=(",", ":")).encode()
    ).decode()
    assert decode_payload(padded) == inner


def test_offer_message_matches_apk_shape() -> None:
    msg = offer_message("v=0\no=x", "client-1")
    assert msg["action"] == "SDP_OFFER"
    assert msg["senderClientId"] == "client-1"
    assert msg["recipientClientId"] == ""
    inner = decode_payload(msg["messagePayload"])
    assert inner["type"] == "offer"
    assert inner["sdp"] == "v=0\r\no=x"


def test_ice_candidate_payload_matches_uri_utils() -> None:
    """UriUtilsKt.getIceCandidatePayload field names."""
    msg = ice_candidate_message("candidate:1", "0", 0, "viewer", "master")
    assert msg["action"] == "ICE_CANDIDATE"
    inner = decode_payload(msg["messagePayload"])
    assert inner == {
        "candidate": "candidate:1",
        "sdpMid": "0",
        "sdpMLineIndex": 0,
    }


def test_parse_incoming_event_message_type() -> None:
    inner = {"type": "answer", "sdp": "v=0"}
    raw = json.dumps(
        {
            "messageType": "SDP_ANSWER",
            "senderClientId": "master-1",
            "messagePayload": encode_payload(inner),
        }
    )
    event = parse_signaling_event(raw)
    assert event is not None
    assert event["messageType"] == "SDP_ANSWER"
    assert event["senderClientId"] == "master-1"
    assert event["payload"]["sdp"] == "v=0"


def test_parse_ignores_non_signaling() -> None:
    assert parse_signaling_event("{}") is None
    assert parse_signaling_event("not json") is None


def test_signaling_url_adds_client_id_when_missing() -> None:
    url = signaling_ws_url(
        "wss://v-test.kinesisvideo.us-east-1.amazonaws.com/?X-Amz-ChannelARN=arn%3Aaws%3Akinesis",
        "arn:aws:kinesis",
        "client-xyz",
    )
    assert "X-Amz-ClientId=client-xyz" in url
    assert url.startswith("wss://")
    # Do not re-add ARN when already present.
    assert url.count("X-Amz-ChannelARN=") == 1


def test_signaling_url_https_becomes_wss() -> None:
    url = signaling_ws_url(
        "https://v-test.kinesisvideo.us-east-1.amazonaws.com/", "arn", "cid"
    )
    assert url.startswith("wss://")
    assert "X-Amz-ChannelARN=arn" in url
    assert "X-Amz-ClientId=cid" in url


def test_signaling_url_rejects_non_kvs_host() -> None:
    with pytest.raises(ValueError, match="Rejected non-KVS"):
        signaling_ws_url("wss://evil.example/", "arn", "cid")


def test_signaling_url_rejects_cleartext() -> None:
    with pytest.raises(ValueError, match="Rejected non-KVS"):
        signaling_ws_url(
            "http://v-test.kinesisvideo.us-east-1.amazonaws.com/", "arn", "cid"
        )
    with pytest.raises(ValueError, match="Rejected non-KVS"):
        signaling_ws_url(
            "ws://v-test.kinesisvideo.us-east-1.amazonaws.com/", "arn", "cid"
        )


def test_signaling_url_rejects_amazonaws_suffix_bypass() -> None:
    with pytest.raises(ValueError, match="Rejected non-KVS"):
        signaling_ws_url("wss://evil.kinesisvideo.s3.amazonaws.com/", "arn", "cid")


def test_signed_url_is_not_mutated() -> None:
    """Appending ClientId to a SigV4 URL would invalidate the signature."""
    signed = (
        "wss://v-test.kinesisvideo.us-east-1.amazonaws.com/"
        "?X-Amz-Algorithm=AWS4-HMAC-SHA256"
        "&X-Amz-Credential=AKI"
        "&X-Amz-Signature=abc"
        "&X-Amz-ClientId=bound-id"
    )
    url = signaling_ws_url(signed, "arn:aws:kinesis", "other-client")
    assert "other-client" not in url
    assert "X-Amz-ClientId=bound-id" in url
    assert "X-Amz-Signature=abc" in url


def test_client_id_from_endpoint() -> None:
    assert (
        client_id_from_endpoint(
            "wss://v-test.kinesisvideo.us-east-1.amazonaws.com/?X-Amz-ClientId=bound-id"
        )
        == "bound-id"
    )
    assert (
        client_id_from_endpoint("wss://v-test.kinesisvideo.us-east-1.amazonaws.com/")
        is None
    )


def test_ice_servers_from_config_maps_url_field() -> None:
    """GraphQL uses iceServers { url username credential ttl }, singular url."""
    shaped = ice_servers_from_config(
        [{"url": "stun:example", "username": "u", "credential": "c", "ttl": 300}]
    )
    assert shaped == [{"urls": "stun:example", "username": "u", "credential": "c"}]


def test_ice_ttl_is_the_shortest_one_kvs_gave() -> None:
    """The TURN credential dies at its own expiry, so the cache lives that long."""
    assert (
        ice_ttl_from_config(
            [
                {"url": "stun:example", "ttl": 300},
                {"url": "turn:example", "ttl": 120},
            ]
        )
        == 120
    )


def test_ice_ttl_ignores_junk_and_falls_back() -> None:
    """A config with no usable ttl must not cache forever or expire instantly."""
    assert ice_ttl_from_config(None) == 300
    assert ice_ttl_from_config([{"url": "stun:example"}]) == 300
    assert ice_ttl_from_config([{"url": "stun:example", "ttl": 0}]) == 300
    assert ice_ttl_from_config(["not-a-dict"]) == 300
    assert ice_ttl_from_config([{"url": "stun:example", "ttl": "nope"}]) == 300


def test_usable_seconds_takes_the_margin_off_the_ttl() -> None:
    """Handing out a credential that dies mid-session is worse than refetching:
    the viewer gets a relay it cannot authenticate to and simply stalls."""
    assert ice_usable_seconds([{"url": "turn:example", "ttl": 300}]) == 270
    assert ice_usable_seconds(None) == 270
    # A ttl shorter than the margin must floor at zero, never go negative --
    # a negative window would date the cache into the past on arrival.
    assert ice_usable_seconds([{"url": "turn:example", "ttl": 5}]) == 0


def test_decode_payload_falls_back_to_standard_base64() -> None:
    """urlsafe decode can fail; Event.java uses flags 0 (standard alphabet)."""
    import binascii
    from unittest.mock import patch

    inner = {"type": "answer"}
    padded = base64.b64encode(
        json.dumps(inner, separators=(",", ":")).encode()
    ).decode()
    with patch(
        "custom_components.rivian.kvs_signaling.base64.urlsafe_b64decode",
        side_effect=binascii.Error,
    ):
        assert decode_payload(padded) == inner


def test_decode_payload_rejects_non_object() -> None:
    raw = json.dumps(["not", "an", "object"], separators=(",", ":")).encode()
    payload = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    with pytest.raises(TypeError, match="not an object"):
        decode_payload(payload)


def test_parse_signaling_event_skips_junk() -> None:
    assert parse_signaling_event("[]") is None
    assert parse_signaling_event('{"messagePayload":"xx"}') is None
    bad = json.dumps(
        {"messageType": "SDP_ANSWER", "messagePayload": "!!!!not-base64!!!!"}
    )
    assert parse_signaling_event(bad) is None


def test_ice_servers_from_config_skips_junk() -> None:
    assert ice_servers_from_config(None) == []
    assert ice_servers_from_config(["stun:x", {}, {"url": ""}]) == []


def test_signaling_url_bare_host_gets_wss() -> None:
    url = signaling_ws_url("v-test.kinesisvideo.us-east-1.amazonaws.com/", "arn", "cid")
    assert url.startswith("wss://")
    assert "X-Amz-ClientId=cid" in url
