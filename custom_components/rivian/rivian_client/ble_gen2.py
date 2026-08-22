"""Rivian Gen 2 (PRE_CCC) BLE pairing handler.

Wire format and crypto are anchored to `docs/development/GEN2_BLE_DELTA.md`, a
read-only static analysis of the Android app. The Gen 2 VAS protocol is NOT
Protocol Buffers -- it is fixed-size little-endian framing -- and the key
derivation is the same HKDF-over-ECDH that `utils.get_secret_key` already
implements correctly for the Gen 1 path. An earlier version of this module
reimplemented both from scratch and got both wrong: it modelled a Protocol
Buffers wire format that does not exist, and it skipped the HKDF step, so
every HMAC was computed under the wrong key regardless of framing.
"""

from __future__ import annotations

import asyncio
from enum import IntEnum
import hashlib
import hmac
import logging
import platform
import secrets

from . import ble_trace
from .utils import get_secret_key

_LOGGER = logging.getLogger(__name__)

try:
    from bleak import BleakClient, BLEDevice  # type: ignore
except ImportError:
    _LOGGER.error("Please install 'rivian-python-client[ble]' to use BLE features.")
    raise


# Gen 2 (PRE_CCC) BLE characteristic UUIDs, re-exported from ble.py rather than
# restated. `detect_vehicle_generation` already needs them at module scope there
# to tell a Gen 2 vehicle from a Gen 1 one, so ble.py is the single source of
# truth and these are aliases.
#
# This matters more than ordinary de-duplication: these four UUIDs are the
# module's own top UNPROVEN item (GEN2_BLE_DELTA.md items 1/2 -- the APK write
# target at C11162i.java:1173 resolves through unresolved uuid6/uuid7). The first
# tester GATT dump is expected to confirm or CORRECT one of them, and a second
# copy would let that correction land in one place and not the other, silently
# restoring the wrong-channel failure this rewrite exists to fix.
#
# Import direction is deliberate and cycle-free: ble.py imports this module only
# lazily, inside pair_phone()'s Gen 2 branch, never at module load.
# There is no ENCRYPTED_DATA_IN alias, and none in ble.py either: nothing writes
# to that characteristic. This module writes only to PLAIN_DATA_IN and reads from
# both OUT channels, and detect_vehicle_generation fingerprints a Gen 2 vehicle
# from PLAIN_DATA_IN + ENCRYPTED_DATA_OUT. The constant was dead in both files
# the moment it was declared and has been removed from both.
from .ble import (
    CONNECT_TIMEOUT,
    GEN2_ENCRYPTED_DATA_OUT_UUID as ENCRYPTED_DATA_OUT_UUID,
    GEN2_PLAIN_DATA_IN_UUID as PLAIN_DATA_IN_UUID,
    GEN2_PLAIN_DATA_OUT_UUID as PLAIN_DATA_OUT_UUID,
)

AUTH_TIMEOUT = 60.0

# Channel name -> the OUT characteristic it was subscribed on. Both channels are
# opened because which one answers is UNPROVEN (GEN2_BLE_DELTA.md item 2), and
# every frame recorded into the trace has to say which one it arrived on -- that
# is the evidence that settles it.
_OUT_UUIDS = {"plain": PLAIN_DATA_OUT_UUID, "encrypted": ENCRYPTED_DATA_OUT_UUID}

# pNonce/vNonce(16) || HMAC-SHA256(32). Both directions of the handshake use this
# length -- AbstractC10624g.java:1160-1169 (outbound), AbstractC10629c.java:262
# (inbound, "the pairing response is 48 bytes: vNonce(16) || HMAC(32)").
AUTH_FRAME_LEN = 48


class AuthState(IntEnum):
    """Gen 2 authentication state machine.

    All four members are APK-accurate (EnumC11122B.java:12-15), but the pairing
    path never enters SIGNED_PARAMS_SENT -- see `pair_phone_gen2`. UNPROVEN: that
    rests on a log string (C11162i.java:1322, "authentication is completed"), not
    decoded state transitions, so it is kept in the enum rather than removed.
    """

    INIT = 0  # Initial state
    PID_PNONCE_SENT = 1  # AUTH_PNONCE sent, waiting for AUTH_VNONCE
    SIGNED_PARAMS_SENT = 2  # UNPROVEN: never entered by this implementation
    AUTHENTICATED = 3  # vNonce HMAC verified


