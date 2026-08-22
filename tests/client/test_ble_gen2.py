"""Tests for Gen 2 (PRE_CCC) BLE pairing.

Anchored to `docs/development/GEN2_BLE_DELTA.md`, the read-only APK analysis that
found the previous implementation invented a wire protocol (Protocol Buffers)
the app does not speak, and derived the crypto key without the HKDF step the
app actually performs -- so every HMAC in the old code was computed under the
wrong key regardless of framing.

Every expected value below is recomputed independently from `hmac`/`hashlib`/
`cryptography` primitives, never by calling the function under test. A test
that hands the code its own output back as the expectation cannot fail when
the protocol is wrong -- which is exactly how the previous 9-test suite
(asserting protobuf tag bytes that never appear on the wire) survived.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import logging
from typing import Self
from unittest.mock import AsyncMock, MagicMock, patch

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from custom_components.rivian.rivian_client import ble_gen2, ble_trace
from custom_components.rivian.rivian_client.utils import (
    encode_private_key,
    encode_public_key,
    get_secret_key,
)


def test_auth_state_values_match_apk_enum() -> None:
    """AuthState must mirror the app's state machine exactly. EnumC11122B.java:12-15."""
    assert ble_gen2.AuthState.INIT == 0
    assert ble_gen2.AuthState.PID_PNONCE_SENT == 1
    assert ble_gen2.AuthState.SIGNED_PARAMS_SENT == 2
    assert ble_gen2.AuthState.AUTHENTICATED == 3


def test_build_auth_pnonce_frame_is_pnonce_then_hmac() -> None:
    """AUTH_PNONCE is exactly pNonce(16) || HMAC-SHA256(key, pNonce)(32) = 48 bytes.

    No CSN, phoneId, or vehicleId -- AbstractC10624g.java:1160-1169. The buffer
    is allocated `new byte[48]` (:1161); the mac is recomputed here directly
    with `hmac`, never via `verify_vnonce` or a second call to this function.

    NON-PALINDROMIC FIXTURES ARE DELIBERATE. `b"\x22" * 16` reads identically
    reversed, so it cannot detect a byte reversal -- and a reversal is the exact
    regression GEN2_BLE_DELTA.md warns about: the APK's `m7360r()`
    (AbstractC15367g.java:322-329) LOOKS like one but is a no-op, because
    ByteBuffer.order() does not affect .array(). A reviewer's mutation proved the
    point: implementing that reversal passed the entire suite against repeated-
    byte fixtures. bytes(range(n)) makes the assertion able to fail.
    """
    secret_key = bytes(range(32))
    phone_nonce = bytes(range(16))

    frame = ble_gen2.build_auth_pnonce_frame(secret_key, phone_nonce)

    assert len(frame) == ble_gen2.AUTH_FRAME_LEN == 48
    assert frame[:16] == phone_nonce
    assert frame[16:] == hmac.new(secret_key, phone_nonce, hashlib.sha256).digest()


def test_parse_auth_vnonce_frame_round_trips_a_known_blob() -> None:
    """AUTH_VNONCE is a plain split at byte 16 -- vNonce(16), HMAC(32).

    Not length-prefixed or tagged. AbstractC10629c.java:262 (`C11135O`, the
    AUTH_VNONCE case): `bytes[0:16]` / `bytes[16:]`.
    """
    vehicle_nonce = bytes(range(16))
    mac = bytes(range(200, 232))
    frame = vehicle_nonce + mac
    assert len(frame) == 48

    parsed_nonce, parsed_mac = ble_gen2.parse_auth_vnonce_frame(frame)

    assert parsed_nonce == vehicle_nonce
    assert parsed_mac == mac


