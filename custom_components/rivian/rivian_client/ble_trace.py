"""Per-vehicle BLE frame trace for Gen 2 pairing diagnostics.

Gen 2 (PRE_CCC) pairing follows the protocol walthowd/rivian-gen2-key-poc
verified on a real vehicle (docs/development/GEN2_BLE_PROTOCOL.md). What is
still untested is this integration's side of it: Home Assistant's Bluetooth
stack, its proxies, and a key enrolled as device type "HA" rather than
"phone". A trace shows how far an attempt got and where it stopped.

These traces are what a beta tester sends back. They are surfaced through
diagnostics.py, which is admin-only and redacted. Nothing here leaves the
instance on its own; there is no upload path, matching how Home Assistant
itself handles diagnostics.

ONE TRACE PER VEHICLE, NOT A MODULE SINGLETON. A multi-vehicle account builds
one pair button PER VEHICLE (button.py:126-132), each guarded by its own
PER-ENTITY `self._pairing` (button.py:168) -- not one guard for the whole
integration. Two vehicles on the same account can therefore pair
concurrently. A single global trace would interleave both pairings' frames
into one stream, and either one's `reset()` would wipe the other's evidence
-- corrupting diagnostics for exactly the tester with two Gen 2 vehicles, who
is the most valuable reporter available. See `get_trace()` below for why
`vehicle_id` is the right key.

ONE ATTEMPT-BOUNDED RETRY, NOT ONE TRACE PER PRESS. `button.py`'s pairing
button retries the search-and-pair loop internally on one press. Resetting
the trace on every retry would destroy the informative early failure and
keep only the least useful last one; never resetting mid-press would let
frames from different attempts blur together with no way to tell them apart.
`start_attempt()` marks the boundary explicitly instead; `reset()` is for the
caller to invoke only when the button itself is pressed again.

WHAT IS MASKED, AND WHY IT IS NOT EVERYTHING:

Stable identifiers -- phone id, VAS vehicle id, the BLE address -- are
fingerprinted via `record_identifiers()`. They outlive the pairing attempt
and are what ties a world-readable bug report back to one owner's vehicle.
That is the disclosure risk that actually matters here.

Ephemeral frame bytes -- the nonces and their MACs -- are recorded as plain
hex by `record_frame()`. They are single-use, dead the moment the connection
drops, and recovering the HMAC key from a (nonce, MAC) pair means breaking
HMAC-SHA256. Masking them would cost most of the trace's diagnostic value
and buy no protection worth having. The Gen 2 frames do carry the phone id and
VAS vehicle id in the clear, so `record_frame()` zeroes every identifier
`record_identifiers()` registered. Register them before the first frame.

THE SALT INVARIANT. `_SALT` is generated fresh per process and is never
included in `as_dict()` / `all_traces_as_dict()`. That is what makes the
64-bit fingerprints below non-brute-forceable back to their inputs from a
downloaded bundle -- which matters most for the BLE MAC, only 48 bits and
otherwise trivially enumerable. Serializing the salt, or swapping the keyed
hash in `fingerprint()` for a plain digest, would silently destroy this
property. Don't.
"""

from __future__ import annotations

from contextlib import suppress
from hashlib import blake2s
import secrets
from typing import Any
from uuid import UUID

# Regenerated every process start. Correlates identifiers within one report;
# never lets two reports -- or a report and the salt itself -- be linked. See
# "THE SALT INVARIANT" above: this must never appear in as_dict().
_SALT = secrets.token_bytes(16)

# A pairing attempt is a handful of frames, and one button press may retry
# several times. Deep enough to survive that without growing without bound.
MAX_FRAMES = 64


def fingerprint(value: bytes | str | None) -> str | None:
    """Return a stable, non-reversible short tag for an identifier."""
    if value is None:
        return None
    data = value.encode() if isinstance(value, str) else bytes(value)
    return blake2s(data, key=_SALT, digest_size=8).hexdigest()


