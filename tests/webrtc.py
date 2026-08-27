"""Builders for the SDP offers these tests need, shared across modules.

`chrome_offer` reproduces the shape Chrome actually sends -- every codec it
supports, with an rtx for each -- because that shape is what overflows a KVS
signaling frame. `sdp_of_length` is for when only the size matters.
"""

from __future__ import annotations

# Chrome's real offer shape: AV1/VP9/VP8/H264 with an rtx for each, red and
# ulpfec, a dozen header extensions. Padded to clear the KVS limit.
VIDEO_CODECS = [
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
APT = {"97": "96", "99": "98", "101": "100", "103": "102", "105": "104"}

# HA's player offers a recvonly AUDIO transceiver as well as video
# (ha-web-rtc-player calls addTransceiver twice), so a faithful fixture has to
# carry this section -- it is weight the vehicle declines outright.
AUDIO_CODECS = [
    ("111", "opus/48000"),
    ("63", "red/48000"),
    ("9", "G722/8000"),
    ("0", "PCMU/8000"),
    ("8", "PCMA/8000"),
    ("13", "CN/8000"),
    ("110", "telephone-event/48000"),
]


def chrome_offer(extmaps: int = 12, fmtp_padding: int = 380) -> str:
    pts = [pt for pt, _ in VIDEO_CODECS]
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
    for pt, name in VIDEO_CODECS:
        lines.append(f"a=rtpmap:{pt} {name}")
        if pt in APT:
            lines.append(f"a=fmtp:{pt} apt={APT[pt]}")
        else:
            # Every primary codec carries its own fmtp, so the fixture's size
            # tracks how many codecs it offers rather than which ones -- the
            # no-H264 case has to stay just as oversized as the default.
            lines.append(
                f"a=fmtp:{pt} level-asymmetry-allowed=1;packetization-mode=1;"
                "profile-level-id=42e01f;" + "x" * fmtp_padding
            )
        lines.append(f"a=rtcp-fb:{pt} nack")
        lines.append(f"a=rtcp-fb:{pt} goog-remb")
    lines += [
        "m=audio 9 UDP/TLS/RTP/SAVPF " + " ".join(pt for pt, _ in AUDIO_CODECS),
        "c=IN IP4 0.0.0.0",
        "a=rtcp-mux",
        "a=mid:1",
        "a=recvonly",
        "a=ice-ufrag:aBcD",
        "a=fingerprint:sha-256 AA:BB:CC:DD",
    ]
    for pt, name in AUDIO_CODECS:
        lines.append(f"a=rtpmap:{pt} {name}")
        lines.append(f"a=fmtp:{pt} minptime=10;useinbandfec=1;" + "y" * fmtp_padding)
    lines += [
        "m=application 9 UDP/DTLS/SCTP webrtc-datachannel",
        "c=IN IP4 0.0.0.0",
        "a=mid:2",
        "a=sctp-port:5000",
        "a=ice-ufrag:aBcD",
        "a=fingerprint:sha-256 AA:BB:CC:DD",
        "",
    ]
    return "\r\n".join(lines)


def sdp_of_length(length: int) -> str:
    """A CRLF-heavy SDP of roughly `length` bytes, like a real browser offer."""
    head = "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\ns=-\r\n"
    line = "a=fmtp:96 profile-level-id=42e01f;packetization-mode=1\r\n"
    return head + line * max(0, (length - len(head)) // len(line))
