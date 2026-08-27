"""Shrink a browser SDP offer until a KVS signaling frame will carry it.

This is not something the Rivian app does -- it builds its own offer and keeps
it small. It exists for Home Assistant's built-in camera player, which offers a
recvonly audio and a recvonly video transceiver, cannot be told to prefer a
codec, and on Chrome arrives well over the KVS limit with AV1, VP9, VP8, four
H264 profiles, red and ulpfec plus an rtx line for each. The bundled card calls
setCodecPreferences (see `www/gear-guard-card.js`) and never reaches here.

The proper fix is upstream: a codec-preference field on HA's
`WebRTCClientConfiguration` that `ha-web-rtc-player` honoured would remove the
need for this module entirely. Until that exists there is no seam -- the offer
arrives as an opaque string after the frontend has already called createOffer.

What this removes is only ever a codec the vehicle would not have chosen (it
answers H264 and nothing else, and no audio at all) or a header extension it
was free to ignore. Payload types are never renumbered and m= sections are
never added, removed or reordered, so the answer that comes back still matches
the offer the browser is holding -- `_preserves_shape` enforces that on the way
out rather than trusting each reduction to have been careful.
"""

from __future__ import annotations

import re
from typing import Final

from .kvs_signaling import offer_exceeds_kvs_limit

_RTPMAP = re.compile(r"^a=rtpmap:(\d+)\s+([^/]+)/")
_FMTP_APT = re.compile(r"^a=fmtp:(\d+)\s+.*\bapt=(\d+)")
# rtcp-fb also uses `*` for "every codec"; that has no digits and is kept.
_PAYLOAD_ATTR = re.compile(r"^a=(?:rtpmap|fmtp|rtcp-fb):(\d+)\b")

# What the vehicle actually answers, per media kind. Every gearGuardLiveConfig
# session observed answers `a=rtpmap:<pt> H264/90000` and rejects audio
# outright; the card encodes the same fact via setCodecPreferences. Anything
# else in the offer is weight paid for an option that will never be taken.
_PREFERRED_CODEC: Final = {"audio": "opus", "video": "h264"}


def _blocks(sdp: str) -> list[list[str]]:
    """Split into the session block followed by one block per m= section."""
    out: list[list[str]] = []
    current: list[str] = []
    for line in sdp.replace("\r\n", "\n").split("\n"):
        if line.startswith("m=") and current:
            out.append(current)
            current = []
        current.append(line)
    if current:
        out.append(current)
    return out


def _join(blocks: list[list[str]]) -> str:
    """Rejoin with CRLF, which is what SDP uses and what came in."""
    return "\r\n".join(line for block in blocks for line in block)


def _media_kind(block: list[str]) -> str | None:
    """The `audio`/`video`/`application` of this block's m= line, if any."""
    if not block[0].startswith("m="):
        return None
    return block[0][2:].split(maxsplit=1)[0]


def _keep_preferred_codec(block: list[str], wanted: str) -> list[str]:
    """Reduce one m= section to `wanted` and the rtx that repairs it."""
    parts = block[0].split()
    if len(parts) < 4:
        return block
    offered = parts[3:]

    names = {
        hit.group(1): hit.group(2).lower()
        for line in block
        if (hit := _RTPMAP.match(line))
    }
    primary = {pt for pt in offered if names.get(pt) == wanted}
    if not primary:
        # Nothing recognisable to keep. Emptying the m= line would reject the
        # whole section, which is worse than an offer that is merely too large.
        return block
    rtx = {
        hit.group(1)
        for line in block
        if (hit := _FMTP_APT.match(line))
        and hit.group(2) in primary
        and names.get(hit.group(1)) == "rtx"
    }
    keep = primary | rtx

    out = [" ".join(parts[:3] + [pt for pt in offered if pt in keep])]
    out.extend(
        line
        for line in block[1:]
        if (hit := _PAYLOAD_ATTR.match(line)) is None or hit.group(1) in keep
    )
    return out


def _shape(sdp: str) -> tuple[list[str], dict[str, str]]:
    """The parts of an offer an answer is negotiated against.

    The m= media kinds in order, and what each surviving payload number means.
    An answer refers back to both, so a reduction may narrow them but must
    never renumber or reorder them.
    """
    kinds: list[str] = []
    codecs: dict[str, str] = {}
    for block in _blocks(sdp):
        if (kind := _media_kind(block)) is not None:
            kinds.append(kind)
        for line in block:
            if hit := _RTPMAP.match(line):
                codecs[hit.group(1)] = hit.group(2).lower()
    return kinds, codecs


def _preserves_shape(original: str, reduced: str) -> bool:
    """Whether `reduced` is still an offer the browser's answer can match."""
    was_kinds, was_codecs = _shape(original)
    now_kinds, now_codecs = _shape(reduced)
    return was_kinds == now_kinds and all(
        was_codecs.get(pt) == name for pt, name in now_codecs.items()
    )


def trim_offer_for_kvs(sdp: str) -> str:
    """Return the smallest faithful form of this offer, or it unchanged.

    Tries the cheapest reduction first and stops as soon as the offer fits, so
    an offer that was already small is returned byte-for-byte. An offer that
    cannot be made to fit is returned at its smallest -- the caller still has
    to check, and report, that it is over. A reduction that would change the
    shape the answer is negotiated against is discarded rather than sent.
    """
    if not offer_exceeds_kvs_limit(sdp):
        return sdp

    blocks = [
        _keep_preferred_codec(block, wanted)
        if (wanted := _PREFERRED_CODEC.get(_media_kind(block) or ""))
        else block
        for block in _blocks(sdp)
    ]
    if not offer_exceeds_kvs_limit(candidate := _join(blocks)):
        return candidate if _preserves_shape(sdp, candidate) else sdp

    # Still over: the extensions are negotiable too, and dropping them costs
    # the viewer nothing the vehicle was going to honour.
    candidate = _join(
        [
            [line for line in block if not line.startswith("a=extmap:")]
            for block in blocks
        ]
    )
    return candidate if _preserves_shape(sdp, candidate) else sdp