class BleNotificationResponse:
    """BLE notification response helper for Gen 2.

    Keeps every frame received, not just the first: a frame arriving after
    authentication is evidence the SIGNED_PARAMS_SENT state is real (see
    `pair_phone_gen2`), not something to discard silently.
    """

    def __init__(self) -> None:
        """Initialize the BLE notification response helper."""
        self.frames: list[bytes] = []
        self.event = asyncio.Event()

    def notification_handler(self, _, notification_data: bytearray) -> None:
        """Notification handler."""
        self.frames.append(bytes(notification_data))
        self.event.set()

    @property
    def data(self) -> bytes | None:
        """The first frame received, if any."""
        return self.frames[0] if self.frames else None


async def create_notification_handler(
    client: BleakClient, char_specifier: str
) -> BleNotificationResponse:
    """Create a notification handler."""
    response = BleNotificationResponse()
    await client.start_notify(char_specifier, response.notification_handler)
    return response


async def _wait_for_first_frame(
    handlers: dict[str, BleNotificationResponse], timeout: float
) -> tuple[str, bytes] | None:
    """Wait for whichever subscribed channel answers first.

    UNPROVEN (GEN2_BLE_DELTA.md item 2): whether the AUTH_VNONCE response arrives
    on PLAIN_DATA_OUT or ENCRYPTED_DATA_OUT is undecided from the APK. Subscribing
    to both and recording which one actually fires is the required mitigation
    (plan Pre-mortem 1) -- returns None on timeout.
    """
    waiters = {name: asyncio.ensure_future(h.event.wait()) for name, h in handlers.items()}
    try:
        done, _ = await asyncio.wait(
            waiters.values(), timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        for name, task in waiters.items():
            if task in done:
                handler = handlers[name]
                assert handler.data is not None
                return name, handler.data
        return None
    finally:
        for task in waiters.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*waiters.values(), return_exceptions=True)


def build_auth_pnonce_frame(secret_key: bytes, phone_nonce: bytes) -> bytes:
    """Build the AUTH_PNONCE frame sent to the vehicle.

    Wire format: pNonce(16) || HMAC-SHA256(key, pNonce)(32) = 48 bytes.
    Anchor: AbstractC10624g.java:1160-1169. Note what is absent: no CSN, phoneId,
    or vehicleId -- those fields exist on the source object but this branch never
    serializes them (the constructor passes CSN -1, a sentinel, not a value).
    """
    if len(phone_nonce) != 16:
        raise ValueError(f"phone_nonce must be 16 bytes, got {len(phone_nonce)}")
    mac = hmac.new(secret_key, phone_nonce, hashlib.sha256).digest()
    return phone_nonce + mac


def parse_auth_vnonce_frame(frame: bytes) -> tuple[bytes, bytes]:
    """Split the AUTH_VNONCE response into (vehicle_nonce, mac).

    Wire format: vNonce(16) || HMAC-SHA256(32), split at byte 16.
    Anchor: AbstractC10629c.java:262 (`C11135O`, the AUTH_VNONCE case).
    """
    if len(frame) != AUTH_FRAME_LEN:
        raise ValueError(
            f"AUTH_VNONCE frame must be {AUTH_FRAME_LEN} bytes, got {len(frame)}"
        )
    return frame[:16], frame[16:]


def verify_vnonce(
    secret_key: bytes, phone_nonce: bytes, vehicle_nonce: bytes, mac: bytes
) -> bool:
    """Verify the vehicle's AUTH_VNONCE response HMAC.

    Anchor: C11162i.java:1302-1314 -- HMAC-SHA256(key, pNonce || vNonce), compared
    against the vehicle-supplied MAC with `Arrays.equals`. Note `m7360r()`
    (AbstractC15367g.java:322-329) is a decompiler-visible no-op --
    `ByteBuffer.order()` does not affect `.array()` -- so no byte reversal is
    applied anywhere in this module; endianness only matters for the
    `ACTIVE_COMMAND`/`PASSIVE_ENTRY` CSN field, which this module does not build
    (see `pair_phone_gen2`).
    """
    expected = hmac.new(secret_key, phone_nonce + vehicle_nonce, hashlib.sha256).digest()
    return hmac.compare_digest(mac, expected)


