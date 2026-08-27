"""Kinesis Video Streams WebRTC signaling, as the Rivian app speaks it.

Send shape is `WebRtcMessage` (`action` + base64 `messagePayload`).
Receive shape is `Event` (`messageType` + base64 `messagePayload`).
APK: `WebRtcMessage.java` createOfferMessage / createIceCandidateMessage
and `Event.java` parseSdpEvent / parseIceCandidate.

Outgoing Base64 uses Android flags 11 (URL_SAFE | NO_WRAP | NO_PADDING).
Incoming payloads may be either alphabet; decode both.

Do not log `endpoint`, `channelArn`, ICE credentials, or signed URLs.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any
from urllib.parse import parse_qs, quote, urlparse, urlunparse
from uuid import uuid4

_KVS_HOST = re.compile(r"^[a-z0-9-]+\.kinesisvideo\.[a-z0-9-]+-\d+\.amazonaws\.com$")


def new_client_id() -> str:
    """KVS viewer client id (X-Amz-ClientId)."""
    return str(uuid4())


def encode_payload(obj: dict[str, Any]) -> str:
    """Base64-encode a signaling inner payload the way the app does."""
    raw = json.dumps(obj, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def decode_payload(payload: str) -> dict[str, Any]:
    """Decode a KVS messagePayload, either alphabet, with or without padding."""
    pad = "=" * ((4 - len(payload) % 4) % 4)
    padded = payload + pad
    try:
        raw = base64.urlsafe_b64decode(padded)
    except binascii.Error:
        raw = base64.b64decode(padded)
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise TypeError("signaling payload is not an object")
    return decoded


def _crlf_sdp(sdp: str) -> str:
    """WebRTC SDP uses CRLF; the app rewrites before wrapping JSON."""
    return sdp.replace("\r\n", "\n").replace("\n", "\r\n")


def offer_message(sdp: str, client_id: str) -> dict[str, str]:
    """Viewer SDP_OFFER — `WebRtcMessage.createOfferMessage`."""
    return {
        "action": "SDP_OFFER",
        "recipientClientId": "",
        "senderClientId": client_id,
        "messagePayload": encode_payload({"type": "offer", "sdp": _crlf_sdp(sdp)}),
    }


def ice_candidate_message(
    candidate: str,
    sdp_mid: str | None,
    sdp_m_line_index: int | None,
    client_id: str,
    recipient_client_id: str,
) -> dict[str, str]:
    """ICE_CANDIDATE — `UriUtilsKt.getIceCandidatePayload` + WebRtcMessage."""
    inner: dict[str, Any] = {
        "candidate": candidate,
        "sdpMid": sdp_mid or "",
        "sdpMLineIndex": 0 if sdp_m_line_index is None else sdp_m_line_index,
    }
    return {
        "action": "ICE_CANDIDATE",
        "recipientClientId": recipient_client_id,
        "senderClientId": client_id,
        "messagePayload": encode_payload(inner),
    }


def parse_signaling_event(raw: str) -> dict[str, Any] | None:
    """Parse an incoming KVS Event. None if it is not a signaling message."""
    if "messagePayload" not in raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    msg_type = data.get("messageType") or data.get("action")
    payload_b64 = data.get("messagePayload")
    if not msg_type or not payload_b64:
        return None
    try:
        inner = decode_payload(payload_b64)
    except (TypeError, ValueError, json.JSONDecodeError, binascii.Error):
        return None
    return {
        "messageType": str(msg_type).upper(),
        "senderClientId": data.get("senderClientId") or "",
        "payload": inner,
    }


def _kvs_signaling_host_ok(host: str | None) -> bool:
    """KVS signaling hosts look like v-….kinesisvideo.<region>.amazonaws.com."""
    return bool(host) and _KVS_HOST.fullmatch(host.lower()) is not None


def signaling_ws_url(endpoint: str, channel_arn: str, client_id: str) -> str:
    """Connect to the signed KVS endpoint. Do not log the result."""
    url = endpoint.strip()
    if url.startswith("https://"):
        url = "wss://" + url[len("https://") :]
    elif url.startswith(("http://", "ws://")):
        raise ValueError("Rejected non-KVS signaling endpoint")
    elif not url.startswith("wss://"):
        url = "wss://" + url

    parsed = urlparse(url)
    if parsed.scheme != "wss" or not _kvs_signaling_host_ok(parsed.hostname):
        raise ValueError("Rejected non-KVS signaling endpoint")
    existing = parse_qs(parsed.query, keep_blank_values=True)
    keys_lower = {k.lower() for k in existing}
    if keys_lower & {"x-amz-signature", "x-amz-credential"}:
        return urlunparse(parsed)
    extra: list[str] = []
    if "x-amz-channelarn" not in keys_lower and channel_arn:
        extra.append(f"X-Amz-ChannelARN={quote(channel_arn, safe='')}")
    if "x-amz-clientid" not in keys_lower and client_id:
        extra.append(f"X-Amz-ClientId={quote(client_id, safe='')}")
    if extra:
        query = parsed.query
        joined = ("&" if query else "") + "&".join(extra)
        parsed = parsed._replace(query=query + joined)
    return urlunparse(parsed)


def client_id_from_endpoint(endpoint: str) -> str | None:
    """Use the ClientId KVS already bound into a signed URL, if any."""
    parsed = urlparse(endpoint.strip())
    for key, values in parse_qs(parsed.query, keep_blank_values=True).items():
        if key.lower() == "x-amz-clientid" and values and values[0]:
            return values[0]
    return None


def ice_servers_from_config(ice_servers: list[Any] | None) -> list[dict[str, Any]]:
    """Shape GraphQL iceServers for RTCIceServer without copying secrets out."""
    out: list[dict[str, Any]] = []
    if not ice_servers:
        return out
    for server in ice_servers:
        if not isinstance(server, dict):
            continue
        urls = server.get("url") or server.get("urls")
        if not urls:
            continue
        entry: dict[str, Any] = {"urls": urls}
        if username := server.get("username"):
            entry["username"] = username
        if credential := server.get("credential"):
            entry["credential"] = credential
        out.append(entry)
    return out