def test_verify_vnonce_accepts_a_correctly_computed_mac() -> None:
    """HMAC-SHA256(key, pNonce || vNonce), Arrays.equals. C11162i.java:1302-1314."""
    secret_key = b"\x33" * 32
    phone_nonce = b"\x44" * 16
    vehicle_nonce = b"\x55" * 16
    mac = hmac.new(secret_key, phone_nonce + vehicle_nonce, hashlib.sha256).digest()

    assert ble_gen2.verify_vnonce(secret_key, phone_nonce, vehicle_nonce, mac) is True


def test_verify_vnonce_rejects_a_single_flipped_bit_in_the_mac() -> None:
    """A vehicle that can't produce an exact MAC must not be accepted as authentic.

    C11162i.java:1302-1314 raises NONCE_VERIFICATION_FAILURE on any mismatch,
    not just a wholly wrong one -- so a one-bit corruption must fail too.
    """
    secret_key = b"\x33" * 32
    phone_nonce = b"\x44" * 16
    vehicle_nonce = b"\x55" * 16
    mac = bytearray(
        hmac.new(secret_key, phone_nonce + vehicle_nonce, hashlib.sha256).digest()
    )
    mac[0] ^= 0x01

    assert (
        ble_gen2.verify_vnonce(secret_key, phone_nonce, vehicle_nonce, bytes(mac))
        is False
    )


def test_verify_vnonce_rejects_a_wrong_vehicle_nonce() -> None:
    """A MAC computed over one vNonce must not verify against a different one.

    Otherwise a stale or replayed vNonce could be substituted after the fact
    and still pass -- C11162i.java:1302-1314's HMAC input includes vNonce
    precisely to bind the two together.
    """
    secret_key = b"\x33" * 32
    phone_nonce = b"\x44" * 16
    vehicle_nonce = b"\x55" * 16
    other_nonce = b"\x66" * 16
    mac = hmac.new(secret_key, phone_nonce + vehicle_nonce, hashlib.sha256).digest()

    assert ble_gen2.verify_vnonce(secret_key, phone_nonce, other_nonce, mac) is False


def test_get_secret_key_applies_hkdf_and_is_not_the_raw_ecdh_secret() -> None:
    """The root-cause defect (delta #1): the old code returned the raw ECDH
    shared secret -- "already 32 bytes for P-256" -- instead of running it
    through HKDF. C15277l.java:908-949: Z = ECDH(phone_priv, vehicle_pub);
    key = HKDF-SHA256(ikm=Z, salt=None, info=b"", L=32). This is the same
    derivation Gen 1 already implements at utils.py:93-99; both the raw ECDH
    secret and the HKDF output are recomputed independently here, from a
    freshly generated P-256 keypair, never by calling `get_secret_key` twice.
    """
    phone_private = ec.generate_private_key(ec.SECP256R1())
    vehicle_private = ec.generate_private_key(ec.SECP256R1())
    vehicle_public = vehicle_private.public_key()

    private_key_str = encode_private_key(phone_private)
    public_key_str = encode_public_key(vehicle_public)

    raw_ecdh = phone_private.exchange(ec.ECDH(), vehicle_public)
    expected = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"").derive(
        raw_ecdh
    )

    result = get_secret_key(private_key_str, public_key_str)

    assert result == expected
    assert result != raw_ecdh


class _FakeGen2Client:
    """Minimal BleakClient double for the Gen 2 pairing exchange.

    `write_gatt_char` plays the vehicle: it reads the pNonce out of the
    outbound AUTH_PNONCE frame, builds an AUTH_VNONCE response with the
    caller-supplied `build_response` (an independent `hmac.new` computation,
    never a call into `ble_gen2`), and fires it through whichever
    notification channel `respond_channel` names. `respond_channel=None`
    simulates a vehicle that never answers, to drive the timeout path.
    """

    def __init__(self, respond_channel: str | None, build_response=None) -> None:
        self.respond_channel = respond_channel
        self.build_response = build_response
        self.notify_handlers: dict[str, object] = {}
        self.written: list[tuple[str, bytes]] = []
        self.pair = AsyncMock()

    async def start_notify(self, char_specifier, handler) -> None:
        self.notify_handlers[char_specifier] = handler

    async def write_gatt_char(self, char_specifier, data) -> None:
        self.written.append((char_specifier, bytes(data)))
        if self.respond_channel is None:
            return
        phone_nonce = bytes(data[:16])
        response = self.build_response(phone_nonce)
        uuid = {
            "plain": ble_gen2.PLAIN_DATA_OUT_UUID,
            "encrypted": ble_gen2.ENCRYPTED_DATA_OUT_UUID,
        }[self.respond_channel]
        self.notify_handlers[uuid](None, bytearray(response))

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False