async def pair_phone_gen2(
    device: BLEDevice,
    phone_id: str,
    vas_vehicle_id: str,
    vehicle_public_key: str,
    private_key: str,
    vehicle_id: str | None = None,
) -> bool:
    """Pair a phone locally via Gen 2 (PRE_CCC) BLE protocol.

    The pairing exchange is a single request/response pair, not the invented
    3-round-trip flow an earlier version of this module implemented:

        phone   -> AUTH_PNONCE:  pNonce(16) || HMAC-SHA256(key, pNonce)(32)
        vehicle -> AUTH_VNONCE:  vNonce(16) || HMAC-SHA256(key, pNonce||vNonce)(32)

    `phone_id` and `vas_vehicle_id` are accepted for call-signature parity with
    `_pair_phone_gen1` (`ble.py`), which routes to this function with the same
    arguments. The APK's AUTH_PNONCE frame does not carry either field
    (GEN2_BLE_DELTA.md delta #5), so neither is placed on the wire here. Full
    vehicle-ID validation (delta #9) is a separate, unresolved question this
    rewrite does not attempt -- see GEN2_BLE_DELTA.md, delta #9.

    Args:
        device: BLE device to connect to
        phone_id: Phone UUID from enrollment (unused on the wire, see above)
        vas_vehicle_id: VAS vehicle ID (unused on the wire, see above)
        vehicle_public_key: Vehicle's EC public key (130 hex chars, "04" prefix)
        private_key: Phone's EC private key (base64-encoded PEM)
        vehicle_id: HA/Rivian internal vehicle id, used ONLY to key the BLE
            diagnostic trace (rivian_client.ble_trace.get_trace). Optional,
            trailing, and defaults to None so every existing positional call
            is unaffected. When omitted, every
            trace call below is a no-op -- see `_trace()`.

    Returns:
        True if pairing succeeded, False otherwise. Never returns True after a
        failed vNonce verification -- there is no fallthrough to bonding.
    """
    _LOGGER.debug("Starting Gen 2 (PRE_CCC) pairing with %s", device)
    state = AuthState.INIT

    trace = ble_trace.get_trace(vehicle_id) if vehicle_id is not None else None

    def _trace(record) -> None:
        """Best-effort trace recording -- must never break pairing."""
        if trace is None:
            return
        try:
            record()
        except Exception:  # tracing is diagnostics only
            _LOGGER.debug("Gen 2: trace recording failed", exc_info=True)

    # Set as early as possible, and deliberately NOT through _trace(): button.py
    # reads this back to gate the Gen-2-only pairing-failure repairs card, which
    # makes it control-flow data, not diagnostics. _trace() swallows exceptions
    # by design ("tracing is diagnostics only") -- routing a value that decides
    # whether a real user sees a repairs card through a path built to fail
    # silently is the same shape as the ContextVar that made the trace inert
    # while tests stayed green. A plain attribute write cannot meaningfully
    # throw, so the None-check is the only guard it needs.
    if trace is not None:
        trace.generation = 2

    try:
        # Root-cause fix (GEN2_BLE_DELTA.md delta #1): this is the same
        # HKDF-SHA256(ECDH(...), salt=None, info=b"") the Gen 1 path already uses
        # (utils.py:93-99). The prior Gen 2 code reimplemented ECDH from scratch,
        # returned the raw shared secret without the HKDF step, and passed a
        # base64-encoded PEM to a loader that expected raw PEM bytes;
        # get_secret_key fixes all three at once.
        #
        # NEVER log `secret_key` (or any intermediate ECDH/HKDF value) at any
        # level, including DEBUG -- HA debug logs get pasted into public GitHub
        # issues verbatim.
        secret_key = get_secret_key(private_key, vehicle_public_key)
    except Exception as ex:  # noqa: BLE001  # ruff waives BLE001 for blind catches logged via .exception(); this one deliberately does NOT use .exception() -- see below. Any failure here is invalid/malformed key material and the caller treats it like any other failed pairing attempt.
        _trace(lambda: trace.record_attempt_outcome("key_derivation_failed"))
        # The error CLASS only -- never `.exception()` or `%s` on the exception
        # itself. This handler wraps the one call that touches the private key
        # and the derived secret, and re-emitting an exception's message would
        # make plan §3.7a ("never log key material at any level") depend on the
        # error-string hygiene of `cryptography` and `binascii` rather than on
        # anything in this repo -- a dependency bump could reintroduce the leak
        # silently. HA debug logs are pasted verbatim into public GitHub issues,
        # and this integration explicitly asks beta testers to do that.
        # Pinned by tests/client/test_ble_gen2.py::TestKeyMaterialNeverReachesLogs.
        _LOGGER.error(
            "Gen 2: failed to derive the shared key (%s)", type(ex).__name__
        )
        return False

    try:
        async with BleakClient(device, timeout=CONNECT_TIMEOUT) as client:
            _LOGGER.debug("Gen 2: connected to %s", device)
            _trace(
                lambda: trace.record_identifiers(
                    phone_id=phone_id, vas_vehicle_id=vas_vehicle_id, address=device.address
                )
            )

            # UNPROVEN (GEN2_BLE_DELTA.md item 2, Pre-mortem 1): dual-subscribe so
            # a tester report can tell us which channel actually answers.
            # Subscribed concurrently: each start_notify() is an independent
            # GATT CCCD-write round trip (tens to low-hundreds of ms), and
            # neither depends on the other. Which channel actually answers is
            # UNPROVEN, which is why both are opened at all.
            plain_handler, encrypted_handler = await asyncio.gather(
                create_notification_handler(client, PLAIN_DATA_OUT_UUID),
                create_notification_handler(client, ENCRYPTED_DATA_OUT_UUID),
            )
            handlers = {"plain": plain_handler, "encrypted": encrypted_handler}

            phone_nonce = secrets.token_bytes(16)
            frame = build_auth_pnonce_frame(secret_key, phone_nonce)

            # UNPROVEN (GEN2_BLE_DELTA.md item 1, called out there as "the top
            # remaining unknown"): C11162i.java:1173 writes via unresolved
            # uuid6/uuid7. PLAIN_DATA_IN is inherited from the pre-rewrite code,
            # not decoded from the APK.
            _LOGGER.debug("Gen 2: sending AUTH_PNONCE (%d bytes)", len(frame))
            _trace(lambda: trace.record_frame("write", PLAIN_DATA_IN_UUID, frame))
            await client.write_gatt_char(PLAIN_DATA_IN_UUID, frame)
            state = AuthState.PID_PNONCE_SENT
            _trace(lambda: trace.record_state(state.name))

            def _record_unconsumed(note: str, skip_first_of: str | None = None) -> None:
                """Record every frame the handshake did not act on.

                `_wait_for_first_frame` takes only frames[0] of whichever channel
                answers first. On the failure paths that is a problem, not a
                detail: if a vehicle delivers the 48-byte AUTH_VNONCE as MTU
                fragments (20+20+8), frame[0] is a short 20-byte frame, parsing
                raises, and the remaining bytes are dropped -- so the bundle
                shows "malformed" with nothing to distinguish FRAGMENTATION from
                a WRONG CHARACTERISTIC or a genuinely malformed reply. Those are
                three different bugs with three different fixes, and MTU
                fragmentation is UNPROVEN item 3. Recording the leftovers is what
                makes them tellable apart from a single tester report.
                """
                for chan, handler in handlers.items():
                    frames = handler.frames
                    if chan == skip_first_of:
                        frames = frames[1:]
                    for extra in frames:
                        _trace(
                            lambda c=chan, d=extra: trace.record_frame(
                                "notify", _OUT_UUIDS[c], d, note=f"channel={c} {note}"
                            )
                        )

            result = await _wait_for_first_frame(handlers, AUTH_TIMEOUT)
            if result is None:
                _trace(lambda: trace.record_attempt_outcome("timeout"))
                # Anything that DID arrive but was not a usable first frame --
                # e.g. a reply on a channel we mis-guessed, or fragments that
                # never completed. Silence here and bytes-on-the-wire here are
                # different diagnoses.
                _record_unconsumed("unconsumed (timeout)")
                _LOGGER.error("Gen 2: timeout waiting for AUTH_VNONCE")
                return False
            channel, response = result
            _LOGGER.debug("Gen 2: AUTH_VNONCE answered on the %s channel", channel)
            characteristic = _OUT_UUIDS[channel]
            _trace(
                lambda: trace.record_frame(
                    "notify", characteristic, response, note=f"channel={channel}"
                )
            )

            try:
                vehicle_nonce, mac = parse_auth_vnonce_frame(response)
            except ValueError as ex:
                _trace(lambda: trace.record_attempt_outcome("malformed_vnonce_frame"))
                # The frame we DID consume is already recorded above; these are
                # the ones after it. If they concatenate with it to 48 bytes,
                # the answer is fragmentation, not a malformed vehicle.
                _record_unconsumed("unconsumed (after malformed)", skip_first_of=channel)
                _LOGGER.error("Gen 2: malformed AUTH_VNONCE response: %s", ex)
                return False

            if not verify_vnonce(secret_key, phone_nonce, vehicle_nonce, mac):
                # Fail closed. Never falls through to bonding below.
                _trace(lambda: trace.record_attempt_outcome("bad_vnonce_mac"))
                # The consumed frame is already recorded; these are the rest.
                # A mirrored wrong-MAC reply on the other channel would say the
                # failure is not specific to the channel we answered on.
                _record_unconsumed(
                    "unconsumed (after bad MAC)", skip_first_of=channel
                )
                _LOGGER.error("Gen 2: vNonce HMAC verification failed")
                return False

            state = AuthState.AUTHENTICATED
            _trace(lambda: trace.record_state(state.name))
            _LOGGER.debug("Gen 2: authentication successful")

            # UNPROVEN (plan §3.4): SIGNED_PARAMS_SENT is never entered above --
            # the pairing exchange is the single request/response pair this
            # function implements. That inference rests on a log string
            # (C11162i.java:1322), not decoded transitions, so anything the
            # vehicle sends after this point is logged rather than discarded --
            # if this assumption is wrong, a WARNING here is what disproves it.
            # UNPROVEN (plan §3.5): zero APK evidence for Gen 2 bonding at all;
            # this mirrors Gen 1's platform split (ble.py:286-295) as a default,
            # not a decoded requirement.
            _LOGGER.debug("Gen 2: attempting to trigger bonding")
            if platform.system() == "Darwin":
                # Gen 1 has no explicit bonding API on macOS, so it subscribes to
                # a protected characteristic to trigger bonding manually
                # (ble.py:288-293). Gen 2 has no APK-confirmed equivalent
                # characteristic; the ENCRYPTED_DATA_OUT subscription established
                # above is reused as that trigger rather than re-subscribing,
                # which some bleak backends reject as a duplicate.
                _LOGGER.debug(
                    "Gen 2: relying on the encrypted-channel subscription to "
                    "trigger bonding (Darwin)"
                )
                _trace(lambda: trace.record_bonding("darwin-passive", "ok"))
            else:
                try:
                    await client.pair()
                except Exception as ex:
                    # Bound to a plain local BEFORE the lambda: Python unbinds
                    # `ex` when the except block exits, so a lambda closing over
                    # it directly is a NameError waiting for a refactor to move
                    # the call one line later.
                    reason = type(ex).__name__
                    _trace(lambda: trace.record_bonding("pair", f"error:{reason}"))
                    raise
                _trace(lambda: trace.record_bonding("pair", "ok"))

            # Scanned AFTER bonding, deliberately: taking this snapshot before
            # client.pair() would miss anything the vehicle sends DURING it, and
            # a frame arriving there is precisely the evidence that would
            # disprove the §3.4 assumption below.
            #
            # UNPROVEN (plan §3.4): SIGNED_PARAMS_SENT is never entered above --
            # the pairing exchange is the single request/response pair this
            # function implements. That inference rests on a log string
            # (C11162i.java:1322), not decoded transitions, so anything the
            # vehicle sends after authentication is recorded in the TRACE as
            # well as logged. The log is volatile; the trace is what the tester
            # actually attaches, and this is the one artifact that could
            # disprove the assumption.
            # skip_first_of=channel, NOT frames[1:] on both: only the channel
            # that ANSWERED had its frames[0] consumed. Skipping the other
            # channel's first frame discards a frame nothing has seen -- and
            # GEN2_BLE_DELTA.md's UNPROVEN item 2 hypothesises the encrypted
            # channel may carry only post-auth traffic, which makes that exact
            # frame the evidence most likely to disprove §3.4.
            for name, handler in handlers.items():
                for extra in handler.frames[1:] if name == channel else handler.frames:
                    _LOGGER.warning(
                        "Gen 2: unexpected frame on the %s channel after "
                        "authentication (%d bytes) -- SIGNED_PARAMS_SENT may be "
                        "real after all",
                        name,
                        len(extra),
                    )
            _record_unconsumed("post-auth (unexpected)", skip_first_of=channel)

            _trace(lambda: trace.record_attempt_outcome("authenticated"))
            _LOGGER.debug("Gen 2: successfully paired with %s", device)
            return True
    except Exception:  # pylint: disable=broad-except  # BLE pairing state machine; changing exception semantics here is out of scope for a transport merge
        _trace(lambda: trace.record_state(AuthState(state).name))
        _trace(lambda: trace.record_attempt_outcome("exception"))
        _LOGGER.exception("Gen 2 pairing failed at state %s", AuthState(state).name)
        return False
