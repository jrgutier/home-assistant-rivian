from __future__ import annotations

from contextlib import suppress
from hashlib import blake2s
import secrets
from typing import Any
from uuid import UUID

_SALT = secrets.token_bytes(16)

MAX_FRAMES = 64


def fingerprint(value: bytes | str | None) -> str | None:
    if value is None:
        return None
    data = value.encode() if isinstance(value, str) else bytes(value)
    return blake2s(data, key=_SALT, digest_size=8).hexdigest()


class BleTrace:
    def __init__(self, vehicle_id: str) -> None:
        self.vehicle_id = vehicle_id
        self.attempts: list[dict[str, Any]] = []
        self.frames: list[dict[str, Any]] = []
        self.services: list[dict[str, Any]] = []
        self.identifiers: dict[str, str | None] = {}
        self.generation: int | None = None
        self.mtu: int | None = None
        self.bonding: dict[str, str] | None = None
        self.state: str | None = None
        self._masked: set[bytes] = set()

    def reset(self) -> None:
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
        self.attempts.append({"attempt": len(self.attempts) + 1, "outcome": None})
        return len(self.attempts)

    def record_attempt_outcome(self, outcome: str) -> None:
        if self.attempts:
            self.attempts[-1]["outcome"] = outcome

    def record_identifiers(
        self,
        *,
        phone_id: str | None = None,
        vas_vehicle_id: str | None = None,
        address: str | None = None,
    ) -> None:
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
        self.services = services

    def record_bonding(self, path: str, outcome: str) -> None:
        self.bonding = {"path": path, "outcome": outcome}

    def record_mtu(self, mtu: int) -> None:
        self.mtu = mtu

    def record_frame(
        self, direction: str, characteristic: str, data: bytes, note: str | None = None
    ) -> None:
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
        self.state = state

    def as_dict(self) -> dict[str, Any]:
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


_TRACES: dict[str, BleTrace] = {}


def get_trace(vehicle_id: str) -> BleTrace:
    if vehicle_id not in _TRACES:
        _TRACES[vehicle_id] = BleTrace(vehicle_id)
    return _TRACES[vehicle_id]


def all_traces_as_dict() -> dict[str, Any]:
    return {vehicle_id: trace.as_dict() for vehicle_id, trace in _TRACES.items()}
