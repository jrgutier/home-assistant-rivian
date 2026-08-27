"""Shrink a browser SDP offer until a KVS signaling frame will carry it.

This is not something the Rivian app does -- it builds its own offer and keeps
it small. It exists for Home Assistant's built-in camera player, which builds
its own offer, cannot be told to prefer a codec, and on Chrome arrives well
over the KVS limit with AV1, VP9, VP8, four H264 profiles, red and ulpfec plus
an rtx line for each. The bundled card calls setCodecPreferences instead and
never reaches here.

What this removes is only ever a codec the vehicle would not have chosen (it
answers H264 and nothing else) or a header extension it was free to ignore.
Payload types are never renumbered and m= sections are never added, removed or
reordered, so the answer that comes back still matches the offer the browser
is holding.
"""

from __future__ import annotations

import re

from .kvs_signaling import offer_exceeds_kvs_limit

_RTPMAP = re.compile(r"^a=rtpmap:(\d+)\s+([^/]+)/")
_FMTP_APT = re.compile(r"^a=fmtp:(\d+)\s+.*\bapt=(\d+)")
# rtcp-fb also uses `*` for "every codec"; that has no digits and is kept.
_PAYLOAD_ATTR = re.compile(r"^a=(?:rtpmap|fmtp|rtcp-fb):(\d+)\b")


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
    return "\n".join(line for block in blocks for line in block)


def _keep_only_h264(block: list[str]) -> list[str]:
    """Reduce one video m= section to H264 and the rtx that repairs it."""
    parts = block[0].split()
    if len(parts) < 4:
        return block
    offered = parts[3:]

    names = {
        hit.group(1): hit.group(2).lower()
        for line in block
        if (hit := _RTPMAP.match(line))
    }
    keep = {pt for pt in offered if names.get(pt) == "h264"}
    if not keep:
        # Nothing recognisable to keep. Emptying the m= line would reject the
        # whole video section, which is worse than an offer that is too large.
        return block
    for line in block:
        if hit := _FMTP_APT.match(line):
            pt, apt = hit.group(1), hit.group(2)
            if apt in keep and names.get(pt) == "rtx":
                keep.add(pt)

    out = [" ".join(parts[:3] + [pt for pt in offered if pt in keep])]
    out.extend(
        line
        for line in block[1:]
        if not ((hit := _PAYLOAD_ATTR.match(line)) and hit.group(1) not in keep)
    )
    return out


def trim_offer_for_kvs(sdp: str) -> str:
    """Return the smallest faithful form of this offer, or it unchanged.

    Tries the cheapest reduction first and stops as soon as the offer fits, so
    an offer that was already small is returned byte-for-byte. An offer that
    cannot be made to fit is returned at its smallest -- the caller still has
    to check, and report, that it is over.
    """
    if not offer_exceeds_kvs_limit(sdp):
        return sdp

    blocks = [
        _keep_only_h264(block) if block[0].startswith("m=video") else block
        for block in _blocks(sdp)
    ]
    if not offer_exceeds_kvs_limit(candidate := _join(blocks)):
        return candidate

    # Still over: the extensions are negotiable too, and dropping them costs
    # the viewer nothing the vehicle was going to honour.
    return _join(
        [
            [line for line in block if not line.startswith("a=extmap:")]
            for block in blocks
        ]
    )