class TestKeyMaterialNeverReachesLogs:
    """Plan §3.7a: the derived key, private key and raw ECDH secret must never be
    logged at ANY level, including DEBUG.

    This is not a hypothetical bar. Home Assistant debug logs get pasted verbatim
    into public GitHub issues, and this integration is about to ASK beta testers
    to do exactly that. A `_LOGGER.exception` around key handling re-emits the
    exception's own message, so the guarantee would otherwise depend on the
    hygiene of third-party error strings (`cryptography`, `binascii`) rather than
    on anything in this repo -- a dependency bump could reintroduce the leak
    silently.
    """

    async def test_a_derive_failure_does_not_echo_the_private_key(self) -> None:
        secret = "SUPERSECRETPRIVATEKEYMATERIAL"
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger(ble_gen2.__name__)
        logger.addHandler(handler)
        previous = logger.level
        logger.setLevel(logging.DEBUG)

        def _raise_with_the_key(private_key, public_key):
            # Worst realistic case: a dependency that puts the key in its message.
            raise ValueError(f"bad key: {private_key}")

        try:
            with patch.object(ble_gen2, "get_secret_key", _raise_with_the_key):
                result = await ble_gen2.pair_phone_gen2(
                    MagicMock(), "phone-id", "vas-id", "vehicle-public-key", secret
                )
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous)

        assert result is False
        assert secret not in buf.getvalue(), (
            "the private key reached the log; HA debug logs are pasted into "
            "public issues verbatim"
        )
        # The failure must still be diagnosable -- the error CLASS is what a
        # maintainer needs, and it carries no key material.
        assert "ValueError" in buf.getvalue()


