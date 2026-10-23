from __future__ import annotations

import re
from typing import Final

from .kvs_signaling import offer_exceeds_kvs_limit

_RTPMAP = re.compile(r"^a=rtpmap:(\d+)\s+([^/]+)/")
_FMTP_APT = re.compile(r"^a=fmtp:(\d+)\s+.*\bapt=(\d+)")
# rtcp-fb also uses `*` for "every codec"; that has no digits and is kept.
_PAYLOAD_ATTR = re.compile(r"^a=(?:rtpmap|fmtp|rtcp-fb):(\d+)\b")

_PREFERRED_CODEC: Final = {"audio": "opus", "video": "h264"}


def _blocks(sdp: str) -> list[list[str]]:
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
    return "\r\n".join(line for block in blocks for line in block)


def _media_kind(block: list[str]) -> str | None:
    if not block[0].startswith("m="):
        return None
    return block[0][2:].split(maxsplit=1)[0]


def _keep_preferred_codec(block: list[str], wanted: str) -> list[str]:
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
    was_kinds, was_codecs = _shape(original)
    now_kinds, now_codecs = _shape(reduced)
    return was_kinds == now_kinds and all(
        was_codecs.get(pt) == name for pt, name in now_codecs.items()
    )


def trim_offer_for_kvs(sdp: str) -> str:
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

    candidate = _join(
        [
            [line for line in block if not line.startswith("a=extmap:")]
            for block in blocks
        ]
    )
    return candidate if _preserves_shape(sdp, candidate) else sdp
