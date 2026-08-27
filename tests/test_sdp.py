"""Trimming an offer HA's own player built, so KVS will carry it.

The vehicle answers H264 and nothing else, so everything removed here is
something it would have declined. What must survive is the shape the browser
is holding: same m= sections in the same order, and payload numbers it can
still recognise in the answer.
"""

from __future__ import annotations

import re

from custom_components.rivian.kvs_signaling import (
    KVS_MAX_MESSAGE_PAYLOAD,
    offer_exceeds_kvs_limit,
    offer_message,
)
from custom_components.rivian.sdp import _preserves_shape, trim_offer_for_kvs

from tests.webrtc import VIDEO_CODECS, chrome_offer


def _video_payload_types(sdp: str) -> list[str]:
    for line in sdp.replace("\r\n", "\n").split("\n"):
        if line.startswith("m=video"):
            return line.split()[3:]
    raise AssertionError("no video m= line")


def _section(sdp: str, m_prefix: str) -> list[str]:
    """The lines of one m= section, m= line first."""
    out: list[str] = []
    for line in sdp.replace("\r\n", "\n").split("\n"):
        if line.startswith("m="):
            if out:
                break
            if not line.startswith(m_prefix):
                continue
        if out or line.startswith(m_prefix):
            out.append(line)
    return out


def _attr_payload_types(sdp: str, prefix: str) -> set[str]:
    return {
        line.split(":", 1)[1].split()[0]
        for line in sdp.replace("\r\n", "\n").split("\n")
        if line.startswith(prefix)
    }


def test_an_offer_that_already_fits_is_returned_untouched() -> None:
    """Trimming is a last resort for a viewer we cannot configure. Anything
    that fits must reach the vehicle exactly as the browser wrote it."""
    small = chrome_offer(extmaps=1, fmtp_padding=0)
    assert not offer_exceeds_kvs_limit(small)
    assert trim_offer_for_kvs(small) is small


def test_an_oversized_offer_is_brought_under_the_limit() -> None:
    """The whole point: HA's player cannot be told to offer less, so an offer
    it builds must be made to fit rather than refused."""
    fat = chrome_offer()
    assert offer_exceeds_kvs_limit(fat)

    trimmed = trim_offer_for_kvs(fat)

    assert not offer_exceeds_kvs_limit(trimmed)


def test_only_h264_and_the_rtx_that_repairs_it_survive() -> None:
    """The vehicle answers H264 and nothing else, so every other codec is
    weight we are paying for an option it will never take. rtx has to follow
    its own codec or retransmission silently stops working."""
    trimmed = trim_offer_for_kvs(chrome_offer())

    video = "\r\n".join(_section(trimmed, "m=video"))
    assert _video_payload_types(trimmed) == ["102", "103", "104", "105"]
    # The attribute lines for dropped codecs go with them.
    assert _attr_payload_types(video, "a=rtpmap:") == {"102", "103", "104", "105"}
    assert _attr_payload_types(video, "a=rtcp-fb:") == {"102", "103", "104", "105"}


def test_payload_numbers_are_never_reassigned() -> None:
    """The browser keeps the offer it built. Renumbering would make the answer
    describe codecs it never offered, and setRemoteDescription would reject."""
    fat = chrome_offer()
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
    trimmed = trim_offer_for_kvs(chrome_offer())

    lines = trimmed.replace("\r\n", "\n").split("\n")
    assert [line.split()[0] for line in lines if line.startswith("m=")] == [
        "m=video",
        "m=audio",
        "m=application",
    ]
    assert "a=sctp-port:5000" in lines
    assert "a=mid:1" in lines


def test_the_negotiating_attributes_survive() -> None:
    """Strip an ice-ufrag or a fingerprint and the session cannot come up at
    all -- a much worse failure than the one being fixed."""
    trimmed = trim_offer_for_kvs(chrome_offer()).replace("\r\n", "\n").split("\n")

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
    modest = chrome_offer()
    assert offer_exceeds_kvs_limit(modest)
    assert "a=extmap:1 " in trim_offer_for_kvs(modest)

    # Enough extensions that dropping codecs alone cannot get under the limit.
    huge = chrome_offer(extmaps=200, fmtp_padding=0)
    trimmed = trim_offer_for_kvs(huge)
    assert "a=extmap:" not in trimmed
    assert not offer_exceeds_kvs_limit(trimmed)


def test_an_offer_with_no_h264_keeps_every_codec_it_had() -> None:
    """Emptying the m= line would reject the video section outright, so with
    nothing recognisable to keep the codec list is left alone -- an offer that
    is merely too large still beats one that cannot describe a stream. The
    extensions are still fair game, so it may shrink; the codecs may not."""
    no_h264 = chrome_offer().replace("H264/90000", "VP8/90000")
    assert offer_exceeds_kvs_limit(no_h264)

    trimmed = trim_offer_for_kvs(no_h264)

    video = "\r\n".join(_section(trimmed, "m=video"))
    assert _video_payload_types(trimmed) == [pt for pt, _ in VIDEO_CODECS]
    assert _attr_payload_types(video, "a=rtpmap:") == {pt for pt, _ in VIDEO_CODECS}


def test_a_trimmed_offer_still_encodes_as_a_valid_kvs_frame() -> None:
    """Trimming happens upstream of offer_message; the result has to survive
    the same CRLF rewrite and base64 the untrimmed one would have."""
    trimmed = trim_offer_for_kvs(chrome_offer())

    message = offer_message(trimmed, "client-1")

    assert message["action"] == "SDP_OFFER"
    assert len(message["messagePayload"]) <= KVS_MAX_MESSAGE_PAYLOAD
    # Rejoined with CRLF like it arrived, so the caller comparing lengths
    # before and after is comparing the same units.
    assert "\r\n" in trimmed
    assert not re.search(r"(?<!\r)\n", trimmed)


def test_the_audio_section_is_narrowed_too() -> None:
    """HA's player offers a recvonly audio transceiver the vehicle declines
    outright. Leaving its seven codecs untouched spends most of a kilobyte on
    an option that cannot be taken -- and it was half the offer this module
    exists to shrink."""
    trimmed = trim_offer_for_kvs(chrome_offer())

    audio = _section(trimmed, "m=audio")
    assert audio[0].split()[3:] == ["111"]
    assert _attr_payload_types("\r\n".join(audio), "a=rtpmap:") == {"111"}
    # Narrowed, not removed: the section has to stay for the answer to line up.
    assert len(_section(trimmed, "m=audio")) > 1


def test_a_reduction_that_changed_the_shape_would_be_discarded() -> None:
    """The safety net for every future stage. Renumbering or dropping an m=
    section makes setRemoteDescription reject the answer, and the symptom is
    the same silent black player this module was written to prevent."""
    fat = chrome_offer()

    assert _preserves_shape(fat, trim_offer_for_kvs(fat))
    # A reduction that renumbers, or loses a section, must not be accepted.
    assert not _preserves_shape(fat, fat.replace("H264/90000", "H265/90000"))
    assert not _preserves_shape(
        fat, "\r\n".join(_l for _l in fat.split("\r\n") if not _l.startswith("m=audio"))
    )