class BleTrace:
    """One vehicle's BLE pairing trace, spanning every attempt of one button press."""

    def __init__(self, vehicle_id: str) -> None:
        """Initialize an empty trace for one vehicle."""
        self.vehicle_id = vehicle_id
        self.attempts: list[dict[str, Any]] = []
        self.frames: list[dict[str, Any]] = []
        self.services: list[dict[str, Any]] = []
        self.identifiers: dict[str, str | None] = {}
        self.generation: int | None = None
        self.mtu: int | None = None
        self.bonding: dict[str, str] | None = None
        self.state: str | None = None
        # Raw byte forms of the registered identifiers, zeroed out of every
        # frame. Never serialized, like _SALT.
        self._masked: set[bytes] = set()

    def reset(self) -> None:
        """Clear the trace. Call ONLY when the pairing button is pressed again --
        never once per retry-loop attempt inside a single press. Attempt
        boundaries within one press are `start_attempt()`, not `reset()`.
        """
        self.attempts.clear()
        self.frames.clear()
        self.services.clear()
        self.identifiers.clear()
        self.generation = None
        self.mtu = None
        self.bonding = None
        self.state = None
        self._masked.clear()

    def start_attempt(self) -> int:
        """Mark the start of one retry-loop attempt; return its 1-based index.

        Frames recorded by `record_frame()` after this call are tagged with
        this attempt number until the next call. Marking the boundary
        explicitly -- rather than trying to infer it from frame content --
        is what lets a maintainer read "attempt 1 died after the auth#1
        write" instead of one undifferentiated stream of frames from
        however many retries the loop made.
        """
        # len(self.attempts) IS the attempt number; a separate counter would be
        # a second name for the same fact, and free to drift from it.
        self.attempts.append({"attempt": len(self.attempts) + 1, "outcome": None})
        return len(self.attempts)

    def record_attempt_outcome(self, outcome: str) -> None:
        """Record how the current attempt ended, e.g. "timeout", "bad_reply",
        "bonded". A no-op if `start_attempt()` was never called.
        """
        if self.attempts:
            self.attempts[-1]["outcome"] = outcome

    def record_identifiers(
        self,
        *,
        phone_id: str | None = None,
        vas_vehicle_id: str | None = None,
        address: str | None = None,
    ) -> None:
        """Record stable identifiers as fingerprints, never raw values.

        These are the identifiers the redaction ruling requires masked:
        they outlive one pairing attempt and are resolvable to a physical
        vehicle (vas_vehicle_id is BLE-broadcast, the address is sniffable),
        unlike the ephemeral frame bytes `record_frame()` keeps as hex.
        """
        # The "_fp" suffix is load-bearing, not decoration. helpers.py's
        # TO_REDACT lists "phone_id", "vas_vehicle_id" and "address" as a
        # second line of defence against a future path that forgets to
        # fingerprint -- and async_redact_data matches by key NAME without
        # inspecting the value. Storing a fingerprint under the bare name
        # would therefore have redact() blanket-replace the already-hashed
        # tag with a placeholder, destroying the one thing fingerprinting
        # exists to preserve: correlation within a bundle ("the same phone
        # paired both vehicles"). The suffix lets both properties hold at
        # once -- raw values still get caught by name, hashed ones survive.
        for value in (phone_id, vas_vehicle_id):
            with suppress(ValueError, TypeError):
                self._masked.add(UUID(value).bytes)
        if phone_id is not None:
            self.identifiers["phone_id_fp"] = fingerprint(phone_id)
        if vas_vehicle_id is not None:
            self.identifiers["vas_vehicle_id_fp"] = fingerprint(vas_vehicle_id)
        if address is not None:
            self.identifiers["address_fp"] = fingerprint(address)

    def record_services(self, services: list[dict[str, Any]]) -> None:
        """Record the vehicle's advertised GATT characteristics.

        UUIDs and properties only, never characteristic values. A vehicle
        that exposes none is the BlueZ Service Changed failure.
        """
        self.services = services

    def record_bonding(self, path: str, outcome: str) -> None:
        """Record which bonding path ran and how it ended.

        Gen 2 bonds when the encrypted T characteristic is subscribed, so a
        tester report has to distinguish "never bonded" from "bonded and still
        rejected". `path` is "subscribe-t". A log line is not enough: the tester
        attaches the diagnostics download, not their log buffer.
        """
        self.bonding = {"path": path, "outcome": outcome}

    def record_mtu(self, mtu: int) -> None:
        """Record the negotiated ATT MTU for this connection.

        auth#1 is 90 bytes, so a link stuck at the 23-byte default MTU
        fragments it; this tells that apart from a silent vehicle.
        """
        self.mtu = mtu

    def record_frame(
        self, direction: str, characteristic: str, data: bytes, note: str | None = None
    ) -> None:
        """Record one frame in the CURRENT attempt (see `start_attempt()`).

        `direction` is caller-defined (e.g. "write", "notify", "subscribe")
        and, paired with `characteristic`, is what tells a write from a
        subscription -- no separate field is needed for that. See the
        module docstring on masking: `data` is recorded as plain hex, with
        registered identifiers zeroed.
        """
        if len(self.frames) >= MAX_FRAMES:
            return
        data = bytes(data)
        for identifier in self._masked:
            data = data.replace(identifier, bytes(len(identifier)))
        self.frames.append(
            {
                "attempt": len(self.attempts) or None,
                "direction": direction,
                "characteristic": characteristic.upper(),
                "length": len(data),
                "hex": data.hex(),
                "note": note,
            }
        )

    def record_state(self, state: str) -> None:
        """Record the furthest authentication state reached."""
        self.state = state

    def as_dict(self) -> dict[str, Any]:
        """Render the trace for a diagnostics download."""
        return {
            "generation": self.generation,
            "mtu": self.mtu,
            "state_reached": self.state,
            "identifiers": dict(self.identifiers),
            "attempts": list(self.attempts),
            "frame_count": len(self.frames),
            "truncated": len(self.frames) >= MAX_FRAMES,
            "bonding": self.bonding,
            "services": self.services,
            "frames": self.frames,
        }


# Keyed by vehicle_id, not a module singleton -- see the module docstring's
# "ONE TRACE PER VEHICLE" section for why a single global trace corrupts
# diagnostics on a multi-vehicle account.
#
# vehicle_id is an acceptable dict key where vas_vehicle_id, VIN and the BLE
# MAC are not. The distinguishing property is RESOLVABILITY, not stability:
# vas_vehicle_id is broadcast in BLE advertisements, the MAC is sniffable,
# and the VIN is readable through the vehicle's windshield -- each ties a
# report to a physical vehicle on sight. `vehicle_id` is meaningful only
# inside Rivian's own backend, and diagnostics.py already keys roughly eight
# other sub-payloads on it for the same reason (diagnostics.py:239-245).
_TRACES: dict[str, BleTrace] = {}


def get_trace(vehicle_id: str) -> BleTrace:
    """Return this vehicle's trace, creating it on first use."""
    if vehicle_id not in _TRACES:
        _TRACES[vehicle_id] = BleTrace(vehicle_id)
    return _TRACES[vehicle_id]


def all_traces_as_dict() -> dict[str, Any]:
    """Every known vehicle's trace, keyed by vehicle_id, for diagnostics.py."""
    return {vehicle_id: trace.as_dict() for vehicle_id, trace in _TRACES.items()}