class TestPairPhoneGen2:
    """`pair_phone_gen2` against a faked BleakClient.

    `get_secret_key` is patched to a fixed value so these tests exercise the
    pairing exchange itself -- frame routing, fail-closed MAC verification,
    dual-channel response handling -- independently of key derivation, which
    is covered on its own above.
    """

    SECRET_KEY = b"\x99" * 32
    ARGS = (
        MagicMock(),
        "phone-id",
        "vas-vehicle-id",
        "vehicle-public-key",
        "private-key",
    )

    async def test_happy_path_reaches_authenticated(self) -> None:
        vehicle_nonce = b"\xaa" * 16

        def _respond(phone_nonce: bytes) -> bytes:
            mac = hmac.new(
                self.SECRET_KEY, phone_nonce + vehicle_nonce, hashlib.sha256
            ).digest()
            return vehicle_nonce + mac

        client = _FakeGen2Client("encrypted", _respond)
        with (
            patch.object(ble_gen2, "get_secret_key", return_value=self.SECRET_KEY),
            patch.object(ble_gen2, "BleakClient", lambda device, timeout=None: client),
        ):
            result = await ble_gen2.pair_phone_gen2(*self.ARGS)

        assert result is True
        # Current code's answer to GEN2_BLE_DELTA.md's "top remaining unknown"
        # (item 1, which characteristic the handshake is written to): pin it so
        # a change there is a visible, deliberate diff rather than a silent one.
        assert client.written[0][0] == ble_gen2.PLAIN_DATA_IN_UUID

    async def test_the_trace_actually_records_the_exchange(self) -> None:
        """The diagnostics path must be exercised, not merely present.

        Every other test here omits `vehicle_id`, so `trace` is None and EVERY
        `_trace()` call is a no-op -- the recording code is imported but never
        run. That is not hypothetical: `_trace()` swallows exceptions by design,
        so a typo'd method name inside any of those lambdas would ship a
        permanently empty trace while the whole suite stayed green. This project
        has already shipped exactly that failure once, when the trace went inert
        behind a swallowed ImportError.

        It matters because nobody owns a Gen 2 vehicle. A beta tester's trace is
        the only evidence that will ever settle the UNPROVEN parts of this
        protocol, so an empty one does not degrade diagnostics -- it removes the
        entire feedback channel while every signal says the change is healthy.
        """
        vehicle_nonce = b"\xcc" * 16

        def _respond(phone_nonce: bytes) -> bytes:
            mac = hmac.new(
                self.SECRET_KEY, phone_nonce + vehicle_nonce, hashlib.sha256
            ).digest()
            return vehicle_nonce + mac

        device = MagicMock()
        device.address = "AA:BB:CC:DD:EE:FF"
        client = _FakeGen2Client("encrypted", _respond)
        trace = ble_trace.get_trace("trace-test-vehicle")
        trace.reset()
        # button.py opens an attempt per retry-loop iteration; without one,
        # record_attempt_outcome() no-ops and that lambda goes unexercised --
        # a typo'd method name inside it would ship a silently missing outcome
        # while every other assertion here still passed.
        trace.start_attempt()

        with (
            patch.object(ble_gen2, "get_secret_key", return_value=self.SECRET_KEY),
            patch.object(ble_gen2, "BleakClient", lambda d, timeout=None: client),
            patch("platform.system", lambda: "Linux"),
        ):
            result = await ble_gen2.pair_phone_gen2(
                device,
                "phone-id",
                "vas-vehicle-id",
                "vehicle-public-key",
                "private-key",
                vehicle_id="trace-test-vehicle",
            )

        assert result is True
        rendered = trace.as_dict()

        # button.py reads this to decide whether to raise the Gen-2-only
        # repairs card, so it is control-flow data, not just diagnostics.
        assert rendered["generation"] == 2
        assert rendered["state_reached"] == "AUTHENTICATED"

        # Identifiers fingerprinted, never raw -- the bundle goes into a public,
        # permanent GitHub issue.
        assert set(rendered["identifiers"]) == {
            "phone_id_fp",
            "vas_vehicle_id_fp",
            "address_fp",
        }
        assert "AA:BB:CC:DD:EE:FF" not in str(rendered)

        # Both directions of the handshake, with the bytes a maintainer needs to
        # reconstruct an UNPROVEN frame layout.
        directions = [f["direction"] for f in rendered["frames"]]
        assert directions == ["write", "notify"]
        written_frame = rendered["frames"][0]
        assert written_frame["characteristic"] == ble_gen2.PLAIN_DATA_IN_UUID
        assert written_frame["length"] == 48
        assert written_frame["hex"] == client.written[0][1].hex()

        # Which channel answered is the whole point of dual-subscribing: it
        # settles GEN2_BLE_DELTA.md's UNPROVEN item 2.
        assert "encrypted" in (rendered["frames"][1].get("note") or "")

        # UNPROVEN §3.5: a tester report must distinguish "never bonded" from
        # "bonded and still rejected", so the bonding path and its outcome have
        # to survive into the bundle -- not just the volatile log.
        assert rendered["bonding"] == {"path": "pair", "outcome": "ok"}

        # The per-attempt outcome is how a multi-retry bundle reads as "attempt 1
        # timed out, attempt 2 authenticated" rather than one undifferentiated
        # stream. Asserting it also exercises the record_attempt_outcome lambda,
        # which every other test here leaves as a no-op.
        assert rendered["attempts"] == [{"attempt": 1, "outcome": "authenticated"}]

    async def test_mtu_fragments_survive_into_the_trace(self) -> None:
        """A fragmented AUTH_VNONCE must leave the evidence to diagnose it.

        `_wait_for_first_frame` acts on frames[0] only. If a vehicle delivers the
        48-byte response as MTU fragments (20+20+8), that first frame is short,
        parsing raises, and the attempt is recorded "malformed_vnonce_frame".
        Without the leftovers, three different bugs look identical in a tester's
        bundle: MTU fragmentation (UNPROVEN item 3), a wrong write/read
        characteristic (UNPROVEN item 1), and a genuinely malformed vehicle
        reply. They have three different fixes.

        Nobody owns a Gen 2 vehicle, so one bundle may be all the evidence there
        ever is. Losing the bytes loses the diagnosis.
        """
        vehicle_nonce = b"\xdd" * 16

        class _Fragmenting(_FakeGen2Client):
            async def write_gatt_char(self, char_specifier, data) -> None:
                self.written.append((char_specifier, bytes(data)))
                mac = hmac.new(
                    TestPairPhoneGen2.SECRET_KEY,
                    bytes(data[:16]) + vehicle_nonce,
                    hashlib.sha256,
                ).digest()
                full = vehicle_nonce + mac
                handler = self.notify_handlers[ble_gen2.ENCRYPTED_DATA_OUT_UUID]
                for chunk in (full[:20], full[20:40], full[40:]):
                    handler(None, bytearray(chunk))

        client = _Fragmenting("encrypted", lambda pn: b"")
        trace = ble_trace.get_trace("frag-vehicle")
        trace.reset()

        with (
            patch.object(ble_gen2, "get_secret_key", return_value=self.SECRET_KEY),
            patch.object(ble_gen2, "BleakClient", lambda d, timeout=None: client),
        ):
            result = await ble_gen2.pair_phone_gen2(
                MagicMock(), "p", "v", "k", "pk", vehicle_id="frag-vehicle"
            )

        assert result is False
        rendered = trace.as_dict()
        inbound = [f for f in rendered["frames"] if f["direction"] == "notify"]
        assert len(inbound) == 3, (
            "only the first fragment was recorded; the rest are exactly the "
            "bytes that distinguish fragmentation from a wrong characteristic"
        )

        # Reassembling them is what tells a maintainer it was fragmentation:
        # the pieces concatenate to a well-formed 48-byte AUTH_VNONCE.
        reassembled = b"".join(bytes.fromhex(f["hex"]) for f in inbound)
        assert len(reassembled) == ble_gen2.AUTH_FRAME_LEN
        assert reassembled[:16] == vehicle_nonce

    async def test_a_post_auth_frame_on_the_other_channel_is_recorded(self) -> None:
        """The non-answering channel's FIRST frame must not be skipped.

        Only the channel that answers the handshake has its frames[0] consumed.
        The other channel's frames[0] was never consumed by anything -- so
        skipping it as "already seen" discards it silently, with no WARNING and
        no trace entry.

        That is not a corner case. GEN2_BLE_DELTA.md's UNPROVEN item 2
        hypothesises that the encrypted channel may carry ONLY post-auth
        traffic. In exactly that world -- handshake answered on plain, a
        confirmation arriving on encrypted -- that dropped frame is the evidence
        that would disprove the SIGNED_PARAMS assumption in plan §3.4, which
        requires recording "anything the vehicle sends after authentication".
        """
        vehicle_nonce = b"\xee" * 16
        post_auth = b"\x99\x88\x77"

        class _AnswersPlainThenTalksEncrypted(_FakeGen2Client):
            async def write_gatt_char(self, char_specifier, data) -> None:
                self.written.append((char_specifier, bytes(data)))
                mac = hmac.new(
                    TestPairPhoneGen2.SECRET_KEY,
                    bytes(data[:16]) + vehicle_nonce,
                    hashlib.sha256,
                ).digest()
                # Handshake answers on PLAIN...
                self.notify_handlers[ble_gen2.PLAIN_DATA_OUT_UUID](
                    None, bytearray(vehicle_nonce + mac)
                )
                # ...and the ENCRYPTED channel then says something unexpected.
                # This is that channel's FIRST frame: nothing has consumed it.
                self.notify_handlers[ble_gen2.ENCRYPTED_DATA_OUT_UUID](
                    None, bytearray(post_auth)
                )

        client = _AnswersPlainThenTalksEncrypted("plain", lambda pn: b"")
        trace = ble_trace.get_trace("post-auth-vehicle")
        trace.reset()

        with (
            patch.object(ble_gen2, "get_secret_key", return_value=self.SECRET_KEY),
            patch.object(ble_gen2, "BleakClient", lambda d, timeout=None: client),
            patch("platform.system", lambda: "Linux"),
        ):
            result = await ble_gen2.pair_phone_gen2(
                MagicMock(), "p", "v", "k", "pk", vehicle_id="post-auth-vehicle"
            )

        assert result is True
        hexes = [f["hex"] for f in trace.as_dict()["frames"]]
        assert post_auth.hex() in hexes, (
            "the encrypted channel's first frame was dropped; it is exactly the "
            "evidence that would disprove the SIGNED_PARAMS assumption"
        )

    async def test_bad_mac_fails_closed_and_never_triggers_pairing(self) -> None:
        # Security property (delta #6, C11162i.java:1302-1314): a corrupt vNonce
        # HMAC must fail the whole attempt and must never reach client.pair()
        # below it -- fail-closed, not fail-open. platform.system() is forced to
        # "Linux" so the bonding branch that calls client.pair() is the one that
        # would run if the fail-closed check were ever skipped; on Darwin that
        # branch is never reached at all, which would make this assertion prove
        # nothing.
        vehicle_nonce = b"\xbb" * 16

        def _respond(phone_nonce: bytes) -> bytes:
            mac = bytearray(
                hmac.new(
                    self.SECRET_KEY, phone_nonce + vehicle_nonce, hashlib.sha256
                ).digest()
            )
            mac[0] ^= 0x01
            return vehicle_nonce + bytes(mac)

        client = _FakeGen2Client("encrypted", _respond)
        with (
            patch.object(ble_gen2, "get_secret_key", return_value=self.SECRET_KEY),
            patch.object(ble_gen2, "BleakClient", lambda device, timeout=None: client),
            patch.object(ble_gen2.platform, "system", return_value="Linux"),
        ):
            result = await ble_gen2.pair_phone_gen2(*self.ARGS)

        assert result is False
        client.pair.assert_not_called()

    async def test_timeout_returns_false(self) -> None:
        client = _FakeGen2Client(respond_channel=None)
        with (
            patch.object(ble_gen2, "get_secret_key", return_value=self.SECRET_KEY),
            patch.object(ble_gen2, "BleakClient", lambda device, timeout=None: client),
            patch.object(ble_gen2, "AUTH_TIMEOUT", 0.05),
        ):
            result = await ble_gen2.pair_phone_gen2(*self.ARGS)

        assert result is False

    async def test_response_on_plain_channel_is_still_accepted(self) -> None:
        # UNPROVEN (delta item 2): the APK doesn't settle whether AUTH_VNONCE
        # arrives on PLAIN_DATA_OUT or ENCRYPTED_DATA_OUT. pair_phone_gen2
        # dual-subscribes for exactly this reason -- either channel must work.
        vehicle_nonce = b"\xcc" * 16

        def _respond(phone_nonce: bytes) -> bytes:
            mac = hmac.new(
                self.SECRET_KEY, phone_nonce + vehicle_nonce, hashlib.sha256
            ).digest()
            return vehicle_nonce + mac

        client = _FakeGen2Client("plain", _respond)
        with (
            patch.object(ble_gen2, "get_secret_key", return_value=self.SECRET_KEY),
            patch.object(ble_gen2, "BleakClient", lambda device, timeout=None: client),
        ):
            result = await ble_gen2.pair_phone_gen2(*self.ARGS)

        assert result is True
