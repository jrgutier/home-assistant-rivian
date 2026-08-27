"""Trimming an offer HA's own player built, so KVS will carry it.

The vehicle answers H264 and nothing else, so everything removed here is
something it would have declined. What must survive is the shape the browser
is holding: same m= sections in the same order, and payload numbers it can
still recognise in the answer.
"""

from __future__ import annotations

from custom_components.rivian.kvs_signaling import (
    encode_payload,
    offer_exceeds_kvs_limit,
    offer_message,
)
from custom_components.rivian.sdp import trim_offer_for_kvs

# Chrome's real offer shape: AV1/VP9/VP8/H264 with an rtx for each, red and
# ulpfec, a dozen header extensions. Padded to clear the KVS limit.
_VIDEO_CODECS = [
    ("96", "AV1/90000"),
    ("97", "rtx/90000"),
    ("98", "VP9/90000"),
    ("99", "rtx/90000"),
    ("100", "VP8/90000"),
    ("101", "rtx/90000"),
    ("102", "H264/90000"),
    ("103", "rtx/90000"),
    ("104", "H264/90000"),
    ("105", "rtx/90000"),
    ("106", "red/90000"),
    ("107", "ulpfec/90000"),
]
_APT = {"97": "96", "99": "98", "101": "100", "103": "102", "105": "104"}


def _chrome_offer(extmaps: int = 12, fmtp_padding: int = 760) -> str:
    pts = [pt for pt, _ in _VIDEO_CODECS]
    lines = [
        "v=0",
        "o=- 4611731400430051336 2 IN IP4 127.0.0.1",
        "s=-",
        "t=0 0",
        "a=group:BUNDLE 0 1",
        "m=video 9 UDP/TLS/RTP/SAVPF " + " ".join(pts),
        "c=IN IP4 0.0.0.0",
        "a=rtcp-mux",
        "a=mid:0",
        "a=recvonly",
        "a=ice-ufrag:aBcD",
        "a=ice-pwd:0123456789abcdef0123",
        "a=fingerprint:sha-256 AA:BB:CC:DD",
        "a=setup:actpass",
    ]
    lines += [
        f"a=extmap:{i} urn:ietf:params:rtp-hdrext:example-{i}"
        for i in range(1, extmaps + 1)
    ]
    for pt, name in _VIDEO_CODECS:
        lines.append(f"a=rtpmap:{pt} {name}")
        if pt in _APT:
            lines.append(f"a=fmtp:{pt} apt={_APT[pt]}")
        else:
            # Every primary codec carries its own fmtp, so the fixture's size
            # tracks how many codecs it offers rather than which ones -- the
            # no-H264 case has to stay just as oversized as the default.
            lines.append(
                f"a=fmtp:{pt} level-asymmetry-allowed=1;packetization-mode=1;"
                f"profile-level-id=42e01f;" + "x" * fmtp_padding
            )
        lines.append(f"a=rtcp-fb:{pt} nack")
        lines.append(f"a=rtcp-fb:{pt} goog-remb")
    lines += [
        "m=application 9 UDP/DTLS/SCTP webrtc-datachannel",
        "c=IN IP4 0.0.0.0",
        "a=mid:1",
        "a=sctp-port:5000",
        "a=ice-ufrag:aBcD",
        "a=fingerprint:sha-256 AA:BB:CC:DD",
        "",
    ]
    return "\r\n".join(lines)


def _video_payload_types(sdp: str) -> list[str]:
    for line in sdp.replace("\r\n", "\n").split("\n"):
        if line.startswith("m=video"):
            return line.split()[3:]
    raise AssertionError("no video m= line")


def _attr_payload_types(sdp: str, prefix: str) -> set[str]:
    return {
        line.split(":", 1)[1].split()[0]
        for line in sdp.replace("\r\n", "\n").split("\n")
        if line.startswith(prefix)
    }


def test_an_offer_that_already_fits_is_returned_untouched() -> None:
    """Trimming is a last resort for a viewer we cannot configure. Anything
    that fits must reach the vehicle exactly as the browser wrote it."""
    small = _chrome_offer(extmaps=1, fmtp_padding=0)
    assert not offer_exceeds_kvs_limit(small)
    assert trim_offer_for_kvs(small) is small


def test_an_oversized_offer_is_brought_under_the_limit() -> None:
    """The whole point: HA's player cannot be told to offer less, so an offer
    it builds must be made to fit rather than refused."""
    fat = _chrome_offer()
    assert offer_exceeds_kvs_limit(fat)

    trimmed = trim_offer_for_kvs(fat)

    assert not offer_exceeds_kvs_limit(trimmed)
    assert len(encode_payload({"type": "offer", "sdp": trimmed})) < len(
        encode_payload({"type": "offer", "sdp": fat})
    )


def test_only_h264_and_the_rtx_that_repairs_it_survive() -> None:
    """The vehicle answers H264 and nothing else, so every other codec is
    weight we are paying for an option it will never take. rtx has to follow
    its own codec or retransmission silently stops working."""
    trimmed = trim_offer_for_kvs(_chrome_offer())

    assert _video_payload_types(trimmed) == ["102", "103", "104", "105"]
    # The attribute lines for dropped codecs go with them.
    assert _attr_payload_types(trimmed, "a=rtpmap:") == {"102", "103", "104", "105"}
    assert _attr_payload_types(trimmed, "a=rtcp-fb:") == {"102", "103", "104", "105"}


def test_payload_numbers_are_never_reassigned() -> None:
    """The browser keeps the offer it built. Renumbering would make the answer
    describe codecs it never offered, and setRemoteDescription would reject."""
    fat = _chrome_offer()
    trimmed = trim_offer_for_kvs(fat)

    original = dict(
        line.split(":", 1)[1].split(" ", 1)
        for line in fat.replace("\r\n", "\n").split("\n")
        if line.startswith("a=rtpmap:")
    )
    for line in trimmed.replace("\r\n", "\n").split("\n"):
        if line.startswith("a=rtpmap:"):
            pt, name = line.split(":", 1)[1].split(" ", 1)
            assert original[pt] == name


def test_the_data_channel_section_is_left_alone() -> None:
    """m= sections must stay in the same order and count, or the answer no
    longer lines up with the offer the browser is holding."""
    trimmed = trim_offer_for_kvs(_chrome_offer())

    lines = trimmed.replace("\r\n", "\n").split("\n")
    assert [line.split()[0] for line in lines if line.startswith("m=")] == [
        "m=video",
        "m=application",
    ]
    assert "a=sctp-port:5000" in lines
    assert "a=mid:1" in lines


def test_the_negotiating_attributes_survive() -> None:
    """Strip an ice-ufrag or a fingerprint and the session cannot come up at
    all -- a much worse failure than the one being fixed."""
    trimmed = trim_offer_for_kvs(_chrome_offer()).replace("\r\n", "\n").split("\n")

    for required in (
        "a=ice-ufrag:aBcD",
        "a=ice-pwd:0123456789abcdef0123",
        "a=fingerprint:sha-256 AA:BB:CC:DD",
        "a=setup:actpass",
        "a=rtcp-mux",
        "a=recvonly",
        "a=mid:0",
    ):
        assert required in trimmed


def test_header_extensions_go_only_when_codecs_were_not_enough() -> None:
    """Extensions are cheap for the vehicle to ignore but they are what the
    viewer uses for things like orientation, so they are the second cut."""
    modest = _chrome_offer()
    assert "a=extmap:1 " in trim_offer_for_kvs(modest)

    # Enough extensions that dropping codecs alone cannot get under the limit.
    huge = _chrome_offer(extmaps=200, fmtp_padding=0)
    trimmed = trim_offer_for_kvs(huge)
    assert "a=extmap:" not in trimmed
    assert not offer_exceeds_kvs_limit(trimmed)


def test_an_offer_with_no_h264_keeps_every_codec_it_had() -> None:
    """Emptying the m= line would reject the video section outright, so with
    nothing recognisable to keep the codec list is left alone -- an offer that
    is merely too large still beats one that cannot describe a stream. The
    extensions are still fair game, so it may shrink; the codecs may not."""
    no_h264 = _chrome_offer().replace("H264/90000", "VP8/90000")
    assert offer_exceeds_kvs_limit(no_h264)

    trimmed = trim_offer_for_kvs(no_h264)

    assert _video_payload_types(trimmed) == [pt for pt, _ in _VIDEO_CODECS]
    assert _attr_payload_types(trimmed, "a=rtpmap:") == {pt for pt, _ in _VIDEO_CODECS}


def test_a_trimmed_offer_still_encodes_as_a_valid_kvs_frame() -> None:
    """Trimming happens upstream of offer_message; the result has to survive
    the same CRLF rewrite and base64 the untrimmed one would have."""
    trimmed = trim_offer_for_kvs(_chrome_offer())

    message = offer_message(trimmed, "client-1")

    assert message["action"] == "SDP_OFFER"
    assert len(message["messagePayload"]) <= 10000
